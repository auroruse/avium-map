// Moves placed cities that are standing in water or on the coastline stroke onto
// the nearest land pixel of layers/base.PNG.
//
// Redrawing the base map moves coastlines under placements that were correct
// when they were made. Most of the drift is a pixel or two — a city that was
// just inland now sits on the white stroke the new base draws along every coast
// — and correcting that by hand across a few hundred cities is not a good use of
// anyone's afternoon.
//
// A big move is a different thing. If the nearest land is 100px away the
// coastline near that city genuinely changed shape, and the nearest pixel could
// easily be across a bay from where the city belongs. Those are left alone and
// listed, because only you know which side of the water they were on.
//
// Reports and changes nothing by default:
//   node scripts/nudge.mjs               what would move
//   node scripts/nudge.mjs --write       move it
//   node scripts/nudge.mjs --max 12      raise the hands-off threshold from 8px
//   node scripts/nudge.mjs --clear 1.5   want more land around each marker
//   node scripts/nudge.mjs --only A,B     only these cities, leaving the rest alone
import sharp from 'sharp'
import { readFileSync, writeFileSync } from 'fs'
import { join, resolve } from 'path'
import { writeCoords } from './coords.mjs'

const root = resolve(import.meta.dirname, '..')
const dataDir = join(root, 'src', 'data')
const jsonPath = join(dataDir, 'cities.json')

const args = process.argv.slice(2)
const WRITE = args.includes('--write')
const MAX = Number(args[args.indexOf('--max') + 1]) || 8
// How much land a marker wants around it, as a multiple of its own drawn radius.
// A flat number cannot be right for both ends of the ladder: the 15M marker is
// 5px across the radius and a hamlet's is 1.7px, so 3px left the big ones sitting
// half in the water while dragging the small ones further inland than they needed
// to go. Read off the tier table so the two cannot drift apart.
const CLEAR_MULT = Number(args[args.indexOf('--clear') + 1]) || 1
// A redrawn coast usually strands one or two cities that matter and a few dozen
// that are merely a pixel short of the room their marker wants. This is how to
// take the first without the second.
const ONLY = args.includes('--only')
  ? new Set(args[args.indexOf('--only') + 1].split(',').map(s => s.trim()))
  : null
const K = 0.8 // the marker scale from user zoom 3 up
const HALO = Number(
  readFileSync(join(root, 'src', 'main.ts'), 'utf8').match(/const HALO = ([\d.]+)/)[1]
)
const TIERS = readFileSync(join(root, 'src', 'main.ts'), 'utf8')
  .split('\n')
  .filter(l => /minPop:\s*[\d_]+, radius:/.test(l))
  .map(l => ({
    minPop: Number(l.match(/minPop:\s*([\d_]+)/)[1].replace(/_/g, '')),
    radius: Number(l.match(/radius:\s*([\d.]+)/)[1]),
  }))
const clearFor = pop => {
  const t = TIERS.find(t => pop >= t.minPop) ?? TIERS[TIERS.length - 1]
  return Math.max(1, Math.ceil(t.radius * HALO * K * CLEAR_MULT))
}

// The three colours base.PNG is drawn in. Sampled, not guessed — see the palette
// note on OCEAN in tile.mjs.
const LAND = [180, 179, 191]
const SEA = [62, 78, 111]
const TOLERANCE = 14

const KM_PER_PX = 20_003.93 / (6000 * Math.SQRT2)

const { data, info } = await sharp(join(root, 'layers', 'base.PNG')).raw().toBuffer({
  resolveWithObject: true,
})
const { width: W, height: H, channels: C } = info

const at = (x, y) => {
  const i = (y * W + x) * C
  return [data[i], data[i + 1], data[i + 2]]
}
const near = (p, t) =>
  Math.abs(p[0] - t[0]) < TOLERANCE &&
  Math.abs(p[1] - t[1]) < TOLERANCE &&
  Math.abs(p[2] - t[2]) < TOLERANCE
const isLand = p => near(p, LAND)
const isSea = p => near(p, SEA)
const isStroke = p => p[0] > 230 && p[1] > 230 && p[2] > 230

// How much land a marker has to stand on: the radius of the largest all-land
// disc centred here, capped at CLEAR because more than that buys nothing.
//
// A bare "is this pixel land" test is not enough. The base draws a thick white
// stroke along every coast, and that stroke strands one-pixel islands of land
// inside it — Ciudad Cuerdas landed on exactly such a pixel, land by colour with
// stroke on both sides, so its marker sat on white with nothing under it.
//
// But demanding CLEAR outright is worse: an island narrower than 2*CLEAR+1 has
// no qualifying pixel at all, so every city in the Vikomte, Dämmerung and
// Aztekische groups would be dragged to a mainland or reported unplaceable.
// Ayanami came out as "no land found". So this returns a score and the search
// takes the best available nearby rather than insisting on a floor.
function clearanceAt(cx, cy, CLEAR) {
  for (let r = 1; r <= CLEAR; r++) {
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        if (dx * dx + dy * dy > r * r) continue
        const x = cx + dx
        const y = cy + dy
        if (x < 0 || y < 0 || x >= W || y >= H) return r - 1
        if (!isLand(at(x, y))) return r - 1
      }
    }
  }
  return CLEAR
}

// The most solid ground within `limit`, preferring the least movement among
// equals. Returns null when nothing nearby stands on more land than the city
// already does — an island city is already as far from the water as it can get.
function bestGround(cx, cy, limit, CLEAR) {
  const now = clearanceAt(cx, cy, CLEAR)
  let best = null
  for (let dy = -limit; dy <= limit; dy++) {
    for (let dx = -limit; dx <= limit; dx++) {
      const d = Math.hypot(dx, dy)
      if (d > limit) continue
      const x = cx + dx
      const y = cy + dy
      if (x < 0 || y < 0 || x >= W || y >= H) continue
      if (!isLand(at(x, y))) continue
      const c = clearanceAt(x, y, CLEAR)
      if (c <= now) continue
      if (!best || c > best.c || (c === best.c && d < best.d)) best = { x, y, d, c }
    }
  }
  return best
}

const cities = JSON.parse(readFileSync(jsonPath, 'utf8'))
const taken = new Set()
for (const c of cities) if (c.x != null) taken.add(`${c.x},${c.y}`)

const moved = []
const skipped = []
const stayed = []

for (const c of cities) {
  if (c.x == null || c.y == null) continue
  if (ONLY && !ONLY.has(c.name)) continue
  const CLEAR = clearFor(c.population)
  const p = at(c.x, c.y)
  const standing = clearanceAt(c.x, c.y, CLEAR)
  if (isLand(p) && standing >= CLEAR) continue
  const where = isStroke(p) ? 'coastline' : isSea(p) ? 'sea' : 'tight'

  // Search a little past the threshold so the report can say how far a skipped
  // city actually is, instead of only that it is too far
  const found = bestGround(c.x, c.y, MAX, CLEAR)
  if (!found) {
    // Nothing nearby is more solid. On an island that is the correct answer.
    stayed.push({ c, where, standing })
    continue
  }

  // Two cities landing on one pixel is the corruption that once had twins
  // sharing a position; step outward until the target is free
  let { x, y } = found
  if (taken.has(`${x},${y}`)) {
    const alt = bestGround(x, y, 4, CLEAR)
    if (alt && !taken.has(`${alt.x},${alt.y}`)) ({ x, y } = alt)
  }
  if (taken.has(`${x},${y}`)) {
    skipped.push({ c, where, d: found.d, reason: 'target already occupied' })
    continue
  }

  taken.delete(`${c.x},${c.y}`)
  taken.add(`${x},${y}`)
  moved.push({ c, where, from: [c.x, c.y], to: [x, y], d: Math.hypot(x - c.x, y - c.y) })
  if (WRITE) {
    c.x = x
    c.y = y
  }
}

const byWhere = w => moved.filter(m => m.where === w)
console.log(`${WRITE ? 'moved' : 'would move'} ${moved.length} cities onto land`)
for (const w of ['coastline', 'sea', 'tight']) {
  const list = byWhere(w)
  if (!list.length) continue
  const ds = list.map(m => m.d).sort((a, b) => a - b)
  console.log(
    `  ${String(list.length).padStart(4)} off the ${w.padEnd(9)} ` +
      `median ${ds[ds.length >> 1].toFixed(1)}px  max ${ds[ds.length - 1].toFixed(1)}px ` +
      `(${(ds[ds.length - 1] * KM_PER_PX).toFixed(0)}km)`
  )
}

if (stayed.length) {
  const tight = stayed
  console.log(`\n${tight.length} left where they are — nothing nearby stands on more land, which is what an island looks like:`)
  for (const s of tight.slice(0, 10)) console.log(`  ${s.standing}px of land  ${s.c.name} (${s.c.nation})`)
  if (tight.length > 10) console.log(`  ...and ${tight.length - 10} more`)
}

if (skipped.length) {
  console.log(`\nleft alone — further than ${MAX}px, decide these by hand:`)
  for (const s of skipped.sort((a, b) => a.d - b.d)) {
    const d = s.d === Infinity ? 'no land found' : `${s.d.toFixed(0)}px (${(s.d * KM_PER_PX).toFixed(0)}km)`
    console.log(`  ${d.padStart(16)}  ${s.c.name} (${s.c.nation})${s.reason ? ' — ' + s.reason : ''}`)
  }
}

if (WRITE) {
  writeFileSync(jsonPath, JSON.stringify(cities, null, 2) + '\n')
  writeCoords(dataDir)
  console.log('\ncities.json written, coordinates.tsv regenerated')
} else {
  console.log('\nnothing written — re-run with --write')
}
