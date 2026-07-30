import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import './style.css'
import citiesData from './data/cities.json'
import labelsData from './data/labels.json'
// Vite fingerprints and emits it; the element lives in index.html so the column
// has its header before any script runs.
import bannerUrl from './assets/banner.png'
import stationsData from './data/stations.json'
import nationsTsv from './data/nations.tsv?raw'
import { talopedia, type TalopediaEntry } from './data/talopedia'

// --- Dev mode ---

const DEV = new URLSearchParams(window.location.search).has('dev')

// Strip diacritics so "Chukyo" matches "Chūkyō" etc.
const norm = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

// --- Constants ---

const TILE_GRID = 8192
const CONTENT = 6000
const U = 256
// Two user levels past the tile resolution. Native detail stops at z5, so the
// top of the range is upscaled and will look soft — the point of it is spacing,
// not detail: cities the placer drops for want of room at one level have room
// at the next, so the last few crowded names resolve instead of never rendering.
const MAX_ZOOM = 7

function px(x: number, y: number): L.LatLngExpression {
  return [(-y * U) / TILE_GRID, (x * U) / TILE_GRID]
}

function toPx(latlng: L.LatLng): [number, number] {
  return [
    Math.round((latlng.lng * TILE_GRID) / U),
    Math.round((-latlng.lat * TILE_GRID) / U),
  ]
}

// --- Geographic coordinates ---
//
// Avium's axial tilt puts the graticule on the map's diagonals rather than its
// edges. The equator runs bottom-left to top-right, the prime meridian top-left
// to bottom-right, and they cross at the middle of the map, which is 0N 0E. That
// puts the north pole in the top-left corner and the south pole in the
// bottom-right, and both ends of the equator — the two remaining corners — on
// the antimeridian.
//
// So the whole square is the world, standing on a corner. Meridians converge on
// the two polar corners, which means the span of longitude available shrinks
// toward them: the four edges of the square are all the antimeridian, folded.
// Reading longitude off the raw diagonal instead would leave half the globe
// with nowhere to be, and every pixel outside the inscribed diamond would sit at
// coordinates that do not exist.
const GEO_ORIGIN = CONTENT / 2
const GEO_R = Math.hypot(GEO_ORIGIN, GEO_ORIGIN) // half-diagonal: pole and antimeridian distance
const SQRT1_2 = Math.SQRT1_2

interface Geo {
  lat: number
  lon: number
}

// Map pixels onto the diagonal axes: u runs east along the equator, v runs north
// along the prime meridian. y grows downward, so north is up-left.
function axes(x: number, y: number): { u: number; v: number } {
  const dx = x - GEO_ORIGIN
  const dy = y - GEO_ORIGIN
  return { u: (dx - dy) * SQRT1_2, v: -(dx + dy) * SQRT1_2 }
}

function toGeo(x: number, y: number): Geo {
  const { u, v } = axes(x, y)
  const lat = (90 * v) / GEO_R
  // Half-width of the world at this latitude. It reaches zero at the poles,
  // where every longitude collapses onto one point and 0 is the honest answer.
  const halfWidth = GEO_R - Math.abs(v)
  return { lat, lon: halfWidth < 1e-9 ? 0 : (180 * u) / halfWidth }
}

function fromGeo(lat: number, lon: number): { x: number; y: number } {
  const v = (lat / 90) * GEO_R
  const u = (lon / 180) * (GEO_R - Math.abs(v))
  return {
    x: GEO_ORIGIN + (u - v) * SQRT1_2,
    y: GEO_ORIGIN - (u + v) * SQRT1_2,
  }
}

// Single cardinal letters, as any atlas uses. The axes run on the diagonals, so
// the letters name hemispheres rather than screen directions: N is toward the
// top-left corner, E toward the top-right.
function fmtGeo(g: Geo, places = 2): string {
  const lat = g.lat >= 0 ? 'N' : 'S'
  const lon = g.lon >= 0 ? 'E' : 'W'
  return `${Math.abs(g.lat).toFixed(places)}°${lat} ${Math.abs(g.lon).toFixed(places)}°${lon}`
}

// --- Map ---

const contentBounds = L.latLngBounds(px(0, CONTENT), px(CONTENT, 0))

const map = L.map('map', {
  crs: L.CRS.Simple,
  minZoom: 2,
  maxZoom: MAX_ZOOM,
  zoomSnap: 0.5,
  zoomDelta: 0.5,
  center: px(CONTENT / 2, CONTENT / 2),
  zoom: 2,
  maxBounds: contentBounds.pad(0.1),
  // The sidebar owns the left edge on a desktop, so every control lives on the
  // right. Leaflet's own zoom control is replaced rather than moved, because its
  // position is fixed at construction.
  zoomControl: false,
})

L.control.zoom({ position: 'topright' }).addTo(map)

// How much of the map the sidebar hides. Zero on a phone, where the sheet
// covers the bottom instead and the map is free to use its own centre.
function sidebarWidth(): number {
  if (!window.matchMedia('(min-width: 900px)').matches) return 0
  const css = getComputedStyle(document.documentElement)
  const rail = parseFloat(css.getPropertyValue('--rail')) || 0
  // The place column only covers the map while it is open, so it only counts
  // toward the offset then — otherwise every jump would land 190px off centre.
  const panelOpen = !(document.getElementById('city-panel') as HTMLElement).hidden
  const panel = panelOpen ? parseFloat(css.getPropertyValue('--panel')) || 0 : 0
  return rail + panel
}

// Centre a point in the visible part of the map. Without this a city opened from
// a link lands under the sidebar, dead centre of a window it only half occupies.
function focusOn(x: number, y: number, zoom: number) {
  const off = sidebarWidth() / 2
  if (!off) {
    map.setView(px(x, y), zoom)
    return
  }
  const target = map.project(px(x, y), zoom).subtract([off, 0])
  map.setView(map.unproject(target, zoom), zoom)
}

// --- Image layers ---

const imgBounds = L.latLngBounds(px(0, CONTENT), px(CONTENT, 0)) as L.LatLngBoundsExpression

// Full-res 6000px layers served as 256px tiles (native detail up to z5,
// upscaled beyond) — only the tiles in view are ever loaded.
// sharp's google layout writes {z}/{y}/{x} (row/column) — using {z}/{x}/{y}
// here is what produced the "scrambled" transposed map previously.
// The base is tiled too: an imageOverlay base rounds its position through a
// different code path than tile layers, drifting 1-2px at half-step zooms.
function tiledLayer(name: string, pane = 'overlayPane'): L.TileLayer {
  return L.tileLayer(`tiles/${name}/{z}/{y}/{x}.png`, {
    maxNativeZoom: 5,
    maxZoom: MAX_ZOOM,
    bounds: contentBounds,
    pane,
  })
}

tiledLayer('base', 'tilePane').addTo(map)

// Where the world stops. The ocean tile and the page behind it are both dark, so
// without this the map has no visible edge at all when zoomed out.
L.rectangle(contentBounds, {
  color: 'rgba(255,255,255,0.5)',
  weight: 1,
  fill: false,
  interactive: false,
}).addTo(map)
const bordersLayer = tiledLayer('borders').addTo(map)
const riversLayer = tiledLayer('rivers').addTo(map)

// Pangaea reference overlay (dev-only toggle in layer control)
let pangaeaLayer: L.ImageOverlay | null = null
if (DEV) {
  const pangaeaImg = new Image()
  pangaeaImg.src = 'overlays/pangaea.png'
  pangaeaImg.onload = () => {
    pangaeaLayer = L.imageOverlay('overlays/pangaea.png', imgBounds, { opacity: 0.4 })
    overlayControl['Pangaea'] = pangaeaLayer
    layerCtrl.addOverlay(pangaeaLayer, 'Pangaea')
  }
}

// --- Layer control ---

// Listed in the order they stack on the map, from the ground up. Territories and
// Cities are added later, where their layers are created, and Research Stations
// after those — so the panel reads Borders, Rivers, Territories, Cities,
// Research Stations without anything needing to sort it.
const overlayControl: Record<string, L.Layer> = {
  'Borders': bordersLayer,
  'Rivers': riversLayer,
}

// Collapsed and moved into the left stack, so layers is a button alongside zoom
// and rotate rather than a permanent card taking a corner of the map to itself.
const layerCtrl = L.control
  .layers({}, overlayControl, { collapsed: true, position: 'topright' })
  .addTo(map)

// Leaflet opens a collapsed control on hover, so it springs open whenever the
// pointer crosses that corner on its way somewhere else. Make it a click toggle.
//
// The hover pair comes off by reference. The button's own click handler is an
// anonymous function inside an object literal, so it can't be removed the same
// way — a capture-phase listener with stopImmediatePropagation gets in front of
// it instead, which halts every remaining listener for that event in any phase.
{
  const ctrl = layerCtrl as unknown as {
    _container?: HTMLElement
    _layersLink?: HTMLElement
    _expandSafely?: () => void
    collapse: () => void
    expand: () => void
  }
  const box = ctrl._container
  const link = ctrl._layersLink
  if (box && link && ctrl._expandSafely) {
    L.DomEvent.off(box, { mouseenter: ctrl._expandSafely, mouseleave: ctrl.collapse }, ctrl)
    const open = () => box.classList.contains('leaflet-control-layers-expanded')
    link.addEventListener(
      'click',
      (e) => {
        e.preventDefault()
        e.stopImmediatePropagation()
        open() ? ctrl.collapse() : ctrl._expandSafely!()
      },
      true
    )
    // Leaflet already closes it on a map click; this covers the rest of the page
    document.addEventListener('click', (e) => {
      if (open() && !box.contains(e.target as Node)) ctrl.collapse()
    })
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && open()) ctrl.collapse()
    })
  }
}

// --- Labels ---

interface LabelDef {
  text: string
  type: string
  x: number | null
  y: number | null
  minZoom: number
  maxZoom?: number // absent = no ceiling, so raising MAX_ZOOM never strands it
  tier?: number // nations/colonies: font size in px
  span?: number // territory width in map px, overriding the derived one
}


const labelDefs = labelsData as LabelDef[]
const labelMarkers = new Map<LabelDef, L.Marker>()
const labelLayer = L.layerGroup().addTo(map)

// Every label is sized to the area it names rather than to a fixed px value,
// which is the whole trick to reading well at every zoom: a fixed size swamps
// a small nation when zoomed out and vanishes on a continent when zoomed in.
const MIN_SPAN = 45   // map px, so a one-city nation still earns a name eventually
const FIT = 0.75      // the name spans this fraction of the area on screen
const FS_MIN = 8.5    // smallest font a derived span is allowed to produce

// Water is the one thing on this map with no border to trace, so its names are
// set tight and italic and lean on colour to read as water; land names track
// wide to claim the ground they cover.
const WATER = new Set(['ocean', 'sea'])
const TRACK = 0.22       // letter-spacing, em — must match --track in the CSS
const TRACK_WATER = 0.08 // ditto, .label-ocean / .label-sea
const GLYPH = 0.68       // char advance before tracking: caps are wider than the 0.62 cities use
const advanceOf = (def: LabelDef) => GLYPH + (WATER.has(def.type) ? TRACK_WATER : TRACK)

interface Anchor { x: number; y: number; span: number }
let anchorCache: Map<string, Anchor> | null = null

// Where a nation's name sits and how much room it has, both derived from the
// cities inside it. Medians, not means: one overseas city should not drag the
// name into the ocean, and the 10-90 spread keeps an exclave from inflating
// the name to continent size.
function anchors(): Map<string, Anchor> {
  if (anchorCache) return anchorCache
  const groups = new Map<string, { xs: number[]; ys: number[] }>()
  const add = (k: string, x: number, y: number) => {
    let g = groups.get(k)
    if (!g) groups.set(k, g = { xs: [], ys: [] })
    g.xs.push(x)
    g.ys.push(y)
  }
  for (const c of cities) {
    if (c.x == null || c.y == null || !c.nation) continue
    add(norm(c.nation), c.x, c.y)
    // A continent has no cities of its own, so it inherits every city of every
    // nation that names it
    const cont = nationByName.get(norm(c.nation))?.continent
    if (cont) add(norm(cont), c.x, c.y)
  }
  const at = (a: number[], f: number) => a[Math.min(a.length - 1, Math.floor(a.length * f))]
  anchorCache = new Map()
  for (const [k, g] of groups) {
    g.xs.sort((a, b) => a - b)
    g.ys.sort((a, b) => a - b)
    anchorCache.set(k, {
      x: at(g.xs, 0.5),
      y: at(g.ys, 0.5),
      span: Math.max(at(g.xs, 0.9) - at(g.xs, 0.1), at(g.ys, 0.9) - at(g.ys, 0.1), MIN_SPAN),
    })
  }
  return anchorCache
}

// Screen px per map px at a zoom level
const scaleAt = (z: number) => (2 ** z * U) / TILE_GRID

// A hand-placed coord always wins; otherwise territories fall back to the
// centre of their cities, which is why no nation needs placing by hand.
function labelPos(def: LabelDef): [number, number] | null {
  if (def.x != null && def.y != null) return [def.x, def.y]
  const a = anchors().get(norm(def.text))
  return a ? [a.x, a.y] : null
}

// Font size that makes the name span FIT of its territory. Returning 0 hides
// it: too small on screen to read is also too small to name, and that single
// rule does the work of hand-tuning minZoom per nation — names arrive as their
// land grows into them.
// What a label with nothing to measure is worth, taken from what its own kind
// measures: an empty polar continent has no cities, and MIN_SPAN would render
// it at under a pixel. Median of the anchored labels of the same type.
const typeSpans = new Map<string, number>()

function fallbackSpan(def: LabelDef): number {
  const band = `${def.minZoom}-${def.maxZoom ?? 'top'}`
  let v = typeSpans.get(band)
  if (v == null) {
    const med = (ds: LabelDef[]) => {
      const s = ds
        .map(d => anchors().get(norm(d.text))?.span)
        .filter((n): n is number => n != null)
        .sort((a, b) => a - b)
      return s.length ? s[s.length >> 1] : null
    }
    // Peers are the labels sharing this zoom band, not this type: a band is a
    // set of names meant to be read at one scale, so a sea inherits from the
    // continents it appears alongside rather than from the map as a whole.
    const peer = med(labelDefs.filter(d => d.minZoom === def.minZoom && d.maxZoom === def.maxZoom))
    typeSpans.set(band, v = peer ?? med(labelDefs) ?? MIN_SPAN)
  }
  return v
}

// A hand-set span is the same quantity the deriver produces, so a tuned label
// runs through the identical pipeline and keeps scaling with zoom. It is also
// taken literally: a size someone chose is a decision, not a suggestion.
//
// A derived span instead floors at whatever renders the name at FS_MIN, because
// deriving from cities says nothing about how long the name is — four cities on
// one island give an island colony 45px of territory, which sets a 28-character
// name at two thirds of a pixel.
function areaSpan(def: LabelDef): number {
  if (def.span != null) return def.span
  const derived = anchors().get(norm(def.text))?.span ?? fallbackSpan(def)
  const legible = (FS_MIN * def.text.length * advanceOf(def)) / (scaleAt(def.minZoom) * FIT)
  return Math.max(derived, legible)
}

// Land names are sized once, at the zoom they first appear at, and hold that
// screen size: zooming into a nation is asking for the cities under its name,
// not for bigger letters.
//
// Water names do the opposite and stay fixed to the map, growing on screen as
// you zoom, because a sea has nothing competing for the space and the name is
// how you read its extent.
//
// A territory too small to carry a legible name at the zoom it appears is
// sized the water way for the same reason. Holding it at that size means it
// only ever loses ground against the land growing beneath it, so it starts
// unreadable and stays unreadable however far you zoom. Growing with the map
// makes zooming in the thing that resolves it.
function screenFixed(def: LabelDef): boolean {
  if (WATER.has(def.type)) return false
  return (areaSpan(def) * scaleAt(def.minZoom) * FIT) / (def.text.length * advanceOf(def)) >= FS_MIN
}

// Small territories grow at a fraction of the map's rate, not with it. Full
// rate put an island's name level with a real nation's by the end of the band,
// which reads as the island having been promoted.
const GROW = 0.6

function sizeZoom(def: LabelDef, z: number): number {
  if (WATER.has(def.type)) return z
  if (screenFixed(def)) return def.minZoom
  return def.minZoom + GROW * (z - def.minZoom)
}

// No floor and no ceiling. A speck is the honest rendering of a territory too
// small to carry its name yet, and zooming in is what resolves it.
function areaFontSize(def: LabelDef, z: number): number {
  return (areaSpan(def) * scaleAt(sizeZoom(def, z)) * FIT) / (def.text.length * advanceOf(def))
}

function inBand(def: LabelDef, z: number): boolean {
  return z >= def.minZoom && z <= (def.maxZoom ?? Infinity)
}

// The rectangle a name occupies at a zoom, in the same translation-free screen
// space computePlacement works in.
function labelBox(def: LabelDef, z: number): Box | null {
  const pos = labelPos(def)
  if (!pos) return null
  const fs = areaFontSize(def, z)
  if (!fs) return null
  const s = scaleAt(z)
  const w = def.text.length * fs * advanceOf(def)
  const h = fs * 1.4
  return { x: pos[0] * s - w / 2, y: pos[1] * s - h / 2, w, h }
}

// A nation name sitting in the same water as a sea name reads as one jumble, and
// the nation is the more specific claim on that spot, so it takes it. The sea
// name is not lost — the nation band ends at z5, and the sea comes back on its
// own the moment it does.
//
// Keyed on zoom because both boxes move with it, and cleared alongside the
// placement cache, since a drag or a span edit changes the geometry.
const seaSuppressCache = new Map<number, Set<LabelDef>>()

function suppressedSeas(z: number): Set<LabelDef> {
  const cached = seaSuppressCache.get(z)
  if (cached) return cached

  const set = new Set<LabelDef>()
  const claims: Box[] = []
  for (const d of labelDefs) {
    if (d.type !== 'nation' && d.type !== 'colony') continue
    if (!inBand(d, z)) continue
    const b = labelBox(d, z)
    if (b) claims.push(b)
  }
  if (claims.length) {
    for (const d of labelDefs) {
      if (d.type !== 'sea') continue
      const b = labelBox(d, z)
      if (b && claims.some(o => boxesOverlap(b, o))) set.add(d)
    }
  }
  seaSuppressCache.set(z, set)
  return set
}

// Once a water name is in its band it stays on screen, however small it renders.
// There is deliberately no size cull: a name too small to read still marks where
// the water is, and zooming in resolves it — the same reasoning that keeps the
// tiny land territories on the map rather than hiding them until they are big.
//
// The one thing that takes a sea off is a nation name landing on it, and that
// lifts by itself when the nation band ends.
function labelShown(def: LabelDef, z: number): boolean {
  if (!map.hasLayer(labelLayer) || !inBand(def, z)) return false
  if (def.type === 'sea' && suppressedSeas(z).has(def)) return false
  return true
}

function makeLabelMarker(def: LabelDef, pos: [number, number]): L.Marker {
  const handles = DEV
    ? ['nw', 'ne', 'sw', 'se'].map(c => `<i class="lh lh-${c}"></i>`).join('')
    : ''
  // Every nation and colony in nations.tsv has a panel to open. Continents,
  // oceans and seas have no entry there, so they stay inert rather than
  // offering a click that does nothing. Dev keeps the label for editing.
  const nation = DEV ? undefined : nationByName.get(norm(def.text))
  const m = L.marker(px(pos[0], pos[1]), {
    icon: L.divIcon({
      className: `map-label label-${def.type}` + (DEV ? ' dev-label' : nation ? ' label-link' : ''),
      html: `<span>${def.text}${handles}</span>`,
      iconSize: [0, 0],
      iconAnchor: [0, 0],
    }),
    interactive: DEV || !!nation,
    draggable: DEV,
    // Under the city markers: a city dot sitting on a name is the smaller
    // target and the more specific answer, so it wins the click
    zIndexOffset: -1000,
  })
  if (nation) m.on('click', () => openNationPanel(nation))
  return m
}

// Dev editing: drag to move, wheel to resize. Both write straight onto the
// def, so the export button picks them up with no separate bookkeeping.
function wireLabelEdit(def: LabelDef, m: L.Marker) {
  const commit = (msg: string) => {
    saveLabelProgress()
    invalidatePlacements()
    updateCities()
    statusEl.textContent = msg
  }

  m.on('dragend', () => {
    ;[def.x, def.y] = toPx(m.getLatLng())
    commit(`${def.text} → [${def.x}, ${def.y}]`)
  })

  const el = m.getElement()
  if (!el) return

  // Double-click hands the label to the placer's span field, for when a corner
  // drag is too coarse or the number has to match another label's
  L.DomEvent.on(el, 'dblclick', (e) => {
    L.DomEvent.stop(e) // or the map zooms out from under the label
    setSpanTarget(def)
    spanInput.focus()
    spanInput.select()
  })

  // Corner handles resize. Distance from the label's centre drives it, so
  // every corner behaves the same and drag-out always means bigger. What gets
  // set is the span, not a font size, so a tuned label keeps scaling with
  // zoom exactly as a derived one does.
  for (const h of el.querySelectorAll<HTMLElement>('.lh')) {
    // Leaflet starts a marker drag on touchstart too when the browser reports
    // touch, so a finger reaching for a handle would drag the label instead
    L.DomEvent.on(h, 'touchstart', L.DomEvent.stop)
    L.DomEvent.on(h, 'mousedown', (e) => {
      L.DomEvent.stop(e) // or Leaflet reads it as the start of a marker drag
      const rect = map.getContainer().getBoundingClientRect()
      const c = map.latLngToContainerPoint(m.getLatLng())
      const reach = (ev: MouseEvent) =>
        Math.hypot(ev.clientX - rect.left - c.x, ev.clientY - rect.top - c.y)
      // Half the box diagonal, per px of font size
      const perFs = Math.hypot(def.text.length * advanceOf(def), 1.4) / 2
      // Handles sit just outside the corner, so the grab starts a little past
      // it; keeping that offset stops the label jumping on mousedown
      const slack = reach(e as MouseEvent) - areaFontSize(def, map.getZoom()) * perFs

      // The grabbed corner tracks the cursor. Solving for size from the
      // pointer each frame, rather than scaling the previous size, is what
      // makes this recoverable: drag to nothing and dragging back out
      // restores it, with no floor needed to prevent a dead end.
      // Only the font size is touched per frame; the placement rebuild that
      // 1700 cities depend on waits for mouseup.
      const move = (ev: MouseEvent) => {
        const fs = Math.max(0, reach(ev) - slack) / perFs
        def.span = (fs * def.text.length * advanceOf(def)) / (scaleAt(sizeZoom(def, map.getZoom())) * FIT)
        updateLabels()
        if (spanTarget === def) syncSpanRow()
      }
      const up = () => {
        document.removeEventListener('mousemove', move)
        document.removeEventListener('mouseup', up)
        commit(`${def.text} → span ${Math.round(def.span!)}`)
      }
      document.addEventListener('mousemove', move)
      document.addEventListener('mouseup', up)
    })
  }
}

function mountLabel(def: LabelDef) {
  const existing = labelMarkers.get(def)
  if (existing) {
    labelLayer.removeLayer(existing)
    labelMarkers.delete(def)
  }
  const pos = labelPos(def)
  if (!pos) return
  const m = makeLabelMarker(def, pos).addTo(labelLayer)
  labelMarkers.set(def, m)
  if (DEV) wireLabelEdit(def, m)
}

// (Re)create a label's marker after its coords change
function refreshLabel(def: LabelDef) {
  mountLabel(def)
  updateLabels()
  invalidatePlacements()
  updateCities()
}

function updateLabels() {
  const z = map.getZoom()
  for (const [def, marker] of labelMarkers) {
    const el = marker.getElement()
    if (!el) continue
    el.style.fontSize = areaFontSize(def, z).toFixed(1) + 'px'
    el.classList.toggle('label-on', labelShown(def, z))
  }
}

// --- Cities ---

interface City {
  name: string
  nation: string
  population: number
  gdp: number
  gdpPerCapita: number
  nativeScript: string
  irlParallel: string
  alpha3: string
  x: number | null
  y: number | null
}

const cities = citiesData as City[]
const cityLayer = L.layerGroup().addTo(map)

// Registered here rather than in overlayControl above because cityLayer has to
// exist first, which puts them under Borders and Rivers in the control
layerCtrl.addOverlay(labelLayer, 'Territories')
layerCtrl.addOverlay(cityLayer, 'Cities')

map.on('overlayadd overlayremove', (e) => {
  if ((e as L.LayersControlEvent).layer !== labelLayer) return
  // Leaflet rebuilds a marker's element when its group is re-added, dropping
  // the inline font size and, in dev, the corner handles bound to the old one
  if (DEV) for (const def of labelDefs) mountLabel(def)
  updateLabels()
  // Names reserve space in the placement grid, so hiding them hands it back
  invalidatePlacements()
  updateCities()
})

// Bigger tiers always beat smaller ones for space; GDP breaks ties within a tier
function tierRank(pop: number): number {
  if (pop >= 5_000_000) return 0
  if (pop >= 2_500_000) return 1
  if (pop >= 1_000_000) return 2
  if (pop >= 750_000) return 3
  if (pop >= 500_000) return 4
  if (pop >= 250_000) return 5
  return 6
}

const citiesByPriority = [...cities].sort(
  (a, b) => tierRank(a.population) - tierRank(b.population) || b.gdp - a.gdp
)

// --- Nations (from nations.tsv) ---

interface Nation {
  name: string
  official: string
  population: number
  gdp: number
  gdpPerCapita: number
  lifeExpectancy: number
  literacy: number
  hdi: number
  popGrowth: number
  alpha3: string
  status: string
  capital: string
  expansionPoints: number
  continent: string
}

// Columns are found by header, not by position. They used to be read as v[10],
// v[11] and so on, which meant inserting CAPITAL in the middle silently shifted
// alpha3 onto the capital, status onto the code and continent onto the expansion
// points — every nation panel wrong, with nothing failing loudly.
const nations: Nation[] = (() => {
  const lines = nationsTsv.trim().split('\n')
  const head = lines[0].split('\t').map(s => s.trim())
  const at = (name: string) => {
    const i = head.indexOf(name)
    if (i < 0) throw new Error(`nations.tsv is missing the ${name} column`)
    return i
  }
  const col = {
    name: at('COMMON NAME'),
    official: at('OFFICIAL NAME'),
    population: at('POPULATION'),
    gdp: at('GDP PPP ($)'),
    gdpPerCapita: at('REAL GDP P/C ($)'),
    lifeExpectancy: at('LIFE EXPECTANCY'),
    literacy: at('LITERACY RATE'),
    hdi: at('HDI'),
    popGrowth: at('POP. GROWTH %'),
    capital: at('CAPITAL'),
    alpha3: at('ALPHA-3 CODE'),
    status: at('STATUS'),
    expansionPoints: at('EXPANSION POINTS'),
    continent: at('CONTINENT'),
  }
  const num = (s: string | undefined) => parseFloat((s ?? '').replace(/[,%]/g, '')) || 0
  const str = (s: string | undefined) => (s === '-' ? '' : (s ?? '').trim())
  return lines.slice(1).map(line => {
    const v = line.split('\t')
    return {
      name: str(v[col.name]),
      official: str(v[col.official]),
      population: num(v[col.population]),
      gdp: num(v[col.gdp]),
      gdpPerCapita: num(v[col.gdpPerCapita]),
      lifeExpectancy: num(v[col.lifeExpectancy]),
      literacy: num(v[col.literacy]),
      hdi: num(v[col.hdi]),
      popGrowth: num(v[col.popGrowth]),
      capital: str(v[col.capital]),
      alpha3: str(v[col.alpha3]),
      status: str(v[col.status]),
      expansionPoints: num(v[col.expansionPoints]),
      continent: str(v[col.continent]),
    }
  }).filter(n => n.name)
})()

// A city is a capital if its own nation names it one. Keyed on both, because a
// name alone is ambiguous — Hollosend and Reino both have a Lachaven.
const capitalKeys = new Set<string>()
for (const n of nations) {
  if (n.capital) capitalKeys.add(`${norm(n.name)}\t${norm(n.capital)}`)
}

const isCapital = (c: City) => capitalKeys.has(`${norm(c.nation)}\t${norm(c.name)}`)

const nationByName = new Map<string, Nation>()
for (const n of nations) nationByName.set(norm(n.name), n)

const worldGdpTotal = nations.reduce((s, n) => s + n.gdp, 0)

interface CityTier {
  radius: number
  outerRing: boolean
  fontSize: number
}

// Style 1 (small cities): dark hollow circle, thin white outline
// Style 2 (large cities): white center, thick black ring, white outer ring
function bigTier(r: number, fontSize: number): CityTier {
  return { radius: r, outerRing: true, fontSize }
}

// Ciudad Cuerdas's marker (r=3) as a single SVG element; every big city
// renders this exact graphic, scaled by s = tierRadius / 3
// Box, not circle: the ring is 11.09 across and the extra 1.01 is padding, so
// the drawn edge never sits on the boundary. It used to, and wherever the marker
// got its own compositing layer the ring was squared off — the same reason the
// small marker's viewBox is padded to 3.0 for a 2.76 drawing.
const BIG_D = 12.1
// The ink is the only thing that marks a capital. Shape and scale are a city's,
// so a capital still reads at its own tier and nothing else has to change.
const CITY_INK = '#111'
const CAPITAL_INK = '#d0342c'

function bigSvgHtml(S: number, ink = CITY_INK): string {
  return (
    `<svg width="${S}" height="${S}" viewBox="-6.05 -6.05 12.1 12.1" xmlns="http://www.w3.org/2000/svg">` +
    `<circle r="5.545" fill="#fff"/>` +
    `<circle r="4.095" fill="${ink}"/>` +
    `<circle r="1.905" fill="#fff" fill-opacity="0.95"/>` +
    `</svg>`
  )
}
function smallTier(r: number, fontSize: number): CityTier {
  return { radius: r, outerRing: false, fontSize }
}

// Small marker (r=2.3 reference) as one SVG element: hollow circle,
// scaled by s = tierRadius / 2.3
// Total radius = r(2.3) + half stroke(0.46) = 2.76; pad to 3.0 so the
// stroke isn't clipped at sub-pixel sizes
const SMALL_D = 6.0
function smallSvgHtml(S: number, ink = CITY_INK): string {
  return (
    `<svg width="${S}" height="${S}" viewBox="-3 -3 6 6" xmlns="http://www.w3.org/2000/svg">` +
    `<circle r="2.3" fill="${ink}" stroke="#ddd" stroke-width="0.92"/>` +
    `</svg>`
  )
}

// Label sizes: 13px megalopolises, 12px other 1M+, small sizes below
function cityTier(pop: number): CityTier {
  if (pop >= 5_000_000)  return bigTier(3,   13)
  if (pop >= 2_500_000)  return bigTier(2.6, 12)
  if (pop >= 1_000_000)  return bigTier(2.2, 12)
  if (pop >= 750_000)    return bigTier(1.9, 10)
  if (pop >= 500_000)    return smallTier(2.3, 10)
  if (pop >= 250_000)    return smallTier(1.9, 9)
  return                        smallTier(1.7, 9)
}

// Eligibility ladder. One user zoom-in = one 0.5 internal step from the
// initial z2 view: z1 = 2.5, z2 = 3, z3 = 3.5.
// init = none, z1 = 5M+, z2 = 1M+, z3 = everything
function minPop(z: number): number {
  if (z >= 3.5) return 0
  if (z >= 3) return 1_000_000
  if (z >= 2.5) return 5_000_000
  return Infinity
}

type Box = { x: number; y: number; w: number; h: number }

function boxesOverlap(a: Box, b: Box): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
}

function visROf(tier: CityTier): number {
  return tier.outerRing
    ? (BIG_D / 2) * (tier.radius / 3)
    : (SMALL_D / 2) * (tier.radius / 2.3)
}

// View-independent screen position of a city at a zoom level (translation-free,
// so collision geometry is identical regardless of where the map is panned)
function ptAt(c: City, z: number): { x: number; y: number } {
  const k = (2 ** z * U) / TILE_GRID
  return { x: c.x! * k, y: c.y! * k }
}

interface Placement {
  c: City
  tier: CityTier
  dir: 'right' | 'left'
  off: [number, number]
}

// Greedy label placement at one zoom level: every placed city is attempted,
// priority-ordered, and space decides. `pinned` cities (survivors of the
// previous half-zoom) place first, so zooming in only ever adds cities.
function computePlacement(z: number, pinned: City[]): Placement[] {
  const threshold = minPop(z)
  const pinnedSet = new Set(pinned)
  const order = [
    ...pinned,
    ...citiesByPriority.filter(
      c => !pinnedSet.has(c) && c.x != null && c.y != null && c.population >= threshold
    ),
  ]

  // Global marker/text scale (tier ratios intact): 0.8× from user zoom 3
  // (the all-cities zoom), even smaller before then
  const k = z >= 3.5 ? 0.8 : 0.65

  const items = order.map(c => {
    const base = cityTier(c.population)
    const tier = { ...base, radius: base.radius * k, fontSize: Math.round(base.fontSize * k) }
    return { c, tier, visR: visROf(tier), pt: ptAt(c, z) }
  })

  // Spatial indexes: same answers as scanning every box, minus the O(n²).
  // A 2D cell grid answers overlap tests, x-stripes answer nearest-distance.
  const CELL = 256
  const boxGrid = new Map<string, Box[]>()
  const stripes = new Map<number, Box[]>()
  let sMin = Infinity
  let sMax = -Infinity

  function addBox(b: Box) {
    const x0 = Math.floor(b.x / CELL), x1 = Math.floor((b.x + b.w) / CELL)
    const y0 = Math.floor(b.y / CELL), y1 = Math.floor((b.y + b.h) / CELL)
    for (let cx = x0; cx <= x1; cx++) {
      for (let cy = y0; cy <= y1; cy++) {
        const key = `${cx},${cy}`
        let cell = boxGrid.get(key)
        if (!cell) boxGrid.set(key, cell = [])
        cell.push(b)
      }
      let stripe = stripes.get(cx)
      if (!stripe) stripes.set(cx, stripe = [])
      stripe.push(b)
    }
    if (x0 < sMin) sMin = x0
    if (x1 > sMax) sMax = x1
  }

  function collides(b: Box): boolean {
    const x0 = Math.floor(b.x / CELL), x1 = Math.floor((b.x + b.w) / CELL)
    const y0 = Math.floor(b.y / CELL), y1 = Math.floor((b.y + b.h) / CELL)
    for (let cx = x0; cx <= x1; cx++) {
      for (let cy = y0; cy <= y1; cy++) {
        const cell = boxGrid.get(`${cx},${cy}`)
        if (!cell) continue
        for (const o of cell) if (boxesOverlap(b, o)) return true
      }
    }
    return false
  }

  // Upcoming marker positions, indexed for futureCost
  const ptGrid = new Map<string, number[]>()
  let maxDotR = 0
  for (let j = 0; j < items.length; j++) {
    const v = items[j]
    if (v.visR > maxDotR) maxDotR = v.visR
    const key = `${Math.floor(v.pt.x / CELL)},${Math.floor(v.pt.y / CELL)}`
    let cell = ptGrid.get(key)
    if (!cell) ptGrid.set(key, cell = [])
    cell.push(j)
  }
  maxDotR += 0.5

  // Area names claim their space before any city competes for it, and never
  // move. A city label that would cross one is pushed to its other side; a
  // city with no free side, or whose dot the name covers outright, does not
  // render at all.
  for (const def of labelDefs) {
    if (!labelShown(def, z)) continue
    const fs = areaFontSize(def, z)
    const pos = labelPos(def)
    if (!fs || !pos) continue
    const s = scaleAt(z)
    const w = def.text.length * fs * advanceOf(def)
    const h = fs * 1.4
    addBox({ x: pos[0] * s - w / 2, y: pos[1] * s - h / 2, w, h })
  }

  const placed: Placement[] = []

  // How many upcoming markers a label box would bury (each buried one = hidden city)
  function futureCost(box: Box, from: number): number {
    let n = 0
    const x0 = Math.floor((box.x - maxDotR) / CELL), x1 = Math.floor((box.x + box.w + maxDotR) / CELL)
    const y0 = Math.floor((box.y - maxDotR) / CELL), y1 = Math.floor((box.y + box.h + maxDotR) / CELL)
    for (let cx = x0; cx <= x1; cx++) {
      for (let cy = y0; cy <= y1; cy++) {
        const cell = ptGrid.get(`${cx},${cy}`)
        if (!cell) continue
        for (const j of cell) {
          if (j < from) continue
          const v = items[j]
          const r = v.visR + 0.5
          if (v.pt.x + r > box.x && v.pt.x - r < box.x + box.w &&
              v.pt.y + r > box.y && v.pt.y - r < box.y + box.h) n++
        }
      }
    }
    return n
  }

  // Distance from box to the nearest occupied element (marker or label):
  // walk x-stripes outward, stopping once the stripe gap alone rules out
  // anything closer than the best found
  function clearance(box: Box): number {
    const x0 = Math.floor(box.x / CELL), x1 = Math.floor((box.x + box.w) / CELL)
    let min = Infinity
    const scan = (s: number) => {
      const stripe = stripes.get(s)
      if (!stripe) return
      for (const o of stripe) {
        const dx = Math.max(0, o.x - (box.x + box.w), box.x - (o.x + o.w))
        const dy = Math.max(0, o.y - (box.y + box.h), box.y - (o.y + o.h))
        const d = dx + dy
        if (d < min) min = d
      }
    }
    for (let s = x0; s <= x1; s++) scan(s)
    for (let r = 1; (r - 1) * CELL < min; r++) {
      const lo = x0 - r, hi = x1 + r
      if (lo < sMin && hi > sMax) break
      scan(lo)
      scan(hi)
    }
    return min
  }

  for (let i = 0; i < items.length; i++) {
    const { c, tier, visR, pt } = items[i]

    const dotR = visR + 0.5
    const dotBox: Box = { x: pt.x - dotR, y: pt.y - dotR, w: dotR * 2, h: dotR * 2 }

    // A city that can't place still reserves its dot area — a less important
    // neighbor must never render over where a more important city belongs
    if (collides(dotBox)) {
      addBox(dotBox)
      continue
    }

    const charW = tier.fontSize * 0.62
    const w = c.name.length * charW + 4
    const h = tier.fontSize + 4
    // Gap from marker edge: anchored at Cuerdas (~1.05px), tighter as markers shrink
    const gapX = visR + 0.15 + visR * 0.16
    const gapY = h / 2 + visR * 0.1

    // Apple Maps: top-right preferred, bottom-left when needed
    const cands: { dir: 'right' | 'left'; off: [number, number]; box: Box }[] = [
      { dir: 'right', off: [gapX, -gapY], box: { x: pt.x + gapX, y: pt.y - gapY - h / 2, w, h } },
      { dir: 'left',  off: [-gapX, gapY], box: { x: pt.x - gapX - w, y: pt.y + gapY - h / 2, w, h } },
    ]

    const valid = cands.filter(cd => !collides(cd.box))
    let hit: (typeof cands)[number] | null
    if (valid.length === 2) {
      // Both fit: bury as few upcoming markers as possible, then keep
      // top-right unless bottom-left has clearly more room
      const cost0 = futureCost(valid[0].box, i + 1)
      const cost1 = futureCost(valid[1].box, i + 1)
      if (cost1 < cost0) hit = valid[1]
      else if (cost0 < cost1) hit = valid[0]
      else hit = clearance(valid[1].box) > clearance(valid[0].box) + 6 ? valid[1] : valid[0]
    } else {
      hit = valid[0] ?? null
    }

    if (hit) {
      addBox(dotBox)
      addBox(hit.box)
      placed.push({ c, tier, dir: hit.dir, off: hit.off })
    } else {
      addBox(dotBox)
    }
  }

  return placed
}

// Placement is view-independent, so each zoom level's result is computed once
// and cached. The cascade recurses through cached lower levels, so a zoomend
// costs at most one computePlacement. Cleared whenever city coords change.
const placementCache = new Map<number, Placement[]>()

function placementsAt(z: number): Placement[] {
  const cached = placementCache.get(z)
  if (cached) return cached
  const pinned = z <= 2.5 ? [] : placementsAt(z - 0.5).map(p => p.c)
  const result = computePlacement(z, pinned)
  placementCache.set(z, result)
  return result
}

function invalidatePlacements() {
  placementCache.clear()
  // Which seas a nation name covers is geometry too, so it goes stale for the
  // same reasons: a drag, a rename, a span edit, a type change
  seaSuppressCache.clear()
}

// Dot and label in one DOM element: no Leaflet tooltip machinery, whose
// per-label layout passes were the main zoom cost
function cityIcon(p: Placement, fade: boolean): L.DivIcon {
  const { c, tier, dir, off } = p
  const S = tier.outerRing ? BIG_D * (tier.radius / 3) : SMALL_D * (tier.radius / 2.3)
  const ink = isCapital(c) ? CAPITAL_INK : CITY_INK
  const svg = tier.outerRing ? bigSvgHtml(S, ink) : smallSvgHtml(S, ink)
  const gapX = Math.abs(off[0])
  const gapY = Math.abs(off[1])
  const pos = dir === 'right'
    ? `left:${S / 2 + gapX}px;top:${S / 2 - gapY}px`
    : `right:${S / 2 + gapX}px;top:${S / 2 + gapY}px`
  return L.divIcon({
    className: fade ? 'city-icon' : 'city-icon city-icon-still',
    html: svg + `<span class="city-label city-fs-${tier.fontSize}" style="${pos}">${c.name}</span>`,
    iconSize: [S, S],
    iconAnchor: [S / 2, S / 2],
  })
}

// Above this many additions and removals in one pass, the marker pane is
// detached for the duration and the fade is skipped. Below it the swap costs
// more than it saves.
const BATCH_MIN = 60

// Currently rendered markers, keyed by city; zoom changes only touch the diff
const shownCities = new Map<City, { marker: L.Marker; key: string }>()

// Fade tracking: a marker fades in only when its city is newly placed at this
// zoom (the pre-culling appearance). Markers re-entering the padded viewport
// during pans, or revealed by zooming out, appear instantly — culling invisible.
let lastAll: Placement[] | null = null
let prevPlaced = new Set<City>()

function placementKey(p: Placement): string {
  return `${p.c.x},${p.c.y}|${p.tier.radius}|${p.tier.fontSize}|${p.dir}|${p.off[0]},${p.off[1]}`
}

function updateCities() {
  const z = map.getZoom()
  const all = z < 2.5 ? [] : placementsAt(z)

  // Viewport cull: placement is still computed map-wide (so what renders is
  // identical), but only markers near the view get DOM nodes. Pad covers the
  // longest label reach so nothing partially visible is ever missing.
  let reach = 64
  for (const p of all) {
    const r = p.c.name.length * p.tier.fontSize * 0.62 + 48
    if (r > reach) reach = r
  }
  const pb = map.getPixelBounds()
  const minX = pb.min!.x - reach, maxX = pb.max!.x + reach
  const minY = pb.min!.y - reach, maxY = pb.max!.y + reach

  const placements: Placement[] = []
  for (const p of all) {
    const pt = ptAt(p.c, z)
    if (pt.x >= minX && pt.x <= maxX && pt.y >= minY && pt.y <= maxY) placements.push(p)
  }

  const want = new Map(placements.map(p => [p.c, p]))
  const isNewSet = all !== lastAll

  const drop: City[] = []
  for (const [c] of shownCities) if (!want.has(c)) drop.push(c)

  const build: Placement[] = []
  for (const p of placements) {
    const existing = shownCities.get(p.c)
    if (existing?.key === placementKey(p)) continue
    build.push(p)
  }

  // Leaflet appends each marker icon to the pane as it is added, so a thousand
  // markers is a thousand separate insertions into a live tree. Detaching the
  // pane first makes them all off-document and costs one reflow at the end
  // instead. Only worth the swap for a big batch — crossing z3 to z3.5 rebuilds
  // every marker on screen, because the global marker scale changes there.
  const churn = drop.length + build.length
  const batched = churn > BATCH_MIN
  const pane = map.getPane('markerPane')!
  const parent = pane.parentNode
  const anchor = pane.nextSibling
  if (batched && parent) parent.removeChild(pane)

  try {
    for (const c of drop) {
      cityLayer.removeLayer(shownCities.get(c)!.marker)
      shownCities.delete(c)
    }

    for (const p of build) {
      const key = placementKey(p)
      const existing = shownCities.get(p.c)
      if (existing) cityLayer.removeLayer(existing.marker)

      // The fade is a nicety for a few markers arriving. A thousand of them at
      // once is a thousand concurrent animations, which is the cost it was
      // meant to soften.
      const fade = !batched && isNewSet && !prevPlaced.has(p.c)
      const marker = L.marker(px(p.c.x!, p.c.y!), { icon: cityIcon(p, fade) })
      marker.on('click', () => openCityPanel(p.c))
      cityLayer.addLayer(marker)
      shownCities.set(p.c, { marker, key })
    }
  } finally {
    // finally, so a throw mid-batch cannot leave the map with no marker pane
    if (batched && parent) parent.insertBefore(pane, anchor)
  }

  if (isNewSet) {
    prevPlaced = new Set(all.map(p => p.c))
    lastAll = all
  }
}

// --- City info panel (Apple Maps style) ---

const cityPanel = document.createElement('div')
cityPanel.id = 'city-panel'
cityPanel.hidden = true
// Inside the left stack, not on the body: on a desktop the rail and this panel
// are flex siblings, so the browser guarantees they sit side by side. Positioning
// them independently meant two width values had to agree, and when they did not
// the panel painted over the rail.
document.getElementById('ui-left')!.appendChild(cityPanel)

function fmtUSD(n: number): string {
  return '$' + n.toLocaleString('en-US')
}

function cityRank(c: City, field: 'population' | 'gdp' | 'gdpPerCapita'): number {
  const val = c[field]
  if (!val) return 0
  let rank = 1
  for (const o of cities) {
    if (o[field] > val) rank++
  }
  return rank
}

function fmtRank(n: number): string {
  if (!n) return ''
  return ` <span class="cp-rank">#${n}</span>`
}

// Banner images: drop Name.png/jpg/jpeg into src/assets/cities/. Vite resolves
// the whole set at build time, so a lookup is a Map hit — the old approach
// probed up to six candidate URLs per open and missed on nearly every city.
// Keys are norm()'d, so file and city names need not agree on diacritics.
const banners = new Map<string, string>()
for (const [path, url] of Object.entries(
  import.meta.glob('./assets/cities/*.{png,jpg,jpeg,PNG,JPG,JPEG}', {
    eager: true,
    query: '?url',
    import: 'default',
  }) as Record<string, string>
)) {
  banners.set(norm(path.slice(path.lastIndexOf('/') + 1).replace(/\.[^.]+$/, '')), url)
}

const talopediaByCity = new Map<string, TalopediaEntry>()
for (const [name, entry] of Object.entries(talopedia)) talopediaByCity.set(norm(name), entry)

// Blurbs are pasted prose, so they carry apostrophes and ampersands that would
// otherwise break out of the template string
function esc(s: string): string {
  return s.replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[ch]!)
}

// Both maps are keyed on bare names, but a city may carry a ", XX" suffix
function byCityName<T>(m: Map<string, T>, name: string): T | undefined {
  return m.get(norm(name)) ?? m.get(norm(name.replace(/,\s*[A-Z]{2,4}$/, '')))
}

function loadBanner(name: string) {
  const holder = cityPanel.querySelector('.cp-banner') as HTMLElement
  const img = holder.querySelector('img') as HTMLImageElement
  const url = byCityName(banners, name)
  if (!url) return
  img.src = url
  holder.classList.add('cp-banner-show')
}

// The blurb is clamped to a few lines; the toggle only appears when there is
// actually something hidden, which can only be known once the panel is laid out
function wireAboutToggle() {
  const text = cityPanel.querySelector('.cp-about-text') as HTMLElement | null
  const btn = cityPanel.querySelector('.cp-more') as HTMLButtonElement | null
  if (!text || !btn || text.scrollHeight <= text.clientHeight + 1) return
  btn.hidden = false
  btn.addEventListener('click', () => {
    const open = text.classList.toggle('cp-about-open')
    btn.textContent = open ? 'Less' : 'More'
  })
}

// One row of a details card: label left, value right on one line. `more` rows
// are the detail behind the number and are built from this same function, so the
// reveal inherits the row's padding, type and hairline instead of inventing its
// own. It is positioned absolutely in CSS, because growing a row on hover would
// shove every row below it down the panel.
// A reveal entry is [label, value, icon?]; the icon is optional so the plain card
// rows can keep passing pairs.
type Reveal = [string, string, string?]

function detailRow(
  label: string,
  value: string,
  link = false,
  more: Reveal[] = [],
  icon = ''
): string {
  const reveal = more.length
    ? `<div class="cp-row-more">` +
      more.map(([l, v, ic]) => detailRow(l, v, false, [], ic)).join('') +
      `</div>`
    : ''
  return (
    `<div class="cp-row">` +
    `<div class="cp-row-label">${icon}${label}</div>` +
    `<div class="cp-row-value${link ? ' cp-link' : ''}">${value}</div>` +
    reveal +
    `</div>`
  )
}

// Falsy entries are dropped, so a caller can list every possible row and let the
// data decide which exist. An empty card renders nothing rather than a heading
// over a blank box.
function detailsCard(rows: string[]): string {
  const body = rows.filter(Boolean).join('')
  return body ? `<div class="cp-section">Details</div><div class="cp-card">${body}</div>` : ''
}

// Stroke icons for the strip. They take currentColor, so one rule tints them.
const STAT_ICON = {
  population:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<circle cx="9" cy="8" r="3.2"/><path d="M2.8 19.6c0-3.3 2.8-5.2 6.2-5.2s6.2 1.9 6.2 5.2"/>' +
    '<path d="M16.6 5.4a3.2 3.2 0 0 1 0 5.2"/><path d="M18.4 15c1.9.7 2.8 2.3 2.8 4.6"/></svg>',
  gdp:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M3.5 20.5h17"/><path d="M6.5 20.5v-6"/><path d="M12 20.5V4.5"/><path d="M17.5 20.5v-9.5"/></svg>',
  hdi:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M3.5 20.5h17"/><path d="M5 16.2c3.4 0 5.1-3.4 7-6.3 1.6-2.4 3.4-4.4 6.5-4.4"/>' +
    '<path d="M15.6 5.8h3v3"/></svg>',
  urban:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M3.5 20.5h17"/><path d="M6 20.5V9l5-3.5V20.5"/><path d="M11 20.5V12h7v8.5"/>' +
    '<path d="M14 15.5h1.5"/><path d="M8.2 12h.6"/></svg>',
  rural:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M12 21v-6"/><path d="M12 15c-3.6 0-6-2.2-6-5.3S8.4 3.5 12 3.5s6 3.1 6 6.2S15.6 15 12 15Z"/>' +
    '<path d="M4 21h16"/></svg>',
  life:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M12 20.3S3.8 15.4 3.8 9.7A4.4 4.4 0 0 1 12 7.4a4.4 4.4 0 0 1 8.2 2.3c0 5.7-8.2 10.6-8.2 10.6Z"/></svg>',
  literacy:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M12 6.6C10.3 5.2 7.8 4.6 4 4.6v13c3.8 0 6.3.6 8 2 1.7-1.4 4.2-2 8-2v-13c-3.8 0-6.3.6-8 2Z"/>' +
    '<path d="M12 6.6v12"/></svg>',
  perCapita:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<circle cx="12" cy="12" r="8.6"/><path d="M12 6.8v10.4"/>' +
    '<path d="M14.7 9.4c-.6-.8-1.6-1.2-2.7-1.2-1.5 0-2.7.8-2.7 2s1.2 1.7 2.7 2 2.7.9 2.7 2.1-1.2 2-2.7 2c-1.1 0-2.1-.4-2.7-1.2"/></svg>',
}

interface Stat {
  label: string
  icon: string
  value: string
  /** Narrow-screen stand-in. CSS swaps to it below 430px, where the exact figure
   *  no longer fits the cell. Omit when the value is short enough either way. */
  short?: string
  more?: Reveal[]
}

// The three headline numbers side by side, above everything else. Values are
// compact: a 400px panel split three ways leaves about 109px per cell, and a
// figure like $2,320,000,000,000 needs closer to 180px. The exact number and its
// rank live in the hover, so shortening the face loses nothing.
function statStrip(stats: Stat[]): string {
  return (
    `<div class="cp-strip">` +
    stats
      .map(
        s =>
          `<div class="cp-cell">` +
          `<div class="cp-cell-label">${s.label}</div>` +
          `<div class="cp-cell-value">${s.icon}` +
          (s.short
            ? `<span class="v-full">${s.value}</span><span class="v-short">${s.short}</span>`
            : `<span>${s.value}</span>`) +
          `</div>` +
          (s.more?.length
            ? `<div class="cp-row-more">${s.more.map(([l, v]) => detailRow(l, v)).join('')}</div>`
            : '') +
          `</div>`
      )
      .join('') +
    `</div>`
  )
}

function openCityPanel(c: City) {
  if (measuring) return
  const wasOpen = !cityPanel.hidden
  const displayName = c.name.replace(/,\s*[A-Z]{2,4}$/, '')
  const popRank = cityRank(c, 'population')
  const gdpRank = cityRank(c, 'gdp')
  const pcRank = cityRank(c, 'gdpPerCapita')
  const nat = nationByName.get(norm(c.nation))
  const wiki = byCityName(talopediaByCity, c.name)
  cityPanel.innerHTML =
    `<div class="cp-banner"><img alt=""></div>` +
    `<button class="cp-close" aria-label="Close">✕</button>` +
    `<div class="cp-name">${displayName}</div>` +
    (c.nativeScript ? `<div class="cp-native">${c.nativeScript}</div>` : '') +
    (c.x != null && c.y != null
      ? `<div class="cp-coord">${fmtGeo(toGeo(c.x, c.y))}</div>`
      : '') +
    statStrip([
      {
        label: 'Population',
        icon: STAT_ICON.population,
        value: c.population.toLocaleString('en-US'),
        short: fmtCompact(c.population),
        more: [['Population', c.population.toLocaleString('en-US') + fmtRank(popRank), STAT_ICON.population]],
      },
      {
        label: 'GDP PPP',
        icon: STAT_ICON.gdp,
        value: '$' + fmtCompact(c.gdp),
        more: [['GDP PPP', fmtUSD(c.gdp) + fmtRank(gdpRank), STAT_ICON.gdp]],
      },
      {
        label: 'Per Capita',
        icon: STAT_ICON.perCapita,
        value: fmtUSD(c.gdpPerCapita),
        more: [['Per Capita', fmtUSD(c.gdpPerCapita) + fmtRank(pcRank), STAT_ICON.perCapita]],
      },
    ]) +
    (wiki?.about
      ? `<div class="cp-section">About</div>` +
        `<div class="cp-about"><p class="cp-about-text">${esc(wiki.about)}</p>` +
        `<button class="cp-more" hidden>More</button></div>`
      : '') +
    (wiki
      ? `<a class="cp-source" href="${wiki.url}" target="_blank" rel="noopener noreferrer">More on <span>the Talopedia</span></a>`
      : '') +
    detailsCard([
      detailRow('Nation', `${c.nation}${c.alpha3 ? ` <span class="cp-sub">(${c.alpha3})</span>` : ''}`, !!nat),
      c.irlParallel ? detailRow('IRL Parallel', c.irlParallel) : '',
    ])
  cityPanel.classList.remove('cp-closing')
  cityPanel.hidden = false
  document.body.classList.add('panel-open')
  closeSheetList()
  markNavOpen(null)
  // A swap only reads as a change when the kind changes. City to city is the
  // same surface showing different content, and re-animating makes an ordinary
  // click feel like the panel reopened.
  if (wasOpen && openCityName === null) replayAnim(cityPanel, 'cp-swap')
  cityPanel.querySelector('.cp-close')!.addEventListener('click', closeCityPanel)
  // flyToNation/goCity rather than the bare open*Panel: a link should land you
  // where the thing is, which is what the search results already do
  if (nat) cityPanel.querySelector('.cp-link')!.addEventListener('click', () => flyToNation(nat))
  wireAboutToggle()
  hideSheet()
  openCityName = c.name
  openNationName = null
  syncHash()
  loadBanner(c.name)
}

// --- Nation info panel ---

type NationStatField = 'population' | 'gdp' | 'gdpPerCapita' | 'hdi' | 'lifeExpectancy' | 'literacy'
const nationRankCache = new Map<NationStatField, Map<Nation, number>>()

function nationRanks(field: NationStatField): Map<Nation, number> {
  let m = nationRankCache.get(field)
  if (!m) {
    const built = new Map<Nation, number>()
    ;[...nations].sort((a, b) => b[field] - a[field]).forEach((n, i) => built.set(n, i + 1))
    nationRankCache.set(field, built)
    m = built
  }
  return m
}

function nationRank(n: Nation, field: NationStatField): number {
  return n[field] ? nationRanks(field).get(n) ?? 0 : 0
}

function openNationPanel(n: Nation) {
  if (measuring) return
  const wasOpen = !cityPanel.hidden
  const agg = mapAggFor(n)
  const urban = agg.pop
  const rural = Math.max(0, n.population - urban)
  const hdiParts: Reveal[] = []
  if (n.hdi) hdiParts.push(['HDI', n.hdi.toFixed(3) + fmtRank(nationRank(n, 'hdi')), STAT_ICON.hdi])
  if (n.lifeExpectancy) {
    hdiParts.push([
      'Life Expectancy',
      n.lifeExpectancy.toFixed(1) + fmtRank(nationRank(n, 'lifeExpectancy')),
      STAT_ICON.life,
    ])
  }
  if (n.literacy) {
    hdiParts.push([
      'Literacy',
      n.literacy.toFixed(1) + '%' + fmtRank(nationRank(n, 'literacy')),
      STAT_ICON.literacy,
    ])
  }
  // The capital as an object, not just a name, so the value can open its panel
  const cap = n.capital
    ? cities.find(c => norm(c.name) === norm(n.capital) && norm(c.nation) === norm(n.name))
    : undefined
  cityPanel.innerHTML =
    `<div class="cp-banner"><img alt=""></div>` +
    `<button class="cp-close" aria-label="Close">✕</button>` +
    `<div class="cp-name">${n.name}</div>` +
    (n.official ? `<div class="cp-native">${n.official}${n.alpha3 ? ` <span class="cp-sub">(${n.alpha3})</span>` : ''}</div>` : '') +
    statStrip([
      {
        label: 'Population',
        icon: STAT_ICON.population,
        value: n.population.toLocaleString('en-US'),
        short: fmtCompact(n.population),
        more: [
          [
            'Population',
            n.population.toLocaleString('en-US') + fmtRank(nationRank(n, 'population')),
            STAT_ICON.population,
          ],
          ...(urban > 0
            ? ([
                ['Urban', urban.toLocaleString('en-US'), STAT_ICON.urban],
                ['Rural', rural.toLocaleString('en-US'), STAT_ICON.rural],
              ] as Reveal[])
            : []),
        ],
      },
      // Per capita is GDP divided by population, so it belongs behind the GDP it
      // comes from rather than as a third headline.
      {
        label: 'GDP PPP',
        icon: STAT_ICON.gdp,
        value: '$' + fmtCompact(n.gdp),
        more: [
          ['GDP PPP', fmtUSD(n.gdp) + fmtRank(nationRank(n, 'gdp')), STAT_ICON.gdp],
          [
            'Per Capita',
            fmtUSD(n.gdpPerCapita) + fmtRank(nationRank(n, 'gdpPerCapita')),
            STAT_ICON.perCapita,
          ],
        ],
      },
      // Life expectancy and literacy are two of the three components HDI is built
      // from, so they travel with it as its reveal rather than becoming rows.
      {
        label: 'HDI',
        icon: STAT_ICON.hdi,
        value: n.hdi ? n.hdi.toFixed(3) : '—',
        more: hdiParts,
      },
    ]) +
    detailsCard([
      n.continent ? detailRow('Continent', n.continent) : '',
      n.capital ? detailRow('Capital', n.capital, !!cap) : '',
      n.status ? detailRow('Status', n.status) : '',
    ]) +
    (agg.count
      ? `<button class="cp-action">View ${agg.count} ${agg.count === 1 ? 'city' : 'cities'}</button>`
      : '')
  cityPanel.classList.remove('cp-closing')
  cityPanel.hidden = false
  document.body.classList.add('panel-open')
  if (wasOpen && openNationName === null) replayAnim(cityPanel, 'cp-swap')
  cityPanel.querySelector('.cp-close')!.addEventListener('click', closeCityPanel)
  // The capital is the only link in a nation panel, so this cannot pick up another
  if (cap) cityPanel.querySelector('.cp-link')!.addEventListener('click', () => goCity(cap))
  cityPanel.querySelector('.cp-action')?.addEventListener('click', () => {
    closeCityPanel()
    openListView('cities', n.name)
  })
  hideSheet()
  openCityName = null
  openNationName = n.name
  syncHash()
  loadBanner(n.name)
}

function closeCityPanel() {
  if (cityPanel.hidden || cityPanel.classList.contains('cp-closing')) return
  cityPanel.classList.remove('cp-swap')
  cityPanel.classList.add('cp-closing')
  cityPanel.addEventListener('animationend', () => {
    cityPanel.classList.remove('cp-closing')
    cityPanel.hidden = true
    document.body.classList.remove('panel-open')
    openCityName = null
    openNationName = null
    syncHash()
    showSheet()
  }, { once: true })
}

map.on('click', () => {
  if (!measuring) closeCityPanel()
})
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return
  if (measuring) endMeasure()
  else if (!cityPanel.hidden) closeCityPanel()
  else closeSheetList()
})

;(window as any)._map = map

// --- Zoom handler ---

map.on('zoomend', () => {
  updateLabels()
  updateCities()
})


// Culling depends on the view, so pans re-diff too. rAF-throttled so inertia
// glides stream markers in; zoom animation frames skipped (zoomend covers them)
let moveRaf = 0
map.on('move', () => {
  if (moveRaf) return
  moveRaf = requestAnimationFrame(() => {
    moveRaf = 0
    if (!(map as any)._animatingZoom) updateCities()
  })
})
map.on('moveend', () => updateCities())

updateLabels()
updateCities()

// --- City placement tool ---

const SAVE_KEY = 'avium-city-coords'

// Placements are keyed on name AND nation. Name alone collides — seven cities
// share a name with one in a different nation — and the collision corrupts in
// both directions: on save, whichever comes last in the array overwrites the
// other's entry, and on load that one coordinate is handed back to both. Place
// one twin and the other jumps on top of it. Tab matches merge-tsv.mjs, and
// neither field can contain one.
const coordKey = (c: { name: string; nation: string }) => `${c.name}\t${c.nation}`

const nameCount = new Map<string, number>()
for (const c of cities) nameCount.set(c.name, (nameCount.get(c.name) ?? 0) + 1)

function saveProgress() {
  markDirty()
  const coords: Record<string, [number, number]> = {}
  for (const c of cities) {
    if (c.x != null && c.y != null) coords[coordKey(c)] = [c.x, c.y]
  }
  localStorage.setItem(SAVE_KEY, JSON.stringify(coords))
}

// Saves written before the key carried the nation are keyed on name alone. They
// are honoured where the name is unique, which is exactly where they mean one
// city — a legacy entry under a shared name is the corruption this exists to
// stop, so it is dropped rather than reapplied to both.
function legacyCoord(
  coords: Record<string, [number, number]>,
  c: City
): [number, number] | undefined {
  return coords[coordKey(c)] ?? (nameCount.get(c.name) === 1 ? coords[c.name] : undefined)
}

function loadProgress() {
  const raw = localStorage.getItem(SAVE_KEY)
  if (!raw) return 0
  const coords: Record<string, [number, number]> = JSON.parse(raw)
  let count = 0
  for (const c of cities) {
    const xy = legacyCoord(coords, c)
    if (xy) {
      ;[c.x, c.y] = xy
      count++
    }
  }
  return count
}

const LABEL_KEY = 'avium-label-coords'

function saveLabelProgress() {
  markDirty()
  const saved: Record<string, Partial<LabelDef>> = {}
  for (const d of labelDefs) {
    // A resized label may never have been dragged, so span alone is enough
    if (d.x == null && d.span == null) continue
    saved[`${d.type}:${d.text}`] = { x: d.x, y: d.y, tier: d.tier, span: d.span }
  }
  localStorage.setItem(LABEL_KEY, JSON.stringify(saved))
}

function loadLabelProgress() {
  const raw = localStorage.getItem(LABEL_KEY)
  if (!raw) return
  const saved: Record<string, any> = JSON.parse(raw)
  for (const d of labelDefs) {
    const s = saved[`${d.type}:${d.text}`]
    if (!s) continue
    const v = Array.isArray(s) ? { x: s[0], y: s[1], tier: s[2] } : s // pre-span sessions
    if (v.x != null) {
      d.x = v.x
      d.y = v.y
    }
    if (v.tier != null) d.tier = v.tier
    if (v.span != null) d.span = v.span
  }
}

// TSV paste import: columns map to city fields by header name.
// Preserves existing coordinates — only data fields get overridden.
// Cities in the TSV that don't exist yet get added; cities not in the
// TSV get removed.
function importTSV(tsv: string) {
  const lines = tsv.trim().split('\n')
  if (lines.length < 2) return

  const headers = lines[0].split('\t').map(h => h.trim())
  const colMap: Record<string, string> = {
    'name': 'name', 'city': 'name',
    'nation': 'nation', 'country': 'nation',
    'population': 'population', 'pop': 'population',
    'gdp': 'gdp', 'grdp ppp ($)': 'gdp',
    'gdp per capita': 'gdpPerCapita', 'gdppercapita': 'gdpPerCapita', 'gdp/capita': 'gdpPerCapita',
    'real grdp p/c ($)': 'gdpPerCapita',
    'native script': 'nativeScript', 'nativescript': 'nativeScript', 'script': 'nativeScript',
    'irl parallel': 'irlParallel', 'irlparallel': 'irlParallel', 'parallel': 'irlParallel',
    'alpha3': 'alpha3', 'code': 'alpha3', 'alpha-3 code': 'alpha3',
  }
  const cols = headers.map(h => colMap[h.toLowerCase()] ?? null)
  const nameCol = cols.indexOf('name')
  if (nameCol < 0) {
    statusEl.textContent = 'TSV needs a "Name" column'
    statusEl.className = 'status-active'
    return
  }

  // Build coord lookup from current state, on the same name+nation key
  const coordMap = new Map<string, [number | null, number | null]>()
  for (const c of cities) coordMap.set(coordKey(c), [c.x, c.y])

  // Also pull from localStorage in case some coords aren't in the current array
  const saved = localStorage.getItem(SAVE_KEY)
  if (saved) {
    const coords = JSON.parse(saved) as Record<string, [number, number]>
    for (const c of cities) {
      const xy = legacyCoord(coords, c)
      const key = coordKey(c)
      if (xy && (!coordMap.has(key) || coordMap.get(key)![0] == null)) coordMap.set(key, xy)
    }
  }

  const newCities: City[] = []
  for (let i = 1; i < lines.length; i++) {
    const vals = lines[i].split('\t').map(v => v.trim())
    if (!vals[nameCol]) continue

    const city: City = {
      name: '', nation: '', population: 0, gdp: 0, gdpPerCapita: 0,
      nativeScript: '', irlParallel: '', alpha3: '', x: null, y: null,
    }
    for (let j = 0; j < cols.length; j++) {
      const field = cols[j]
      if (!field || !vals[j]) continue
      if (field === 'population' || field === 'gdp' || field === 'gdpPerCapita') {
        (city as any)[field] = parseFloat(vals[j].replace(/,/g, '')) || 0
      } else {
        (city as any)[field] = vals[j] === '-' ? '' : vals[j]
      }
    }

    // Preserve coordinates
    const existing = coordMap.get(coordKey(city))
    if (existing) { city.x = existing[0]; city.y = existing[1] }
    newCities.push(city)
  }

  cities.length = 0
  cities.push(...newCities)

  // Rebuild priority sort
  citiesByPriority.length = 0
  citiesByPriority.push(
    ...[...cities].sort(
      (a, b) => tierRank(a.population) - tierRank(b.population) || b.gdp - a.gdp
    )
  )

  saveProgress()
  invalidatePlacements()
  updateCities()
  updateCount()
  statusEl.textContent = `TSV: ${newCities.length} cities loaded, ${newCities.filter(c => c.x != null).length} placed`
  statusEl.className = 'status-done'
}

function importJSON(file: File) {
  const reader = new FileReader()
  reader.onload = () => {
    const data = JSON.parse(reader.result as string)

    // Labels file: entries have type + text instead of name + population
    if (Array.isArray(data) && data[0]?.type && data[0]?.text) {
      let count = 0
      for (const imported of data as LabelDef[]) {
        if (imported.x == null || imported.y == null) continue
        const match = labelDefs.find(d => d.type === imported.type && d.text === imported.text)
        if (match) {
          match.x = imported.x
          match.y = imported.y
          if (imported.tier != null) match.tier = imported.tier
          refreshLabel(match)
          count++
        }
      }
      saveLabelProgress()
      updateCount()
      statusEl.textContent = `Imported ${count} labels`
      statusEl.className = 'status-done'
      return
    }

    let count = 0
    for (const imported of data as City[]) {
      if (imported.x == null || imported.y == null) continue
      const match = cities.find(c => c.name === imported.name)
      if (match) {
        match.x = imported.x
        match.y = imported.y
        count++
      }
    }
    saveProgress()
    updateCount()
    invalidatePlacements()
    updateCities()
    statusEl.textContent = `Imported ${count} cities`
    statusEl.className = 'status-done'
  }
  reader.readAsText(file)
}

const loaded = loadProgress()
if (loaded > 0) {
  updateCities()
}

loadLabelProgress()
// mountLabel, not refreshLabel: one placement rebuild at the end rather than
// one per label
for (const def of labelDefs) mountLabel(def)
updateLabels()
invalidatePlacements()
updateCities()

const panel = document.getElementById('place-panel')!
const searchInput = document.getElementById('place-search') as HTMLInputElement
const resultsList = document.getElementById('place-results')!
const statusEl = document.getElementById('place-status')!
const coordEl = document.querySelector('.coord-display') as HTMLElement
const countEl = document.getElementById('place-count')!
const importInput = document.getElementById('place-import') as HTMLInputElement
const unassignedPanel = document.getElementById('unassigned-panel')!
const unassignedHeader = document.getElementById('unassigned-header')!
const unassignedList = document.getElementById('unassigned-list')!
const spanRow = document.getElementById('span-row')!
const spanInput = document.getElementById('place-span') as HTMLInputElement
const spanReadout = document.getElementById('span-readout')!

if (!DEV) {
  panel.style.display = 'none'
  coordEl.style.display = 'none'
  unassignedPanel.style.display = 'none'
}

let selectedCity: City | null = null
let selectedLabel: LabelDef | null = null

// Declared here, not beside the code that uses them: updateCount() runs during
// module init and reaches updateUnassigned(), which reads both. Left at the
// bottom of the file they are still in the temporal dead zone at that moment,
// which throws and takes every listener registered after it down with it.
interface Station {
  name: string
  continent: string
  x: number | null
  y: number | null
}

const stations = stationsData as Station[]
let selectedStation: Station | null = null

type PlacerTab = 'cities' | 'labels'
let tab: PlacerTab = 'cities'

// The label the span field edits. Tracked apart from selectedLabel, which is
// armed for a placement click and cleared the moment one lands — the size
// usually wants a few passes after the position is right.
let spanTarget: LabelDef | null = null

function syncSpanRow() {
  const d = spanTarget
  spanRow.hidden = !d
  if (!d) return
  const span = Math.round(areaSpan(d))
  if (document.activeElement !== spanInput) spanInput.value = String(span)
  spanReadout.textContent = `${d.text} · ${areaFontSize(d, map.getZoom()).toFixed(1)}px`
}

function setSpanTarget(d: LabelDef | null) {
  spanTarget = d
  syncSpanRow()
}

spanInput.addEventListener('input', () => {
  const n = Number(spanInput.value)
  if (!spanTarget || !isFinite(n) || n <= 0) return
  spanTarget.span = n
  // Per keystroke, only the ~70 label markers redraw; the placement rebuild
  // that 1700 cities depend on waits for blur or Enter
  updateLabels()
  syncSpanRow()
})

spanInput.addEventListener('change', () => {
  if (!spanTarget?.span) return
  saveLabelProgress()
  invalidatePlacements()
  updateCities()
  statusEl.textContent = `${spanTarget.text} → span ${Math.round(spanTarget.span)}`
  statusEl.className = 'status-done'
})
let placedMarker: L.CircleMarker | null = null

function updateCount() {
  const placed = cities.filter(c => c.x != null && c.y != null).length
  // A derived anchor counts as placed: that label is already on the map and
  // draggable, so the placer has nothing left to do for it
  const lPlaced = labelDefs.filter(d => labelPos(d) != null).length
  countEl.textContent = `${placed}/${cities.length} cities · ${lPlaced}/${labelDefs.length} labels`
  updateUnassigned()
}

function updateUnassigned() {
  if (!DEV) return
  // Scoped to the open tab, so the panel is a worklist for the job in hand
  // rather than a pile of both
  const unplacedLabels = tab === 'labels' ? labelDefs.filter(d => labelPos(d) == null) : []
  const unplacedStations = tab === 'labels' ? stations.filter(p => p.x == null) : []
  const unplaced = tab === 'cities' ? citiesByPriority.filter(c => c.x == null || c.y == null) : []
  const total = unplacedLabels.length + unplacedStations.length + unplaced.length
  unassignedHeader.textContent = `Unassigned (${total})`
  if (!total) {
    unassignedPanel.style.display = 'none'
    return
  }
  unassignedPanel.style.display = ''
  unassignedList.innerHTML = ''
  // Labels first: there are a handful, and each covers more map than any city
  for (const d of unplacedLabels) {
    const li = document.createElement('li')
    li.innerHTML = `<span class="result-name">${d.text}</span>` +
      `<span class="result-meta">${d.type.toUpperCase()}</span>`
    li.addEventListener('click', () => selectLabel(d))
    unassignedList.appendChild(li)
  }
  for (const p of unplacedStations) {
    const li = document.createElement('li')
    li.innerHTML = `<span class="result-name">${p.name}</span>` +
      `<span class="result-meta">STATION</span>`
    li.addEventListener('click', () => selectStation(p))
    unassignedList.appendChild(li)
  }
  for (const c of unplaced) {
    const li = document.createElement('li')
    li.innerHTML = `<span class="result-name">${c.name}</span>` +
      `<span class="result-meta">${c.nation} · ${(c.population / 1e6).toFixed(2)}M</span>`
    li.addEventListener('click', () => selectCity(c))
    unassignedList.appendChild(li)
  }
}

updateCount()

importInput.addEventListener('change', () => {
  if (importInput.files?.[0]) importJSON(importInput.files[0])
  importInput.value = ''
})

function renderResults() {
  const q = norm(searchInput.value.trim())
  resultsList.innerHTML = ''
  // Cities need a query: there are 1747 and nobody browses that. Labels and
  // stations number about a hundred, so an empty box lists all of them — on that
  // tab this is a browser, not a search field, and without it the tab looked
  // broken whenever everything happened to be placed already.
  const browsing = tab === 'labels' && !q
  if (!browsing && q.length < 2) return

  const matches = tab === 'cities'
    ? cities.filter(c => norm(c.name).includes(q) || norm(c.nation).includes(q)).slice(0, 10)
    : []

  for (const c of matches) {
    const li = document.createElement('li')
    const placed = c.x != null
    li.innerHTML = `<span class="result-name">${c.name}</span>` +
      `<span class="result-meta">${c.nation} &middot; ${(c.population / 1e6).toFixed(2)}M${placed ? ' ✓' : ''}</span>`
    if (placed) li.classList.add('placed')
    li.addEventListener('click', () => selectCity(c))
    resultsList.appendChild(li)
  }

  const labelMatches = tab === 'labels'
    ? labelDefs.filter(d => !q || norm(d.text).includes(q)).slice(0, browsing ? 400 : 6)
    : []

  for (const d of labelMatches) {
    const li = document.createElement('li')
    const placed = d.x != null
    li.innerHTML = `<span class="result-name">${d.text}</span>` +
      `<span class="result-meta">${d.type.toUpperCase()}${placed ? ' ✓' : ''}</span>`
    if (placed) li.classList.add('placed')
    li.addEventListener('click', () => selectLabel(d))
    resultsList.appendChild(li)
  }

  const stationMatches = tab === 'labels'
    ? stations.filter(p => !q || norm(p.name).includes(q)).slice(0, browsing ? 400 : 6)
    : []

  for (const p of stationMatches) {
    const li = document.createElement('li')
    const placed = p.x != null
    li.innerHTML = `<span class="result-name">${p.name}</span>` +
      `<span class="result-meta">STATION${placed ? ' ✓' : ''}</span>`
    if (placed) li.classList.add('placed')
    li.addEventListener('click', () => selectStation(p))
    resultsList.appendChild(li)
  }
}

searchInput.addEventListener('input', renderResults)

function selectCity(c: City) {
  selectedCity = c
  selectedLabel = null
  selectedStation = null
  setSpanTarget(null)
  syncEditRow()
  resultsList.innerHTML = ''
  searchInput.value = c.name
  statusEl.textContent = `Click the map to place ${c.name}`
  statusEl.className = 'status-active'

  if (c.x != null && c.y != null) focusOn(c.x, c.y, Math.max(map.getZoom(), 4))
}

function selectLabel(d: LabelDef) {
  selectedLabel = d
  selectedCity = null
  selectedStation = null
  setSpanTarget(d)
  syncEditRow()
  resultsList.innerHTML = ''
  searchInput.value = d.text
  statusEl.className = 'status-active'
  statusEl.textContent = `Click the map to place ${d.text} (${d.type})`

  if (d.x != null && d.y != null) focusOn(d.x, d.y, map.getZoom())
}

map.on('click', (e: L.LeafletMouseEvent) => {
  const [x, y] = toPx(e.latlng)

  if (selectedStation) {
    selectedStation.x = x
    selectedStation.y = y
    saveStationProgress()
    updateStations()
    markDirty()
    statusEl.textContent = `${selectedStation.name} → [${x}, ${y}]`
    statusEl.className = 'status-done'
    // Stays selected: a station is placed and then usually named, and dropping
    // the selection here would close the rename field the moment it is needed
    syncEditRow()
    return
  }

  if (selectedLabel) {
    selectedLabel.x = x
    selectedLabel.y = y
    refreshLabel(selectedLabel)
    saveLabelProgress()
    updateCount()

    statusEl.textContent = `${selectedLabel.text} → [${x}, ${y}]`
    statusEl.className = 'status-done'

    selectedLabel = null
    searchInput.value = ''
    searchInput.focus()
    return
  }

  if (selectedCity) {
    selectedCity.x = x
    selectedCity.y = y

    if (placedMarker) {
      map.removeLayer(placedMarker)
    }
    placedMarker = L.circleMarker(e.latlng, {
      radius: 6,
      fillColor: '#0f0',
      fillOpacity: 0.8,
      color: '#fff',
      weight: 2,
    }).addTo(map)

    statusEl.textContent = `${selectedCity.name} → [${x}, ${y}]`
    statusEl.className = 'status-done'
    updateCount()
    invalidatePlacements()
    updateCities()
    saveProgress()

    selectedCity = null
    searchInput.value = ''
    searchInput.focus()

    setTimeout(() => {
      if (placedMarker) {
        map.removeLayer(placedMarker)
        placedMarker = null
      }
    }, 1500)
  }
})

if (DEV) {
  map.on('mousemove', (e: L.LeafletMouseEvent) => {
    const [x, y] = toPx(e.latlng)
    // One decimal: at the widest, a tenth of a degree is about 2px, so a second
    // place would report precision the pointer does not have
    coordEl.textContent = `x: ${x}  y: ${y}   ${fmtGeo(toGeo(x, y), 1)}`
  })
}

// Export is the Save button now — one press writes all three files, so a session
// can't end with cities.json current and labels.json a version behind.

// TSV paste toggle
const tsvArea = document.getElementById('tsv-paste') as HTMLTextAreaElement
document.getElementById('tsv-toggle')!.addEventListener('click', () => {
  const show = tsvArea.hidden
  tsvArea.hidden = !show
  if (show) tsvArea.focus()
})

tsvArea.addEventListener('keydown', (e: KeyboardEvent) => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
    importTSV(tsvArea.value)
    tsvArea.value = ''
    tsvArea.hidden = true
  }
})

// Undo last placement
document.getElementById('place-undo')!.addEventListener('click', () => {
  const last = [...cities].reverse().find(c => c.x != null && c.y != null)
  if (last) {
    statusEl.textContent = `Removed ${last.name} [${last.x}, ${last.y}]`
    statusEl.className = 'status-active'
    last.x = null
    last.y = null
    updateCount()
    invalidatePlacements()
    updateCities()
    saveProgress()
  }
})

// --- Bottom sheet (public mode) ---

const sheet = document.getElementById('bottom-sheet')!
const bsHome = document.getElementById('bs-home')!
const bsList = document.getElementById('bs-list')!
const bsSearch = document.getElementById('bs-search') as HTMLInputElement
const bsResults = document.getElementById('bs-results')!
const bsItems = document.getElementById('bs-items')!
const bsFilter = document.getElementById('bs-filter') as HTMLInputElement
const bsTitle = document.getElementById('bs-title')!

if (DEV) sheet.style.display = 'none'

// Restart a one-shot CSS animation class regardless of current state
function replayAnim(el: HTMLElement, cls: string) {
  el.classList.remove(cls)
  void el.offsetWidth
  el.classList.add(cls)
}

const bsBanner = document.getElementById('bs-banner') as HTMLImageElement | null
if (bsBanner) bsBanner.src = bannerUrl

// The column is permanent on a desktop — the place panel opens beside it rather
// than over it — so there is nothing to hide. On a phone the sheet still has to
// get out of the way of the panel that replaces it.
function onDesktop(): boolean {
  return window.matchMedia('(min-width: 900px)').matches
}

function hideSheet() {
  if (!DEV && !onDesktop()) sheet.classList.add('bs-away')
}

function showSheet() {
  if (DEV || measuring) return
  sheet.classList.remove('bs-away')
}

function closeSheetList() {
  if (DEV || bsList.hidden) return
  bsList.hidden = true
  bsHome.hidden = false
  markNavOpen(null)
  showSheet()
  if (!onDesktop()) replayAnim(bsHome, 'bs-pop')
}

// Normalized name/nation index, built once (public data never mutates)
type SearchEntry = { c: City; n: string; nat: string }
let searchIdx: SearchEntry[] | null = null
function idx(): SearchEntry[] {
  if (!searchIdx) searchIdx = cities.map(c => ({ c, n: norm(c.name), nat: norm(c.nation) }))
  return searchIdx
}

function fmtCompact(n: number): string {
  if (n >= 1e12) return (n / 1e12).toFixed(2) + 'T'
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B'
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k'
  return String(n)
}

function goCity(c: City) {
  bsResults.innerHTML = ''
  bsSearch.value = ''
  if (c.x != null && c.y != null) focusOn(c.x, c.y, Math.max(map.getZoom(), 4))
  openCityPanel(c)
}

// Home search
let searchSel = -1

bsSearch.addEventListener('input', () => {
  const q = norm(bsSearch.value.trim())
  bsResults.innerHTML = ''
  searchSel = -1
  if (q.length < 2) return
  const matches = idx().filter(e => e.n.includes(q) || e.nat.includes(q)).slice(0, 10)
  for (const { c } of matches) {
    const li = document.createElement('li')
    li.innerHTML = `<span class="bs-cname">${c.name}</span>` +
      `<span class="bs-cnation">${c.nation} · ${fmtCompact(c.population)}</span>`
    li.addEventListener('click', () => goCity(c))
    bsResults.appendChild(li)
  }
})

// Arrow keys walk the results; Enter opens the highlighted one (or the first,
// so a fast typist can hit Enter without arrowing down first)
function moveSearchSel(d: number) {
  const items = bsResults.children
  if (!items.length) return
  items[searchSel]?.classList.remove('sel')
  searchSel = (searchSel + d + items.length) % items.length
  const el = items[searchSel] as HTMLElement
  el.classList.add('sel')
  el.scrollIntoView({ block: 'nearest' })
}

bsSearch.addEventListener('keydown', e => {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    moveSearchSel(1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    moveSearchSel(-1)
  } else if (e.key === 'Enter' && bsResults.children.length) {
    e.preventDefault()
    ;(bsResults.children[Math.max(searchSel, 0)] as HTMLElement).click()
  }
})

// List views
type SortField = 'name' | 'population' | 'gdp' | 'gdpPerCapita'
let listMode: 'cities' | 'nations' = 'cities'

let sortField: SortField = 'name'
let sortAsc = true
let listRows: City[] = []
let renderedCount = 0
const LIST_CHUNK = 150

// Global rank per stat, computed once per field on demand
const rankCache = new Map<SortField, Map<City, number>>()
function statRanks(field: SortField): Map<City, number> {
  let m = rankCache.get(field)
  if (!m) {
    m = new Map()
    const f = field as 'population'
    const sorted = [...cities].sort((a, b) => b[f] - a[f])
    sorted.forEach((c, i) => m!.set(c, i + 1))
    rankCache.set(field, m)
  }
  return m
}

function statText(c: City): string {
  if (sortField === 'gdp') return '$' + fmtCompact(c.gdp)
  if (sortField === 'gdpPerCapita') return '$' + c.gdpPerCapita.toLocaleString('en-US')
  return fmtCompact(c.population)
}

function renderMoreRows() {
  if (listMode === 'nations' || renderedCount >= listRows.length) return
  const end = Math.min(renderedCount + LIST_CHUNK, listRows.length)
  const rm = sortField !== 'name' ? statRanks(sortField) : null
  const frag = document.createDocumentFragment()
  for (let i = renderedCount; i < end; i++) {
    const c = listRows[i]
    const li = document.createElement('li')
    li.innerHTML =
      `<span class="bs-rank">${rm ? rm.get(c) : ''}</span>` +
      `<span class="bs-cinfo"><span class="bs-cname">${c.name}</span><span class="bs-cnation">${c.nation}</span></span>` +
      `<span class="bs-cstat">${statText(c)}</span>`
    li.addEventListener('click', () => goCity(c))
    frag.appendChild(li)
  }
  bsItems.appendChild(frag)
  renderedCount = end
}

bsItems.addEventListener('scroll', () => {
  if (bsItems.scrollTop + bsItems.clientHeight > bsItems.scrollHeight - 300) renderMoreRows()
})

const sortChips = Array.from(document.querySelectorAll<HTMLButtonElement>('.bs-sorts button'))

function updateSortChips() {
  for (const chip of sortChips) {
    const active = chip.dataset.sort === sortField
    chip.classList.toggle('active', active)
    const label = chip.dataset.sort === 'name' ? 'Name'
      : chip.dataset.sort === 'population' ? 'Population'
      : chip.dataset.sort === 'gdp' ? 'GDP' : 'Per Capita'
    chip.textContent = active ? `${label} ${sortAsc ? '↑' : '↓'}` : label
  }
}

// Map presence per nation (city count, urban pop, marker bounds), derived once
let nationMapAggs: Map<string, { count: number; pop: number; pts: L.LatLngExpression[] }> | null = null

function mapAggFor(n: Nation): { count: number; pop: number; pts: L.LatLngExpression[] } {
  if (!nationMapAggs) {
    nationMapAggs = new Map()
    for (const c of cities) {
      if (!c.nation) continue
      const k = norm(c.nation)
      let a = nationMapAggs.get(k)
      if (!a) nationMapAggs.set(k, a = { count: 0, pop: 0, pts: [] })
      a.count++
      a.pop += c.population
      if (c.x != null && c.y != null) a.pts.push(px(c.x, c.y))
    }
  }
  return nationMapAggs.get(norm(n.name)) ?? { count: 0, pop: 0, pts: [] }
}

function flyToNation(n: Nation) {
  const agg = mapAggFor(n)
  if (agg.pts.length) {
    // Pad by the sidebar so the nation is framed in the visible half
    map.flyToBounds(L.latLngBounds(agg.pts).pad(0.2), {
      maxZoom: 5,
      duration: 0.8,
      paddingTopLeft: [sidebarWidth(), 0],
    })
  }
  openNationPanel(n)
}

function nationStatText(n: Nation): string {
  if (sortField === 'gdp') return '$' + fmtCompact(n.gdp)
  if (sortField === 'gdpPerCapita') return '$' + n.gdpPerCapita.toLocaleString('en-US')
  return fmtCompact(n.population)
}

function renderNations(q: string) {
  bsItems.innerHTML = ''
  bsItems.scrollTop = 0
  let rows = [...nations]
  if (q) rows = rows.filter(n => norm(n.name).includes(q) || norm(n.official).includes(q))
  if (sortField === 'name') {
    rows.sort((a, b) => a.name.localeCompare(b.name))
  } else {
    const f = sortField as 'population'
    rows.sort((a, b) => a[f] - b[f])
  }
  if (!sortAsc) rows.reverse()
  const rm = sortField !== 'name' ? nationRanks(sortField as NationStatField) : null
  const frag = document.createDocumentFragment()
  for (const n of rows) {
    const agg = mapAggFor(n)
    const pct = worldGdpTotal ? (n.gdp / worldGdpTotal) * 100 : 0
    const pctText = pct >= 0.1 ? pct.toFixed(1) + '%' : '<0.1%'
    const li = document.createElement('li')
    li.innerHTML =
      `<span class="bs-rank">${rm ? rm.get(n) : ''}</span>` +
      `<span class="bs-cinfo"><span class="bs-cname">${n.name}</span><span class="bs-cnation">${agg.count} ${agg.count === 1 ? 'city' : 'cities'} · ${pctText} of world GDP</span></span>` +
      `<span class="bs-cstat">${nationStatText(n)}</span>`
    li.addEventListener('click', () => flyToNation(n))
    frag.appendChild(li)
  }
  bsItems.appendChild(frag)
}

function rebuildList(animate = true) {
  const q = norm(bsFilter.value.trim())
  if (listMode === 'nations') {
    renderNations(q)
  } else {
    let rows = idx()
    if (q) rows = rows.filter(e => e.n.includes(q) || e.nat.includes(q))
    const sorted = [...rows]
    if (sortField === 'name') {
      sorted.sort((a, b) => a.c.name.localeCompare(b.c.name))
    } else {
      const f = sortField as 'population'
      sorted.sort((a, b) => a.c[f] - b.c[f])
    }
    if (!sortAsc) sorted.reverse()
    listRows = sorted.map(e => e.c)
    bsItems.innerHTML = ''
    bsItems.scrollTop = 0
    renderedCount = 0
    renderMoreRows()
  }
  updateSortChips()
  if (animate) replayAnim(bsItems, 'bs-pulse')
}

bsFilter.addEventListener('input', () => rebuildList(false))

for (const chip of sortChips) {
  chip.addEventListener('click', () => {
    const field = chip.dataset.sort as SortField
    if (field === sortField) {
      sortAsc = !sortAsc
    } else {
      sortField = field
      sortAsc = field === 'name'
    }
    rebuildList()
  })
}

// The rail stays on screen beside an open list, so it has to say which one is
// open. Cities is the button labelled 'all' in the markup.
function markNavOpen(view: 'all' | 'nations' | null) {
  for (const b of document.querySelectorAll<HTMLElement>('.bs-btn')) {
    b.classList.toggle('is-on', !!view && b.dataset.view === view)
  }
}

function openListView(mode: 'cities' | 'nations', filter = '') {
  listMode = mode
  bsTitle.textContent = mode === 'nations' ? 'Nations' : 'Cities'
  bsFilter.value = filter
  bsFilter.placeholder = 'Search'
  if (mode === 'nations') {
    sortField = 'population'
    sortAsc = false
  } else {
    sortField = 'name'
    sortAsc = true
  }
  // The list is its own surface now. On a desktop it opens beside the rail, so
  // the rail keeps its search and nav; on a phone it takes the footer's place,
  // so the rail has to get out of the way.
  bsHome.hidden = !onDesktop()
  bsList.hidden = false
  markNavOpen(mode === 'nations' ? 'nations' : 'all')
  hideSheet()
  rebuildList(false)
}

document.querySelector('.bs-btn[data-view="all"]')!.addEventListener('click', () => openListView('cities'))
document.querySelector('.bs-btn[data-view="nations"]')!.addEventListener('click', () => openListView('nations'))
document.querySelector('.bs-btn[data-view="share"]')!.addEventListener('click', () => shareView())
document.querySelector('.bs-btn[data-view="measure"]')!.addEventListener('click', () => startMeasure())

document.getElementById('bs-back')!.addEventListener('click', closeSheetList)

// --- Share view (permalink) ---

let openCityName: string | null = null
let openNationName: string | null = null

function syncHash() {
  let h: string
  if (openCityName) {
    h = 'city=' + encodeURIComponent(openCityName)
  } else if (openNationName) {
    h = 'nation=' + encodeURIComponent(openNationName)
  } else {
    const [cx, cy] = toPx(map.getCenter())
    h = `${map.getZoom()}/${cx}/${cy}`
  }
  history.replaceState(null, '', '#' + h)
}

const shareLabel = document.querySelector('.bs-btn[data-view="share"] .bs-btn-label') as HTMLElement
const shareCircle = document.querySelector('.bs-btn[data-view="share"] .bs-circle') as HTMLElement

function shareView() {
  syncHash()
  navigator.clipboard.writeText(location.href).then(
    () => {
      replayAnim(shareCircle, 'bs-bounce')
      flashShare('Copied!')
    },
    () => flashShare('Copy failed')
  )
}

function flashShare(text: string) {
  shareLabel.textContent = text
  replayAnim(shareLabel, 'bs-label-pop')
  setTimeout(() => {
    shareLabel.textContent = 'Share'
    replayAnim(shareLabel, 'bs-label-pop')
  }, 1400)
}

// --- Measure ---
// Lore scale: the 6000px map diagonal equals Earth's pole-to-pole distance
// (half the meridional circumference, 20,003.93 km) → ~2.357 km per px
const PX2KM = 20_003.93 / (6000 * Math.SQRT2)

let measuring = false
let measurePts: L.LatLng[] = []
let vertexMarkers: L.CircleMarker[] = []
let measureLine: L.Polyline | null = null
const measureLayer = L.layerGroup()
const measureBar = document.getElementById('measure-bar')!
const measureTotal = document.getElementById('measure-total')!
const mapEl = document.getElementById('map')!

function fmtKm(km: number): string {
  return km >= 100 ? Math.round(km).toLocaleString('en-US') + ' km' : km.toFixed(1) + ' km'
}

// Vertices are added incrementally (never rebuilt), so each dot's pop-in
// animation plays exactly once
function syncMeasureLine() {
  if (!measureLine) {
    measureLine = L.polyline([], {
      color: '#fff', weight: 2, dashArray: '6 6', opacity: 0.9, interactive: false,
    }).addTo(measureLayer)
  }
  measureLine.setLatLngs(measurePts)
  let km = 0
  for (let i = 1; i < measurePts.length; i++) {
    const a = measurePts[i - 1], b = measurePts[i]
    km += Math.hypot((b.lng - a.lng) * TILE_GRID / U, (b.lat - a.lat) * TILE_GRID / U) * PX2KM
  }
  measureTotal.textContent = measurePts.length < 2 ? 'Click the map' : fmtKm(km)
  replayAnim(measureTotal, 'bs-label-pop')
}

function addMeasurePoint(ll: L.LatLng) {
  measurePts.push(ll)
  vertexMarkers.push(L.circleMarker(ll, {
    radius: 4, color: '#fff', weight: 2, fillColor: '#0a84ff', fillOpacity: 1,
    interactive: false, className: 'measure-vertex',
  }).addTo(measureLayer))
  syncMeasureLine()
}

function startMeasure() {
  measuring = true
  // Clear every surface first. A place panel or a browse list left open would
  // sit over the map the tool is about to be used on, and the rail would still
  // highlight a tab for a list that is no longer there.
  closeCityPanel()
  closeSheetList()
  markNavOpen(null)
  hideSheet()
  measurePts = []
  vertexMarkers = []
  measureLine = null
  measureLayer.clearLayers()
  measureLayer.addTo(map)
  measureBar.classList.remove('mb-closing')
  measureBar.hidden = false
  measureTotal.textContent = 'Click the map'
  mapEl.classList.add('measure-mode')
}

function endMeasure() {
  measuring = false
  measurePts = []
  vertexMarkers = []
  measureLine = null
  measureLayer.clearLayers()
  map.removeLayer(measureLayer)
  measureBar.classList.add('mb-closing')
  measureBar.addEventListener('animationend', () => {
    measureBar.classList.remove('mb-closing')
    if (!measuring) measureBar.hidden = true
  }, { once: true })
  mapEl.classList.remove('measure-mode')
  showSheet()
}

map.on('click', (e: L.LeafletMouseEvent) => {
  if (!measuring) return
  addMeasurePoint(e.latlng)
})

document.getElementById('measure-undo')!.addEventListener('click', () => {
  if (!measurePts.length) return
  measurePts.pop()
  const m = vertexMarkers.pop()
  if (m) measureLayer.removeLayer(m)
  syncMeasureLine()
})

document.getElementById('measure-clear')!.addEventListener('click', () => {
  measurePts = []
  for (const m of vertexMarkers) measureLayer.removeLayer(m)
  vertexMarkers = []
  syncMeasureLine()
})

document.getElementById('measure-done')!.addEventListener('click', endMeasure)

// --- Deep links: #city=Name, #nation=Name, or #zoom/x/y ---

{
  const h = decodeURIComponent(location.hash.slice(1))
  if (h.startsWith('city=')) {
    const name = h.slice(5)
    const c = cities.find(x => x.name === name) ?? cities.find(x => norm(x.name) === norm(name))
    if (c) {
      if (c.x != null && c.y != null) focusOn(c.x, c.y, Math.max(map.getZoom(), 4))
      openCityPanel(c)
    }
  } else if (h.startsWith('nation=')) {
    const n = nationByName.get(norm(h.slice(7)))
    if (n) {
      const pts = mapAggFor(n).pts
      if (pts.length) {
        map.fitBounds(L.latLngBounds(pts).pad(0.2), {
          maxZoom: 5,
          paddingTopLeft: [sidebarWidth(), 0],
        })
      }
      openNationPanel(n)
    }
  } else {
    const m = h.match(/^(\d+(?:\.\d+)?)\/(-?\d+)\/(-?\d+)$/)
    if (m) {
      const z = Math.min(MAX_ZOOM, Math.max(2, parseFloat(m[1])))
      focusOn(parseInt(m[2]), parseInt(m[3]), z)
    }
  }
}

map.on('moveend', syncHash)

// --- Map rotation ---
// A placement aid: the map turns under a fixed UI so a diagonal coastline can be
// worked square to the screen. Nothing is re-projected. The whole map pane turns
// as one image, so cities, labels and borders all rotate with the terrain and
// every collision box the placement engine computed stays valid.

let bearing = 0

// The controls live inside the map container, which is about to be oversized and
// rotated. Moving them out to the body keeps them upright and at the viewport
// corners. Leaflet only ever appends to this element, so it does not care where
// the element itself sits in the DOM.
document.body.appendChild(mapEl.querySelector('.leaflet-control-container')!)

// A rotated rectangle leaves the viewport corners empty, so while turned the
// container grows to the square that covers the viewport at every angle: its own
// diagonal. Measured in px rather than a flat 142% because a wide viewport needs
// more than sqrt(2) of its shorter side, and the extra tiles are only paid for
// while the tool is in use.
function applyBearing() {
  if (bearing) {
    const w = window.innerWidth
    const h = window.innerHeight
    const d = Math.ceil(Math.hypot(w, h))
    mapEl.style.width = `${d}px`
    mapEl.style.height = `${d}px`
    mapEl.style.marginLeft = `${(w - d) / 2}px`
    mapEl.style.marginTop = `${(h - d) / 2}px`
  } else {
    mapEl.style.width = ''
    mapEl.style.height = ''
    mapEl.style.marginLeft = ''
    mapEl.style.marginTop = ''
  }
  mapEl.style.transform = bearing ? `rotate(${bearing}deg)` : ''
  map.invalidateSize({ animate: false })
}

// getBoundingClientRect on a rotated element reports the axis-aligned box, which
// is no use for a local coordinate — but rotation about the centre leaves that
// box centred on the element, so the centre is still exact. Turn the offset from
// it back through -bearing and the result is the unrotated container point.
const domToContainer = map.mouseEventToContainerPoint.bind(map)
map.mouseEventToContainerPoint = (e: MouseEvent) => {
  if (!bearing) return domToContainer(e)
  const r = mapEl.getBoundingClientRect()
  const dx = e.clientX - (r.left + r.width / 2)
  const dy = e.clientY - (r.top + r.height / 2)
  const rad = (-bearing * Math.PI) / 180
  const c = Math.cos(rad)
  const s = Math.sin(rad)
  return L.point(dx * c - dy * s + mapEl.offsetWidth / 2, dx * s + dy * c + mapEl.offsetHeight / 2)
}

// Leaflet pans by adding the raw screen delta to the map pane, but the pane is
// inside the rotated element, so an untouched delta sends the map off at an
// angle to the cursor. Turning the delta back through -bearing makes the map
// follow the hand again.
const draggable = (map as unknown as { dragging: { _draggable: any } }).dragging._draggable
const moveDraggable = draggable._updatePosition.bind(draggable)
draggable._updatePosition = function (this: any) {
  if (bearing) {
    const rad = (-bearing * Math.PI) / 180
    const c = Math.cos(rad)
    const s = Math.sin(rad)
    const o = this._newPos.subtract(this._startPos)
    this._newPos = this._startPos.add(L.point(o.x * c - o.y * s, o.x * s + o.y * c))
  }
  moveDraggable()
}

const STEP = 15

function setBearing(deg: number) {
  bearing = ((deg % 360) + 360) % 360
  applyBearing()
}

const RotateControl = L.Control.extend({
  options: { position: 'topright' as L.ControlPosition },
  onAdd() {
    const c = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-rotate')
    const button = (label: string, title: string, fn: () => void) => {
      const a = L.DomUtil.create('a', '', c)
      a.href = '#'
      a.textContent = label
      a.title = title
      L.DomEvent.on(a, 'click', (e: Event) => {
        L.DomEvent.stop(e)
        fn()
      })
      return a
    }
    // Two buttons only. STEP divides 360 exactly, so stepping either way always
    // lands back on true north without needing a reset button to get there.
    button('↺', `Rotate ${STEP}° counter-clockwise`, () => setBearing(bearing - STEP))
    button('↻', `Rotate ${STEP}° clockwise`, () => setBearing(bearing + STEP))
    L.DomEvent.disableClickPropagation(c)
    return c
  },
})

new RotateControl().addTo(map)
window.addEventListener('resize', () => bearing && applyBearing())

// --- Research stations ---
//
// Points of interest for Hyperborea and Tartarus, which hold no cities at all —
// nothing lives at either pole, so a station is the only thing there is to mark.
// They are their own layer rather than cities with a flag: a station has no
// population, no GDP and no tier, and every one of those drives how a city is
// drawn, ranked and culled.

// Stations arrive at the same moment the continent names hand over to the nation
// names — the zoom where the map stops being an overview and starts naming
// places. Derived from the nation band rather than written as a number, so
// retuning that band carries the stations with it.
const STATION_MIN_ZOOM = Math.min(
  ...labelDefs.filter(d => d.type === 'nation' || d.type === 'colony').map(d => d.minZoom)
)
// The label matches a small city exactly — same family, weight and size — so a
// station sits in the same register as everything around it.
//
// The marker cannot. A small city dot comes out at 4.8px, and at that size the
// atom's strokes land at a third of a pixel and vanish, which is why the icon
// looked empty. 11px is the point where the nucleus and both orbits resolve.
// This is the knob if it wants to be bigger or smaller.
const STATION_TIER = cityTier(500_000)
const STATION_SCALE = 0.8
const STATION_FS = Math.round(STATION_TIER.fontSize * STATION_SCALE)
const STATION_D = 11
// Wraps past this. The CSS keeps nowrap and renders the breaks this decides, so
// the collision box and the drawn text can never disagree about the line count.
const STATION_MAX_W = 62
const STATION_CHAR = 0.62 // same advance the city labels measure with

const stationLayer = L.layerGroup().addTo(map)
layerCtrl.addOverlay(stationLayer, 'Research Stations')

const stationMarkers = new Map<Station, L.Marker>()

// Greedy wrap on the same character advance the collision box is measured with,
// so the box and the rendered text agree on how many lines there are
function wrapStation(name: string): string[] {
  const charW = STATION_FS * STATION_CHAR
  const lines: string[] = []
  let line = ''
  for (const word of name.split(' ')) {
    const next = line ? `${line} ${word}` : word
    if (line && next.length * charW > STATION_MAX_W) {
      lines.push(line)
      line = word
    } else {
      line = next
    }
  }
  if (line) lines.push(line)
  return lines
}

// A lab flask on a light blue disc, in the same -3 -3 6 6 viewBox the city
// markers use so the two share a coordinate system.
//
// The flask is one filled path rather than an outline. At 11px a stroked glyph
// lands near a third of a pixel and disappears — which is exactly what went
// wrong with the atom — whereas a solid silhouette still reads. Every dimension
// is chosen for what it becomes at STATION_D; that constant is the knob.
function stationIcon(station: Station, dir: 'right' | 'left'): L.DivIcon {
  const r = STATION_D / 2
  // Kept inside r=2.15 so the base clears the disc's edge — at the full 1.8
  // half-width the corners were being clipped by the circle.
  const flask =
    'M-0.55-1.62 L0.55-1.62 L0.55-1.32 L0.34-1.32 L0.34-0.4 ' +
    'L1.55 1.3 L1.55 1.56 L-1.55 1.56 L-1.55 1.3 L-0.34-0.4 L-0.34-1.32 L-0.55-1.32 Z'
  const svg =
    `<svg width="${STATION_D}" height="${STATION_D}" viewBox="-3 -3 6 6" xmlns="http://www.w3.org/2000/svg">` +
    `<circle r="2.6" fill="#5860be" stroke="#b9c3f2" stroke-width="0.5"/>` +
    `<path d="${flask}" fill="#fff"/>` +
    `</svg>`
  const gap = r + 3
  const side = dir === 'right' ? `left:${r + gap}px` : `right:${r + gap}px`
  const align = dir === 'right' ? 'left' : 'right'
  return L.divIcon({
    className: 'station-icon',
    html: svg + `<span class="station-label" style="${side};text-align:${align}">${wrapStation(station.name).join('<br>')}</span>`,
    iconSize: [STATION_D, STATION_D],
    iconAnchor: [r, r],
  })
}

// Right unless it collides, then left — the same preference the city labels use,
// minus the future-cost weighing, since nothing else competes for space out here
function updateStations() {
  for (const [, m] of stationMarkers) stationLayer.removeLayer(m)
  stationMarkers.clear()
  if (!map.hasLayer(stationLayer) || map.getZoom() < STATION_MIN_ZOOM) return

  const s = scaleAt(map.getZoom())
  const taken: Box[] = []
  for (const station of stations) {
    if (station.x == null || station.y == null) continue
    const lines = wrapStation(station.name)
    const w = Math.min(STATION_MAX_W, Math.max(...lines.map(l => l.length * STATION_FS * STATION_CHAR)))
    const h = lines.length * STATION_FS * 1.25
    const px0 = station.x * s
    const py = station.y * s
    const gap = STATION_D / 2 + 4

    const cands: { dir: 'right' | 'left'; box: Box }[] = [
      { dir: 'right', box: { x: px0 + gap, y: py - h / 2, w, h } },
      { dir: 'left', box: { x: px0 - gap - w, y: py - h / 2, w, h } },
    ]
    const hit = cands.find(c => !taken.some(t => boxesOverlap(c.box, t))) ?? cands[0]
    taken.push(hit.box)

    const m = L.marker(px(station.x, station.y), {
      icon: stationIcon(station, hit.dir),
      draggable: DEV,
    }).addTo(stationLayer)
    if (DEV) {
      m.on('dragend', () => {
        const [nx, ny] = toPx(m.getLatLng())
        station.x = nx
        station.y = ny
        saveStationProgress()
        updateStations()
        statusEl.textContent = `${station.name} → ${nx}, ${ny}`
        statusEl.className = 'status-done'
      })
    }
    stationMarkers.set(station, m)
  }
}

const STATION_KEY = 'avium-station-coords'

function saveStationProgress() {
  markDirty()
  const coords: Record<string, [number, number]> = {}
  for (const p of stations) if (p.x != null && p.y != null) coords[p.name] = [p.x, p.y]
  localStorage.setItem(STATION_KEY, JSON.stringify(coords))
}

function loadStationProgress() {
  const raw = localStorage.getItem(STATION_KEY)
  if (!raw) return
  const coords: Record<string, [number, number]> = JSON.parse(raw)
  for (const p of stations) if (coords[p.name]) [p.x, p.y] = coords[p.name]
}

loadStationProgress()
updateStations()
map.on('zoomend', updateStations)
map.on('overlayadd overlayremove', (e) => {
  if ((e as L.LayersControlEvent).layer === stationLayer) updateStations()
})

// --- Label and station editing (dev) ---
//
// Everything here mutates the in-memory arrays and the localStorage mirror only.
// The JSON files change when Save is pressed and at no other moment: an edit
// session is a draft until it is written out, which is why the button carries a
// dot the moment anything is touched.

let dirty = false

const editRow = document.getElementById('edit-row') as HTMLElement
const renameInput = document.getElementById('place-rename') as HTMLInputElement
const kindSelect = document.getElementById('place-kind') as HTMLSelectElement
const deleteBtn = document.getElementById('place-delete') as HTMLButtonElement
const saveBtn = document.getElementById('place-save') as HTMLButtonElement

// A label's zoom band belongs to its type, not to the label. Picking "sea" from
// the dropdown used to change only the styling, leaving the new label on the
// nation band it was created with — so it looked like a sea and then vanished at
// z5.5 with the nation names. The band travels with the type now.
const TYPE_BAND: Record<string, { minZoom: number; maxZoom?: number }> = {
  continent: { minZoom: 2.5, maxZoom: 3 },
  ocean: { minZoom: 2.5 },
  sea: { minZoom: 3.5 },
  nation: { minZoom: 3.5, maxZoom: 5 },
  colony: { minZoom: 3.5, maxZoom: 5 },
}

const LABEL_KINDS = Object.keys(TYPE_BAND)

function setLabelType(def: LabelDef, type: string) {
  const band = TYPE_BAND[type]
  if (!band) return
  def.type = type
  def.minZoom = band.minZoom
  // Absent means uncapped — water runs to whatever the top zoom is
  if (band.maxZoom == null) delete def.maxZoom
  else def.maxZoom = band.maxZoom
}

function markDirty() {
  dirty = true
  saveBtn.textContent = 'Save •'
  saveBtn.classList.add('pp-dirty')
}

// The edit row serves labels and stations both. A station has no type to choose,
// so the kind selector is hidden for one and populated for the other.
function syncEditRow() {
  const target = selectedLabel ?? selectedStation
  // Never leave the button armed across a change of selection
  disarmDelete()
  editRow.hidden = !target
  if (!target) return
  const isLabel = selectedLabel != null
  renameInput.value = isLabel ? selectedLabel!.text : selectedStation!.name
  kindSelect.hidden = !isLabel
  if (isLabel) {
    kindSelect.innerHTML = LABEL_KINDS.map(
      k => `<option value="${k}"${k === selectedLabel!.type ? ' selected' : ''}>${k}</option>`
    ).join('')
  }
}

function selectStation(p: Station) {
  selectedStation = p
  selectedLabel = null
  selectedCity = null
  setSpanTarget(null)
  resultsList.innerHTML = ''
  searchInput.value = p.name
  statusEl.className = 'status-active'
  statusEl.textContent = `Click the map to place ${p.name}`
  syncEditRow()
  if (p.x != null && p.y != null) focusOn(p.x, p.y, Math.max(map.getZoom(), STATION_MIN_ZOOM))
}

renameInput.addEventListener('input', () => {
  const name = renameInput.value
  if (selectedLabel) {
    selectedLabel.text = name
    refreshLabel(selectedLabel)
    saveLabelProgress()
  } else if (selectedStation) {
    selectedStation.name = name
    saveStationProgress()
    updateStations()
  } else {
    return
  }
  markDirty()
  updateCount()
})

kindSelect.addEventListener('change', () => {
  if (!selectedLabel) return
  setLabelType(selectedLabel, kindSelect.value)
  refreshLabel(selectedLabel)
  saveLabelProgress()
  markDirty()
})

// Two clicks on the button itself rather than a native confirm(). A browser that
// has had "prevent additional dialogs" triggered returns false from confirm()
// forever, with no dialog and no error — the button just stops working, which is
// indistinguishable from it being unwired. This cannot fail that way, and it
// keeps the interaction in the panel.
let armed = false
let armedTimer = 0

function disarmDelete() {
  armed = false
  clearTimeout(armedTimer)
  deleteBtn.textContent = 'Delete'
  deleteBtn.classList.remove('is-armed')
}

deleteBtn.addEventListener('click', () => {
  const name = selectedLabel?.text ?? selectedStation?.name
  if (!name) {
    statusEl.textContent = 'Nothing selected'
    statusEl.className = ''
    return
  }

  if (!armed) {
    armed = true
    deleteBtn.textContent = 'Sure?'
    deleteBtn.classList.add('is-armed')
    // Disarms itself, so a stray first click can't leave the button primed for
    // a real delete minutes later
    armedTimer = window.setTimeout(disarmDelete, 3000)
    return
  }
  disarmDelete()
  if (selectedLabel) {
    const m = labelMarkers.get(selectedLabel)
    if (m) {
      labelLayer.removeLayer(m)
      labelMarkers.delete(selectedLabel)
    }
    labelDefs.splice(labelDefs.indexOf(selectedLabel), 1)
    selectedLabel = null
    saveLabelProgress()
    invalidatePlacements()
    updateCities()
  } else if (selectedStation) {
    stations.splice(stations.indexOf(selectedStation), 1)
    selectedStation = null
    saveStationProgress()
    updateStations()
  }
  setSpanTarget(null)
  syncEditRow()
  markDirty()
  updateCount()
  searchInput.value = ''
  statusEl.textContent = `Deleted ${name}`
  statusEl.className = 'status-done'
})

document.getElementById('place-add-label')!.addEventListener('click', () => {
  // Born unplaced, so it lands in the Unassigned panel rather than silently
  // appearing at some default spot on the map
  const def: LabelDef = { text: 'New Label', type: 'nation', x: null, y: null, minZoom: 0 }
  setLabelType(def, 'nation')
  labelDefs.push(def)
  markDirty()
  updateCount()
  selectLabel(def)
  renameInput.focus()
  renameInput.select()
})

document.getElementById('place-add-station')!.addEventListener('click', () => {
  const station: Station = { name: 'New Station', continent: '', x: null, y: null }
  stations.push(station)
  markDirty()
  selectStation(station)
  renameInput.focus()
  renameInput.select()
})

function download(name: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  a.click()
  URL.revokeObjectURL(a.href)
}

// Straight into src/data via the dev server, so a save is done when the button
// says it is. The download path is the fallback for a built preview, where the
// middleware does not exist — better a file in Downloads than a silent no-op.
async function writeData(file: string, data: unknown): Promise<boolean> {
  try {
    const res = await fetch('/__save', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ file, data }),
    })
    return res.ok
  } catch {
    return false
  }
}

saveBtn.addEventListener('click', async () => {
  saveBtn.disabled = true
  statusEl.textContent = 'Saving…'
  statusEl.className = 'status-active'

  const files: [string, unknown][] = [
    ['cities.json', cities],
    ['labels.json', labelDefs],
    ['stations.json', stations],
  ]
  const written = await Promise.all(files.map(([f, d]) => writeData(f, d)))
  const failed = files.filter((_, i) => !written[i])
  for (const [f, d] of failed) download(f, d)

  saveBtn.disabled = false
  dirty = false
  saveBtn.textContent = 'Save'
  saveBtn.classList.remove('pp-dirty')
  statusEl.className = 'status-done'
  statusEl.textContent = failed.length
    ? `Downloaded ${failed.map(f => f[0]).join(', ')} — dev server not writing`
    : `Saved ${files.length} files to src/data`
})

// Losing an edit session to a stray refresh is the one thing localStorage cannot
// protect against, because the JSON on disk is what the next load reads
window.addEventListener('beforeunload', (e) => {
  if (!dirty) return
  e.preventDefault()
  e.returnValue = ''
})

// --- Placer tabs ---
//
// Cities and territory names are different jobs: one is a long grind through a
// list of 1747, the other is a handful of names being shaped. Splitting them
// means the search, the results, the Unassigned list and the toolbar can each
// answer for one job instead of mixing both. Save spans them, because a session
// usually touches both and writing one file without the other is how the two
// drift apart.


const tabButtons = [...document.querySelectorAll<HTMLButtonElement>('.pp-tab')]

function setTab(next: PlacerTab, focus = true) {
  tab = next
  for (const b of tabButtons) b.classList.toggle('is-on', b.dataset.tab === next)
  for (const el of document.querySelectorAll<HTMLElement>('.pp-toolbar [data-for]')) {
    el.hidden = el.dataset.for !== next
  }
  searchInput.placeholder = next === 'cities' ? 'Search cities…' : 'Search labels and stations…'
  // Clearing is the honest move: a selection made on the other tab is no longer
  // reachable, and leaving it live means the next map click places something the
  // panel is no longer showing
  selectedCity = null
  selectedLabel = null
  selectedStation = null
  setSpanTarget(null)
  syncEditRow()
  searchInput.value = ''
  renderResults()
  statusEl.textContent = ''
  statusEl.className = ''
  updateUnassigned()
  if (focus) searchInput.focus()
}

for (const b of tabButtons) {
  b.addEventListener('click', () => setTab(b.dataset.tab as PlacerTab))
}

// No focus on the initial call: the panel is hidden outside ?dev, and focusing
// an input inside it would take the caret away from the page for everyone else
setTab('cities', false)
