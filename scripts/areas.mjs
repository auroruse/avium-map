// No shebang: tile.mjs and merge-tsv.mjs both import this, and esbuild will not
// bundle a module that starts with one.
//
// Writes src/data/areas.json: the territorial area of every nation, in km².
//
// Derived, never hand-edited. layers/borders.PNG and the city placements are the
// source of truth, and this is regenerated whenever either changes.
//
// How a country gets measured
// ---------------------------
// borders.PNG is a flat colour fill, but the colours are blocs rather than
// nations: 188,0,45 is Nichirin and also Kinshū, Hōrai, Mizuho and Ryūgu. Colour
// alone cannot answer "how big is Nichirin".
//
// Connected components of one colour can. Nichirin proper is one region of red
// and Kinshū is another, so each component is a single territory, and the cities
// standing in it say whose it is. 93 of the 100 components that hold cities have
// cities of exactly one nation; the seven that do not are lopsided enough
// (Rudania 102 against Karjania 1) that the majority is the answer.
//
// Components with no city at all are small islands, about 1.6% of the coloured
// area. Each is adopted by the nearest component of its own colour that does have
// an owner — same colour, because an islet drawn in Nichirin's red belongs to
// something in that bloc and never to whoever happens to be closest.
//
// Area comes from the projection, not from pixel counts: see pxArea below and the
// long note beside its twin in src/main.ts.
import sharp from 'sharp'
import { existsSync, readFileSync, writeFileSync } from 'fs'
import { join, resolve } from 'path'

const CONTENT = 6000
const GEO_ORIGIN = CONTENT / 2
const GEO_R = Math.hypot(GEO_ORIGIN, GEO_ORIGIN)
const S = Math.SQRT1_2
const PX2KM = 20_003.93 / (6000 * Math.SQRT2)
const PLANET_R = (GEO_R * PX2KM) / (Math.PI / 2)
const AREA_K = (PLANET_R * PLANET_R * Math.PI * Math.PI) / (2 * GEO_R * GEO_R)

// Ground covered by one map pixel at (x, y). The projection is not equal-area —
// a pixel near a pole is worth more than half as much again as one on the
// equator — so this cannot be a constant.
function pxArea(x, y) {
  const v = -(x - GEO_ORIGIN + (y - GEO_ORIGIN)) * S
  const t = 1 - Math.abs(v) / GEO_R
  return t <= 0 ? 0 : (AREA_K * Math.sin((t * Math.PI) / 2)) / t
}

export async function writeAreas(root = resolve(import.meta.dirname, '..')) {
  const bordersPath = join(root, 'layers', 'borders.png')
  const dataDir = join(root, 'src', 'data')
  if (!existsSync(bordersPath)) return null

  const { data, info } = await sharp(bordersPath).raw().toBuffer({ resolveWithObject: true })
  const { width: W, height: H, channels: C } = info
  const N = W * H

  // -1 for anything transparent; otherwise the packed colour, which is what
  // components are grown within
  const colour = new Int32Array(N).fill(-1)
  for (let p = 0; p < N; p++) {
    const i = p * C
    if (C === 4 && data[i + 3] < 128) continue
    colour[p] = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2]
  }

  const label = new Int32Array(N).fill(-1)
  const stack = new Int32Array(N)
  const comps = []
  for (let s = 0; s < N; s++) {
    if (colour[s] < 0 || label[s] >= 0) continue
    const id = comps.length
    let sp = 0
    let area = 0
    let n = 0
    let sx = 0
    let sy = 0
    stack[sp++] = s
    label[s] = id
    while (sp) {
      const p = stack[--sp]
      const x = p % W
      const y = (p / W) | 0
      area += pxArea(x, y)
      sx += x
      sy += y
      n++
      // Four-way: a pair of regions touching only at a corner are two places,
      // not one, and eight-way would weld them together
      if (x + 1 < W && label[p + 1] < 0 && colour[p + 1] === colour[s]) { label[p + 1] = id; stack[sp++] = p + 1 }
      if (x > 0 && label[p - 1] < 0 && colour[p - 1] === colour[s]) { label[p - 1] = id; stack[sp++] = p - 1 }
      if (y + 1 < H && label[p + W] < 0 && colour[p + W] === colour[s]) { label[p + W] = id; stack[sp++] = p + W }
      if (y > 0 && label[p - W] < 0 && colour[p - W] === colour[s]) { label[p - W] = id; stack[sp++] = p - W }
    }
    comps.push({ colour: colour[s], area, px: n, cx: sx / n, cy: sy / n, owner: null })
  }

  const cities = JSON.parse(readFileSync(join(dataDir, 'cities.json'), 'utf8'))
  const votes = new Map()
  for (const c of cities) {
    if (c.x == null || c.y == null) continue
    const l = label[c.y * W + c.x]
    if (l < 0) continue
    if (!votes.has(l)) votes.set(l, new Map())
    const m = votes.get(l)
    m.set(c.nation, (m.get(c.nation) ?? 0) + 1)
  }
  for (const [l, m] of votes) {
    comps[l].owner = [...m].sort((a, b) => b[1] - a[1])[0][0]
  }

  // Adopt the orphans — the 428 territories with no city on them, which between
  // them are 2.7% of the world's land. A metropole and its colonies are painted
  // the same colour, so colour alone cannot say which of them an empty island
  // belongs to and the distance to the nearest one has to decide it.
  //
  // Nearest by centroid alone got that badly wrong. Skjarnland's Elysian half is
  // 30,000px of unpopulated land that happens to sit 483px from Spetsbergen's
  // arctic islands and 578px from Skjarnland's own mainland, so a 738px colony
  // was handed a landmass forty times its size and came out with 453,000 km²
  // against its metropole's 664,000. Karjania lost its Elysian territory to
  // Cuohpnjalla the same way.
  //
  // So size gates the candidates before distance picks between them: a territory
  // is adopted by the nearest neighbour that is at least as big as it is, and
  // when none of them is, by whichever of them holds the most populated land. A
  // colony can inherit an islet off its own coast; it cannot swallow a continent.
  const owned = comps.filter(c => c.owner)
  const ownedPx = new Map()
  for (const o of owned) ownedPx.set(o.owner, (ownedPx.get(o.owner) ?? 0) + o.px)
  let adopted = 0
  let orphanArea = 0
  for (const c of comps) {
    if (c.owner) continue
    const peers = owned.filter(o => o.colour === c.colour)
    const big = peers.filter(o => o.px >= c.px)
    let best = null
    if (big.length) {
      let bestD = Infinity
      for (const o of big) {
        const d = (o.cx - c.cx) ** 2 + (o.cy - c.cy) ** 2
        if (d < bestD) { bestD = d; best = o }
      }
    } else {
      for (const o of peers) if (!best || ownedPx.get(o.owner) > ownedPx.get(best.owner)) best = o
    }
    if (best) { c.owner = best.owner; adopted++ } else orphanArea += c.area
  }

  const total = new Map()
  for (const c of comps) if (c.owner) total.set(c.owner, (total.get(c.owner) ?? 0) + c.area)

  const areas = {}
  for (const [n, a] of [...total].sort((x, y) => y[1] - x[1])) areas[n] = Math.round(a)
  writeFileSync(join(dataDir, 'areas.json'), JSON.stringify(areas, null, 2) + '\n')

  const measured = [...total.values()].reduce((a, b) => a + b, 0)
  return { nations: total.size, comps: comps.length, adopted, measured, orphanArea }
}

if (process.argv[1] && process.argv[1].endsWith('areas.mjs')) {
  const r = await writeAreas()
  if (!r) {
    console.error('layers/borders.png not found — nothing to measure')
    process.exit(1)
  }
  console.log(
    `areas.json — ${r.nations} nations over ${r.comps} territories ` +
      `(${r.adopted} unpopulated ones adopted by their nearest neighbour), ` +
      `${(r.measured / 1e6).toFixed(2)}M km² measured` +
      (r.orphanArea ? `, ${(r.orphanArea / 1e6).toFixed(2)}M km² unclaimed` : '')
  )
}
