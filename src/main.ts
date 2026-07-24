import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import './style.css'
import citiesData from './data/cities.json'
import labelsData from './data/labels.json'

// --- Dev mode ---

const DEV = new URLSearchParams(window.location.search).has('dev')

// --- Constants ---

const TILE_GRID = 8192
const CONTENT = 6000
const U = 256
const MAX_ZOOM = 8

function px(x: number, y: number): L.LatLngExpression {
  return [(-y * U) / TILE_GRID, (x * U) / TILE_GRID]
}

function toPx(latlng: L.LatLng): [number, number] {
  return [
    Math.round((latlng.lng * TILE_GRID) / U),
    Math.round((-latlng.lat * TILE_GRID) / U),
  ]
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
})

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

const overlayControl: Record<string, L.Layer> = {
  'National Borders': bordersLayer,
  'Rivers': riversLayer,
}

const layerCtrl = L.control.layers({}, overlayControl, { collapsed: false }).addTo(map)

// --- Labels ---

interface LabelDef {
  text: string
  type: string
  x: number | null
  y: number | null
  minZoom: number
  maxZoom: number
  tier?: number // nations/colonies: font size in px
}


const labelDefs = labelsData as LabelDef[]
const labelMarkers = new Map<LabelDef, L.Marker>()

function labelVisible(def: LabelDef, z: number): boolean {
  if (def.type === 'continent' || def.type === 'nation' || def.type === 'colony') return false
  return z >= def.minZoom && z <= def.maxZoom
}

function makeLabelMarker(def: LabelDef): L.Marker {
  return L.marker(px(def.x!, def.y!), {
    icon: L.divIcon({
      className: `map-label label-${def.type}`,
      html: `<span>${def.text}</span>`,
      iconSize: [0, 0],
      iconAnchor: [0, 0],
    }),
    interactive: false,
    zIndexOffset: -1000,
  })
}

// (Re)create a label's marker after its coords change
function refreshLabel(def: LabelDef) {
  const existing = labelMarkers.get(def)
  if (existing) {
    map.removeLayer(existing)
    labelMarkers.delete(def)
  }
  if (def.x == null || def.y == null) return
  labelMarkers.set(def, makeLabelMarker(def).addTo(map))
  updateLabels()
  invalidatePlacements()
  updateCities()
}

function updateLabels() {
  const z = map.getZoom()
  for (const [def, marker] of labelMarkers) {
    const el = marker.getElement()
    if (!el) continue
    el.style.display = labelVisible(def, z) ? '' : 'none'
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
const BIG_D = 11.09
function bigSvgHtml(S: number): string {
  return (
    `<svg width="${S}" height="${S}" viewBox="-5.545 -5.545 11.09 11.09" xmlns="http://www.w3.org/2000/svg">` +
    `<circle r="5.545" fill="#fff"/>` +
    `<circle r="4.095" fill="#111"/>` +
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
function smallSvgHtml(S: number): string {
  return (
    `<svg width="${S}" height="${S}" viewBox="-3 -3 6 6" xmlns="http://www.w3.org/2000/svg">` +
    `<circle r="2.3" fill="#111" stroke="#ddd" stroke-width="0.92"/>` +
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
}

// Dot and label in one DOM element: no Leaflet tooltip machinery, whose
// per-label layout passes were the main zoom cost
function cityIcon(p: Placement, fade: boolean): L.DivIcon {
  const { c, tier, dir, off } = p
  const S = tier.outerRing ? BIG_D * (tier.radius / 3) : SMALL_D * (tier.radius / 2.3)
  const svg = tier.outerRing ? bigSvgHtml(S) : smallSvgHtml(S)
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

  for (const [c, e] of shownCities) {
    if (!want.has(c)) {
      cityLayer.removeLayer(e.marker)
      shownCities.delete(c)
    }
  }

  for (const p of placements) {
    const key = placementKey(p)
    const existing = shownCities.get(p.c)
    if (existing?.key === key) continue
    if (existing) cityLayer.removeLayer(existing.marker)

    const marker = L.marker(px(p.c.x!, p.c.y!), { icon: cityIcon(p, isNewSet && !prevPlaced.has(p.c)) })
    marker.on('click', () => openCityPanel(p.c))
    cityLayer.addLayer(marker)
    shownCities.set(p.c, { marker, key })
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
document.body.appendChild(cityPanel)

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

function openCityPanel(c: City) {
  const displayName = c.name.replace(/,\s*[A-Z]{2,4}$/, '')
  const popRank = cityRank(c, 'population')
  const gdpRank = cityRank(c, 'gdp')
  const pcRank = cityRank(c, 'gdpPerCapita')
  cityPanel.innerHTML =
    `<button class="cp-close" aria-label="Close">✕</button>` +
    `<div class="cp-name">${displayName}</div>` +
    (c.nativeScript ? `<div class="cp-native">${c.nativeScript}</div>` : '') +
    `<div class="cp-stats">` +
    `<div class="cp-stat"><div class="cp-label">Nation</div><div class="cp-value">${c.nation}${c.alpha3 ? ` <span class="cp-sub">(${c.alpha3})</span>` : ''}</div></div>` +
    (c.irlParallel ? `<div class="cp-stat"><div class="cp-label">IRL Parallel</div><div class="cp-value">${c.irlParallel}</div></div>` : '') +
    `<div class="cp-stat cp-wide"><div class="cp-label">Population</div><div class="cp-value">${c.population.toLocaleString('en-US')}${fmtRank(popRank)}</div></div>` +
    `<div class="cp-stat cp-wide"><div class="cp-label">GDP PPP</div><div class="cp-value">${fmtUSD(c.gdp)}${fmtRank(gdpRank)}</div></div>` +
    `<div class="cp-stat cp-wide"><div class="cp-label">Per Capita</div><div class="cp-value">${fmtUSD(c.gdpPerCapita)}${fmtRank(pcRank)}</div></div>` +
    `</div>`
  cityPanel.classList.remove('cp-closing')
  cityPanel.hidden = false
  cityPanel.querySelector('.cp-close')!.addEventListener('click', closeCityPanel)
}

function closeCityPanel() {
  if (cityPanel.hidden || cityPanel.classList.contains('cp-closing')) return
  cityPanel.classList.add('cp-closing')
  cityPanel.addEventListener('animationend', () => {
    cityPanel.classList.remove('cp-closing')
    cityPanel.hidden = true
  }, { once: true })
}

map.on('click', closeCityPanel)
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeCityPanel()
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

function saveProgress() {
  const coords: Record<string, [number, number]> = {}
  for (const c of cities) {
    if (c.x != null && c.y != null) coords[c.name] = [c.x, c.y]
  }
  localStorage.setItem(SAVE_KEY, JSON.stringify(coords))
}

function loadProgress() {
  const raw = localStorage.getItem(SAVE_KEY)
  if (!raw) return 0
  const coords: Record<string, [number, number]> = JSON.parse(raw)
  let count = 0
  for (const c of cities) {
    if (coords[c.name]) {
      ;[c.x, c.y] = coords[c.name]
      count++
    }
  }
  return count
}

const LABEL_KEY = 'avium-label-coords'

function saveLabelProgress() {
  const coords: Record<string, number[]> = {}
  for (const d of labelDefs) {
    if (d.x != null && d.y != null) {
      coords[`${d.type}:${d.text}`] = d.tier != null ? [d.x, d.y, d.tier] : [d.x, d.y]
    }
  }
  localStorage.setItem(LABEL_KEY, JSON.stringify(coords))
}

function loadLabelProgress() {
  const raw = localStorage.getItem(LABEL_KEY)
  if (!raw) return
  const coords: Record<string, number[]> = JSON.parse(raw)
  for (const d of labelDefs) {
    const c = coords[`${d.type}:${d.text}`]
    if (c) {
      d.x = c[0]
      d.y = c[1]
      if (c[2] != null) d.tier = c[2]
    }
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

  // Build coord lookup from current state
  const coordMap = new Map<string, [number | null, number | null]>()
  for (const c of cities) coordMap.set(c.name, [c.x, c.y])

  // Also pull from localStorage in case some coords aren't in the current array
  const saved = localStorage.getItem(SAVE_KEY)
  if (saved) {
    for (const [name, xy] of Object.entries(JSON.parse(saved) as Record<string, [number, number]>)) {
      if (!coordMap.has(name) || coordMap.get(name)![0] == null) coordMap.set(name, xy)
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
        (city as any)[field] = vals[j]
      }
    }

    // Preserve coordinates
    const existing = coordMap.get(city.name)
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
for (const def of labelDefs) refreshLabel(def)

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

if (!DEV) {
  panel.style.display = 'none'
  coordEl.style.display = 'none'
  unassignedPanel.style.display = 'none'
}

let selectedCity: City | null = null
let selectedLabel: LabelDef | null = null
let placedMarker: L.CircleMarker | null = null

function updateCount() {
  const placed = cities.filter(c => c.x != null && c.y != null).length
  const activeDefs = labelDefs.filter(d => d.type !== 'continent' && d.type !== 'nation' && d.type !== 'colony')
  const lPlaced = activeDefs.filter(d => d.x != null && d.y != null).length
  countEl.textContent = `${placed}/${cities.length} cities · ${lPlaced}/${activeDefs.length} labels`
  updateUnassigned()
}

function updateUnassigned() {
  if (!DEV) return
  const unplaced = citiesByPriority.filter(c => c.x == null || c.y == null)
  unassignedHeader.textContent = `Unassigned (${unplaced.length})`
  if (!unplaced.length) {
    unassignedPanel.style.display = 'none'
    return
  }
  unassignedPanel.style.display = ''
  unassignedList.innerHTML = ''
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

// Strip diacritics so "Chukyo" matches "Chūkyō" etc.
const norm = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

searchInput.addEventListener('input', () => {
  const q = norm(searchInput.value.trim())
  resultsList.innerHTML = ''
  if (q.length < 2) return

  const matches = cities
    .filter(c => norm(c.name).includes(q) || norm(c.nation).includes(q))
    .slice(0, 10)

  for (const c of matches) {
    const li = document.createElement('li')
    const placed = c.x != null
    li.innerHTML = `<span class="result-name">${c.name}</span>` +
      `<span class="result-meta">${c.nation} &middot; ${(c.population / 1e6).toFixed(2)}M${placed ? ' ✓' : ''}</span>`
    if (placed) li.classList.add('placed')
    li.addEventListener('click', () => selectCity(c))
    resultsList.appendChild(li)
  }

  const labelMatches = labelDefs
    .filter(d => d.type !== 'continent' && d.type !== 'nation' && d.type !== 'colony'
      && d.text.toLowerCase().includes(q))
    .slice(0, 6)

  for (const d of labelMatches) {
    const li = document.createElement('li')
    const placed = d.x != null
    li.innerHTML = `<span class="result-name">${d.text}</span>` +
      `<span class="result-meta">${d.type.toUpperCase()}${placed ? ' ✓' : ''}</span>`
    if (placed) li.classList.add('placed')
    li.addEventListener('click', () => selectLabel(d))
    resultsList.appendChild(li)
  }
})

function selectCity(c: City) {
  selectedCity = c
  selectedLabel = null
  resultsList.innerHTML = ''
  searchInput.value = c.name
  statusEl.textContent = `Click the map to place ${c.name}`
  statusEl.className = 'status-active'

  if (c.x != null && c.y != null) {
    map.setView(px(c.x, c.y), Math.max(map.getZoom(), 4))
  }
}

function selectLabel(d: LabelDef) {
  selectedLabel = d
  selectedCity = null
  resultsList.innerHTML = ''
  searchInput.value = d.text
  statusEl.className = 'status-active'
  statusEl.textContent = `Click the map to place ${d.text} (${d.type})`

  if (d.x != null && d.y != null) {
    map.setView(px(d.x, d.y), map.getZoom())
  }
}

map.on('click', (e: L.LeafletMouseEvent) => {
  const [x, y] = toPx(e.latlng)

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
    coordEl.textContent = `x: ${x}  y: ${y}`
  })
}

// Export
document.getElementById('place-export')!.addEventListener('click', () => {
  const blob = new Blob([JSON.stringify(cities, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'cities.json'
  a.click()
  URL.revokeObjectURL(a.href)
})

document.getElementById('place-export-labels')!.addEventListener('click', () => {
  const blob = new Blob([JSON.stringify(labelDefs, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'labels.json'
  a.click()
  URL.revokeObjectURL(a.href)
})

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
