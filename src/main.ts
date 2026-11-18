import L from 'leaflet'
// Both stylesheets are linked from index.html — see the note there
import citiesData from './data/cities.json'
import tileVersions from './data/tiles.json'
import labelsData from './data/labels.json'
import waterFitData from './data/water.json'
// Vite fingerprints and emits it; the element lives in index.html so the column
// has its header before any script runs.
import bannerUrl from './assets/banner.png'
import politicalThumb from './assets/map-modes/political.png'
import zonesThumb from './assets/map-modes/zones.png'
import hybridThumb from './assets/map-modes/hybrid.png'
import terrainThumb from './assets/map-modes/terrain.png'
import stationsData from './data/stations.json'
import nationsTsv from './data/nations.tsv?raw'
import areasData from './data/areas.json'
import zonesData from './data/zones.json'
import { icAt as icAtReal, icNow, rateNow, realAt } from './ictime'
import { talopedia, talopediaSlug, talopediaUrl, type TalopediaEntry } from './data/talopedia'

// --- Dev mode ---

const DEV = new URLSearchParams(window.location.search).has('dev')

// Strip diacritics so "Chukyo" matches "Chūkyō" etc.
const norm = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

// --- Constants ---

const TILE_GRID = 8192
const CONTENT = 6000
const U = 256
// Six user levels past the tile resolution. Native detail stops at z5, so the
// top of the range is upscaled and will look soft — the point of it is spacing,
// not detail: cities the placer drops for want of room at one level have room
// at the next, so the last few crowded names resolve instead of never rendering.
const MAX_ZOOM = 8

// Lore scale: the 6000px map diagonal equals Earth's pole-to-pole distance
// (half the meridional circumference, 20,003.93 km) → ~2.357 km per px. Up here
// with the other constants rather than down in Measure, because the planet's
// radius below is built from it.
const PX2KM = 20_003.93 / (6000 * Math.SQRT2)

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
//
// scripts/coords.mjs carries the same projection, to write src/data/coordinates.tsv
// for anything that needs a place's position without running the map. It is a
// Node script and cannot import this, so a change here has to be made there too.
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

// Avium is a sphere and this is a projection of it, so a map pixel is not a fixed
// amount of ground and cannot be measured as though it were. The graticule runs
// on the diagonals: the meridian diagonal carries 180° of latitude and the
// equator diagonal carries 360° of longitude, which makes the equator twice the
// scale of the meridian, and the squeeze toward the poles is linear where the
// sphere's own is a cosine. Measuring in flat pixels loses 61% of the planet.
//
// PX2KM is the meridian scale, so the half-diagonal is a quarter of the
// circumference and the radius falls out of it: 6367km, an Earth.
const PLANET_R = (GEO_R * PX2KM) / (Math.PI / 2)
const D2R = Math.PI / 180

// Ground area of a square of `side` map pixels centred on (x, y).
//
// dA = Rp²·cosφ·dφ·dλ, and the projection gives dφ = 90·dv/GEO_R and
// dλ = 180·du/halfWidth, with du·dv = dx·dy because the diagonal axes are just a
// rotation. Writing t for halfWidth/GEO_R, the latitude is 90(1-t) degrees and so
// cosφ is exactly sin(tπ/2) — which keeps the poles finite, where cosφ and
// halfWidth both reach zero and the naive ratio would not survive.
//
// Summed over the whole map this comes to 4πRp². That is the check that it is
// the right expression, and it is worth re-running if any of this ever moves.
const AREA_K = (PLANET_R * PLANET_R * Math.PI * Math.PI) / (2 * GEO_R * GEO_R)
function pxArea(x: number, y: number, side: number): number {
  const t = 1 - Math.abs(axes(x, y).v) / GEO_R
  if (t <= 0) return 0
  return (AREA_K * Math.sin((t * Math.PI) / 2) * side * side) / t
}

// A straight line on this projection is not a great circle, so a path is measured
// leg by leg between the points actually clicked.
function geoKm(a: Geo, b: Geo): number {
  const p1 = a.lat * D2R
  const p2 = b.lat * D2R
  const h =
    Math.sin((p2 - p1) / 2) ** 2 +
    Math.cos(p1) * Math.cos(p2) * Math.sin(((b.lon - a.lon) * D2R) / 2) ** 2
  return 2 * PLANET_R * Math.asin(Math.min(1, Math.sqrt(h)))
}

// The poles sit in the top-left and bottom-right corners and the equator runs
// corner to corner the other way, so both axes are named for the diagonal they
// actually run along: NW toward the top-left pole and SE toward the bottom-right,
// NE toward the top-right and SW toward the bottom-left.
function fmtGeo(g: Geo, places = 2): string {
  const lat = g.lat >= 0 ? 'NW' : 'SE'
  const lon = g.lon >= 0 ? 'NE' : 'SW'
  return `${Math.abs(g.lat).toFixed(places)}°${lat} ${Math.abs(g.lon).toFixed(places)}°${lon}`
}

// --- Time zones: data and clocks ---
//
// The layer itself is further down, under Time zones and daylight.

const ZONES = zonesData as {
  nations: Record<string, number[]>
  home: Record<string, number[]>
  cities: Record<string, number>
}
const ZONE_LOOKUP = 1500
const HOUR = 3_600_000

function fmtZone(z: number): string {
  return z ? `UTC${z > 0 ? '+' : '−'}${Math.abs(z)}` : 'UTC'
}

function solarZone(x: number, y: number): number {
  const z = Math.round(toGeo(x, y).lon / 15)
  return z === -12 ? 12 : z
}

function cityZone(c: City): number {
  return ZONES.cities[`${c.name}|${c.nation}`] ?? (c.x != null && c.y != null ? solarZone(c.x, c.y) : 0)
}

// Every zone a nation holds land in, colonies included (its panel lists these)
function nationZones(name: string): number[] {
  return ZONES.nations[name] ?? []
}

const two = (n: number) => String(n).padStart(2, '0')
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function hhmm(z: number, ms = icNow()): string {
  const d = new Date(ms + z * HOUR)
  return `${two(d.getUTCHours())}:${two(d.getUTCMinutes())}`
}

// A city's clock, live, in a pill at the end of its coordinates line: the time,
// then the day there and the offset
function timeLine(z: number, ms = icNow()): string {
  const d = new Date(ms + z * HOUR)
  return `<b>${hhmm(z, ms)}</b> ${WEEKDAYS[d.getUTCDay()]} · ${fmtZone(z)}`
}

// --- Map ---

// Leaflet rounds each tile level's offset to a whole pixel. At a whole zoom the offset is whole already; at a half step
// every layer rounds its own, and layers cut at different zooms (borders at 5, rivers and relief at 6), or whose level
// was made at a different moment, land up to 0.7px apart (measured). That was the hairline of bare ground down one side
// of every coast and border at 5.5, 6.5 and 7.5. Left unrounded, every layer lands on the same spot.
;(L.GridLayer as unknown as { include(o: object): void }).include({
  _setZoomTransform(
    this: { _map: L.Map & { _getNewPixelOrigin(c: L.LatLng, z: number): L.Point } },
    level: { el: HTMLElement; origin: L.Point; zoom: number },
    center: L.LatLng,
    zoom: number
  ) {
    const scale = this._map.getZoomScale(zoom, level.zoom)
    L.DomUtil.setTransform(level.el, level.origin.multiplyBy(scale).subtract(this._map._getNewPixelOrigin(center, zoom)), scale)
  },
})

const contentBounds = L.latLngBounds(px(0, CONTENT), px(CONTENT, 0))

const map = L.map('map', {
  crs: L.CRS.Simple,
  minZoom: 2,
  maxZoom: MAX_ZOOM,
  // No snap: the zoom rests wherever the wheel leaves it (Smooth zoom, at the
  // foot of this file). A click on + or - is still half a level.
  zoomSnap: 0,
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

// The zoom is continuous (see Smooth zoom, at the foot of this file): it rests at
// any fraction, not on half levels. What is drawn follows it as closely as is
// worth working out. Sizes are solved from the zoom itself. Which names are on is
// worked out per eighth of a level, the eighth at or below, which is the one whose
// spacing is guaranteed to hold at any larger scale; at that grain a zoom in
// brings names on a few at a time, where half levels brought them on in batches
// (the user: "we don't have true smooth scrolling because labels and everything
// still follow stages").
const ZOOM_STEP = 0.125
const stepZoom = (z: number) => Math.floor(z / ZOOM_STEP + 1e-6) * ZOOM_STEP
const quarterStep = (z: number) => Math.round(z * 4) / 4

// A marker that leaves its z-index alone. Leaflet stacks markers by how far down
// the screen they are and rewrites every one's z-index each time it moves them,
// which during a zoom is every frame: several hundred stacking changes for names
// that never overlap in the first place. These take their order from the
// stylesheet instead (area names under stations under cities).
const FlatMarker = L.Marker.extend({ _updateZIndex() {} }) as unknown as new (
  latlng: L.LatLngExpression,
  options?: L.MarkerOptions
) => L.Marker

// How much of the map the sidebar hides. Zero on a phone, where the sheet
// covers the bottom instead and the map is free to use its own centre.
function sidebarWidth(): number {
  if (!window.matchMedia('(min-width: 900px)').matches) return 0
  const css = getComputedStyle(document.documentElement)
  const rail = parseFloat(css.getPropertyValue('--rail')) || 0
  // The second column only covers the map while it is open, so it only counts
  // toward the offset then — otherwise every jump would land 190px off centre.
  // A place panel and a list (Cities, Nations, Explore...) share that column.
  const open =
    !(document.getElementById('city-panel') as HTMLElement).hidden ||
    !(document.getElementById('bs-list') as HTMLElement).hidden
  const panel = open ? parseFloat(css.getPropertyValue('--panel')) || 0 : 0
  return rail + panel
}

// How much of the map the sidebar covered when the view was last lined up with
// it. When the column opens or closes the visible map narrows or widens, and
// the view slides by half the difference so what was in the middle stays there
// instead of ending up under the column.
let lastCover = 0
// While that slide runs the city labels are not re-placed frame by frame (the
// pan is half a column, nothing worth streaming in) and the columns drop their
// blur, which would otherwise re-blur the moving map under them every frame.
// Both come back when the slide ends.
let coverPanning = false
let coverTimer = 0
function syncCover() {
  const w = sidebarWidth()
  if (w === lastCover) return
  coverPanning = true
  document.body.classList.add('col-moving')
  clearTimeout(coverTimer)
  coverTimer = window.setTimeout(() => {
    coverPanning = false
    document.body.classList.remove('col-moving')
    updateCities()
  }, 340)
  map.panBy([-(w - lastCover) / 2, 0], { duration: 0.25 })
  lastCover = w
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
  // Already placed for the column as it is now, so there is nothing to slide
  lastCover = sidebarWidth()
}

// --- Image layers ---

const imgBounds = L.latLngBounds(px(0, CONTENT), px(CONTENT, 0)) as L.LatLngBoundsExpression

// Full-res 6000px layers served as 256px tiles (native detail up to z5,
// upscaled beyond) — only the tiles in view are ever loaded.
// sharp's google layout writes {z}/{y}/{x} (row/column) — using {z}/{x}/{y}
// here is what produced the "scrambled" transposed map previously.
// The base is tiled too: an imageOverlay base rounds its position through a
// different code path than tile layers, drifting 1-2px at half-step zooms.
function tiledLayer(
  name: string,
  pane = 'overlayPane',
  // The terrain layers are drawn at 12000px, one zoom level finer than the rest,
  // and the two opaque ones are WebP: shaded relief is the one thing here that
  // PNG cannot make small.
  { ext = 'png', maxNative = 5, zIndex = 1 } = {}
): L.TileLayer {
  // Versioned per layer, from the signature scripts/tile.mjs stamps its output
  // with. Tile paths never change, so without this a browser keeps serving the
  // copy it cached the first time and a retiled border only reaches the reader
  // on the zoom levels their cache happened to drop.
  const v = (tileVersions as Record<string, string>)[name]
  return L.tileLayer(`tiles/${name}/{z}/{y}/{x}.${ext}` + (v ? `?v=${v}` : ''), {
    maxNativeZoom: maxNative,
    zIndex,
    maxZoom: MAX_ZOOM,
    bounds: contentBounds,
    pane,
    // Three of these layers request tiles together, and a zoom is exactly when
    // the frame budget is tightest — the markers are being rebuilt in the same
    // moment. Leaflet scales what it already has for the length of the animation
    // and fetches once it settles. keepBuffer is left at its default: 1 saves
    // memory and 3 cuts pop-in when panning, and neither is obviously right.
    updateWhenZooming: false,
  })
}

const baseLayer = tiledLayer('base', 'tilePane').addTo(map)

// Where the world stops. The ocean tile and the page behind it are both dark, so
// without this the map has no visible edge at all when zoomed out.
L.rectangle(contentBounds, {
  color: 'rgba(255,255,255,0.5)',
  weight: 1,
  fill: false,
  interactive: false,
}).addTo(map)
const bordersLayer = tiledLayer('borders').addTo(map)
// Drawn at 12000px like the terrain it runs through, so it stays a line one level deeper
const riversLayer = tiledLayer('rivers', 'overlayPane', { maxNative: 6, zIndex: 3 }).addTo(map)
// Over the border tint, under the rivers
const contoursLayer = tiledLayer('contours', 'overlayPane', { ext: 'webp', maxNative: 6, zIndex: 2 })

// Pangaea reference overlay (dev-only toggle in layer control)
let pangaeaLayer: L.ImageOverlay | null = null
if (DEV) {
  const pangaeaImg = new Image()
  pangaeaImg.src = 'overlays/pangaea.png'
  pangaeaImg.onload = () => {
    pangaeaLayer = L.imageOverlay('overlays/pangaea.png', imgBounds, { opacity: 0.4 })
  }
}

// --- Layer control ---
//
// There is none: the Map sheet further down owns every layer, with the map
// modes as tiles and the overlays as switches. Its button goes into the stack
// here so it sits between zoom and rotate, where the layers button was.
const mapBtn = L.DomUtil.create('a', 'map-btn') as HTMLAnchorElement
mapBtn.href = '#'
mapBtn.setAttribute('role', 'button')
mapBtn.setAttribute('aria-label', 'Map')
mapBtn.title = 'Map'
new (L.Control.extend({
  onAdd() {
    const c = L.DomUtil.create('div', 'leaflet-bar leaflet-control map-btn-ctl')
    c.appendChild(mapBtn)
    L.DomEvent.disableClickPropagation(c)
    return c
  },
}))({ position: 'topright' }).addTo(map)

// --- Settings ---
//
// What the map shows, as one record: which of the three maps it is, and which
// switches are on. A map can rule a switch out (Time Zones has no borders,
// only Terrain has contour lines, only Time Zones has day and night) without touching it, so going back to a map
// brings back exactly what was on before. Borders are kept twice, once for
// Terrain and once for the rest: Terrain starts with them off and the switch
// still works there, and turning them on or off on one map leaves the other as
// it was. Read during the first render, so it has to be resolved before any of
// it runs.

// 'hybrid' is the map the sheet calls Satellite: the name changed (17 Nov 2026),
// and the id stayed so that saved settings, the tiles and the stylesheet did not
// all have to move with it
type MapMode = 'hybrid' | 'political' | 'terrain' | 'zones'
const MAP_MODES: MapMode[] = ['hybrid', 'political', 'terrain', 'zones']

interface Settings {
  mode: MapMode
  relief: boolean
  daylight: boolean
  borders: boolean
  terrainBorders: boolean
  hybridBorders: boolean
  rivers: boolean
  contours: boolean
  territories: boolean
  water: boolean
  cities: boolean
  stations: boolean
}

const SETTINGS_KEY = 'avium-settings'
// Bumped when a default changes and saved entries should take it: 2 (16 Nov
// 2026) turned contour lines off by default, and every entry before it had
// saved the old default of on; 3 (16 Nov 2026) made Hybrid the default map and
// dropped Terrain, which came back the next day with nothing to bump for
const SETTINGS_VERSION = 3

const settings: Settings = {
  mode: 'hybrid',
  relief: true,
  daylight: false,
  borders: true,
  terrainBorders: false,
  hybridBorders: true,
  rivers: true,
  contours: false,
  territories: true,
  water: true,
  cities: true,
  stations: true,
}

// Key by key and typed, so a stale or hand-edited entry cannot introduce a
// non-boolean that then reads as truthy forever. Relief and Day & Night were
// maps of their own until 15 Nov 2026 and Night Lights was a third; an entry
// left on Relief comes back as the political map with Relief on, one on Day &
// Night as Time Zones with it on, and one on Night Lights as the political map.
try {
  const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? '{}')
  const v = typeof saved?.v === 'number' ? saved.v : 0
  const old = v < 2
  for (const k of Object.keys(settings) as (keyof Settings)[]) {
    if (old && k === 'contours') continue
    if (k !== 'mode' && typeof saved?.[k] === 'boolean') settings[k] = saved[k]
  }
  // Before 3 the political map was the default, so a saved one was rarely a choice
  if (MAP_MODES.includes(saved?.mode) && !(v < 3 && saved.mode === 'political')) settings.mode = saved.mode
  else if (saved?.mode === 'relief') settings.relief = true
  else if (saved?.mode === 'daylight') {
    settings.mode = 'zones'
    settings.daylight = true
  }
  // Older still: night as a switch that overwrote the others and kept their
  // old values aside
  if (saved?.night === true) {
    const p = saved.preNight
    if (p && typeof p === 'object') {
      for (const k of ['territories', 'water', 'stations', 'borders', 'rivers'] as const) {
        if (typeof p[k] === 'boolean') settings[k] = p[k]
      }
    }
  }
} catch {
  // unreadable entry, defaults stand
}

function saveSettings() {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...settings, v: SETTINGS_VERSION }))
  } catch {
    // private mode or a full quota; the session still works, it just forgets
  }
}

// What each map leaves room for. Time Zones is the map as a backdrop for the
// clocks: its colours cover every pixel, so the ground and the lines go, and
// the names stay because they carry each nation's clock. Day and night belongs
// to the clocks, contour lines to the two maps of the ground itself.
const modeAllows = {
  relief: (m: MapMode) => m === 'political' || m === 'terrain',
  daylight: (m: MapMode) => m === 'zones',
  borders: (m: MapMode) => m !== 'zones',
  rivers: (m: MapMode) => m !== 'zones',
  contours: (m: MapMode) => m === 'terrain' || m === 'hybrid',
  territories: (_m: MapMode) => true,
  water: (_m: MapMode) => true,
  cities: (_m: MapMode) => true,
  stations: (_m: MapMode) => true,
}

// The setting a switch stands for on the current map: only Borders has more than one
type Switch = keyof typeof modeAllows
const settingKey = (k: Switch): keyof Settings =>
  k !== 'borders' ? k : settings.mode === 'terrain' ? 'terrainBorders' : settings.mode === 'hybrid' ? 'hybridBorders' : k

function shows(k: Switch): boolean {
  return (settings[settingKey(k)] as boolean) && modeAllows[k](settings.mode)
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
  // Country labels are sized directly in screen px and hold it at every zoom.
  // A span says how much ground a name covers, which is the right question for a
  // sea and the wrong one for a country: it made Rudania 70px and thirty-three
  // others 9px, when what an atlas does is set every country at one of two close
  // sizes and let the map say how big it is.
  size?: number
}


const labelDefs = labelsData as LabelDef[]
const labelMarkers = new Map<LabelDef, L.Marker>()
const labelLayer = L.layerGroup().addTo(map)

// Every label is sized to the area it names rather than to a fixed px value,
// which is the whole trick to reading well at every zoom: a fixed size swamps
// a small nation when zoomed out and vanishes on a continent when zoomed in.
// The two sizes a country name comes in, in screen px. Close together on
// purpose: the reference sets a large country and a small one at nearly the same
// size, and lets position and territory carry the difference.
const LABEL_SIZE = { major: 13, minor: 11, islet: 9 }

// Longest a line of a wrapped name wants to be, in characters, and the most
// lines it may take. A country name too long for its land is what an atlas
// breaks over two lines rather than shrinking or letting it run into the sea.
const WRAP_CHARS = 12
const WRAP_MAX = 3

const MIN_SPAN = 45   // map px, so a one-city nation still earns a name eventually
const FIT = 0.75      // the name spans this fraction of the area on screen
const FS_MIN = 8.5    // legible: the floor a derived span produces, and the size a
                      // land name grows to before it stops

// Water is the one thing on this map with no border to trace, so its names are
// set tight and italic and lean on colour to read as water; land names track
// wide to claim the ground they cover.
const WATER = new Set(['ocean', 'sea'])
// Character advance in em for each kind of label: the face's own advance plus the
// tracking its rule sets. Measured in the browser against the real names on this
// map, not guessed — the sizing math solves a font size from this number, so an
// advance that disagrees with what is drawn produces a name that overshoots or
// undershoots the span it was given.
//
// Change a font-family or a --track in style.css and the matching entry moves
// with it. Continents keep the old pair on purpose: nothing about them changed.
const ADVANCE = {
  continent: 0.68 + 0.22, // system stack, 500
  // Bold condensed capitals, measured over all 77 of these names: 0.52 in San
  // Francisco Condensed and 0.53 in Roboto Condensed — .label-nation, .label-colony
  land: 0.53 + 0.08,
  water: 0.655 + 0.15, // Inter 300 italic — .label-ocean, .label-sea
  // Semibold italic in mixed case, measured over all 81 of these names: 0.51 in
  // San Francisco, which a Mac draws them in, and 0.565 in Inter, which everything
  // else does — the Satellite map's water (body.hybridmap .label-ocean, .label-sea)
  waterSat: 0.565 + 0.08,
}
// The Satellite map sets its water as Apple Maps' satellite view does (looked at
// zoom by zoom, 17 Nov 2026): small, italic, in upper and lower case, at a size
// that says how big the water is and never at the width of it. On the drawn maps
// a sea's name is how its extent is read; over a photograph the water is plain to
// see and a name laid across all of it is in the way.
const satWater = (def: LabelDef) => settings.mode === 'hybrid' && WATER.has(def.type)
// Screen px. A name is never smaller than `min`; it grows with its water until
// it reaches the cap its water has earned (satWaterCap); and it is not shown at
// all until it fits inside its water at `min`, which is what brings the lakes in
// one by one on the way down, as they come in there.
//
// `fill` is how much of its water's width a name may take. It was all of it, so
// a name came on the moment it reached from shore to shore and stayed that way
// while it grew: LAKE ARAKANA was 62px across a lake of 70 (the user, 17 Nov
// 2026: "why are these smaller features so big and overflowing?"). Apple's are
// nowhere near their shores: Ligurian Sea is 46px in a sea of 300.
const SAT_WATER = { min: 9.5, fill: 0.6 }
// Where each of these names sits and how wide a box of its own shape is water
// there, [x, y, width] in px of the drawing, measured against the land by
// topo/scripts/waternames.py. The hand-placed point and span in labels.json are
// for a name spread across its sea; set small, a name went on the moment it was
// half the width of that span, which for sixty of the eighty-one put it across
// the shore (LAKE RAZYRV three quarters on land when it first appeared; the user:
// "Did you align all water labels correctly within their bodies and check at
// every zoom?"). With these no name has more than a tenth of itself on land at
// any zoom it is shown: `waternames.py check` prints the whole table.
const WATER_FIT = waterFitData as unknown as Record<string, [number, number, number]>
// An ocean and the largest seas at 14px, a middling sea at 11.5 to 12.5 and a
// lake or a bay at 10.5: a pixel per doubling of the water's width. Measured off
// Apple's map the day the city names were: North Atlantic Ocean 12.5px, North Sea
// and Mediterranean Sea 13.5 to 14, Ligurian Sea 11. It ran to 17 ("Ours seems
// too bulky?").
const satWaterCap = (span: number) => Math.min(14, Math.max(10.5, 8.5 + Math.log2(span / 20)))
const advanceOf = (def: LabelDef) =>
  WATER.has(def.type)
    ? satWater(def)
      ? ADVANCE.waterSat
      : ADVANCE.water
    : def.type === 'continent'
      ? ADVANCE.continent
      : ADVANCE.land

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
  // The Satellite map's water sits where it was measured to fit. A hand placement
  // still moves the name on the drawn maps; this one follows by rerunning the script.
  const fit = satWater(def) ? WATER_FIT[def.text] : undefined
  if (fit) return [fit[0], fit[1]]
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
  const legible = (FS_MIN * labelWidest(def) * advanceOf(def)) / (scaleAt(def.minZoom) * FIT)
  return Math.max(derived, legible)
}

// The size a name arrives at: what its span renders at, at its own minZoom.
function arrivalSize(def: LabelDef): number {
  return (areaSpan(def) * scaleAt(def.minZoom) * FIT) / (labelWidest(def) * advanceOf(def))
}

// Land names grow with the map until they are legible, then hold that screen
// size: zooming into a nation is asking for the cities under its name, not for
// bigger letters. A name that already arrives legible has no growing to do and
// holds from the moment it appears.
//
// Water names never stop, because a sea has nothing competing for the space and
// the name is how you read its extent.
//
// This replaced a test — is the arrival size at least FS_MIN — that sorted every
// land name into one of two behaviours. A name arriving at 8.42px grew for the
// rest of the map while one arriving at 8.59px was frozen forever, and the line
// fell through the middle of the set: fifty of the eighty land names on one side
// of it, thirty on the other. Nothing about a sixth of a pixel earns that.
//
// Saturating is also what makes growing at the map's own rate safe. It was
// throttled to 0.6 before because an island's name drew level with a nation's by
// the end of the band; the real fault was that nothing stopped it. Now it stops
// at legible, which is below where any comfortable name already sits, so an
// island resolves without being promoted.
function sizeZoom(def: LabelDef, z: number): number {
  if (WATER.has(def.type)) return z
  // Zoom levels of growth needed to reach FS_MIN. Zero once it is already there,
  // and it approaches zero smoothly rather than switching off at a threshold.
  const shortfall = Math.max(0, Math.log2(FS_MIN / arrivalSize(def)))
  return Math.min(z, def.minZoom + shortfall)
}

// A country carries its size on its back: one number, the same at every zoom.
// Everything else — continents, oceans, seas — is still solved from the ground it
// covers, which is the question that suits them.
//
// No floor and no ceiling on the solved path. A speck is the honest rendering of
// a territory too small to carry its name yet, and zooming in is what resolves it.
// A name broken into the lines it is drawn on. Zoom does not enter into it, so
// a name never reflows while you scroll — the break is a property of the name.
//
// Hyphens are break points as well as spaces, which is the whole reason
// HOCHBRUNN-AM-SAHARAMEER can be dealt with at all: as one token it is 23
// characters of unbreakable name laid across a bay.
//
// The Satellite map's water is the exception, and breaks as Apple Maps breaks a
// sea: lines of nine characters at most, which in practice is a word to a line
// (South / Atlantic / Ocean) with a short word kept on the line before it (Gulf
// of / Guinea). Balanced over two lines by length, GREAT SPATRYAN BIGHT came out
// as Great over Spatryan Bight (the user: "some spacing problems with the new
// water, eh?"). Which rule a name was broken by is part of its cache key, and
// applySettings redraws the water names when the map changes between the two.
const SAT_WRAP_CHARS = 9
const wrapCache = new Map<string, string[]>()
function labelLines(def: LabelDef): string[] {
  const sat = satWater(def)
  const key = (sat ? 'sat\t' : '') + def.text
  let lines = wrapCache.get(key)
  if (lines) return lines
  const tokens = def.text.split(/(?<=-)|\s+/).filter(Boolean)
  const n = Math.min(WRAP_MAX, Math.ceil(def.text.length / WRAP_CHARS))
  if (sat) {
    lines = ['']
    for (const t of tokens) {
      const cur = lines[lines.length - 1]
      const joined = cur + (cur && !cur.endsWith('-') ? ' ' : '') + t
      if (cur && joined.length > SAT_WRAP_CHARS && lines.length < WRAP_MAX) lines.push(t)
      else lines[lines.length - 1] = joined
    }
  } else if (tokens.length < 2 || n < 2) {
    lines = [def.text]
  } else {
    // Aim for equal lines rather than filling each to the brim, or the last one
    // ends up a single short word hanging under the rest
    const target = def.text.length / n
    lines = ['']
    for (const t of tokens) {
      const cur = lines[lines.length - 1]
      const joined = cur + (cur && !cur.endsWith('-') ? ' ' : '') + t
      if (cur && lines.length < n && joined.length > target && cur.length >= target * 0.5) lines.push(t)
      else lines[lines.length - 1] = joined
    }
    lines = lines.map(l => l.trim()).filter(Boolean)
  }
  wrapCache.set(key, lines)
  return lines
}

// The longest line, which is what the name is as wide as
const labelWidest = (def: LabelDef) =>
  labelLines(def).reduce((m, l) => Math.max(m, l.length), 0)

// A country's name as Apple Maps sets one (looked at zoom by zoom over southern
// Africa and the Balkans, 17 Nov 2026; the user: "sizes are way too big unless you
// also adjust nation names to use Apple Maps behavior"). It is small bold
// capitals, smaller than the name of a city: 8px for the least of them and 10.5px
// for the largest where they first appear, a pixel or so more by the time they
// go. It never shrinks with the map; a country too small on screen to hold its
// name has no name yet (landFits), and where two names would touch, the smaller
// country's waits (landCrowded).
//
// From the continent view inward it grows, as the city names do. Measured the
// same day off Apple's map over Europe at every zoom: GERMANY is 9.5px at
// Apple's zoom 4, 11.5 at 5, 13.5 at 6 and 15 at 7, BELGIUM 8, 9, 12 and 12, so
// a country's name stays a little under its capital's all the way in. Apple's 4
// is 4.45 here.
//
// The size in labels.json is still one of the three tiers (13, 11, 9) or a
// hand-set value between them, and this is what a tier comes out at on screen.
const LAND = new Set(['nation', 'colony'])
const LAND_GROW = 1.5 // px per zoom level
const LAND_GROW_FROM = 4.45
const LAND_GROW_SPAN = 3.5 // levels it keeps growing for
const landSize = (size: number, z: number, minZoom: number) =>
  8.5 + (size - 9) * 0.5 + LAND_GROW * Math.min(LAND_GROW_SPAN, Math.max(0, z - Math.max(minZoom, LAND_GROW_FROM)))
// How far past the spread of its cities a name may run. The spread is the middle
// four fifths of them, which is narrower than the land they stand on.
const LAND_FIT = 1.6

function areaFontSize(def: LabelDef, z: number): number {
  if (def.size != null) return landSize(def.size, z, def.minZoom)
  if (satWater(def)) {
    const span = areaSpan(def)
    // The width of water it has; a name the script has not seen falls back on its span
    const room = WATER_FIT[def.text]?.[2] ?? span * FIT
    const fit = (SAT_WATER.fill * room * scaleAt(z)) / (labelWidest(def) * advanceOf(def))
    return fit < SAT_WATER.min ? 0 : Math.min(fit, satWaterCap(span))
  }
  return (areaSpan(def) * scaleAt(sizeZoom(def, z)) * FIT) / (labelWidest(def) * advanceOf(def))
}

// A country's name stays for good once it has appeared. Apple Maps drops a
// country's name on the way in because the cities under it spread into real
// built-up ground that takes over the view; there is no such ground here, so
// past its band a country would just have no name (the user, 17 Nov 2026: "make
// nations names not disappear"). Its maxZoom in labels.json is now only the zoom
// by which the name is on whether or not its land can hold it (landFits).
function inBand(def: LabelDef, z: number): boolean {
  if (def.type === 'nation' || def.type === 'colony') return z >= def.minZoom
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
  const w = labelWidest(def) * fs * advanceOf(def)
  const h = fs * 1.4 * labelLines(def).length
  return { x: pos[0] * s - w / 2, y: pos[1] * s - h / 2, w, h }
}

// Whether a country is big enough on screen to carry its name. From the zoom its
// band used to end at it carries it regardless: an island colony of one city
// never grows into a name.
function landFits(def: LabelDef, z: number): boolean {
  if (z >= (def.maxZoom ?? MAX_ZOOM)) return true
  const span = anchors().get(norm(def.text))?.span ?? fallbackSpan(def)
  return labelWidest(def) * areaFontSize(def, z) * advanceOf(def) <= LAND_FIT * span * scaleAt(z)
}

// The country names that give way at a zoom: every name that fits claims its
// box, the widest country first, and one whose box is already spoken for waits
// for the next zoom. Keyed and cleared like the sea cache below.
const landCrowdCache = new Map<number, Set<LabelDef>>()

function landCrowded(z: number): Set<LabelDef> {
  const cached = landCrowdCache.get(z)
  if (cached) return cached
  const set = new Set<LabelDef>()
  const spanOf = (d: LabelDef) => anchors().get(norm(d.text))?.span ?? 0
  const taken: Box[] = []
  const lands = labelDefs
    .filter(d => LAND.has(d.type) && d.size != null && inBand(d, z) && landFits(d, z))
    .sort((a, b) => spanOf(b) - spanOf(a))
  for (const d of lands) {
    const b = labelBox(d, z)
    if (!b) continue
    if (taken.some(o => boxesOverlap(b, o))) set.add(d)
    else taken.push(b)
  }
  landCrowdCache.set(z, set)
  return set
}

const landShown = (def: LabelDef, z: number) =>
  inBand(def, z) && (def.size == null || (landFits(def, z) && !landCrowded(z).has(def)))

// A nation name sitting in the same water as a sea name reads as one jumble, and
// the nation is the more specific claim on that spot, so it takes it. The sea
// name is not lost. A country's name used to end at z5 and the sea came back
// then; now that it stays, past that zoom it only turns away a sea name set near
// its own size. On the drawn maps a sea's name keeps growing with the zoom, and
// by then it is lettering a small name can sit on, as a city's does.
//
// Keyed on zoom because both boxes move with it, and cleared alongside the
// placement cache, since a drag or a span edit changes the geometry.
const seaSuppressCache = new Map<number, Set<LabelDef>>()

function suppressedSeas(z: number): Set<LabelDef> {
  const cached = seaSuppressCache.get(z)
  if (cached) return cached

  const set = new Set<LabelDef>()
  // `reach` is the largest sea name a claim still turns away
  const claims: { box: Box; reach: number }[] = []
  for (const d of labelDefs) {
    if (!LAND.has(d.type) || !landShown(d, z)) continue
    const b = labelBox(d, z)
    if (b) claims.push({ box: b, reach: z > (d.maxZoom ?? Infinity) ? areaFontSize(d, z) * WATER_BLOCK : Infinity })
  }
  if (claims.length) {
    for (const d of labelDefs) {
      if (d.type !== 'sea') continue
      const b = labelBox(d, z)
      if (!b) continue
      const fs = areaFontSize(d, z)
      if (claims.some(o => fs <= o.reach && boxesOverlap(b, o.box))) set.add(d)
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
  // continent, nation and colony are the land names, so they answer to
  // Territories; ocean and sea answer to Bodies of Water.
  if (!shows(WATER.has(def.type) ? 'water' : 'territories')) return false
  if (!inBand(def, z)) return false
  // A country's name waits until its land can hold it and no larger name is there
  if (LAND.has(def.type) && !landShown(def, z)) return false
  // The Satellite map's water waits until it has the room
  if (satWater(def) && !areaFontSize(def, z)) return false
  if (def.type === 'sea' && suppressedSeas(z).has(def)) return false
  return true
}

// Water names are kept in capitals in labels.json and drawn in capitals on every
// map but one. They go into the page in upper and lower case, which the
// stylesheet puts back into capitals wherever it is not the Satellite map.
const SMALL_WORDS = new Set(['of', 'the', 'and'])
const titleCase = (s: string) =>
  s
    .toLowerCase()
    .replace(/(^|[\s-])(\p{L}+)/gu, (m, sep: string, w: string, i: number) =>
      i > 0 && SMALL_WORDS.has(w) ? m : sep + w[0].toUpperCase() + w.slice(1)
    )

function makeLabelMarker(def: LabelDef, pos: [number, number]): L.Marker {
  const handles = DEV
    ? ['nw', 'ne', 'sw', 'se'].map(c => `<i class="lh lh-${c}"></i>`).join('')
    : ''
  // Every nation and colony in nations.tsv has a panel to open. Continents,
  // oceans and seas have no entry there, so they stay inert rather than
  // offering a click that does nothing. Dev keeps the label for editing.
  const nation = DEV ? undefined : nationByName.get(norm(def.text))
  const m = new FlatMarker(px(pos[0], pos[1]), {
    icon: L.divIcon({
      className: `map-label label-${def.type}` + (DEV ? ' dev-label' : nation ? ' label-link' : ''),
      html: `<span>${(WATER.has(def.type) ? labelLines(def).map(titleCase) : labelLines(def)).join('<br>')}${handles}</span>`,
      iconSize: [0, 0],
      iconAnchor: [0, 0],
    }),
    interactive: DEV || !!nation,
    draggable: DEV,
    // Under the city markers (.map-label's z-index): a city dot sitting on a name
    // is the smaller target and the more specific answer, so it wins the click
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
      const perFs = Math.hypot(labelWidest(def) * advanceOf(def), 1.4 * labelLines(def).length) / 2
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
        // A country is sized in px directly; everything else still resolves back
        // to the span that produces that size at this zoom
        // back through landSize, at the zoom the name first appears
        if (sizedLabel(def)) def.size = 9 + (fs - 8.5) * 2
        else {
            def.span = (fs * labelWidest(def) * advanceOf(def)) / (scaleAt(sizeZoom(def, map.getZoom())) * FIT)
        }
        updateLabels()
        if (spanTarget === def) syncSpanRow()
      }
      const up = () => {
        document.removeEventListener('mousemove', move)
        document.removeEventListener('mouseup', up)
        commit(
          sizedLabel(def)
            ? `${def.text} → ${def.size!.toFixed(1)}px`
            : `${def.text} → span ${Math.round(def.span!)}`
        )
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

// Called every frame of a zoom, so it writes to the page only what has changed:
// most names hold one size across most of a zoom, and a write is what costs.
const labelDrawn = new WeakMap<HTMLElement, string>()
function updateLabels() {
  const z = map.getZoom()
  const zs = stepZoom(z)
  for (const [def, marker] of labelMarkers) {
    const el = marker.getElement()
    if (!el) continue
    const fs = areaFontSize(def, z).toFixed(1)
    const on = labelShown(def, zs)
    const state = fs + (on ? '+' : '-')
    if (labelDrawn.get(el) === state) continue
    labelDrawn.set(el, state)
    el.style.fontSize = fs + 'px'
    el.classList.toggle('label-on', on)
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

// Territories, water names, cities and stations are all in the Settings tab
// instead of the layer control. Their groups now stay on the map for the life of
// the session and the settings gate what goes into them, which is what lets one
// labelLayer answer to two separate switches.

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
  alpha3: string
  status: string
  capital: string
  expansionPoints: number
  continent: string
  // Territory in km², from scripts/areas.mjs. Not in nations.tsv: it is measured
  // off the borders drawing rather than written down, so it cannot fall out of
  // step with the map the way a typed-in figure would. Nations with nothing
  // drawn for them read 0.
  area: number
  // People per km². Derived rather than given, but it is a headline figure with
  // a rank, and ranking reads a field off the object like every other stat.
  density: number
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
    const areas = areasData as Record<string, number>
    return {
      area: areas[str(v[col.name])] ?? 0,
      density: areas[str(v[col.name])] ? num(v[col.population]) / areas[str(v[col.name])] : 0,
      name: str(v[col.name]),
      official: str(v[col.official]),
      population: num(v[col.population]),
      gdp: num(v[col.gdp]),
      gdpPerCapita: num(v[col.gdpPerCapita]),
      lifeExpectancy: num(v[col.lifeExpectancy]),
      literacy: num(v[col.literacy]),
      hdi: num(v[col.hdi]),
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

// A share is only meaningful where the parts add up to the whole. Population and
// GDP do. Land area nearly does — the world has ground no nation claims, so this
// is a share of what is claimed. Per capita and density are ratios: a nation has
// no share of the world's density, so those rows carry the city count alone.
//
// The subline says only "of world" because the sort already names the stat, and
// the figure it is a share of is sitting at the end of the same row.
const SHARE: Partial<Record<SortField, (n: Nation) => number>> = {
  population: n => n.population,
  gdp: n => n.gdp,
  area: n => n.area,
}
const worldTotals = new Map<string, number>()
function worldTotal(key: string, pick: (n: Nation) => number): number {
  let t = worldTotals.get(key)
  if (t === undefined) {
    t = nations.reduce((sum, n) => sum + pick(n), 0)
    worldTotals.set(key, t)
  }
  return t
}

// The ink is the only thing that marks a capital. Shape and scale are a city's,
// so a capital still reads at its own tier and nothing else has to change.
const CITY_INK = '#111'
const CAPITAL_INK = '#d0342c'

interface CityTier {
  radius: number // the ink disc, in CSS px — every other measurement is a ratio of it
  core?: boolean // draws the white centre; below 1M there is no room for one
  fontSize: number
  weight?: number // 400 unless set; the axis that still separates bands at 7px
}

// One marker, drawn once, scaled per band. The proportions never vary: a white
// halo, the ink disc, and a white core punched out of it, all fixed multiples of
// the ink radius, so the viewBox is in units of that radius and a tier's size is
// the only thing that changes between bands.
//
// Per-band variants were tried and cut. Eight drawings meant eight visual
// languages on one map, and the ones the small bands could carry at 3px across
// were a plain disc and a faded one, which read as smudges rather than as the
// bottom of a ladder.
const HALO = 1.354 // white disc behind the ink
const CORE = 0.465 // white centre, the same proportion in every band that draws one
// What a marker reserves in the placement grid, in ink radii. Deliberately wider
// than the halo it draws, so two markers at the limit still have air between them.
const MARKER_RESERVE = 6.05 / 4.095

// Three concentric circles at fixed ratios, painted as one element carrying a
// size and an ink colour. It used to be an inline <svg> with two or three
// <circle> children: 276 bytes apiece, 462KB of markup across the map, and an
// SVG subtree per city for the browser to parse and lay out.
//
// This is also what retired MARKER_SLACK. That 1px of transparent margin existed
// only because an SVG viewBox clips its own circle and squared the rim off at
// small sizes. A border-radius circle has no viewBox and nothing to clip
// against, so the element is exactly the halo.
//
// The rings are painted inward from one box's own edge rather than as nested
// boxes. A nested box is laid out symmetrically but rasterised on its own: at
// these sizes the browser rounded the outer and inner circles apart, and six of
// the sixteen tier-by-zoom combinations came out with a white rim one pixel
// thick on one side and none on the other, which reads as the ink disc sitting
// off centre. Two lost the rim entirely down one side. Sharing a box makes that
// impossible, whatever the device pixel ratio.
//
// The halo and the rim are whole pixels because those two are what the eye reads
// as the marker's edge, and a fractional one lands differently per band. The
// core keeps its exact fraction: quantising it too is the one thing that cannot
// be done here, because a whole-pixel core has to share the halo's parity, and
// over d = 5..10 the only ladder that satisfies that and still grows with the
// band is core = d - 4 — a one-pixel ink ring around a hole, which is not the
// marker. Measured against a mirror-symmetry check on the rendered pixels, the
// exact core also comes out the most symmetric of the three drawings tried.
function markerGeom(tier: CityTier): { d: number; rim: number; ring: number } {
  const ink = tier.radius * 2
  const halo = ink * HALO
  const d = Math.max(3, Math.round(halo))
  // Leave the centre at least a pixel, however thin the arithmetic wants a ring
  const rim = Math.min(Math.floor((d - 1) / 2), Math.max(1, Math.round((halo - ink) / 2)))
  // How far in the ink reaches. Past the centre for the bands with no core.
  const ring = tier.core
    ? Math.min((d - 1) / 2, rim + Math.max(0.5, (ink - ink * CORE) / 2))
    : d
  return { d, rim, ring }
}

function cityMarkerStyle(g: { d: number; rim: number; ring: number }, ink: string): string {
  return `--d:${g.d}px;--rim:${g.rim}px;--ring:${g.ring.toFixed(2)}px;--ink:${ink}`
}

function cityMarkerHtml(g: { d: number; rim: number; ring: number }, ink: string): string {
  return `<i class="city-dot" style="${cityMarkerStyle(g, ink)}"></i>`
}

// --- City names: Apple Maps' rule ---
//
// Measured off Apple Maps itself on 17 Nov 2026 ("Zoom into Europe with Apple
// Maps literally level by level and see how they distribute cities. Get this
// right."): its satellite map over Europe captured at every half zoom from 3 to
// 10, every name on each capture read off with its position, its letter height
// and its stroke, and the same words rendered at known sizes and weights to
// calibrate. What Apple does:
//
//   classes  A city's importance decides the zoom its name is switched on. Only
//            world capitals and megacities exist at the world and continent
//            views (eight names in all of Europe at Apple's zoom 3 and 3.5);
//            cities of about a million join at 4, regional centres of 150k or
//            so at 5, towns of 50k at 6, small towns at 7.
//   room     Within what is switched on, the most important name is placed
//            first and a name that would touch one already there waits. There is
//            no even spacing: Rome and Naples stand 30px apart and both are
//            named, and empty country stays empty.
//   growth   Every name enters at 10.5px in a medium weight and grows about
//            1.5px a zoom level from the level its class came on, thickening as
//            it goes, to 17.5px bold for Paris four levels in. So at any zoom
//            the long-established cities are the large ones, and at the world
//            view everything is one size.
//
// The result on Apple's map is a name per 19,000px of land at zoom 3, 37,000 at
// 3.5, 11,000 at 4 and between 6,000 and 8,000 from 5 inward. Over Evria, with
// Apple's zoom taken as ours less 0.45 (the same share of the world on screen),
// this rule gives 22,000, 30,000, 15,000 and 6,000 to 7,600, until user zoom 9
// or so, where this world runs out of cities to add.
//
// What it replaced, in order: a population floor per zoom with every name that
// fitted drawn at up to 15px bold ("Stuff gets cluttered so fast!", "the city
// names are too damn massive!"); one distance asked of every city, which named
// Lyonara two zooms ahead of Lutèce ("It just looks weird"); a distance by
// importance that held 27 names on a screen at every zoom, all one size, an even
// grid with no hierarchy that was too many at the world view and too few close
// in ("notice how Apple isn't trying to cram every possible city in???").
const CAPITAL_WEIGHT = 10
const cityScore = (c: City) => c.population * (isCapital(c) ? CAPITAL_WEIGHT : 1)
const citiesByPriority = [...cities].sort((a, b) => cityScore(b) - cityScore(a) || b.gdp - a.gdp)

// Bands of weighted population. An index is a rank: placement goes band by band,
// and FALLBACK_RANK is counted in them.
const SCORE_BANDS = [15_000_000, 5_000_000, 2_000_000, 1_000_000, 500_000, 250_000, 100_000, 0]
function tierRank(score: number): number {
  for (let i = 0; i < SCORE_BANDS.length; i++) if (score >= SCORE_BANDS[i]) return i
  return SCORE_BANDS.length - 1
}

// Weighted population against the zoom a name is switched on at, read between
// the rows on a log scale so that names arrive one by one as the map is zoomed
// and never as a batch. Apple's levels are ours plus 0.45: its 3, 4, 5, 6 and 7
// are 3.45, 4.45, 5.45, 6.45 and 7.45 here. The first two rows thin the world
// class out below Apple's zoom 3, where its web map stops and ours goes on to
// the whole world on one screen; the gap between the second and third is
// Apple's 3.5, which adds nothing to 3.
const NAME_ON: [number, number][] = [
  [100_000_000, 2.5],
  [10_000_000, 3.45],
  [9_900_000, 4.1],
  [1_000_000, 4.45],
  [600_000, 5],
  [150_000, 5.45],
  [100_000, 6],
  [50_000, 6.45],
  [30_000, 7],
  [15_000, 7.2],
]

function nameOnZoom(score: number): number {
  if (score >= NAME_ON[0][0]) return NAME_ON[0][1]
  for (let i = 1; i < NAME_ON.length; i++) {
    if (score < NAME_ON[i][0]) continue
    const [s0, z0] = NAME_ON[i - 1], [s1, z1] = NAME_ON[i]
    return z0 + ((z1 - z0) * Math.log(s0 / score)) / Math.log(s0 / s1)
  }
  return NAME_ON[NAME_ON.length - 1][1]
}

// A name's size at a zoom. It grows from the zoom its class came on; the world
// class, which is on from the start, grows from Apple's zoom 3 or a little
// after, the greatest capitals first (London is 12px at Apple's 4, 14 at 5, 15.5
// at 6 and 17.5 at 7; Munich, which arrives at 4, is 12, 13.5 and 14.5).
const NAME_FS = 10.5
const NAME_FS_MAX = 17.5
const NAME_GROW = 1.5 // px per zoom level
const GROW_WORLD = 3.8 // where a score of 10M starts to grow
const GROW_TOP = 3.2 // and one of 100M or more

function nameGrowZoom(score: number): number {
  return score >= 10_000_000
    ? Math.max(GROW_TOP, GROW_WORLD - (GROW_WORLD - GROW_TOP) * Math.log10(score / 10_000_000))
    : nameOnZoom(score)
}

function nameSizeAt(growZoom: number, z: number): number {
  // In half pixels, so a name is restyled three times a zoom level rather than
  // on every step of one
  return Math.min(NAME_FS_MAX, Math.round((NAME_FS + NAME_GROW * Math.max(0, z - growZoom)) * 2) / 2)
}

// The zooms a city's name comes on at and starts growing from. Worked out once,
// and again if a city is moved or edited.
let cityZoomCache: Map<City, { on: number; grow: number }> | null = null
function cityZooms(): Map<City, { on: number; grow: number }> {
  if (cityZoomCache) return cityZoomCache
  cityZoomCache = new Map()
  for (const c of cities) {
    const score = Math.max(1, cityScore(c))
    cityZoomCache.set(c, { on: nameOnZoom(score), grow: nameGrowZoom(score) })
  }
  return cityZoomCache
}

// What a city is drawn with at a zoom: the name's size, a weight that follows it
// (medium at 10.5px, semibold by 13, bold from 15, as measured), and a dot that
// follows it too, 4px across to 6, which is Apple's 4.5 to 6.5. A city of 2M or
// more keeps its white centre at every size. One object per distinct style, so
// two cities drawn alike share it.
const styleCache = new Map<string, CityTier>()
function cityStyle(c: City, z: number): CityTier {
  const fontSize = nameSizeAt(cityZooms().get(c)!.grow, z)
  const core = c.population >= 2_000_000
  const key = `${fontSize}|${core ? 1 : 0}`
  let style = styleCache.get(key)
  if (!style) {
    style = {
      radius: Math.min(2.2, Math.max(core ? 1.85 : 1.55, 1.55 + 0.13 * (fontSize - NAME_FS))),
      core,
      fontSize,
      weight: Math.min(700, Math.round((500 + 45 * (fontSize - NAME_FS)) / 10) * 10),
    }
    styleCache.set(key, style)
  }
  return style
}

// How much bigger than the biggest city label a water name may be and still
// reserve space against one. Past this it is scenery, and city names print over
// it the way they do on paper.
const WATER_BLOCK = 2.5

// Down to and including the 1M band. The bands above this get two extra corners
// to try before they are dropped from the map; the ones below do not.
const FALLBACK_RANK = 3

// Clear air kept around every name, on each side, on top of the box it is
// measured in. Apple's closest pairs of names stand about 21px apart centre to
// centre, one above the other.
const NAME_PAD = 2

// A city with nowhere to put its name holds back the lesser cities this close to
// it, so nothing is named ahead of a more important neighbour ("Lyonara shows up
// before Lutece").
const NAME_WAIT = 70

type Box = { x: number; y: number; w: number; h: number; water?: boolean }

function boxesOverlap(a: Box, b: Box): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
}

function visROf(tier: CityTier): number {
  return tier.radius * MARKER_RESERVE
}

// Average character advance as a fraction of the font size. A heavier cut of the
// same face is wider, and the placement grid reserves a box from this number, so
// a bolder label would otherwise be handed less room than it takes and print
// over its neighbour.
function advanceFor(weight = 400): number {
  // A line through the three measured weights, 400, 500 and 600
  return 0.62 + Math.max(0, weight - 400) * 0.000133
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
  corner: number // index into the candidate list, so the next zoom can reuse it
}

// Greedy label placement at one zoom level: every placed city is attempted,
// priority-ordered, and space decides. `pinned` cities (survivors of the
// previous half-zoom) place first, so zooming in only ever adds cities.
function computePlacement(z: number, pinned: Placement[]): Placement[] {
  const comesOn = cityZooms()
  // Which corner each survivor used last time. A greedy pass is not stable under
  // new candidates: futureCost weighs every marker still to come, so one more
  // band changes the arithmetic for cities placed long before it and they flip
  // sides, and each flip moves boxes that everything after it collides against.
  // Holding a survivor's corner stops that cascade at the source.
  const held = new Map(pinned.map(p => [p.c, p.corner]))
  //
  // Sorted by band afterwards, and the sort is stable, so within a band the
  // survivors still come first and keep their order. Pinned-first on its own
  // inverted rank the moment a large city failed a level: Cap de Bonne-Espérance,
  // 4.2M, was boxed in at user zoom 2 by the SOUTH PELAGONIA and KOGELLAND
  // labels either side of it, and from then on Vourcestre — 102k, one of its
  // suburbs — held the ground it needed at every zoom after.
  const order = [
    ...pinned.map(p => p.c),
    ...citiesByPriority.filter(
      c => !held.has(c) && (comesOn.get(c)?.on ?? Infinity) <= z + 1e-9
    ),
  ].sort((a, b) => tierRank(cityScore(a)) - tierRank(cityScore(b)))

  const items = order.map(c => {
    const tier = cityStyle(c, z)
    return { c, tier, visR: visROf(tier), pt: ptAt(c, z), rank: tierRank(cityScore(c)) }
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

  function collides(b: Box, skipWater = false): boolean {
    const x0 = Math.floor(b.x / CELL), x1 = Math.floor((b.x + b.w) / CELL)
    const y0 = Math.floor(b.y / CELL), y1 = Math.floor((b.y + b.h) / CELL)
    for (let cx = x0; cx <= x1; cx++) {
      for (let cy = y0; cy <= y1; cy++) {
        const cell = boxGrid.get(`${cx},${cy}`)
        if (!cell) continue
        for (const o of cell) {
          if (skipWater && o.water) continue
          if (boxesOverlap(b, o)) return true
        }
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
  // move. A city label that would cross one is pushed to its other side, and a
  // city with no free side does not render.
  //
  // Water names are marked, because a marker may sit on one where it may not sit
  // on a land name. A sea name is italic text drifting over empty blue and a
  // marker is a 4px dot: an atlas puts one over the other without comment. A
  // nation name is a claim on the ground the city stands in, and a dot landing
  // in the middle of it reads as a mistake, so those still turn a city away.
  //
  // Letting a sea name bury a marker cost real cities. Satsuno, 2.6M, sits
  // inside the label LAKE SATSUNO, so it vanished from the map for three zoom
  // levels while its 325k neighbour — whose dot happened to fall in a gap
  // between glyphs — kept a name the whole way.
  // labelBox is the one place a name's rectangle is worked out. This used to
  // measure its own, off the unwrapped text and a single line, and once long
  // names started wrapping the two stopped agreeing: EASTERN PANTHALASSAN OCEAN
  // renders as three stacked lines 1487px wide at user zoom 5 and reserved a
  // 3222px strip on one line, a band of dead ground reaching a thousand pixels
  // inland from where the words are. Cortesia, Turulia and Slytlia lost every
  // city they had to it.
  // Display-scale water lettering is not a collision object. An ocean name keeps
  // growing with the zoom — WESTERN PANTHALASSAN OCEAN is 2269px across at user
  // zoom 3 and 9078px at 5 — and at that size it is a wash of light italic the
  // eye reads as background, which is why an atlas prints coastal names straight
  // over it. Treated as a box it blanked every city under its footprint: Cap de
  // Bonne-Espérance, 4.2M, had a name at user zoom 1 and nowhere after that.
  //
  // A lake name set at city size is a different thing and still turns names
  // away, so the cut is where the water name stops being comparable to the
  // largest city label at this zoom rather than at a fixed size.
  const cityFsMax = nameSizeAt(GROW_TOP, z)
  for (const def of labelDefs) {
    if (!labelShown(def, z)) continue
    const b = labelBox(def, z)
    if (!b) continue
    const water = WATER.has(def.type)
    if (water && areaFontSize(def, z) > cityFsMax * WATER_BLOCK) continue
    addBox({ ...b, water })
  }

  const placed: Placement[] = []
  // Cities whose marker is on the map and whose name found no room
  const waiting: { x: number; y: number }[] = []

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
    const { c, tier, visR, pt, rank } = items[i]

    const dotR = visR + 0.5
    const dotBox: Box = { x: pt.x - dotR, y: pt.y - dotR, w: dotR * 2, h: dotR * 2 }

    // A city that can't place still reserves its dot area — a less important
    // neighbor must never render over where a more important city belongs.
    // Water names are skipped here: a sea name blocks this city's label, not its
    // marker. Every other name, territory or city, still blocks both.
    if (collides(dotBox, true)) {
      addBox(dotBox)
      continue
    }

    // A name already on the map is never held back, only a new arrival
    if (!held.has(c) && waiting.some(p => Math.hypot(p.x - pt.x, p.y - pt.y) < NAME_WAIT)) {
      addBox(dotBox)
      continue
    }

    const charW = tier.fontSize * advanceFor(tier.weight)
    const w = c.name.length * charW + 4
    const h = tier.fontSize + 4
    // Gap from marker edge: anchored at Cuerdas (~1.05px), tighter as markers shrink
    const gapX = visR + 0.15 + visR * 0.16
    const gapY = h / 2 + visR * 0.1

    // Apple Maps: top-right preferred, bottom-left when needed. The other two
    // corners are a fallback and only for cities from 1M up, tried when neither
    // default fits. Rank ordering alone was not translating into what actually
    // reached the map — with two positions a city is dropped the moment both are
    // taken, however important it is, so at the widest zoom nearly half the 5M
    // band had no name while the smallest band, whose labels ask for the least
    // room, did better than the 100k one.
    //
    // Withheld below 1M on purpose. Handing the extra reach to every band lifts
    // the small names as much as the large ones and just makes the map denser;
    // this way the label count barely moves and the labels that exist are the
    // ones that matter.
    const corners: { dir: 'right' | 'left'; off: [number, number]; box: Box }[] = [
      { dir: 'right', off: [gapX, -gapY], box: { x: pt.x + gapX, y: pt.y - gapY - h / 2, w, h } },
      { dir: 'left',  off: [-gapX, gapY], box: { x: pt.x - gapX - w, y: pt.y + gapY - h / 2, w, h } },
      { dir: 'right', off: [gapX, gapY], box: { x: pt.x + gapX, y: pt.y + gapY - h / 2, w, h } },
      { dir: 'left',  off: [-gapX, -gapY], box: { x: pt.x - gapX - w, y: pt.y - gapY - h / 2, w, h } },
    ]
    for (const cd of corners) {
      cd.box = { x: cd.box.x - NAME_PAD, y: cd.box.y - NAME_PAD, w: w + 2 * NAME_PAD, h: h + 2 * NAME_PAD }
    }

    // A survivor keeps the corner it already had, so its name does not walk
    // around the dot from one zoom to the next — but only while that corner is
    // free and costs nothing. A held corner that has come to sit on a smaller
    // city takes that city off the map, and a name moving is cheaper than a
    // neighbour disappearing.
    const blocked = corners.map(cd => collides(cd.box))
    // Top-right or bottom-left, and nothing else while either is free (the user,
    // 17 Nov 2026: "only at top right or bottom left unless absolutely necessary
    // (or else they'd be invisible)"). The other two corners used to compete on
    // cost with the defaults, so a name went bottom-right whenever that buried one
    // marker fewer, and a survivor then held it there at every zoom after.
    const defaultFree = !blocked[0] || !blocked[1]
    const keep = held.get(c)
    if (
      keep !== undefined && (keep < 2 || !defaultFree) &&
      !blocked[keep] && !futureCost(corners[keep].box, i + 1)
    ) {
      addBox(dotBox)
      addBox(corners[keep].box)
      placed.push({ c, tier, dir: corners[keep].dir, off: corners[keep].off, corner: keep })
      continue
    }

    // Between the two defaults, the one that buries the fewest upcoming markers
    // wins, and the order above breaks ties, so a name prefers top-right and
    // falls back to bottom-left. The other pair is reached only when both
    // defaults are blocked outright, which for a city from 1M up is the
    // difference between a name in an odd corner and no name at all.
    const free = corners
      .map((cd, idx) => ({ ...cd, idx }))
      .filter(cd => !blocked[cd.idx] && (cd.idx < 2 || (!defaultFree && rank <= FALLBACK_RANK)))

    let hit: (typeof free)[number] | null = null
    let bestCost = Infinity
    for (const cd of free) {
      const cost = futureCost(cd.box, i + 1)
      if (cost < bestCost) {
        hit = cd
        bestCost = cost
      } else if (
        cost === bestCost &&
        hit &&
        hit.idx === 0 &&
        cd.idx === 1 &&
        clearance(cd.box) > clearance(hit.box) + 6
      ) {
        // Two equally clean defaults: keep top-right unless bottom-left has
        // clearly more room around it
        hit = cd
      }
    }

    if (hit) {
      addBox(dotBox)
      addBox(hit.box)
      placed.push({ c, tier, dir: hit.dir, off: hit.off, corner: hit.idx })
    } else {
      addBox(dotBox)
      waiting.push(pt)
    }
  }

  return placed
}

// Where to stand to look at one city. Jumping to a fixed zoom 4 landed a link to
// a small town on empty ground: the eligibility ladder only lets a name onto the
// map when the band reaches its population, and a crowded neighbour can hold it
// off past that. The placer is the only thing that knows which, so it is asked
// rather than second-guessed from the population.
function zoomForCity(c: City, from: number): number {
  for (let z = stepZoom(Math.max(from, 4)); z <= MAX_ZOOM; z += ZOOM_STEP) {
    if (placementsAt(z).some(p => p.c === c)) return Math.max(from, z)
  }
  return MAX_ZOOM
}

function focusCity(c: City) {
  if (c.x == null || c.y == null) return
  focusOn(c.x, c.y, zoomForCity(c, map.getZoom()))
}

function clearFocus() {
  if (!focusedCity) return
  focusedCity = null
  updateCities()
}

// Placement is view-independent, so each zoom level's result is computed once
// and cached. The cascade recurses through cached lower levels, so a zoomend
// costs at most one computePlacement. Cleared whenever city coords change.
const placementCache = new Map<number, Placement[]>()

function placementsAt(z: number): Placement[] {
  z = stepZoom(z)
  const cached = placementCache.get(z)
  if (cached) return cached
  // The whole placement, not just the city: the corner each one settled on is
  // what the next level reuses to keep it where it is
  const pinned = z <= 2.5 ? [] : placementsAt(z - ZOOM_STEP)
  const result = computePlacement(z, pinned)
  placementCache.set(z, result)
  return result
}

function invalidatePlacements() {
  placementCache.clear()
  // Which seas a nation name covers is geometry too, so it goes stale for the
  // same reasons: a drag, a rename, a span edit, a type change
  seaSuppressCache.clear()
  landCrowdCache.clear()
  cityZoomCache = null
  warmPlacements()
}

// Every zoom level's placement, worked out one level at a time while the page is
// idle. Each is a greedy pass over up to 1,700 cities, and left to the moment it
// is first needed that pass lands in the middle of the zoom that asked for it.
let warmRun = 0
function warmPlacements() {
  const run = ++warmRun
  // Safari has no requestIdleCallback
  const idle = (window as { requestIdleCallback?: Window['requestIdleCallback'] }).requestIdleCallback
  const later = (f: () => void) => (idle ? idle.call(window, f, { timeout: 1500 }) : window.setTimeout(f, 200))
  let z = 2.5
  const step = () => {
    if (run !== warmRun || !settings.cities) return
    while (z <= MAX_ZOOM && placementCache.has(z)) z += ZOOM_STEP
    if (z > MAX_ZOOM) return
    placementsAt(z)
    later(step)
  }
  window.setTimeout(() => later(step), 400)
}

// Dot and label in one DOM element: no Leaflet tooltip machinery, whose
// per-label layout passes were the main zoom cost
function cityIcon(p: Placement, fade: boolean): L.DivIcon {
  const { c, tier } = p
  // The element is the halo, exactly — no margin, because nothing clips it now
  const g = markerGeom(tier)
  const S = g.d
  const ink = isCapital(c) ? CAPITAL_INK : CITY_INK
  const svg = cityMarkerHtml(g, ink)
  const focus = c === focusedCity ? ' city-icon-focus' : ''
  return L.divIcon({
    className: (fade ? 'city-icon' : 'city-icon city-icon-still') + focus,
    html: svg + `<span class="city-label" style="${cityLabelStyle(p, S)}">${c.name}</span>`,
    iconSize: [S, S],
    iconAnchor: [S / 2, S / 2],
  })
}

function cityLabelStyle(p: Placement, S: number): string {
  const { tier, dir, off } = p
  // dir picks the side, off[1] the vertical, signed — a fallback corner puts the
  // name above on the left or below on the right, which the two defaults never do
  const side = dir === 'right' ? 'left' : 'right'
  const pos = `${side}:${S / 2 + Math.abs(off[0])}px;top:${S / 2 + off[1]}px`
  return pos + `;font-size:${tier.fontSize.toFixed(2)}px` + (tier.weight ? `;font-weight:${tier.weight}` : '')
}

// A marker already on the map, redrawn where it stands. A name grows half a
// pixel at a time as the map is zoomed, a third of the names on screen at each
// step of a zoom, and taking each of those markers off the map and putting a
// new one on was the cost: this is five style writes to the element it has.
function restyleCity(el: HTMLElement, p: Placement) {
  const g = markerGeom(p.tier)
  const S = g.d
  el.style.width = el.style.height = `${S}px`
  el.style.marginLeft = el.style.marginTop = `${-S / 2}px`
  const dot = el.firstElementChild as HTMLElement | null
  const label = el.lastElementChild as HTMLElement | null
  if (dot) dot.style.cssText = cityMarkerStyle(g, isCapital(p.c) ? CAPITAL_INK : CITY_INK)
  if (label) label.style.cssText = cityLabelStyle(p, S)
  el.classList.toggle('city-icon-focus', p.c === focusedCity)
}

// Above this many additions and removals in one pass, the marker pane is
// detached for the duration and the fade is skipped. Below it the swap costs
// more than it saves.
const BATCH_MIN = 60

// Currently rendered markers, keyed by city; zoom changes only touch the diff
const shownCities = new Map<City, { marker: L.Marker; key: string }>()

// The city whose panel is open, ringed on the map for as long as it is. Declared
// up here because cityIcon reads it on the first render, before any panel exists.
let focusedCity: City | null = null

// Cities with a photograph, filled in once the image set is known further down.
let photoSet: Set<City> | null = null

// Explore state, up here because updateCities reads it on the first render. The
// cities whose card won a place: their ordinary marker steps aside for the card.
// A photographed city with no room for a card keeps its ordinary marker, which
// the map's own label placement already keeps from piling up.
let exploring = false
let carded = new Set<City>()

function syncExploreMarkers() {
  for (const [c, s] of shownCities) {
    const el = s.marker.getElement()
    if (!el) continue
    el.classList.toggle('city-icon-carded', exploring && carded.has(c))
    el.classList.toggle('city-icon-pic', exploring && !!photoSet?.has(c))
  }
}

// Fade tracking: a marker fades in only when its city is newly placed at this
// zoom (the pre-culling appearance). Markers re-entering the padded viewport
// during pans, or revealed by zooming out, appear instantly — culling invisible.
let lastAll: Placement[] | null = null
let prevPlaced = new Set<City>()

function placementKey(p: Placement): string {
  return (
    `${p.c.x},${p.c.y}|${p.tier.radius}|${p.tier.fontSize}|${p.dir}|${p.off[0]},${p.off[1]}` +
    (p.c === focusedCity ? '|f' : '')
  )
}

// What the last cull kept: the set it was cut from and the rectangle it was cut
// to, in map px. A pan that stays inside that rectangle changes nothing, and it
// is cut CULL_SLACK screen px wide of the view so that most frames of a pan, and
// every frame of a zoom in, do.
const NO_CITIES: Placement[] = []
const CULL_SLACK = 120
const reachOf = new WeakMap<Placement[], number>()
let culledAll: Placement[] | null = null
let culledBox = { x0: 0, y0: 0, x1: 0, y1: 0 }

// `panOnly` is the call a moving map makes every frame: nothing about the cities
// has changed, only where the view is, so it may stop at the rectangle test.
// Every other caller has changed something (the focus, a setting, the zoom) and
// gets the whole pass.
function updateCities(panOnly = false) {
  const zr = map.getZoom()
  const z = stepZoom(zr)
  // Empty falls through the same diff as any other change, so both toggles tear
  // the markers down without a separate path.
  const hidden = !settings.cities || z < 2.5
  const all = hidden ? NO_CITIES : placementsAt(z)

  // Viewport cull: placement is still computed map-wide (so what renders is
  // identical), but only markers near the view get DOM nodes. Pad covers the
  // longest label reach so nothing partially visible is ever missing.
  let reach = reachOf.get(all)
  if (reach == null) {
    reach = 64
    for (const p of all) {
      const r = p.c.name.length * p.tier.fontSize * advanceFor(p.tier.weight) + 48
      if (r > reach) reach = r
    }
    reachOf.set(all, reach)
  }
  const s = scaleAt(zr)
  const pb = map.getPixelBounds()
  const x0 = (pb.min!.x - reach) / s, x1 = (pb.max!.x + reach) / s
  const y0 = (pb.min!.y - reach) / s, y1 = (pb.max!.y + reach) / s
  if (
    panOnly && all === culledAll &&
    x0 >= culledBox.x0 && y0 >= culledBox.y0 && x1 <= culledBox.x1 && y1 <= culledBox.y1
  ) return
  const slack = CULL_SLACK / s
  culledAll = all
  culledBox = { x0: x0 - slack, y0: y0 - slack, x1: x1 + slack, y1: y1 + slack }

  const placements: Placement[] = []
  for (const p of all) {
    const cx = p.c.x!, cy = p.c.y!
    if (cx >= culledBox.x0 && cx <= culledBox.x1 && cy >= culledBox.y0 && cy <= culledBox.y1) placements.push(p)
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
      const el = existing?.marker.getElement()
      if (existing && el) {
        restyleCity(el, p)
        existing.key = key
        continue
      }
      if (existing) cityLayer.removeLayer(existing.marker)

      // The fade is a nicety for a few markers arriving. A thousand of them at
      // once is a thousand concurrent animations, which is the cost it was
      // meant to soften.
      const fade = !batched && isNewSet && !prevPlaced.has(p.c)
      const marker = new FlatMarker(px(p.c.x!, p.c.y!), { icon: cityIcon(p, fade) })
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
  if (exploring) syncExploreMarkers()
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
// Two sets keyed the same way: the photograph as maintained, and the 1000px 16:9
// crop scripts/thumbs.mjs derives from it. The panel loads the crop — 125KB
// against 4.5MB for a frame 380px wide — and the full view loads the original.
// The crops are generated at build time and not in git, so the only city image
// to keep up to date is the full one.
const cityImageKey = (path: string) =>
  norm(path.slice(path.lastIndexOf('/') + 1).replace(/\.[^.]+$/, ''))

const banners = new Map<string, string>()
for (const [path, url] of Object.entries(
  import.meta.glob('./assets/cities/*.{png,jpg,jpeg,PNG,JPG,JPEG}', {
    eager: true,
    query: '?url',
    import: 'default',
  }) as Record<string, string>
)) {
  banners.set(cityImageKey(path), url)
}

// Empty on a checkout where the script has not run yet, which just means the
// panel falls back to the full image rather than failing
const thumbs = new Map<string, string>()
for (const [path, url] of Object.entries(
  import.meta.glob('./assets/city-thumbs/*.jpg', {
    eager: true,
    query: '?url',
    import: 'default',
  }) as Record<string, string>
)) {
  thumbs.set(cityImageKey(path), url)
}

// The smallest set, for Explore's cards and the rows of the city list
const cards = new Map<string, string>()
for (const [path, url] of Object.entries(
  import.meta.glob('./assets/city-cards/*.jpg', {
    eager: true,
    query: '?url',
    import: 'default',
  }) as Record<string, string>
)) {
  cards.set(cityImageKey(path), url)
}
// The 480px crop where the build has made one, else the panel's, else the photo
const cardUrl = (c: City) =>
  byCityName(cards, c.name) ?? byCityName(thumbs, c.name) ?? byCityName(banners, c.name) ?? ''

photoSet = new Set(cities.filter(c => byCityName(banners, c.name)))

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

// Flags (src/assets/flags/<nation>.webp, written by scripts/flags.mjs from the
// Talopedia's), keyed by the nation's name as a slug.
const flags = new Map<string, string>()
for (const [path, url] of Object.entries(
  import.meta.glob('./assets/flags/*.webp', { eager: true, query: '?url', import: 'default' }) as Record<string, string>
)) {
  flags.set(path.slice(path.lastIndexOf('/') + 1, -5), url)
}

// A nation's own flag, or its overlord's when it has none: twelve colonies fly
// nothing of their own (user, 18 Nov 2026: "can use overlord's flag"). The
// overlord is the first nation in nations.tsv with the colony's code, which is
// how the sheet is laid out: Elvester, then Noradia, Thule and New Celyddon
// under ELV. `of` is whose flag it is, for the image's label.
function flagFor(n: Nation): { url: string; of: string } | null {
  const own = flags.get(talopediaSlug(n.name))
  if (own) return { url: own, of: n.name }
  const lord = n.alpha3 ? nations.find(m => m.alpha3 === n.alpha3) : undefined
  const theirs = lord && lord !== n ? flags.get(talopediaSlug(lord.name)) : undefined
  return theirs ? { url: theirs, of: lord!.name } : null
}

function loadBanner(name: string) {
  const holder = cityPanel.querySelector('.cp-banner') as HTMLElement
  const img = holder.querySelector('img') as HTMLImageElement
  const full = byCityName(banners, name)
  if (!full) return
  img.src = byCityName(thumbs, name) ?? full
  img.dataset.full = full
  img.alt = name
  holder.classList.add('cp-banner-show')
}

// --- Full view ---
//
// The panel crops its banner to 16:9 at 380px, which is a long way from what
// these images actually are. Clicking one opens it whole.
//
// Delegated from the panel rather than bound in loadBanner: the panel rebuilds
// its innerHTML on every open, so a listener on the banner itself would have to
// be re-attached each time and the old one would leak until GC.
const lightbox = document.getElementById('lightbox')!
const lightboxImg = lightbox.querySelector('img') as HTMLImageElement

cityPanel.addEventListener('click', e => {
  // A nation's flag, washed behind its name: the band is the way in to the flag itself
  const wash = (e.target as HTMLElement).closest('.cp-wash') as HTMLElement | null
  if (wash) {
    lightboxImg.src = wash.dataset.full!
    lightboxImg.alt = wash.dataset.alt ?? ''
    lightbox.hidden = false
    return
  }
  const banner = (e.target as HTMLElement).closest('.cp-banner') as HTMLElement | null
  if (!banner) return
  const img = banner.querySelector('img') as HTMLImageElement
  if (!img.src) return
  // The panel is showing a crop; this is what the full view is for
  lightboxImg.src = img.dataset.full ?? img.src
  lightboxImg.alt = img.alt
  lightbox.hidden = false
})

// Anywhere, including the image — the whole overlay is the dismiss target, which
// is why it carries a zoom-out cursor rather than putting a close button on it.
lightbox.addEventListener('click', () => {
  lightbox.hidden = true
})

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
  area:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M4 8.5V6a2 2 0 0 1 2-2h2.5"/><path d="M15.5 4H18a2 2 0 0 1 2 2v2.5"/>' +
    '<path d="M20 15.5V18a2 2 0 0 1-2 2h-2.5"/><path d="M8.5 20H6a2 2 0 0 1-2-2v-2.5"/></svg>',
  density:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<circle cx="7" cy="7" r="1.6"/><circle cx="14.5" cy="6" r="1.6"/><circle cx="6" cy="14.5" r="1.6"/>' +
    '<circle cx="13" cy="13" r="1.6"/><circle cx="19" cy="17.5" r="1.6"/><circle cx="17.5" cy="10.5" r="1.6"/></svg>',
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
  /** Always the compact form. The exact figure is a hover away, and a cell is
   *  107px on a desktop and 81px on a phone — a full population overran both. */
  value: string
  more?: Reveal[]
}

// The three headline numbers side by side, above everything else. Values are
// compact: a 400px panel split three ways leaves about 109px per cell, and a
// figure like $2,320,000,000,000 needs closer to 180px. The exact number and its
// rank live in the hover, so shortening the face loses nothing.
// Three stats fit one row of a 380px panel; a fourth leaves each 81px against
// the 98px an area needs, so four wrap to two rows of two. That also buys the
// room to write the numbers out in full rather than as 371.76M.
function statStrip(stats: Stat[]): string {
  return (
    `<div class="cp-strip${stats.length >= 4 ? ' cp-strip-grid' : ''}">` +
    stats
      .map(
        s =>
          `<div class="cp-cell">` +
          `<div class="cp-cell-label">${s.label}</div>` +
          `<div class="cp-cell-value">${s.icon}<span>${s.value}</span></div>` +
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
      ? `<div class="cp-coord"><span>${fmtGeo(toGeo(c.x, c.y))}</span>` +
        `<span class="cp-time" data-z="${cityZone(c)}">${timeLine(cityZone(c))}</span></div>`
      : '') +
    statStrip([
      {
        label: 'Population',
        icon: STAT_ICON.population,
        value: fmtCompact(c.population),
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
    (wiki
      ? `<div class="cp-section cp-section-row">About` +
        `<a class="cp-source" href="${talopediaUrl(displayName)}" target="_blank" rel="noopener noreferrer">Talopedia<span aria-hidden="true">›</span></a></div>` +
        `<div class="cp-about"><p class="cp-about-text">${esc(wiki.about)}</p>` +
        `<button class="cp-more" hidden>More</button></div>`
      : '') +
    detailsCard([
      detailRow('Nation', `${c.nation}${c.alpha3 ? ` <span class="cp-sub">(${c.alpha3})</span>` : ''}`, !!nat),
      c.irlParallel ? detailRow('Stat Donor', c.irlParallel) : '',
    ])
  cityPanel.classList.remove('cp-closing')
  cityPanel.hidden = false
  document.body.classList.add('panel-open')
  closeSheetList()
  markNavOpen(null)
  cityPanel.querySelector('.cp-close')!.addEventListener('click', closeCityPanel)
  wireAboutToggle()
  // flyToNation/goCity rather than the bare open*Panel: a link should land you
  // where the thing is, which is what the search results already do
  if (nat) cityPanel.querySelector('.cp-link')!.addEventListener('click', () => flyToNation(nat))
  hideSheet()
  openCityName = c.name
  focusedCity = c
  updateCities()
  openNationName = null
  syncHash()
  loadBanner(c.name)
}

// --- Nation info panel ---

type NationStatField =
  | 'population' | 'gdp' | 'gdpPerCapita' | 'hdi' | 'lifeExpectancy' | 'literacy' | 'area'
  | 'density'
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

// The panel has the width for the whole number, and a country's area is the kind
// of figure people compare digit by digit. fmtKm2 stays for the measure bar and
// the list column, where the room is a readout's worth and a stat column's.
function fmtArea(km2: number): string {
  return Math.round(km2).toLocaleString('en-US') + ' km²'
}

// People per square kilometre. Two decimals under 1 because the empty north has
// nations that round to nothing, one under 100, whole numbers above.
function fmtDensity(d: number): string {
  if (!d) return '—'
  return (d < 1 ? d.toFixed(2) : d < 100 ? d.toFixed(1) : Math.round(d).toLocaleString('en-US')) +
    ' / km²'
}

function openNationPanel(n: Nation) {
  if (measuring) return
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
  // The flag is washed in behind the name and the official name, fading out
  // toward them; clicking the band opens the flag whole (the panel's click
  // handler, beside the banner's)
  const flag = flagFor(n)
  const title =
    `<div class="cp-name">${n.name}</div>` +
    (n.official ? `<div class="cp-native">${n.official}${n.alpha3 ? ` <span class="cp-sub">(${n.alpha3})</span>` : ''}</div>` : '')
  cityPanel.innerHTML =
    `<div class="cp-banner"><img alt=""></div>` +
    `<button class="cp-close" aria-label="Close">✕</button>` +
    (flag
      ? `<div class="cp-wash" style="--flag:url('${flag.url}')" data-full="${flag.url}" data-alt="Flag of ${esc(flag.of)}" title="Flag of ${esc(flag.of)}">${title}</div>`
      : title) +
    statStrip([
      {
        label: 'Population',
        icon: STAT_ICON.population,
        value: n.population.toLocaleString('en-US'),
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
        // The one figure that stays short. Written out it is nineteen characters
        // against the 162px a cell has, and thirteen digits is not a number
        // anybody reads — the full amount is a hover away with its rank.
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
      // Measured off the borders drawing rather than typed into nations.tsv, so
      // it cannot drift from the map. Density hangs off it because it is this
      // divided by the population, the same way per capita hangs off GDP.
      {
        label: 'Area',
        icon: STAT_ICON.area,
        value: n.area ? fmtArea(n.area) : '—',
        more: n.area
          ? ([
              ['Area', fmtArea(n.area) + fmtRank(nationRank(n, 'area')), STAT_ICON.area],
              [
                'Density',
                fmtDensity(n.density) + fmtRank(nationRank(n, 'density')),
                STAT_ICON.density,
              ],
            ] as Reveal[])
          : [],
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
      nationZones(n.name).length
        ? detailRow(nationZones(n.name).length > 1 ? 'Time Zones' : 'Time Zone', nationZones(n.name).map(fmtZone).join(', '))
        : '',
      n.status ? detailRow('Status', n.status) : '',
    ]) +
    (agg.count
      ? `<button class="cp-action">View ${agg.count} ${agg.count === 1 ? 'city' : 'cities'}</button>`
      : '')
  cityPanel.classList.remove('cp-closing')
  cityPanel.hidden = false
  document.body.classList.add('panel-open')
  closeSheetList()
  markNavOpen(null)
  cityPanel.querySelector('.cp-close')!.addEventListener('click', closeCityPanel)
  // The capital is the only link in a nation panel, so this cannot pick up another
  if (cap) cityPanel.querySelector('.cp-link')!.addEventListener('click', () => goCity(cap))
  cityPanel.querySelector('.cp-action')?.addEventListener('click', () => {
    closeCityPanel()
    openListView('cities', n.name)
  })
  hideSheet()
  openCityName = null
  clearFocus()
  openNationName = n.name
  syncHash()
  loadBanner(n.name)
}

// The state reset, without the animation that normally precedes it. Opening a
// list takes the panel's column on desktop and its place on the screen on
// mobile, so the panel has to be gone before the list arrives rather than
// sliding out from under it.
function dismissPanel() {
  if (cityPanel.hidden) return
  cityPanel.removeEventListener('animationend', onCloseEnd)
  cityPanel.classList.remove('cp-closing')
  cityPanel.hidden = true
  document.body.classList.remove('panel-open')
  openCityName = null
  clearFocus()
  openNationName = null
  syncHash()
  showSheet()
}

// The nation banner fades in inside the panel and animationend bubbles, so this
// has to be sure the event is the panel's own close. cp-closing is the other
// half: reopening the panel mid-close clears the class and cancels the
// animation, which leaves this registered with nothing to end it.
function onCloseEnd(e: AnimationEvent) {
  if (e.target === cityPanel && cityPanel.classList.contains('cp-closing')) dismissPanel()
}

function closeCityPanel() {
  if (cityPanel.hidden || cityPanel.classList.contains('cp-closing')) return
  cityPanel.classList.add('cp-closing')
  // Not { once: true } — a bubbled banner fade would spend the registration and
  // the real close would never land. Removed in dismissPanel; re-adding the same
  // function is a no-op, so an abandoned one cannot accumulate.
  cityPanel.addEventListener('animationend', onCloseEnd)
}

map.on('click', () => {
  if (!measuring) closeCityPanel()
})
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return
  // Innermost first: the full view sits over the panel that opened it, so it has
  // to take the key before the panel does
  if (!lightbox.hidden) lightbox.hidden = true
  else if (!sortMenu.hidden) closeSortMenu()
  else if (measuring) endMeasure()
  else if (!cityPanel.hidden) closeCityPanel()
  else if (exploring) endExplore()
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
  if (moveRaf || coverPanning) return
  moveRaf = requestAnimationFrame(() => {
    moveRaf = 0
    if (!(map as any)._animatingZoom) updateCities(true)
  })
})
map.on('moveend', () => {
  if (!coverPanning) updateCities()
})

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
    saved[`${d.type}:${d.text}`] = { x: d.x, y: d.y, tier: d.tier, span: d.span, size: d.size }
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
    if (v.size != null) d.size = v.size
    if (v.span != null) d.span = v.span
  }
}

// TSV paste import: columns map to city fields by header name.
// Preserves existing coordinates — only data fields get overridden.
// Cities in the TSV that don't exist yet get added; cities not in the
// TSV get removed.
// Dev only, all three of these. The placer's localStorage is a scratch copy of
// an editing session, and laying it over the shipped data on the public site
// means anyone who has ever opened ?dev on that origin keeps seeing their old
// coordinates — for good, because it is not a cache and clearing the cache does
// not touch it. Which is exactly what happened: the deployed map rendered
// positions from a stale editing session in one profile and the committed ones
// in a private window, with the file, the bundle and the tiles all identical.
const loaded = DEV ? loadProgress() : 0
if (loaded > 0) {
  updateCities()
}

if (DEV) loadLabelProgress()
// mountLabel, not refreshLabel: one placement rebuild at the end rather than
// one per label
for (const def of labelDefs) mountLabel(def)
updateLabels()
invalidatePlacements()
updateCities()

const panel = document.getElementById('place-panel')!
const placeRail = document.getElementById('place-rail')!

// The rail buttons are an icon and a label, so writing textContent on one wipes
// the icon. Every state change goes through here instead.
function navLabel(btn: HTMLElement, text: string) {
  const span = btn.querySelector('span:last-child')
  if (span) span.textContent = text
}
const searchInput = document.getElementById('place-search') as HTMLInputElement
const resultsList = document.getElementById('place-results')!
const statusEl = document.getElementById('place-status')!
const coordEl = document.querySelector('.coord-display') as HTMLElement
const countEl = document.getElementById('place-count')!
const spanRow = document.getElementById('span-row')!
const spanInput = document.getElementById('place-span') as HTMLInputElement
const spanReadout = document.getElementById('span-readout')!
const spanLabel = document.getElementById('span-label')!
const sizeMajorBtn = document.getElementById('size-major') as HTMLButtonElement
const sizeMinorBtn = document.getElementById('size-minor') as HTMLButtonElement
const sizeIsletBtn = document.getElementById('size-islet') as HTMLButtonElement

// A country label is edited in screen px, everything else in map px of territory.
// Two different quantities, so the row says which one it is showing.
const sizedLabel = (d: LabelDef) => d.type === 'nation' || d.type === 'colony'

if (DEV) {
  // Lets the stylesheet tell the two modes apart. In dev the placer owns the left
  // edge and the public rail is not on screen at all.
  document.body.classList.add('dev')
} else {
  panel.style.display = 'none'
  placeRail.style.display = 'none'
  coordEl.style.display = 'none'
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
  const sized = sizedLabel(d)
  spanLabel.textContent = sized ? 'Size' : 'Span'
  spanInput.step = sized ? '0.5' : '10'
  sizeMajorBtn.hidden = !sized
  sizeMinorBtn.hidden = !sized
  sizeIsletBtn.hidden = !sized
  const v = sized ? (d.size ?? areaFontSize(d, map.getZoom())) : areaSpan(d)
  if (document.activeElement !== spanInput) spanInput.value = String(Math.round(v * 10) / 10)
  sizeMajorBtn.classList.toggle('is-on', sized && d.size === LABEL_SIZE.major)
  sizeMinorBtn.classList.toggle('is-on', sized && d.size === LABEL_SIZE.minor)
  sizeIsletBtn.classList.toggle('is-on', sized && d.size === LABEL_SIZE.islet)
  spanReadout.textContent = `${d.text} · ${areaFontSize(d, map.getZoom()).toFixed(1)}px`
}

for (const [btn, px] of [
  [sizeMajorBtn, LABEL_SIZE.major],
  [sizeMinorBtn, LABEL_SIZE.minor],
  [sizeIsletBtn, LABEL_SIZE.islet],
] as const) {
  btn.addEventListener('click', () => {
    if (!spanTarget || !sizedLabel(spanTarget)) return
    spanTarget.size = px
    updateLabels()
    syncSpanRow()
    // Same four steps wireLabelEdit's commit does; that one is scoped to a marker
    saveLabelProgress()
    invalidatePlacements()
    updateCities()
    statusEl.textContent = `${spanTarget.text} → ${px}px`
  })
}

function setSpanTarget(d: LabelDef | null) {
  spanTarget = d
  syncSpanRow()
}

spanInput.addEventListener('input', () => {
  const n = Number(spanInput.value)
  if (!spanTarget || !isFinite(n) || n <= 0) return
  if (sizedLabel(spanTarget)) spanTarget.size = n
  else spanTarget.span = n
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

// Two chips rather than a sentence. "1722/1763 cities · 161/161 labels" was
// thirty-odd characters in a 190px rail, so it wrapped under the title and the
// numbers — the only part worth reading — came second.
const COUNT_ICON = {
  city:
    '<svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor">' +
    '<rect x="4" y="4" width="7" height="7" rx="2"/><rect x="13" y="4" width="7" height="7" rx="2"/>' +
    '<rect x="4" y="13" width="7" height="7" rx="2"/><rect x="13" y="13" width="7" height="7" rx="2"/></svg>',
  label:
    '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" ' +
    'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M4 7h9"/><path d="M4 12h13"/><path d="M4 17h7"/><circle cx="19" cy="7" r="1.6"/></svg>',
}

function updateCount() {
  const placed = cities.filter(c => c.x != null && c.y != null).length
  // A derived anchor counts as placed: that label is already on the map and
  // draggable, so the placer has nothing left to do for it
  const lPlaced = labelDefs.filter(d => labelPos(d) != null).length
  const chip = (icon: string, done: number, all: number, what: string) =>
    `<span class="pp-chip${done === all ? ' is-done' : ''}" title="${done} of ${all} ${what} placed">` +
    `${icon}<span>${done}<span class="pp-of">/${all}</span></span></span>`
  countEl.innerHTML =
    chip(COUNT_ICON.city, placed, cities.length, 'cities') +
    chip(COUNT_ICON.label, lPlaced, labelDefs.length, 'labels')
}

updateCount()

// How well a city answers the query, lowest first. The nation is searchable
// because "guandong" is a reasonable way to ask for its cities — but a nation is
// also a long word that swallows short queries, and matching on it alone used to
// win on equal terms. Typing Andō returned ten Guandong cities and not Andō:
// "ando" sits inside "gu-ando-ng", 54 of its cities matched, and the list was
// full before the two name matches were reached.
//
// The IRL parallel ranks between the two. It is how a city is found when its
// Avium name is the thing you cannot remember — "what did I call the Fukuoka
// one" — and being a city name itself it is about as specific as the name, where
// a nation covers dozens of rows at once.
// The results list runs the height of the column now rather than a 156px box in
// a floating slab, so it can afford to show what it finds
const PLACE_MAX = 40

// What is left to do comes first. This is the worklist the unassigned tray used
// to be — it sat in its own floating panel repeating half of this list, and with
// an empty search box now browsing, there was nothing left for it to say.
function sortUnplacedFirst<T>(rows: T[], placed: (r: T) => boolean): T[] {
  return [...rows].sort((a, b) => Number(placed(a)) - Number(placed(b)))
}

const MISS = 7
function matchRank(c: City, q: string): number {
  const name = norm(c.name)
  if (name === q) return 0
  if (name.startsWith(q)) return 1
  if (name.includes(q)) return 2
  const par = norm(c.irlParallel)
  if (par.startsWith(q)) return 3
  if (par.includes(q)) return 4
  const nation = norm(c.nation)
  if (nation.startsWith(q)) return 5
  if (nation.includes(q)) return 6
  return MISS
}

// One nation's cities at a time. Each option carries how many are left, so the
// drop-down doubles as the worklist of which nations still need work.
const nationSelect = document.getElementById('place-nation') as HTMLSelectElement

function syncNationFilter() {
  const left = new Map<string, number>()
  for (const c of cities) left.set(c.nation, (left.get(c.nation) ?? 0) + (c.x == null ? 1 : 0))
  const keep = nationSelect.value
  nationSelect.innerHTML = ''
  nationSelect.add(new Option('All nations', ''))
  for (const n of [...left.keys()].sort((a, b) => a.localeCompare(b))) {
    const k = left.get(n)!
    nationSelect.add(new Option(k ? `${n} (${k} left)` : n, n))
  }
  nationSelect.value = keep
}

syncNationFilter()
nationSelect.addEventListener('change', renderResults)

function renderResults() {
  const q = norm(searchInput.value.trim())
  resultsList.innerHTML = ''
  nationSelect.hidden = tab !== 'cities'
  // An empty box browses rather than sitting blank. On labels that is all of
  // them, a hundred or so. On cities it is the ones still to place, biggest
  // first — the work queue, which is what the tab is opened to do. All 1763 is
  // not a list anybody reads. With a nation picked it is that whole nation,
  // unplaced first, which is short enough to read.
  const browsing = !q
  if (!browsing && q.length < 2) return
  const nation = tab === 'cities' ? nationSelect.value : ''
  const pool = nation ? cities.filter(c => c.nation === nation) : cities

  const matches =
    tab !== 'cities'
      ? []
      : browsing
        ? nation
          ? sortUnplacedFirst([...pool].sort((a, b) => b.population - a.population), c => c.x != null)
          : pool
              .filter(c => c.x == null)
              .sort((a, b) => b.population - a.population)
              .slice(0, PLACE_MAX)
        : pool
            .filter(c => matchRank(c, q) < MISS)
            .sort((a, b) => matchRank(a, q) - matchRank(b, q) || b.population - a.population)
            .slice(0, nation ? 400 : PLACE_MAX)

  for (const c of matches) {
    const li = document.createElement('li')
    const placed = c.x != null
    if (c === selectedCity) li.classList.add('is-selected')
    // The parallel is always on the row, placed or not. It is how a city is
    // recognised when the Avium name is the thing that will not come — and it is
    // what a search for "fukuoka" matched on, so a row that showed it only
    // sometimes read as a row that had matched nothing.
    const par = c.irlParallel ? ` &middot; ${c.irlParallel}` : ''
    li.innerHTML = `<span class="result-name">${c.name}</span>` +
      `<span class="result-meta">${c.nation}${par} &middot; ${(c.population / 1e6).toFixed(2)}M${placed ? ' ✓' : ''}</span>`
    if (placed) li.classList.add('placed')
    li.addEventListener('click', () => selectCity(c))
    resultsList.appendChild(li)
  }

  const labelMatches = tab === 'labels'
    ? sortUnplacedFirst(
        labelDefs.filter(d => !q || norm(d.text).includes(q)),
        d => labelPos(d) != null
      ).slice(0, browsing ? 400 : PLACE_MAX)
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
    ? sortUnplacedFirst(
        stations.filter(p => !q || norm(p.name).includes(q)),
        p => p.x != null
      ).slice(0, browsing ? 400 : PLACE_MAX)
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
  // The search and the list stay as they were, with this row lit, so the next
  // city is one click away once this one lands
  renderResults()
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
    syncNationFilter()
    renderResults()

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
// --- Bottom sheet (public mode) ---

const sheet = document.getElementById('bottom-sheet')!
const bsHome = document.getElementById('bs-home')!
const bsList = document.getElementById('bs-list')!
const bsSearch = document.getElementById('bs-search') as HTMLInputElement
const bsResults = document.getElementById('bs-results')!
const bsItems = document.getElementById('bs-items')!
const bsFilter = document.getElementById('bs-filter') as HTMLInputElement
const bsTitle = document.getElementById('bs-title')!
const bsControls = document.querySelector('.bs-controls') as HTMLElement
// Whether the second column is currently holding search results rather than a
// browse list, a settings page or the measure menu
let searchOpen = false

if (DEV) sheet.style.display = 'none'

// Restart a one-shot CSS animation class regardless of current state
function replayAnim(el: HTMLElement, cls: string) {
  el.classList.remove(cls)
  void el.offsetWidth
  el.classList.add(cls)
}

for (const id of ['bs-banner', 'place-banner']) {
  const img = document.getElementById(id) as HTMLImageElement | null
  if (img) img.src = bannerUrl
}

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
  searchOpen = false
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
  // Number() drops a trailing .00 or .0 that toFixed leaves behind, so a round
  // figure reads as 2M rather than 2.00M
  const cut = (div: number, places: number, suffix: string) =>
    String(Number((n / div).toFixed(places))) + suffix
  if (n >= 1e12) return cut(1e12, 2, 'T')
  if (n >= 1e9) return cut(1e9, 2, 'B')
  if (n >= 1e6) return cut(1e6, 2, 'M')
  if (n >= 1e3) return cut(1e3, 1, 'k')
  return String(n)
}

function goCity(c: City) {
  bsResults.innerHTML = ''
  bsSearch.value = ''
  searchSel = -1
  closeSearchColumn()
  openCityPanel(c)
  focusCity(c)
}

// Home search
//
// On a desktop the results go in the second column rather than under the field.
// The rail is clamp(190px, 12.5vw, 320px) and only reaches its full width on a
// 2560px screen, so on an ordinary laptop it is 190px and a result had about
// 150px to say "Montlionne · Barbary · 1.19M" in. The column has 380px and the
// height for more than ten of them.
//
// The field stays in the rail. Apple Maps moves it into the column, but the rail
// here is where a search starts and taking its field away would leave the tab
// that owns the column with nothing to open it from.
//
// Narrow screens keep the old inline list: the column rises from the bottom edge
// there and would cover the field being typed into.
let searchSel = -1
const SEARCH_MAX_RAIL = 10
const SEARCH_MAX_COLUMN = 50

// Whichever list is live, so the arrow keys walk the one on screen
function searchItems(): HTMLCollection {
  return searchOpen ? bsItems.children : bsResults.children
}

function closeSearchColumn() {
  if (searchOpen) closeSheetList()
}

function renderSearch(q: string) {
  const wide = onDesktop()
  const matches = idx()
    .filter(e => e.n.includes(q) || e.nat.includes(q))
    .slice(0, wide ? SEARCH_MAX_COLUMN : SEARCH_MAX_RAIL)

  if (!wide) {
    closeSearchColumn()
    for (const { c } of matches) {
      const li = document.createElement('li')
      li.innerHTML = `<span class="bs-cname"><span class="bs-ctext">${c.name}</span></span>` +
        `<span class="bs-cnation">${c.nation} · ${fmtCompact(c.population)}</span>`
      li.addEventListener('click', () => goCity(c))
      bsResults.appendChild(li)
    }
    return
  }

  // Reopening on every keystroke would replay the column's slide each time, so
  // it is opened once and then only refilled
  if (!searchOpen) {
    openColumn('Search', false, null)
    searchOpen = true
  }
  bsItems.innerHTML = ''
  bsItems.scrollTop = 0
  if (!matches.length) {
    bsItems.innerHTML = `<li class="bs-empty">No place matches “${bsSearch.value.trim()}”</li>`
    return
  }
  // The same row the Cities list uses: the name and its nation stacked in a
  // column that can shrink, which is the shape that never truncated
  const frag = document.createDocumentFragment()
  for (const { c } of matches) {
    const li = document.createElement('li')
    li.innerHTML =
      `<span class="bs-cinfo"><span class="bs-cname"><span class="bs-ctext">${c.name}</span></span>` +
      `<span class="bs-cnation">${c.nation}</span></span>` +
      `<span class="bs-cstat">${fmtCompact(c.population)}</span>`
    li.addEventListener('click', () => goCity(c))
    frag.appendChild(li)
  }
  bsItems.appendChild(frag)
}

bsSearch.addEventListener('input', () => {
  const q = norm(bsSearch.value.trim())
  bsResults.innerHTML = ''
  searchSel = -1
  if (q.length < 2) {
    closeSearchColumn()
    return
  }
  renderSearch(q)
})

// Arrow keys walk the results; Enter opens the highlighted one (or the first,
// so a fast typist can hit Enter without arrowing down first)
function moveSearchSel(d: number) {
  const items = searchItems()
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
  } else if (e.key === 'Enter' && searchItems().length) {
    e.preventDefault()
    ;(searchItems()[Math.max(searchSel, 0)] as HTMLElement).click()
  }
})

// List views
type SortField = 'name' | 'population' | 'gdp' | 'gdpPerCapita' | 'area' | 'density'
let listMode: 'cities' | 'nations' = 'cities'

let sortField: SortField = 'name'
let sortAsc = true

// Few of the 1,800 cities have a photograph, so the picture on a row alone leaves
// them scattered a page apart. The filter narrows Cities to just those, keeping
// whatever sort is in force; it lives in the sort menu because that is where the
// list's other ways of being cut already are.
let photoOnly = false
const hasPhoto = (c: City) => !!byCityName(banners, c.name)
const PHOTO_ICON =
  '<svg class="bs-photo" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" ' +
  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-label="Has photo">' +
  '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.5"/><path d="M21 16l-5-5-11 8"/></svg>'
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
    // A city with a photograph wears it behind its row
    if (hasPhoto(c)) {
      li.className = 'bs-pic'
      li.style.setProperty('--pic', `url('${cardUrl(c)}')`)
    }
    li.innerHTML =
      `<span class="bs-rank">${rm ? rm.get(c) : ''}</span>` +
      `<span class="bs-cinfo"><span class="bs-cname"><span class="bs-ctext">${c.name}</span></span>` +
      `<span class="bs-cnation">${c.nation}</span></span>` +
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

// A row of chips ran out of room at five and there are six sorts now, two of
// them nations-only. So it is a button carrying the current sort with a menu
// behind it, next to the field it belongs to, rather than a segmented control
// squeezing "Population ↓" into 60px.
const SORTS: [SortField, string, boolean][] = [
  // field, label, nations only
  ['name', 'Alphabetical', false],
  ['population', 'Population', false],
  ['gdp', 'GDP PPP', false],
  ['gdpPerCapita', 'GDP Per Capita', false],
  ['area', 'Land Area', true],
  ['density', 'Density', true],
]
const sortBtn = document.getElementById('bs-sort-btn') as HTMLButtonElement
const sortMenu = document.getElementById('bs-sort-menu')!
const sortLabel = (f: SortField) => SORTS.find(s => s[0] === f)?.[1] ?? 'Alphabetical'

function closeSortMenu() {
  sortMenu.hidden = true
  sortBtn.setAttribute('aria-expanded', 'false')
}

function updateSortChips() {
  const photo = listMode === 'cities' && photoOnly
  sortBtn.innerHTML =
    (photo ? PHOTO_ICON : '') +
    `<span>${sortLabel(sortField)}</span><span class="bs-sort-dir">${sortAsc ? '↑' : '↓'}</span>`
  sortMenu.innerHTML =
    SORTS.filter(([, , nat]) => !nat || listMode === 'nations')
      .map(
        ([f, label]) =>
          `<li data-sort="${f}"${f === sortField ? ' class="is-on"' : ''} role="option">${label}` +
          (f === sortField ? `<span class="bs-sort-dir">${sortAsc ? '↑' : '↓'}</span>` : '') +
          `</li>`
      )
      .join('') +
    (listMode === 'cities'
      ? `<li class="bs-sort-photo${photo ? ' is-on' : ''}" data-photo role="option" aria-checked="${photo}">` +
        `<span class="bs-sort-photo-l">${PHOTO_ICON}With Photo</span>` +
        `<span class="bs-check">${photo ? '✓' : ''}</span></li>`
      : '')
}

sortBtn.addEventListener('click', e => {
  e.stopPropagation()
  const open = sortMenu.hidden
  sortMenu.hidden = !open
  sortBtn.setAttribute('aria-expanded', String(open))
})

// Picking the sort already in force flips its direction, which is what the chips
// did when you clicked the lit one
sortMenu.addEventListener('click', e => {
  if ((e.target as HTMLElement).closest('[data-photo]')) {
    photoOnly = !photoOnly
    closeSortMenu()
    rebuildList()
    return
  }
  const li = (e.target as HTMLElement).closest('[data-sort]') as HTMLElement | null
  if (!li) return
  const field = li.dataset.sort as SortField
  if (field === sortField) sortAsc = !sortAsc
  else {
    sortField = field
    sortAsc = field === 'name'
  }
  closeSortMenu()
  rebuildList()
})

document.addEventListener('click', e => {
  if (!sortMenu.hidden && !(e.target as HTMLElement).closest('.bs-sortwrap')) closeSortMenu()
})

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
  // Panel first, so the padding below is measured with the column it opens
  openNationPanel(n)
  if (agg.pts.length) {
    // Pad by the sidebar so the nation is framed in the visible half
    map.flyToBounds(L.latLngBounds(agg.pts).pad(0.2), {
      maxZoom: 5,
      duration: 0.8,
      paddingTopLeft: [sidebarWidth(), 0],
    })
    lastCover = sidebarWidth()
  }
}

function nationStatText(n: Nation): string {
  if (sortField === 'density') return fmtDensity(n.density)
  if (sortField === 'area') return fmtKm2(n.area)
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
  // Sorted by name there is no stat in play, so the share falls back to the one
  // a list of countries is most often read for
  const shareKey: SortField = sortField === 'name' ? 'population' : sortField
  const share = SHARE[shareKey]
  for (const n of rows) {
    const agg = mapAggFor(n)
    const sub = [`${agg.count} ${agg.count === 1 ? 'city' : 'cities'}`]
    if (share) {
      const total = worldTotal(shareKey, share)
      const pct = total ? (share(n) / total) * 100 : 0
      sub.push(`${pct >= 0.1 ? pct.toFixed(1) + '%' : '<0.1%'} of world`)
    }
    const li = document.createElement('li')
    li.innerHTML =
      `<span class="bs-rank">${rm ? rm.get(n) : ''}</span>` +
      `<span class="bs-cinfo"><span class="bs-cname"><span class="bs-ctext">${n.name}</span></span><span class="bs-cnation">${sub.join(' · ')}</span></span>` +
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
    if (photoOnly) rows = rows.filter(e => hasPhoto(e.c))
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

// The rail stays on screen beside an open list, so it has to say which one is
// open. Cities is the button labelled 'all' in the markup.
function markNavOpen(view: 'all' | 'nations' | 'measure' | 'explore' | 'time' | null) {
  for (const b of document.querySelectorAll<HTMLElement>('.bs-btn')) {
    // Explore is a mode rather than a column, so it stays lit while it is on
    b.classList.toggle('is-on', (!!view && b.dataset.view === view) || (exploring && b.dataset.view === 'explore'))
  }
}

// Every view in the second column opens the same way: the info panel gives up
// the slot, the column takes it, and the rail lights the tab that owns it. Only
// the title, whether there is a filter-and-sort row, and the rows themselves
// differ between them.
function openColumn(
  title: string,
  controls: boolean,
  nav: 'all' | 'nations' | 'measure' | 'explore' | 'time' | null
) {
  // Another tab taking the column is leaving Explore
  if (nav !== 'explore') endExplore()
  // A list and an info panel are the same slot, so one replaces the other. The
  // panel goes without its close animation — before hideSheet below, since the
  // reset ends in a showSheet.
  dismissPanel()
  searchOpen = false
  bsTitle.textContent = title
  bsControls.hidden = !controls
  bsHome.hidden = !onDesktop()
  bsList.hidden = false
  markNavOpen(nav)
  hideSheet()
}

function openListView(mode: 'cities' | 'nations', filter = '') {
  openColumn(mode === 'nations' ? 'Nations' : 'Cities', true, mode === 'nations' ? 'nations' : 'all')
  listMode = mode
  bsFilter.value = filter
  bsFilter.placeholder = 'Search'
  if (mode === 'nations') {
    sortField = 'population'
    sortAsc = false
  } else {
    // Cities opens on every place, richest first; With Photo is a filter the
    // reader turns on
    sortField = 'gdp'
    sortAsc = false
    photoOnly = false
  }
  rebuildList(false)
}

// Which tab is open, read off the highlight rather than tracked alongside it.
// One source of truth, and nothing to initialise before the hash restore runs.
const navOpen = () =>
  (document.querySelector('.bs-btn.is-on') as HTMLElement | null)?.dataset.view ?? null

// Clicking the open tab closes it. Export is the one action left that is not a
// tab — it leaves nothing open to click a second time.
function navTab(view: string, open: () => void) {
  document.querySelector(`.bs-btn[data-view="${view}"]`)!.addEventListener('click', () => {
    if (navOpen() === view) closeSheetList()
    else open()
  })
}

navTab('all', () => openListView('cities'))
navTab('nations', () => openListView('nations'))
navTab('measure', () => openMeasureMenu())
navTab('time', () => openTimeView())
document.querySelector('.bs-btn[data-view="export"]')!.addEventListener('click', () => exportView())

// --- Measure tab ---
//
// Two things called measuring, so the button asks which before it takes over the
// map. Same column as the settings page for the same reason: the surface already
// exists and a third one would be the slide-out and the bottom sheet written
// twice more to say something this short.

const MEASURE_MODES: [MeasureMode, string, string][] = [
  ['distance', 'Distance', 'Great-circle length along a path'],
  ['area', 'Area', 'Close a shape for its land and sea area'],
]

function openMeasureMenu() {
  openColumn('Measure', false, 'measure')
  bsItems.innerHTML = MEASURE_MODES.map(
    ([mode, title, sub]) =>
      `<li class="pick-row" data-measure="${mode}">` +
      `<span class="pick-title">${title}</span><span class="pick-sub">${sub}</span></li>`
  ).join('')
}

// Delegated, because the rows are rewritten every time the tab opens. The list's
// own rows attach their handlers individually, so this only ever sees these two.
bsItems.addEventListener('click', e => {
  const row = (e.target as HTMLElement).closest('[data-measure]') as HTMLElement | null
  if (row) startMeasure(row.dataset.measure as MeasureMode)
})

// --- Applying the settings ---

// Every switch and mode tile lands here, and so does the first render. Enforced
// as a state rather than applied as a transition, so a reload lands where the
// click did.
let waterBrokenForSat = settings.mode === 'hybrid'
function applySettings() {
  const m = settings.mode
  const relief = shows('relief')
  document.body.classList.toggle('clockmap', m === 'zones')
  document.body.classList.toggle('zones-on', m === 'zones')
  document.body.classList.toggle('hybridmap', m === 'hybrid')
  const put = (l: L.Layer, on: boolean) => (on ? map.hasLayer(l) || l.addTo(map) : l.remove())
  // The zone layer paints every pixel, sea and unclaimed land included, so
  // Time Zones needs no ground under it
  put(baseLayer, m === 'political' && !relief)
  put(reliefLayer, m === 'political' && relief)
  put(terrainLayer, m === 'terrain' && relief)
  put(tintLayer, m === 'terrain' && !relief)
  put(hybridLayer, m === 'hybrid')
  // Hybrid draws its borders as lines over the ground and leaves the fills off
  put(bordersLayer, shows('borders') && m !== 'hybrid')
  showBorderLines(shows('borders') && m === 'hybrid')
  // The fills are opaque, so over the shaded ground they are let down far
  // enough for the hills to read through: a little on the political map, most
  // of the way on the terrain, where they are only a tint
  bordersLayer.setOpacity(m === 'terrain' ? 0.22 : relief ? 0.75 : 1)
  put(contoursLayer, shows('contours'))
  put(riversLayer, shows('rivers') && m !== 'hybrid')
  put(riversFineLayer, shows('rivers') && m === 'hybrid')
  put(zonesLayer, m === 'zones')
  if (m !== 'zones') zoneGlow.remove()
  put(daylightLayer, shows('daylight'))
  // The Satellite map breaks its water names differently (labelLines), and the
  // lines are written into the marker when it is made
  if ((m === 'hybrid') !== waterBrokenForSat) {
    waterBrokenForSat = m === 'hybrid'
    for (const d of labelDefs) if (WATER.has(d.type) && labelMarkers.has(d)) mountLabel(d)
  }
  // Names reserve space in the placement grid, so hiding them hands it back
  invalidatePlacements()
  updateLabels()
  updateCities()
  updateStations()
  renderMapSheet()
}

document.getElementById('bs-back')!.addEventListener('click', closeSheetList)

// --- Permalink ---
// The hash still tracks the view and the open panel, so a copied URL reopens
// where you left it. Nothing in the UI points at it any more; the Export button
// took that slot.

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
    h = `${+map.getZoom().toFixed(2)}/${cx}/${cy}`
  }
  history.replaceState(null, '', '#' + h)
}

// --- Export view (PNG) ---

const exportLabel = document.querySelector('.bs-btn[data-view="export"] .bs-btn-label') as HTMLElement
const exportCircle = document.querySelector('.bs-btn[data-view="export"] .bs-circle') as HTMLElement

// Named after whatever the view is about, so a folder of these reads as
// something other than avium-map (7).png
function exportName(): string {
  const subject = openCityName ?? openNationName
  const slug = subject?.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  return `avium-${slug || 'map'}.png`
}

let exporting = false

async function exportView() {
  if (exporting) return
  exporting = true
  flashExport('Rendering…', 0)
  try {
    // Half the size of Leaflet itself, for a button most sessions never press.
    // Importing it here keeps it out of the initial load — Vite gives it its own
    // chunk, fetched on the first click and cached after.
    const { default: html2canvas } = await import('html2canvas')
    const canvas = await html2canvas(mapEl, {
      // #map's own background, which is what shows outside the world bounds.
      // html2canvas fills with white otherwise. Read rather than hardcoded, so
      // the Time Zones map's black page comes through.
      backgroundColor: getComputedStyle(mapEl).backgroundColor,
      // The label text is re-rendered at this scale and comes out crisp. The
      // tiles are only upscaled, since past z5 there is no more detail to draw
      // — 2 is where the file size stops buying anything on a 3x display.
      scale: Math.min(window.devicePixelRatio || 1, 2),
      logging: false,
      // Rotated, the container is an oversized square carrying a rotate(). The
      // clone is a separate document, so dropping the transform there exports
      // the view upright without the live map flinching. What lands in frame is
      // that square: everything on screen, plus the corners the rotation filled.
      onclone: (_doc, el) => {
        el.style.transform = ''
      },
    })
    const blob = await new Promise<Blob | null>(res => canvas.toBlob(res, 'image/png'))
    if (!blob) throw new Error('canvas.toBlob returned null')
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = exportName()
    a.click()
    // Revoking in the same tick has been known to cancel the download before it
    // starts. Nothing else holds the blob, so a beat is enough.
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    replayAnim(exportCircle, 'bs-bounce')
    flashExport('Saved')
  } catch (err) {
    console.error('export failed', err)
    flashExport('Export failed')
  } finally {
    exporting = false
  }
}

// restoreAfter 0 holds the message up, for the render that has not finished yet.
// Clearing first stops a pending restore from wiping the message after it.
let flashTimer: ReturnType<typeof setTimeout> | undefined

function flashExport(text: string, restoreAfter = 1400) {
  clearTimeout(flashTimer)
  exportLabel.textContent = text
  replayAnim(exportLabel, 'bs-label-pop')
  if (!restoreAfter) return
  flashTimer = setTimeout(() => {
    exportLabel.textContent = 'Export'
    replayAnim(exportLabel, 'bs-label-pop')
  }, restoreAfter)
}

// --- Measure ---

type MeasureMode = 'distance' | 'area'

let measuring = false
let measureMode: MeasureMode = 'distance'
let measurePts: L.LatLng[] = []
let vertexMarkers: L.CircleMarker[] = []
let measureShape: L.Polyline<any> | null = null
const measureLayer = L.layerGroup()
const measureBar = document.getElementById('measure-bar')!
const measureTotal = document.getElementById('measure-total')!
const mapEl = document.getElementById('map')!

function fmtKm(km: number): string {
  return km >= 100 ? Math.round(km).toLocaleString('en-US') + ' km' : km.toFixed(1) + ' km'
}

// Areas run from a city's footprint to a hemisphere, so the unit moves with them
function fmtKm2(km2: number): string {
  const n =
    km2 >= 1e6
      ? (km2 / 1e6).toFixed(km2 >= 1e7 ? 1 : 2) + 'M'
      : km2 >= 1000
        ? Math.round(km2).toLocaleString('en-US')
        : km2.toFixed(km2 >= 10 ? 1 : 2)
  return `${n} km²`
}

// --- Land mask ---
//
// public/landmask.png, written by scripts/tile.mjs from the same drawing the
// tiles come from: one byte per 4px square holding how much of it is land. The
// tiles cannot answer this themselves — by the time they reach the browser they
// are pictures, and below native zoom they are not even the right pixels.
//
// Fetched the first time an area is measured rather than on load, because most
// visits never measure anything and it is 58KB.
const MASK_CELL = 4 // world px per texel — must match scripts/tile.mjs
let maskCov: Uint8Array | null = null
let maskW = 0
let maskPromise: Promise<void> | null = null
let maskFailed = false

function loadMask(): Promise<void> {
  if (!maskPromise) {
    maskPromise = new Promise<void>((resolve, reject) => {
      const img = new Image()
      img.onload = () => {
        const c = document.createElement('canvas')
        c.width = img.width
        c.height = img.height
        const ctx = c.getContext('2d')
        if (!ctx) return reject(new Error('no 2d context'))
        ctx.drawImage(img, 0, 0)
        const rgba = ctx.getImageData(0, 0, img.width, img.height).data
        maskW = img.width
        maskCov = new Uint8Array(img.width * img.height)
        // Grey, so every channel carries the same number; one is enough
        for (let i = 0; i < maskCov.length; i++) maskCov[i] = rgba[i * 4]
        resolve()
      }
      img.onerror = () => reject(new Error('landmask.png failed to load'))
      img.src = 'landmask.png'
    })
    // Cleared on failure so a later measurement tries again rather than
    // inheriting one bad network moment for the rest of the session
    maskPromise.catch(() => {
      maskPromise = null
      maskFailed = true
    })
  }
  return maskPromise
}

function landAt(x: number, y: number): number {
  if (!maskCov) return 0
  const mx = Math.min(maskW - 1, Math.max(0, Math.floor(x / MASK_CELL)))
  const my = Math.min(maskW - 1, Math.max(0, Math.floor(y / MASK_CELL)))
  return maskCov[my * maskW + mx] / 255
}

interface AreaParts {
  total: number
  land: number
  sea: number
}

// Scanline fill in map pixels, weighing each cell by the ground it actually
// covers at that latitude. The grid sizes itself to the shape so a bay is not
// answered in 9km steps and a continent does not cost a million cells; it is
// never coarser than the mask, which would throw away detail already paid for.
function polygonArea(pts: [number, number][]): AreaParts {
  const out: AreaParts = { total: 0, land: 0, sea: 0 }
  if (pts.length < 3) return out

  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const [x, y] of pts) {
    minX = Math.min(minX, x)
    maxX = Math.max(maxX, x)
    minY = Math.min(minY, y)
    maxY = Math.max(maxY, y)
  }
  const cell = Math.min(MASK_CELL, Math.max(Math.max(maxX - minX, maxY - minY) / 400, 0.02))

  const rows = Math.ceil((maxY - minY) / cell)
  const xs: number[] = []
  for (let r = 0; r < rows; r++) {
    const y = minY + (r + 0.5) * cell
    xs.length = 0
    // Even-odd crossings, so a shape drawn back over itself still has a
    // defensible answer rather than whatever the winding happened to be
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      const [x1, y1] = pts[j]
      const [x2, y2] = pts[i]
      if ((y1 <= y) === (y2 <= y)) continue
      xs.push(x1 + ((y - y1) / (y2 - y1)) * (x2 - x1))
    }
    xs.sort((a, b) => a - b)
    for (let k = 0; k + 1 < xs.length; k += 2) {
      const from = xs[k]
      const to = xs[k + 1]
      for (let c = Math.floor((from - minX) / cell); ; c++) {
        const x = minX + (c + 0.5) * cell
        if (x < from) continue
        if (x > to) break
        const a = pxArea(x, y, cell)
        const f = landAt(x, y)
        out.total += a
        out.land += a * f
        out.sea += a * (1 - f)
      }
    }
  }
  return out
}

// Unrounded, unlike toPx: a measurement should not quantise its own inputs
function measurePx(ll: L.LatLng): [number, number] {
  return [(ll.lng * TILE_GRID) / U, (-ll.lat * TILE_GRID) / U]
}

function setReadout(main: string, sub = '') {
  measureTotal.innerHTML = sub
    ? `<span class="mt-main">${main}</span><span class="mt-sub">${sub}</span>`
    : main
  measureTotal.classList.toggle('mt-wide', !!sub)
  replayAnim(measureTotal, 'bs-label-pop')
}

function syncDistance() {
  let km = 0
  for (let i = 1; i < measurePts.length; i++) {
    const [ax, ay] = measurePx(measurePts[i - 1])
    const [bx, by] = measurePx(measurePts[i])
    km += geoKm(toGeo(ax, ay), toGeo(bx, by))
  }
  setReadout(measurePts.length < 2 ? 'Click the map' : fmtKm(km))
}

function syncArea() {
  if (measurePts.length < 3) {
    setReadout(measurePts.length ? 'Three points to close a shape' : 'Click the map')
    return
  }
  const a = polygonArea(measurePts.map(measurePx))
  // The total stands on its own — it is the projection, not the mask. Only the
  // land and sea split has to wait for the file.
  if (!maskCov) {
    setReadout(fmtKm2(a.total), maskFailed ? 'land data unavailable' : 'measuring land…')
    return
  }
  const pct = a.total > 0 ? Math.round((a.land / a.total) * 100) : 0
  setReadout(fmtKm2(a.total), `land ${fmtKm2(a.land)} (${pct}%) · sea ${fmtKm2(a.sea)}`)
}

// Vertices are added incrementally (never rebuilt), so each dot's pop-in
// animation plays exactly once
function syncMeasure() {
  // L.Polygon extends L.Polyline, so one handle holds either — the mode picks
  // which is built and nothing after that has to care
  let shape = measureShape
  if (!shape) {
    const style = {
      color: '#fff', weight: 2, dashArray: '6 6', opacity: 0.9, interactive: false,
    }
    shape =
      measureMode === 'area'
        ? L.polygon([], { ...style, fillColor: '#0a84ff', fillOpacity: 0.16 })
        : L.polyline([], style)
    shape.addTo(measureLayer)
    measureShape = shape
  }
  shape.setLatLngs(measurePts)
  if (measureMode === 'area') syncArea()
  else syncDistance()
}

function addMeasurePoint(ll: L.LatLng) {
  measurePts.push(ll)
  vertexMarkers.push(L.circleMarker(ll, {
    radius: 4, color: '#fff', weight: 2, fillColor: '#0a84ff', fillOpacity: 1,
    interactive: false, className: 'measure-vertex',
  }).addTo(measureLayer))
  syncMeasure()
}

function startMeasure(mode: MeasureMode) {
  measuring = true
  measureMode = mode
  // Clear every surface first. A place panel or a browse list left open would
  // sit over the map the tool is about to be used on, and the rail would still
  // highlight a tab for a list that is no longer there.
  closeCityPanel()
  closeSheetList()
  markNavOpen(null)
  hideSheet()
  measurePts = []
  vertexMarkers = []
  measureShape = null
  measureLayer.clearLayers()
  measureLayer.addTo(map)
  measureBar.classList.remove('mb-closing')
  measureBar.hidden = false
  setReadout('Click the map')
  mapEl.classList.add('measure-mode')
  // Kicked off now rather than on the third click, so the shape usually closes
  // onto an answer that is already there
  // Guarded: the file can land after the tool has been closed again, and a
  // resolved fetch is no reason to redraw into a layer that is off the map
  if (mode === 'area') {
    const done = () => {
      if (measuring && measureMode === 'area') syncMeasure()
    }
    loadMask().then(done, done)
  }
}

function endMeasure() {
  measuring = false
  measurePts = []
  vertexMarkers = []
  measureShape = null
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
  syncMeasure()
})

document.getElementById('measure-clear')!.addEventListener('click', () => {
  measurePts = []
  for (const m of vertexMarkers) measureLayer.removeLayer(m)
  vertexMarkers = []
  syncMeasure()
})

document.getElementById('measure-done')!.addEventListener('click', endMeasure)

// --- Deep links: #city=Name, #nation=Name, or #zoom/x/y ---

{
  const h = decodeURIComponent(location.hash.slice(1))
  if (h.startsWith('city=')) {
    const name = h.slice(5)
    const c = cities.find(x => x.name === name) ?? cities.find(x => norm(x.name) === norm(name))
    if (c) {
      openCityPanel(c)
      focusCity(c)
    }
  } else if (h.startsWith('nation=')) {
    const n = nationByName.get(norm(h.slice(7)))
    if (n) {
      const pts = mapAggFor(n).pts
      openNationPanel(n)
      if (pts.length) {
        map.fitBounds(L.latLngBounds(pts).pad(0.2), {
          maxZoom: 5,
          paddingTopLeft: [sidebarWidth(), 0],
        })
        lastCover = sidebarWidth()
      }
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
const STATION_TIER: CityTier = { radius: 1.4, fontSize: 9.5, weight: 550 }
const STATION_SCALE = 1
const STATION_FS = Math.round(STATION_TIER.fontSize * STATION_SCALE)
const STATION_D = 11
// Wraps past this. The CSS keeps nowrap and renders the breaks this decides, so
// the collision box and the drawn text can never disagree about the line count.
const STATION_MAX_W = 78
const STATION_CHAR = 0.66 // the advance a city label measures with at weight 700, which is what these are

const stationLayer = L.layerGroup().addTo(map)

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
  if (!shows('stations') || map.getZoom() < STATION_MIN_ZOOM) return

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

    const m = new FlatMarker(px(station.x, station.y), {
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

if (DEV) loadStationProgress()
updateStations()
map.on('zoomend', updateStations)

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
  navLabel(saveBtn, 'Save •')
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

// The placer keeps its own copy of every placement in localStorage and lays it
// over the files on load, which is what makes a refresh safe mid-session. The
// same thing makes it a trap: after cities.json is changed out from under it —
// by a merge, or by scripts/nudge.mjs — the browser is still holding the old
// coordinates, and the next Save writes them straight back over the new ones.
//
// This drops all three stores and reloads, so the files on disk win. Armed like
// Delete, because it throws away unsaved work as readily as stale work.
const dropLocalBtn = document.getElementById('place-drop-local') as HTMLButtonElement
let dropArmed = false
let dropTimer = 0

function disarmDrop() {
  dropArmed = false
  clearTimeout(dropTimer)
  navLabel(dropLocalBtn, 'Reset')
  dropLocalBtn.classList.remove('is-armed')
}

dropLocalBtn.addEventListener('click', () => {
  if (!dropArmed) {
    dropArmed = true
    // A refresh is safe on its own — every placement is written to localStorage
    // as it is made, so reloading restores the session. This button is the one
    // thing that is not safe, because it clears exactly that store and then
    // reloads. Said plainly here, because "Sure?" is not: an edit session was
    // lost to this, and the button gave no sign it was about to happen.
    navLabel(dropLocalBtn, dirty ? 'Lose edits?' : 'Reset — sure?')
    dropLocalBtn.classList.add('is-armed')
    if (dirty) {
      statusEl.textContent = 'Unsaved placements will be lost — Save first to keep them'
      statusEl.className = 'status-warn'
    }
    dropTimer = window.setTimeout(disarmDrop, 3000)
    return
  }
  disarmDrop()
  for (const k of [SAVE_KEY, LABEL_KEY, STATION_KEY]) localStorage.removeItem(k)
  // Reload rather than re-read: the coordinates are already spread across the
  // city array, the markers and the placement cache, and putting the files back
  // over all of that is exactly what a fresh load does.
  location.reload()
})

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
  navLabel(saveBtn, 'Save')
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


const tabButtons = [...document.querySelectorAll<HTMLButtonElement>('.pp-tab[data-tab]')]

function setTab(next: PlacerTab, focus = true) {
  tab = next
  for (const b of tabButtons) b.classList.toggle('is-on', b.dataset.tab === next)
  const tools = [...document.querySelectorAll<HTMLElement>('.pp-toolbar [data-for]')]
  for (const el of tools) el.hidden = el.dataset.for !== next
  // With nothing left for the cities tab, the toolbar is a border-top and a gap
  // — a divider under the results marking off an empty strip
  const toolbar = document.querySelector('.pp-toolbar') as HTMLElement
  toolbar.hidden = !tools.some(el => !el.hidden)
  searchInput.placeholder = 'Search'
  // Only in dev: on the public map these markers are the whole point of clicking
  mapEl.classList.toggle('placing-cities', DEV && next === 'cities')
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
  if (focus) searchInput.focus()
}

for (const b of tabButtons) {
  b.addEventListener('click', () => setTab(b.dataset.tab as PlacerTab))
}

// No focus on the initial call: the panel is hidden outside ?dev, and focusing
// an input inside it would take the caret away from the page for everyone else
setTab('cities', false)

// --- Explore ---
//
// The photographed cities as photographs: each one stands on the map as a small
// rounded-square pin of its own picture, the rest of the map dimmed around them.
// Pins that would overlap merge into one showing the biggest city's photo and a
// count, and the groups are worked out once per zoom from the closest zoom
// outward, so zooming in only ever splits a group and a city that has its own
// pin keeps it. A route through all of them drives a tour bar and the gallery.

const PIN = 40 // the photo square
const TIP = 7 // the pointer under it, whose tip is the city

let touring = false
let tourIdx = 0

map.createPane('explore-cards')
map.getPane('explore-cards')!.style.zIndex = '620' // over the dimmed markers at 600
const cardLayer = L.layerGroup()
const cardMarkers = new Map<City, L.Marker>()

// A closed loop through every photographed city: nearest neighbour from the
// westernmost, then 2-opt until no two legs cross. Forty-odd points, so this is
// instant, and it is worked out once.
let route: City[] | null = null
function tourRoute(): City[] {
  if (route) return route
  const pts = [...(photoSet ?? [])].filter(c => c.x != null && c.y != null)
  const d = (a: City, b: City) => Math.hypot(a.x! - b.x!, a.y! - b.y!)
  const left = pts.sort((a, b) => a.x! - b.x!)
  const tour: City[] = left.length ? [left.shift()!] : []
  while (left.length) {
    const last = tour[tour.length - 1]
    let bi = 0
    for (let i = 1; i < left.length; i++) if (d(last, left[i]) < d(last, left[bi])) bi = i
    tour.push(left.splice(bi, 1)[0])
  }
  const n = tour.length
  for (let improved = n > 3; improved; ) {
    improved = false
    for (let i = 0; i < n - 1; i++) {
      for (let j = i + 2; j < n; j++) {
        if (i === 0 && j === n - 1) continue
        const a = tour[i], b = tour[i + 1], c = tour[j], e = tour[(j + 1) % n]
        if (d(a, c) + d(b, e) < d(a, b) + d(c, e) - 1e-9) {
          tour.splice(i + 1, j - i, ...tour.slice(i + 1, j + 1).reverse())
          improved = true
        }
      }
    }
  }
  return (route = tour)
}

// Which side of its city a pin stands on: above, right, left or below, tried in
// that order. A pin that has no room above can lean off to a side before it has
// to fold into a neighbour's group.
type Side = 't' | 'r' | 'l' | 'b'
const SIDES: Side[] = ['t', 'r', 'l', 'b']
type Cluster = { rep: City; members: City[]; side: Side }
const clusterCache = new Map<number, Cluster[]>()
const zKey = (z: number) => Math.min(MAX_ZOOM, Math.max(2, Math.round(z * 2) / 2))

// The ground a pin and its name take up at a zoom, in the placer's screen space.
// Above, the name sits under the pointer's tip; on any other side it sits under
// the photo.
function pinBox(c: City, z: number, side: Side): Box {
  const box = sideBox(c, z, side)
  // Room for a group's count badge, which hangs off the photo's top right corner
  return { x: box.x, y: box.y - 9, w: box.w + 12, h: box.h + 9 }
}

function sideBox(c: City, z: number, side: Side): Box {
  const pt = ptAt(c, z)
  const half = Math.max(PIN + 6, c.name.length * 6.4 + 6) / 2
  const reach = PIN + TIP
  if (side === 't') return { x: pt.x - half, y: pt.y - reach - 4, w: half * 2, h: reach + 22 }
  if (side === 'b') return { x: pt.x - half, y: pt.y - 4, w: half * 2, h: reach + 22 }
  const mid = side === 'r' ? pt.x + TIP + PIN / 2 : pt.x - TIP - PIN / 2
  const x0 = Math.min(mid - half, side === 'r' ? pt.x + TIP - 3 : pt.x - reach - 3)
  const x1 = Math.max(mid + half, side === 'r' ? pt.x + reach + 3 : pt.x - TIP + 3)
  return { x: x0, y: pt.y - PIN / 2 - 3, w: x1 - x0, h: PIN + 22 }
}

// The groups at a zoom: the groups one half-step closer in, with any whose pins
// would overlap here folded into the bigger one. The biggest city in a group is
// always its face, at every zoom it is a group, so it never swaps for another.
function clustersAt(z: number): Cluster[] {
  const k = zKey(z)
  const hit = clusterCache.get(k)
  if (hit) return hit
  const from: Cluster[] =
    k >= MAX_ZOOM
      ? tourRoute().map(c => ({ rep: c, members: [c], side: 't' as Side }))
      : clustersAt(k + 0.5).map(g => ({ rep: g.rep, members: [...g.members], side: 't' as Side }))
  from.sort((a, b) => b.rep.gdp - a.rep.gdp)
  // No pin may stand over another group's city, whichever side it leans
  const spots = from.map(g => ptAt(g.rep, k))
  const kept: { g: Cluster; box: Box }[] = []
  for (const [i, g] of from.entries()) {
    let box: Box | null = null
    for (const side of SIDES) {
      const b = pinBox(g.rep, k, side)
      if (kept.some(o => boxesOverlap(o.box, b))) continue
      if (spots.some((q, j) => j !== i && q.x > b.x && q.x < b.x + b.w && q.y > b.y && q.y < b.y + b.h)) continue
      box = b
      g.side = side
      break
    }
    if (box) {
      kept.push({ g, box })
      continue
    }
    // Nowhere to stand: fold into the nearest group already placed
    const pt = spots[i]
    let into = kept[0]
    let best = Infinity
    for (const o of kept) {
      const q = ptAt(o.g.rep, k)
      const d = (q.x - pt.x) ** 2 + (q.y - pt.y) ** 2
      if (d < best) { best = d; into = o }
    }
    if (into) into.g.members.push(...g.members)
    else kept.push({ g, box: pinBox(g.rep, k, 't') })
  }
  const res = kept.map(o => o.g)
  clusterCache.set(k, res)
  return res
}

// The first zoom at which a city stands on its own pin
function soloZoom(c: City): number {
  for (let k = 2; k <= MAX_ZOOM; k += 0.5) {
    if (clustersAt(k).some(g => g.rep === c && g.members.length === 1)) return k
  }
  return MAX_ZOOM
}

function pinIcon(g: Cluster): L.DivIcon {
  const c = g.rep
  const more = g.members.length - 1
  return L.divIcon({
    className: `xp xp-${g.side}`,
    html:
      `<div class="xp-pin"><img src="${cardUrl(c)}" alt="">` +
      `<span class="xp-cap"><b>${c.name}</b><span>${c.nation}${more ? ` · ${more} more` : ''}</span></span></div>` +
      (more ? `<span class="xp-count">+${more}</span>` : '') +
      `<i class="xp-tip"></i><span class="xp-name">${c.name}</span>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  })
}

// Every photographed city, mapped to the pin that stands for it right now
let pinOf = new Map<City, L.Marker>()

function renderCards() {
  cardLayer.clearLayers()
  cardMarkers.clear()
  pinOf = new Map()
  carded = new Set()
  if (!exploring) return
  for (const g of clustersAt(map.getZoom())) {
    const m = L.marker(px(g.rep.x!, g.rep.y!), {
      icon: pinIcon(g),
      pane: 'explore-cards',
      keyboard: false,
      riseOnHover: true,
    })
    m.on('click', () => {
      if (g.members.length === 1) return goTour(tourRoute().indexOf(g.rep))
      // A group opens by zooming to where it first comes apart, centred on it
      let k = zKey(map.getZoom()) + 0.5
      while (k < MAX_ZOOM && clustersAt(k).find(h => h.rep === g.rep)!.members.length === g.members.length) k += 0.5
      const cx = g.members.reduce((s, c) => s + c.x!, 0) / g.members.length
      const cy = g.members.reduce((s, c) => s + c.y!, 0) / g.members.length
      focusOn(cx, cy, Math.min(MAX_ZOOM, k))
    })
    cardLayer.addLayer(m)
    cardMarkers.set(g.rep, m)
    for (const c of g.members) {
      pinOf.set(c, m)
      carded.add(c)
    }
  }
  syncExploreMarkers()
  markCards()
}

function markCards() {
  const cur = touring ? pinOf.get(tourRoute()[tourIdx]) : undefined
  for (const m of cardMarkers.values()) {
    const el = m.getElement()
    if (!el) continue
    el.classList.toggle('xp-on', m === cur)
    m.setZIndexOffset(m === cur ? 1000 : 0)
  }
}

const xBar = document.getElementById('explore-bar')!
const xLabel = document.getElementById('xb-label')!

// The photographed city nearest the middle of the map you can actually see
function nearestToView(): number {
  const r = tourRoute()
  const size = map.getSize()
  const mid = map.containerPointToLatLng([(size.x + sidebarWidth()) / 2, size.y / 2])
  let best = 0
  let bd = Infinity
  r.forEach((c, i) => {
    const p = L.latLng(px(c.x!, c.y!))
    const dd = (p.lat - mid.lat) ** 2 + (p.lng - mid.lng) ** 2
    if (dd < bd) { bd = dd; best = i }
  })
  return best
}

function syncBar() {
  const r = tourRoute()
  if (!r.length) return
  if (!touring) tourIdx = nearestToView()
  xLabel.innerHTML = `<b>${r[tourIdx].name}</b><span>${tourIdx + 1} / ${r.length}</span>`
}

function goTour(i: number) {
  const r = tourRoute()
  if (!r.length) return
  touring = true
  tourIdx = (i + r.length) % r.length
  const c = r[tourIdx]
  openCityPanel(c)
  focusOn(c.x!, c.y!, Math.max(zKey(map.getZoom()), soloZoom(c)))
  renderCards()
  syncBar()
}

// The first press goes to where the tour starts, the city nearest the view;
// every press after that moves along the route
function stepTour(dir: 1 | -1) {
  goTour(touring ? tourIdx + dir : tourIdx)
}

// Explore is a mode of the map, not a page in the column: the tab switches it on
// and off and stays lit while it is on, and the column is left clear for the map
function startExplore() {
  closeSheetList()
  exploring = true
  touring = false
  markNavOpen(null)
  document.body.classList.add('exploring')
  cardLayer.addTo(map)
  renderCards()
  xBar.classList.remove('mb-closing')
  xBar.hidden = false
  syncBar()
}

function endExplore() {
  if (!exploring) return
  exploring = false
  touring = false
  markNavOpen(null)
  document.body.classList.remove('exploring')
  cardLayer.clearLayers()
  cardMarkers.clear()
  carded = new Set()
  syncExploreMarkers()
  map.removeLayer(cardLayer)
  xBar.hidden = true
}

document.querySelector('.bs-btn[data-view="explore"]')!.addEventListener('click', () => {
  if (exploring) endExplore()
  else startExplore()
})

document.getElementById('xb-prev')!.addEventListener('click', () => stepTour(-1))
document.getElementById('xb-next')!.addEventListener('click', () => stepTour(1))
document.getElementById('xb-close')!.addEventListener('click', endExplore)

document.addEventListener('keydown', e => {
  if (!exploring || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return
  if (e.target instanceof Element && e.target.closest('input, textarea, select')) return
  e.preventDefault()
  stepTour(e.key === 'ArrowLeft' ? -1 : 1)
})

map.on('zoomend', () => {
  if (exploring) renderCards()
})
map.on('moveend', () => {
  if (exploring && !touring) syncBar()
})

// Every way the column opens or closes ends in its hidden attribute flipping, so
// that is the one place to watch. The callback runs after the code that flipped
// it, which lets a focusOn in the same breath record its own placement first.
lastCover = sidebarWidth()
{
  const watch = new MutationObserver(syncCover)
  for (const id of ['city-panel', 'bs-list']) {
    watch.observe(document.getElementById(id)!, { attributes: true, attributeFilter: ['hidden'] })
  }
}

// --- Time zones and daylight ---
//
// Zones come from scripts/zones.mjs: one clock per nation, set by where its land
// sits, with the very widest split along meridians. Sea and unclaimed land keep
// solar time. The layer is a tiled picture like the borders; zones.png beside it
// is a quarter-size lookup (red = offset + 13, 0 for no zone) for saying which
// zone a point is in.

map.createPane('zones')
map.getPane('zones')!.style.zIndex = '450' // over the borders and rivers, under day and night and the markers
map.getPane('zones')!.style.pointerEvents = 'none'
map.createPane('daylight')
map.getPane('daylight')!.style.zIndex = '455'
map.getPane('daylight')!.style.pointerEvents = 'none'

const zonesLayer = tiledLayer('zones', 'zones')


// Hover: the zone under the pointer lights up everywhere it is, and a readout
// gives its time. Over sea and unclaimed land that is the solar hour.
let zoneLook: Uint8Array | null = null
let zoneLookLoading = false
function loadZoneLookup() {
  if (zoneLook || zoneLookLoading) return
  zoneLookLoading = true
  const img = new Image()
  img.onload = () => {
    const c = document.createElement('canvas')
    c.width = c.height = ZONE_LOOKUP
    const ctx = c.getContext('2d')!
    ctx.drawImage(img, 0, 0)
    const rgba = ctx.getImageData(0, 0, ZONE_LOOKUP, ZONE_LOOKUP).data
    zoneLook = new Uint8Array(ZONE_LOOKUP * ZONE_LOOKUP)
    for (let i = 0; i < zoneLook.length; i++) zoneLook[i] = rgba[i * 4]
  }
  img.onerror = () => (zoneLookLoading = false)
  img.src = 'zones.png'
}

// The zone at a map point: the lookup covers sea and unclaimed land too (solar
// time there); solar time is the answer anywhere it has not loaded
function zoneAt(x: number, y: number): number {
  if (zoneLook && x >= 0 && y >= 0 && x < CONTENT && y < CONTENT) {
    const v = zoneLook[Math.floor(y / 4) * ZONE_LOOKUP + Math.floor(x / 4)]
    if (v) return v - 13
  }
  return solarZone(x, y)
}

const zoneTip = document.createElement('div')
zoneTip.className = 'zone-tip'
zoneTip.hidden = true
map.getContainer().appendChild(zoneTip)

// The highlight is drawn tile by tile from zone-id tiles at the zone map's own
// detail, so its edge sits exactly on the gold line at every zoom. Each tile
// keeps its ids and is repainted when the hovered zone changes: the zone lifted
// in white, with a crisp white edge.
type GlowTile = HTMLCanvasElement & { ids?: Uint8Array }
let glowZone: number | null = null

function paintGlow(c: GlowTile) {
  const ctx = c.getContext('2d')!
  ctx.clearRect(0, 0, 256, 256)
  const ids = c.ids
  if (!ids || glowZone === null) return
  const v = glowZone + 13
  const img = ctx.createImageData(256, 256)
  const a = img.data
  for (let p = 0; p < 65536; p++) {
    if (ids[p] !== v) continue
    const x = p & 255, y = p >> 8
    // a tile's own edge is not the zone's, so off-tile neighbours count as same
    const edge =
      (x > 0 && ids[p - 1] !== v) || (x < 255 && ids[p + 1] !== v) ||
      (y > 0 && ids[p - 256] !== v) || (y < 255 && ids[p + 256] !== v)
    a[p * 4] = a[p * 4 + 1] = a[p * 4 + 2] = 255
    a[p * 4 + 3] = edge ? 235 : 38
  }
  ctx.putImageData(img, 0, 0)
}

const ZoneGlowLayer = L.GridLayer.extend({
  createTile(coords: L.Coords, done: L.DoneCallback) {
    const c = document.createElement('canvas') as GlowTile
    c.width = c.height = 256
    const img = new Image()
    img.onload = () => {
      const r = document.createElement('canvas')
      r.width = r.height = 256
      const rctx = r.getContext('2d')!
      rctx.drawImage(img, 0, 0)
      const d = rctx.getImageData(0, 0, 256, 256).data
      c.ids = new Uint8Array(65536)
      for (let p = 0; p < 65536; p++) c.ids[p] = d[p * 4]
      paintGlow(c)
      done(undefined, c)
    }
    img.onerror = () => done(undefined, c)
    img.src = `tiles/zoneid/${coords.z}/${coords.y}/${coords.x}.png?v=${(zonesData as { v?: string }).v ?? ''}`
    return c
  },
})
const zoneGlow = new (ZoneGlowLayer as unknown as new (o: L.GridLayerOptions) => L.GridLayer)({
  pane: 'zones',
  zIndex: 2,
  maxNativeZoom: 5,
  maxZoom: MAX_ZOOM,
  bounds: contentBounds,
  updateWhenZooming: false,
})

// The layer is only on the map while something is lit. Its tiles each decode and
// keep a canvas, and loaded behind every pan they made opening the side panel
// over the zone map stutter; so it comes off when the pointer leaves the map,
// which is on its way to the panel.
function lightZone(z: number | null) {
  if (z === glowZone) return
  glowZone = z
  if (z === null) {
    zoneGlow.remove()
    return
  }
  if (!map.hasLayer(zoneGlow)) zoneGlow.addTo(map)
  const tiles = (zoneGlow as unknown as { _tiles: Record<string, { el: GlowTile }> })._tiles
  for (const k in tiles) paintGlow(tiles[k].el)
}

map.on('mousemove', (e: L.LeafletMouseEvent) => {
  if (!map.hasLayer(zonesLayer)) return
  const [x, y] = toPx(e.latlng)
  if (x < 0 || y < 0 || x >= CONTENT || y >= CONTENT) {
    zoneTip.hidden = true
    lightZone(null)
    return
  }
  const z = zoneAt(x, y)
  zoneTip.innerHTML = `<b>${hhmm(z)}</b> ${fmtZone(z)}`
  zoneTip.style.left = `${e.containerPoint.x}px`
  zoneTip.style.top = `${e.containerPoint.y}px`
  zoneTip.classList.toggle('flip', e.containerPoint.x > map.getSize().x - 160)
  zoneTip.hidden = false
  lightZone(z)
})
map.getContainer().addEventListener('mouseleave', () => {
  zoneTip.hidden = true
  lightZone(null)
})

zonesLayer.on('add', loadZoneLookup)
zonesLayer.on('remove', () => {
  zoneTip.hidden = true
  lightZone(null)
})

// Day and night: the sun's height over every point, from Avium's 45-degree tilt
// with the spring equinox on 21 March, as the Time Counter draws it. Shaded on a
// small canvas and stretched over the world, since the edge is soft anyway, with
// the terminator itself drawn exactly as a line.
const SHADE = 400
const RAD = Math.PI / 180
const shadeCanvas = document.createElement('canvas')
shadeCanvas.width = shadeCanvas.height = SHADE
const shadeOverlay = L.imageOverlay(shadeCanvas.toDataURL(), imgBounds, { pane: 'daylight', interactive: false })
const terminator = L.polyline([], {
  pane: 'daylight',
  renderer: L.svg({ pane: 'daylight' }),
  color: 'rgba(255, 255, 255, 0.7)',
  weight: 1,
  interactive: false,
})
const daylightLayer = L.layerGroup([shadeOverlay, terminator])

function drawDaylight(ms: number) {
  const y = new Date(ms).getUTCFullYear()
  const L0 = (2 * Math.PI * (ms - Date.UTC(y, 2, 21))) / (365.2425 * 86_400_000)
  const dec = Math.asin(Math.sin(45 * RAD) * Math.sin(L0))
  const hours = (((ms % 86_400_000) + 86_400_000) % 86_400_000) / HOUR
  const sunLon = (12 - hours) * 15
  const sd = Math.sin(dec), cd = Math.cos(dec), step = CONTENT / SHADE
  const ctx = shadeCanvas.getContext('2d')!
  const img = ctx.createImageData(SHADE, SHADE)
  const a = img.data
  for (let j = 0; j < SHADE; j++) {
    for (let i = 0; i < SHADE; i++) {
      const g = toGeo((i + 0.5) * step, (j + 0.5) * step)
      const la = g.lat * RAD
      const alt = Math.sin(la) * sd + Math.cos(la) * cd * Math.cos((g.lon - sunLon) * RAD)
      const p = (j * SHADE + i) * 4
      a[p + 3] = Math.round(Math.min(1, Math.max(0, (0.03 - alt) / 0.1)) * 110)
    }
  }
  ctx.putImageData(img, 0, 0)
  shadeOverlay.setUrl(shadeCanvas.toDataURL())

  // sin(lat)sin(dec) + cos(lat)cos(dec)cos(dLon) = 0, solved for lat; broken
  // where it jumps across the world rather than drawn straight over it
  const lines: L.LatLngExpression[][] = []
  if (Math.abs(dec) > 1e-4) {
    let run: L.LatLngExpression[] = []
    let prev: { x: number; y: number } | null = null
    for (let lon = -180; lon <= 180; lon += 0.5) {
      const p = fromGeo(Math.atan(-Math.cos((lon - sunLon) * RAD) / Math.tan(dec)) / RAD, lon)
      if (prev && Math.hypot(p.x - prev.x, p.y - prev.y) > CONTENT * 0.2) {
        lines.push(run)
        run = []
      }
      run.push(px(p.x, p.y))
      prev = p
    }
    lines.push(run)
  }
  terminator.setLatLngs(lines)
}
daylightLayer.on('add', () => drawDaylight(icNow()))

// The ground: the same land and sea as the base, modelled by the terrain under
// them (relief) or coloured by height as well (terrain), and the terrain's
// colours unshaded (tint) for when Relief is off. Built by topo/ from real
// elevation carried through the Pangaea overlay; see topo/README.md.
const reliefLayer = tiledLayer('relief', 'tilePane', { ext: 'webp', maxNative: 6 })
const terrainLayer = tiledLayer('terrain', 'tilePane', { ext: 'webp', maxNative: 6 })
const tintLayer = tiledLayer('tint', 'tilePane', { ext: 'webp', maxNative: 6 })
// The terrain in the colours the ground has from space (real imagery through the warps under the relief map's
// hillshade; topo/scripts/colour.py, render.py) over a sea tinted by its depth and its cold
// (seacolour.py), with no line inked at the coast. Drawn at 24000px (topo/scripts/hybrid.py), a level finer
// again than the relief: this is the map people zoom into to look at the ground
const hybridLayer = tiledLayer('hybrid', 'tilePane', { ext: 'webp', maxNative: 7 })
// The rivers at something near their real width, in the colour of that sea's shallows: the rivers layer draws
// them several kilometres wide, which over this ground outweighs the borders
const riversFineLayer = tiledLayer('rivers-fine', 'overlayPane', { maxNative: 6, zIndex: 3 })

// The Hybrid map's borders: every border as a line of one weight at every zoom,
// traced off the fills by scripts/borderlines.mjs. A tiled line would be eight
// times as thick at the deepest zoom as at the level it was cut for. In a pane
// of its own over the rivers, because a border that follows a river was moved
// to run down the middle of it and would be hidden for its whole length.
map.createPane('borderlines')
map.getPane('borderlines')!.style.zIndex = '440' // over the rivers, under the zones and the markers
map.getPane('borderlines')!.style.pointerEvents = 'none'
let borderLines: L.Polyline | null = null
// Apple Maps' satellite view, measured zoom by zoom (17 Nov 2026): one dark plum
// line with no casing, a pixel wide from the whole world down to a country, and
// only a little heavier closer in (1.5px where a city fills the screen). This map
// stops about where that reaches 1.5.
//
// Zoomed out it goes under Apple's pixel. This world is a quarter the size of
// that one and has as many borders, so at the widest views a country is a dozen
// pixels across and a full pixel round each of them is most of what there is to
// see (the user, of the first version: "why are the borders still so thick zoomed
// out"). From user zoom 2 outward the line is 0.6px and a little fainter, and it
// reaches the pixel at zoom 7.
//
// The colour is not Apple's. Theirs is a dark plum, which this map carried until
// 17 Nov 2026; their ground is pale and ours is deep forest green, on which that
// line all but disappeared (the user: "You also cannot be using the same border
// colors as Apple. They have a lighter satellite map"). Six were drawn over the
// real ground, plum to white. A light orchid was tried first for keeping some of
// the plum ("wildly out of place for a professional Apple Maps-like app"); this is
// plain white let down, which is what the other satellite maps with dark ground
// draw a border in.
const BORDER_LINE = '#ffffff'
const borderWeight = (z: number) =>
  z <= 3 ? 0.6 : z <= 5.5 ? 0.6 + ((z - 3) / 2.5) * 0.4 : 1 + ((z - 5.5) / 2.5) * 0.6
const borderOpacity = (z: number) => (z <= 3 ? 0.55 : z >= 5.5 ? 0.7 : 0.55 + ((z - 3) / 2.5) * 0.15)
// The trace runs along pixel edges (scripts/borderlines.mjs), so a border arrives
// as unit steps and square corners, and at the deepest zooms each of those is
// sixteen screen pixels of staircase. Every corner is cut back by up to `r` px of
// the drawing along each of its two sides, twice, which turns a staircase into
// its diagonal and a drawn corner into a tight curve; no point moves further than
// that, so a line still runs down the middle of the river it follows.
function roundCorners(l: number[], r: number): number[] {
  const n = l.length / 2
  if (n < 3) return l
  const closed = l[0] === l[2 * n - 2] && l[1] === l[2 * n - 1]
  const out: number[] = []
  const cut = (ax: number, ay: number, bx: number, by: number) => {
    // from b toward a, by r or a third of the side, whichever is less
    const d = Math.hypot(ax - bx, ay - by)
    const t = d > 0 ? Math.min(r, d / 3) / d : 0
    out.push(bx + (ax - bx) * t, by + (ay - by) * t)
  }
  const m = closed ? n - 1 : n
  for (let i = 0; i < m; i++) {
    if (!closed && (i === 0 || i === n - 1)) {
      out.push(l[2 * i], l[2 * i + 1])
      continue
    }
    const a = (i - 1 + m) % m
    const c = (i + 1) % m
    cut(l[2 * a], l[2 * a + 1], l[2 * i], l[2 * i + 1])
    cut(l[2 * c], l[2 * c + 1], l[2 * i], l[2 * i + 1])
  }
  if (closed) out.push(out[0], out[1])
  return out
}
let borderLinesOn = false
let borderLinesLoading = false
function syncBorderLines() {
  if (!borderLines) return
  const z = map.getZoom()
  borderLines.setStyle({ weight: borderWeight(z), opacity: borderOpacity(z) })
}
map.on('zoomend', syncBorderLines)
function showBorderLines(on: boolean) {
  borderLinesOn = on
  if (borderLines) {
    on ? map.hasLayer(borderLines) || borderLines.addTo(map) : borderLines.remove()
    return
  }
  // Fetched the first time Hybrid is opened, so no other map pays for it
  if (!on || borderLinesLoading) return
  borderLinesLoading = true
  import('./data/borderlines.json').then(m => {
    const lines = (m.default as number[][]).map(raw => {
      const l = roundCorners(roundCorners(raw, 1.5), 0.75)
      const pts: L.LatLngExpression[] = []
      for (let i = 0; i < l.length; i += 2) pts.push(px(l[i], l[i + 1]))
      return pts
    })
    // A light line in a dark casing was tried first, on the reasoning that no one
    // colour stands out against a photograph: it read as a road, and three pixels
    // of it outweighed the ground it ran over (the user: "way too thick").
    borderLines = L.polyline(lines, {
      pane: 'borderlines',
      renderer: L.svg({ pane: 'borderlines' }),
      color: BORDER_LINE,
      weight: borderWeight(map.getZoom()),
      opacity: borderOpacity(map.getZoom()),
      lineJoin: 'round',
      lineCap: 'round',
      // the default drops points closer than a pixel, which puts the corners back
      smoothFactor: 0.3,
      interactive: false,
    })
    // Whatever the map is by the time the lines arrive, not what it was when they were asked for
    if (borderLinesOn) borderLines.addTo(map)
  })
}

// --- Map sheet ---
//
// Apple Maps' map card: the four maps as picture tiles, and under them the
// switches in groups. A switch the current map has no room for goes grey but
// keeps its setting, so the map it belongs to comes back as it was left.

const MODE_TILES: [MapMode, string, string][] = [
  ['hybrid', 'Satellite', hybridThumb],
  ['political', 'Political', politicalThumb],
  ['terrain', 'Terrain', terrainThumb],
  ['zones', 'Time Zones', zonesThumb],
]

const SHEET_GROUPS: [string, [keyof typeof modeAllows, string][]][] = [
  ['Shading', [['relief', 'Relief'], ['daylight', 'Day & Night']]],
  ['Lines', [['borders', 'Borders'], ['rivers', 'Rivers'], ['contours', 'Contour Lines']]],
  ['Labels', [['territories', 'Nation Names'], ['water', 'Water Names'], ['cities', 'Cities'], ['stations', 'Research Stations']]],
]
const SHEET_ROWS = SHEET_GROUPS.flatMap(([, rows]) => rows)

const sheetRow = (label: string, attr: string, key = '') =>
  `<label class="ms-row"${key ? ` data-row="${key}"` : ''}><span>${label}</span>` +
  `<input type="checkbox" class="set-switch" ${attr}></label>`

const mapSheet = document.createElement('div')
mapSheet.id = 'map-sheet'
mapSheet.hidden = true
mapSheet.innerHTML =
  `<div class="ms-head"><span>Map</span><button class="ms-close" aria-label="Close">✕</button></div>` +
  `<div class="ms-modes">` +
  MODE_TILES.map(
    ([m, label, src]) =>
      `<button class="ms-mode" data-mode="${m}"><span class="ms-thumb"><img src="${src}" alt=""></span>` +
      `<span class="ms-label">${label}</span></button>`
  ).join('') +
  `</div>` +
  SHEET_GROUPS.map(
    ([title, rows]) =>
      `<div class="ms-group">${title}</div><div class="ms-card">` +
      rows.map(([k, label]) => sheetRow(label, `data-set="${k}"`, k)).join('') +
      `</div>`
  ).join('') +
  (DEV ? `<div class="ms-group">Dev</div><div class="ms-card">${sheetRow('Pangaea', 'data-dev="pangaea"')}</div>` : '')
document.body.appendChild(mapSheet)

function renderMapSheet() {
  for (const b of mapSheet.querySelectorAll<HTMLElement>('.ms-mode')) {
    const on = b.dataset.mode === settings.mode
    b.classList.toggle('is-on', on)
    b.setAttribute('aria-pressed', String(on))
  }
  for (const [k] of SHEET_ROWS) {
    const row = mapSheet.querySelector<HTMLElement>(`[data-row="${k}"]`)!
    const box = row.querySelector('input')!
    const allowed = modeAllows[k](settings.mode)
    box.checked = settings[settingKey(k)] as boolean
    box.disabled = !allowed
    row.classList.toggle('is-locked', !allowed)
  }
}

function openMapSheet(open: boolean) {
  mapSheet.hidden = !open
  mapBtn.classList.toggle('is-on', open)
  if (open) renderMapSheet()
}

mapBtn.addEventListener('click', e => {
  e.preventDefault()
  openMapSheet(mapSheet.hidden)
})
mapSheet.querySelector('.ms-close')!.addEventListener('click', () => openMapSheet(false))
mapSheet.addEventListener('click', e => {
  const tile = (e.target as Element).closest<HTMLElement>('.ms-mode')
  if (!tile) return
  settings.mode = tile.dataset.mode as MapMode
  saveSettings()
  applySettings()
})
mapSheet.addEventListener('change', e => {
  const box = e.target as HTMLInputElement
  if (box.dataset.dev === 'pangaea') {
    if (pangaeaLayer) box.checked ? pangaeaLayer.addTo(map) : pangaeaLayer.remove()
    return
  }
  const k = box.dataset.set as keyof typeof modeAllows | undefined
  if (!k) return
  ;(settings[settingKey(k)] as boolean) = box.checked
  saveSettings()
  applySettings()
})
document.addEventListener('click', e => {
  if (!mapSheet.hidden && !mapSheet.contains(e.target as Node) && !mapBtn.contains(e.target as Node)) openMapSheet(false)
})
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !mapSheet.hidden) openMapSheet(false)
})

// --- Time ---
//
// What was the Avium Time Counter: the in-RP date under the logo, and a Time tab
// with the live clock, the countdowns to the next day, week, month and year, and
// a converter between real time and in-RP time. All of it in UTC on the IC side.

const WEEKDAYS_LONG = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
  'October', 'November', 'December']

const irpDate = document.getElementById('irp-date') as HTMLButtonElement
function syncIrpDate(ms = icNow()) {
  const d = new Date(ms)
  irpDate.innerHTML =
    `<b>${d.getUTCDate()} ${MONTHS_LONG[d.getUTCMonth()]} ${d.getUTCFullYear()}</b>` +
    `<span>${WEEKDAYS_LONG[d.getUTCDay()]} · ${two(d.getUTCHours())}:${two(d.getUTCMinutes())} UTC</span>`
}
syncIrpDate()
irpDate.addEventListener('click', () => (navOpen() === 'time' ? closeSheetList() : openTimeView()))

function duration(ms: number): string {
  const t = Math.max(0, Math.round(ms / 1000))
  const d = Math.floor(t / 86400), h = Math.floor((t % 86400) / 3600), m = Math.floor((t % 3600) / 60), s = t % 60
  if (d) return `${d}d ${h}h ${two(m)}m`
  if (h) return `${h}h ${two(m)}m ${two(s)}s`
  return `${m}m ${two(s)}s`
}

const shortDate = (ms: number) => {
  const d = new Date(ms)
  return `${WEEKDAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

// The four countdowns. Each runs from the start of the current day, week
// (Monday), month or year to the next, and says how much real time is left at
// the current rate, which IC date it ends on, and the real moment that is in the
// viewer's own time zone.
const realWhen = new Intl.DateTimeFormat(undefined, {
  weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
})
function nextRows(ms: number, mult: number): string {
  const d = new Date(ms)
  const y = d.getUTCFullYear(), mo = d.getUTCMonth()
  const day = Date.UTC(y, mo, d.getUTCDate())
  const week = day - ((d.getUTCDay() + 6) % 7) * 86_400_000
  const spans: [string, number, number][] = [
    ['Day', day, day + 86_400_000],
    ['Week', week, week + 7 * 86_400_000],
    ['Month', Date.UTC(y, mo, 1), Date.UTC(y, mo + 1, 1)],
    ['Year', Date.UTC(y, 0, 1), Date.UTC(y + 1, 0, 1)],
  ]
  return spans
    .map(([name, a, b]) =>
      `<div class="tv-row"><div class="tv-row-top"><span>${name}</span><b>${duration((b - ms) / mult)}</b></div>` +
      `<div class="tv-bar"><i style="width:${(((ms - a) / (b - a)) * 100).toFixed(2)}%"></i></div>` +
      `<div class="tv-row-at"><span>${shortDate(b)}</span><span>${realWhen.format(Date.now() + (b - ms) / mult)}</span></div></div>`
    )
    .join('')
}

let timeView: HTMLElement | null = null
let timeRaf = 0
let lastTvSec = -1

function openTimeView() {
  openColumn('Time', false, 'time')
  const now = new Date()
  const off = -now.getTimezoneOffset() / 60
  const ic = new Date(icNow())
  bsItems.innerHTML =
    `<li class="tv">` +
    `<div class="tv-clock"><div class="tv-top"><span class="tv-date"></span>` +
    `<span class="tv-rate" title="In-RP seconds per real second">×${rateNow().mult.toFixed(2)}</span></div>` +
    `<div class="tv-time"></div></div>` +
    `<div class="cp-section">Next</div><div class="cp-card tv-next"></div>` +
    `<div class="cp-section">Converter</div>` +
    `<div class="cp-card tv-conv">` +
    `<div class="tv-seg" role="group"><button data-dir="r2i" aria-pressed="true">Real → IRP</button>` +
    `<button data-dir="i2r" aria-pressed="false">IRP → Real</button></div>` +
    `<div class="tv-fields" data-for="r2i">` +
    `<label>Date<input type="date" data-k="rd" value="${now.getFullYear()}-${two(now.getMonth() + 1)}-${two(now.getDate())}"></label>` +
    `<label>Time<input type="time" data-k="rt" value="${two(now.getHours())}:${two(now.getMinutes())}"></label>` +
    `<label>Hours from GMT<input type="number" step="0.5" data-k="ro" value="${off}"></label>` +
    `<button class="tv-now" type="button">Now</button></div>` +
    `<div class="tv-fields" data-for="i2r" hidden>` +
    `<label>Date<input type="date" data-k="id" value="${ic.getUTCFullYear()}-${two(ic.getUTCMonth() + 1)}-${two(ic.getUTCDate())}"></label>` +
    `<label>Time<input type="time" data-k="it" value="${two(ic.getUTCHours())}:${two(ic.getUTCMinutes())}"></label></div>` +
    `<div class="tv-result" aria-live="polite"></div>` +
    `</div></li>`
  timeView = bsItems.querySelector('.tv')
  lastTvSec = -1
  convertTime()
  cancelAnimationFrame(timeRaf)
  timeRaf = requestAnimationFrame(tickTimeView)
}

// rAF while the tab is open, but the DOM only changes when the IC second does,
// about seven times a real second at 52 days a year
function tickTimeView() {
  if (!timeView || !timeView.isConnected || navOpen() !== 'time') {
    timeView = null
    return
  }
  const ms = icNow()
  const sec = Math.floor(ms / 1000)
  if (sec !== lastTvSec) {
    lastTvSec = sec
    const d = new Date(ms)
    const { mult } = rateNow()
    timeView.querySelector('.tv-date')!.textContent =
      `${WEEKDAYS_LONG[d.getUTCDay()]}, ${d.getUTCDate()} ${MONTHS_LONG[d.getUTCMonth()]} ${d.getUTCFullYear()}`
    timeView.querySelector('.tv-time')!.innerHTML =
      `${two(d.getUTCHours())}:${two(d.getUTCMinutes())}<span>:${two(d.getUTCSeconds())}</span>`
    timeView.querySelector('.tv-next')!.innerHTML = nextRows(ms, mult)
  }
  timeRaf = requestAnimationFrame(tickTimeView)
}

function convertTime() {
  if (!timeView) return
  const val = (k: string) => (timeView!.querySelector(`[data-k="${k}"]`) as HTMLInputElement).value
  const out = timeView.querySelector('.tv-result') as HTMLElement
  const show = (main: string, sub = '', err = false) => {
    out.innerHTML = main ? `<b>${main}</b>${sub ? `<span>${sub}</span>` : ''}` : ''
    out.classList.toggle('is-error', err)
  }
  const r2i = timeView.querySelector('[data-dir="r2i"]')!.getAttribute('aria-pressed') === 'true'
  if (r2i) {
    const dv = val('rd')
    if (!dv) return show('')
    const [h, m] = (val('rt') || '00:00').split(':').map(Number)
    const real = Date.UTC(+dv.slice(0, 4), +dv.slice(5, 7) - 1, +dv.slice(8, 10), h, m) - (parseFloat(val('ro')) || 0) * HOUR
    const ic = new Date(icAtReal(real))
    if (isNaN(ic.getTime())) return show('That date is out of range.', '', true)
    show(
      `${WEEKDAYS_LONG[ic.getUTCDay()]}, ${ic.getUTCDate()} ${MONTHS_LONG[ic.getUTCMonth()]} ${ic.getUTCFullYear()}`,
      `${two(ic.getUTCHours())}:${two(ic.getUTCMinutes())} UTC in RP`
    )
  } else {
    const dv = val('id')
    if (!dv) return show('')
    const [h, m] = (val('it') || '00:00').split(':').map(Number)
    const r = realAt(Date.UTC(+dv.slice(0, 4), +dv.slice(5, 7) - 1, +dv.slice(8, 10), h, m))
    if (r === 'before') return show('Before recorded time.', 'The RP calendar starts on 1 June 1931.', true)
    if (r === 'skipped') return show('Skipped by a timeskip.', 'No real moment ever showed this date.', true)
    const real = new Date(r)
    show(
      real.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }),
      real.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', timeZoneName: 'short' })
    )
  }
}

bsItems.addEventListener('click', e => {
  if (!timeView) return
  const t = e.target as HTMLElement
  const seg = t.closest<HTMLElement>('.tv-seg button')
  if (seg) {
    for (const b of timeView.querySelectorAll('.tv-seg button')) b.setAttribute('aria-pressed', String(b === seg))
    for (const f of timeView.querySelectorAll<HTMLElement>('.tv-fields')) f.hidden = f.dataset.for !== seg.dataset.dir
    convertTime()
  } else if (t.closest('.tv-now')) {
    const now = new Date()
    const set = (k: string, v: string) => ((timeView!.querySelector(`[data-k="${k}"]`) as HTMLInputElement).value = v)
    set('rd', `${now.getFullYear()}-${two(now.getMonth() + 1)}-${two(now.getDate())}`)
    set('rt', `${two(now.getHours())}:${two(now.getMinutes())}`)
    set('ro', String(-now.getTimezoneOffset() / 60))
    convertTime()
  }
})
bsItems.addEventListener('input', () => convertTime())

// One tick a real second; the work only happens when the IC minute turns, which
// is about every eight seconds at 52 days a year.
let lastIcMinute = -1
setInterval(() => {
  const ms = icNow()
  const minute = Math.floor(ms / 60_000)
  if (minute === lastIcMinute) return
  lastIcMinute = minute
  for (const el of document.querySelectorAll<HTMLElement>('.cp-time')) el.innerHTML = timeLine(+el.dataset.z!, ms)
  syncIrpDate(ms)
  if (map.hasLayer(daylightLayer)) drawDaylight(ms)
}, 1000)

// --- Smooth zoom ---
//
// The wheel and the trackpad zoom the map continuously, the way Apple Maps does,
// where Leaflet's own handler waits, picks a step and plays a quarter-second
// animation to it, then another. Each frame the zoom moves a fraction of the way
// to where the wheel has asked for, about the point under the cursor, through
// the same call a two-finger pinch on a phone makes, and it stops where the
// wheel leaves it: there are no levels to land on.
{
  const m = map as unknown as {
    _stop(): void
    _moveStart(zoomChanged: boolean, noMoveStart: boolean): void
    _move(center: L.LatLng, zoom: number, data?: { pinch: boolean }): void
    _moveEnd(zoomChanged: boolean): void
    _limitCenter(c: L.LatLng, z: number, b?: L.LatLngBoundsExpression): L.LatLng
    _animatingZoom?: boolean
  }
  map.scrollWheelZoom.disable()

  const RATE = 1 / 220 // zoom levels per px of wheel
  const PINCH_RATE = 1 / 60 // a trackpad pinch arrives as small ctrl+wheel deltas
  const NOTCH = 0.5 // the least one click of a notched mouse wheel moves the zoom
  const TAU = 55 // ms; how quickly the zoom closes on its target
  const IDLE = 110 // ms without a wheel event before the gesture is over

  let live = false
  let raf = 0
  let goal = 0 // where the wheel has asked for
  let lastWheel = 0
  let lastT = 0
  let mouse: L.Point | null = null
  let anchor: L.LatLng = map.getCenter()
  // What this loop last left the map at. If either has changed by the next frame,
  // something else moved it (a zoom button, a jump to a city) and owns the view.
  let leftZoom = 0
  let leftCenter: L.LatLng = map.getCenter()
  let drawnQuarter = 0

  const clampZoom = (z: number) => Math.min(map.getMaxZoom(), Math.max(map.getMinZoom(), z))

  // The centre that keeps the anchor under the cursor at a zoom
  const centreAt = (z: number) => {
    const off = mouse!.subtract(map.getSize().divideBy(2))
    const c = map.unproject(map.project(anchor, z).subtract(off), z)
    return m._limitCenter(c, z, map.options.maxBounds)
  }

  const stop = () => {
    live = false
    cancelAnimationFrame(raf)
    raf = 0
    mapEl.classList.remove('zoom-live')
  }

  // The drawn lines are redone each quarter of a level on the way. The vector
  // layers are drawn for one zoom and stretched between redraws, and cover only
  // a little more than the view, which a long zoom out would run past.
  const redraw = (z: number) => {
    const q = quarterStep(z)
    if (q === drawnQuarter) return
    drawnQuarter = q
    syncBorderLines()
    // What a renderer does when a zoom ends: every path projected again, then
    // the drawing laid out afresh round the view as it now is
    map.eachLayer(l => {
      if (!(l instanceof L.Renderer)) return
      const r = l as unknown as { _onZoomEnd(): void; _update(): void }
      r._onZoomEnd()
      r._update()
    })
  }

  const frame = (t: number) => {
    raf = 0
    if (!live) return
    if (map.getZoom() !== leftZoom || !map.getCenter().equals(leftCenter)) {
      stop()
      return
    }
    const dt = Math.min(50, Math.max(0, t - lastT))
    lastT = t
    let z = map.getZoom()
    z += (goal - z) * (1 - Math.exp(-dt / TAU))
    const done = performance.now() - lastWheel > IDLE && Math.abs(goal - z) < 0.003
    if (done) z = goal
    // Marked as a pinch on every frame but the ones that cross a quarter level,
    // which is what tells the tile layers to stretch what they have and leave
    // their grids alone; on a crossing, and at the end, they take stock and fetch.
    m._move(centreAt(z), z, done || quarterStep(z) !== drawnQuarter ? undefined : { pinch: true })
    leftZoom = map.getZoom()
    leftCenter = map.getCenter()
    if (done) {
      stop()
      m._moveEnd(true)
      return
    }
    // Area names take their size from the zoom itself, every frame; the cities
    // follow through the map's own move handler
    updateLabels()
    redraw(z)
    raf = requestAnimationFrame(frame)
  }

  mapEl.addEventListener(
    'wheel',
    e => {
      e.preventDefault()
      // One of Leaflet's own zoom animations is running; it finishes in a quarter second
      if (m._animatingZoom) return
      const dy = e.deltaY * (e.deltaMode === 1 ? 20 : e.deltaMode === 2 ? 60 : 1)
      if (!dy) return
      if (!live) {
        m._stop()
        goal = map.getZoom()
        drawnQuarter = quarterStep(goal)
        mouse = null
        live = true
        lastT = performance.now()
        mapEl.classList.add('zoom-live')
        m._moveStart(true, false)
        leftZoom = map.getZoom()
        leftCenter = map.getCenter()
      }
      const at = map.mouseEventToContainerPoint(e)
      if (!mouse || !at.equals(mouse)) {
        mouse = at
        anchor = map.containerPointToLatLng(at)
      }
      let by = -dy * (e.ctrlKey ? PINCH_RATE : RATE)
      // A notched mouse wheel, as far as it can be told from a trackpad: lines or
      // pages rather than pixels, or Chrome and Safari's 4.000244 per notch on a
      // Mac. A slow click of one is a few px, which would barely move the map.
      const notch = e.deltaMode !== 0 || (!e.ctrlKey && Math.abs(e.deltaY) >= 4 && Math.abs(e.deltaY % 4.000244140625) < 1e-4)
      if (notch && Math.abs(by) < NOTCH) by = Math.sign(by) * NOTCH
      goal = clampZoom(goal + by)
      lastWheel = performance.now()
      if (!raf) raf = requestAnimationFrame(frame)
    },
    { passive: false }
  )

  // A press on the map while it is still easing: stop where it is, so the drag
  // that follows starts from a map that is standing still
  mapEl.addEventListener(
    'pointerdown',
    () => {
      if (!live) return
      stop()
      m._moveEnd(true)
    },
    true
  )
}

applySettings()
