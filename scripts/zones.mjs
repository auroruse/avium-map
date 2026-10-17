// No shebang, for the same reason as areas.mjs: tile.mjs and merge-tsv.mjs import it.
//
// Time zones. Writes three things, all derived and never hand-edited:
//
//   layers/zones.png       the zone map at full size, tiled like any other layer
//   public/zones.png       a quarter-size lookup the app reads to say which zone a
//                          point is in, sea included: red = offset + 13
//   public/tiles/zoneid/   which zone every pixel is in, as tiles at the zone map's
//                          own detail (grey = offset + 13), for the hover highlight
//   src/data/zones.json    each city's offset and each nation's offsets
//
// Avium has no canon zones, so these are made the way most real ones were: a
// country's clock is set by where its land sits, the average longitude of its
// home territory over 15, rounded. A large country (SPLIT_KM2 and up) wider
// than SPLIT hours between its 5th and 95th percentile of land takes about one
// zone per hour of that spread, cut on the half-hour meridians.
// The size floor matters: meridians run diagonally here, and across a smaller
// country lying along them (Recolotta) a cut came out as a strip one coast wide. Islands off the coast keep the mainland's clock; a
// colony far from home keeps its own longitude rather than its metropole's.
//
// Sea and unclaimed land keep plain solar time, round(longitude / 15), the
// convention ships keep. At sea each hour is a band in a dark shade of its
// colour, so a zone runs off the land and on across the water the way it does
// on a printed time zone map; unclaimed land stays neutral.
import sharp from 'sharp'
import { writeFileSync, readFileSync, rmSync, mkdirSync } from 'fs'
import { createHash } from 'crypto'
import { join, resolve } from 'path'
import { territories } from './areas.mjs'

const CONTENT = 6000
const MO = CONTENT / 2
const MR = Math.hypot(MO, MO)
const S = Math.SQRT1_2
// Only a country this large (km², from areas.json) is ever split; smaller ones
// keep one clock however they lie
const SPLIT_KM2 = 2_000_000
const SPLIT = 1.5 // hours of spread before a nation is given more than one zone
const PER = 1 // hours of spread per zone once it is split
// A slice of a split nation smaller than this share of its land joins its neighbour
const MIN_SHARE = 0.15
// How far outside its mainland's bounding box a territory can sit and still be
// counted as home rather than as a colony with a clock of its own, in map px
const HOME = 400
// A nation named here gets exactly this many zones, whatever its spread
const OVERRIDES = {}
// A nation named here is cut at exactly these hours of longitude instead of into
// equal land. Nichirin's own cut fell between Futahashi and Shinkeisei, through
// the capital; 6.5 is the true +6/+7 meridian and puts the whole Senpan Bay
// region on +7. Seignid is under the size floor but splits on the 8.5 line
// anyway, so its north matches Furan's +9 beside it. Hollosend runs across
// three bands and takes all three, so its east matches E.S.U. and Eivorie.
const CUTS = { Nichirin: [6.5], Seignid: [8.5], Hollosend: [-4.5, -3.5] }

const NONE = 127
const LOOKUP = 1500
const STEP = CONTENT / LOOKUP

function hourAt(x, y) {
  const dx = x - MO, dy = y - MO
  const u = (dx - dy) * S, v = -(dx + dy) * S, half = MR - Math.abs(v)
  return half < 1e-9 ? 0 : (12 * u) / half
}

function pxArea(x, y) {
  const v = -(x - MO + (y - MO)) * S
  const t = 1 - Math.abs(v) / MR
  return t <= 0 ? 0 : Math.sin((t * Math.PI) / 2) / t
}

// One colour per hour, from six that alternate warm and cool so neighbouring
// zones never sit close together. Land takes the colour itself, the sea a dark
// shade of it, and a gold line runs wherever the hour changes.
const HUES = [210, 30, 150, 330, 50, 265]
function hsl(h, s, l) {
  const f = n => {
    const k = (n + h / 30) % 12
    return Math.round(255 * (l - s * Math.min(l, 1 - l) * Math.max(-1, Math.min(k - 3, 9 - k, 1))))
  }
  return [f(0), f(8), f(4)]
}
const hueOf = z => HUES[((z % 6) + 6) % 6]
const landColour = z => hsl(hueOf(z), 0.42, 0.55)
const seaColour = z => hsl(hueOf(z), 0.4, 0.17)
const UNCLAIMED = [62, 62, 66]
const EDGE = [230, 184, 76] // gold

export async function writeZones(root = resolve(import.meta.dirname, '..')) {
  const t = await territories(root)
  if (!t) return null
  const { W, H, label, comps } = t

  // Each territory's own mean hour (weighted by true area) and extent
  const BINS = 24 * 20
  const binOf = h => Math.max(0, Math.min(BINS - 1, Math.floor((h + 12) * 20)))
  const cSum = new Float64Array(comps.length)
  const cW = new Float64Array(comps.length)
  const box = comps.map(() => [Infinity, -Infinity, Infinity, -Infinity])
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const l = label[y * W + x]
      if (l < 0) continue
      const o = comps[l].owner
      if (!o) continue
      const h = hourAt(x, y), w = pxArea(x, y)
      cSum[l] += h * w
      cW[l] += w
      const b = box[l]
      if (x < b[0]) b[0] = x
      if (x > b[1]) b[1] = x
      if (y < b[2]) b[2] = y
      if (y > b[3]) b[3] = y
    }
  }

  // Each nation's mainland is its biggest territory, and home is that box with
  // HOME px to spare around it
  const main = new Map()
  for (let l = 0; l < comps.length; l++) {
    const o = comps[l].owner
    if (o && (!main.has(o) || cW[l] > cW[main.get(o)])) main.set(o, l)
  }
  const atHome = l => {
    const b = box[main.get(comps[l].owner)], c = comps[l]
    return c.cx >= b[0] - HOME && c.cx <= b[1] + HOME && c.cy >= b[2] - HOME && c.cy <= b[3] + HOME
  }

  // Per nation: a histogram by hour of its land at home. Colonies keep their own
  // clocks below, so they have no say in the metropole's: Skjarnland's empty
  // Elysian territory once pulled its mainland, every one of its cities, an
  // hour back.
  const home = new Uint8Array(comps.length)
  for (let l = 0; l < comps.length; l++) if (comps[l].owner && atHome(l)) home[l] = 1
  const hist = new Map()
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const l = label[y * W + x]
      if (l < 0 || !home[l]) continue
      const o = comps[l].owner
      let a = hist.get(o)
      if (!a) hist.set(o, (a = new Float64Array(BINS)))
      a[binOf(hourAt(x, y))] += pxArea(x, y)
    }
  }

  const areas = JSON.parse(readFileSync(join(root, 'src', 'data', 'areas.json'), 'utf8'))
  // Each nation's bands: [from, to) in hours, and the offset of each
  const bands = new Map()
  const total = new Map()
  for (const [n, a] of hist) {
    const sum = a.reduce((p, q) => p + q, 0)
    total.set(n, sum)
    const q = f => {
      let acc = 0
      for (let i = 0; i < BINS; i++) { acc += a[i]; if (acc >= f * sum) return i / 20 - 12 }
      return 12
    }
    const spread = q(0.95) - q(0.05)
    const big = (areas[n] ?? 0) >= SPLIT_KM2
    const fixed = CUTS[n]
    const k = fixed ? fixed.length + 1 : OVERRIDES[n] ?? (!big || spread <= SPLIT ? 1 : Math.max(2, Math.round(spread / PER)))
    // Cut on the real half-hour meridians, so a split nation's zone edges line up
    // with its neighbours' and with the bands at sea; a slice holding less than
    // MIN_SHARE of the land folds into the slice beside it
    const share = (a0, b0) => {
      let w = 0
      for (let b = 0; b < BINS; b++) { const h = b / 20 - 12 + 0.025; if (h >= a0 && h < b0) w += a[b] }
      return w / sum
    }
    let inner = []
    if (fixed) inner = [...fixed]
    else if (k > 1) for (let h = Math.ceil(q(0.02) - 0.5) + 0.5; h < q(0.98); h++) inner.push(h)
    if (!fixed) {
      for (let changed = true; changed && inner.length; ) {
        changed = false
        const edges = [-Infinity, ...inner, Infinity]
        for (let i = 0; i < edges.length - 1; i++) {
          // too small, or one slice more than the nation's spread warrants: the
          // smallest slice goes first
          const sh = share(edges[i], edges[i + 1])
          const smallest = Math.min(...edges.slice(0, -1).map((e, j) => share(e, edges[j + 1])))
          if (sh >= MIN_SHARE && (inner.length + 1 <= k || sh > smallest)) continue
          // drop the cut on the side with less land beyond it
          const left = i > 0 ? share(edges[i - 1], edges[i]) : Infinity
          const right = i < edges.length - 2 ? share(edges[i + 1], edges[i + 2]) : Infinity
          inner.splice(left <= right ? i - 1 : i, 1)
          changed = true
          break
        }
      }
    }
    const cuts = [-Infinity, ...inner, Infinity]
    const list = []
    for (let i = 0; i < cuts.length - 1; i++) {
      let s = 0, w = 0
      for (let b = 0; b < BINS; b++) {
        const h = b / 20 - 12 + 0.025
        if (h >= cuts[i] && h < cuts[i + 1]) { s += h * a[b]; w += a[b] }
      }
      list.push({ from: cuts[i], to: cuts[i + 1], z: w ? Math.round(s / w) : Math.round(q(0.5)) })
    }
    bands.set(n, list)
  }
  const bandZone = (n, h) => {
    for (const b of bands.get(n)) if (h >= b.from && h < b.to) return b.z
    return 0
  }

  // A territory either takes one clock whole (a colony its own, anything small
  // or in a one-zone nation the band at its own mean) or is cut along the band
  // lines (the mainland of a split nation). Sharing the ground out between
  // cities instead was tried: in an empty interior a handful of towns each took
  // a huge straight-sided polygon, and Rudania's hours came out of order.
  const whole = new Int8Array(comps.length).fill(NONE)
  for (let l = 0; l < comps.length; l++) {
    const o = comps[l].owner
    if (!o || !cW[l]) continue
    const mean = cSum[l] / cW[l]
    if (!atHome(l)) whole[l] = Math.round(mean)
    else if (bands.get(o).length === 1 || cW[l] < 0.05 * total.get(o)) whole[l] = bandZone(o, mean)
  }

  const cities = JSON.parse(readFileSync(join(root, 'src', 'data', 'cities.json'), 'utf8'))

  const zone = new Int8Array(W * H).fill(NONE)
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const p = y * W + x, l = label[p]
      if (l < 0 || !comps[l].owner) continue
      zone[p] = whole[l] !== NONE ? whole[l] : bandZone(comps[l].owner, hourAt(x, y))
    }
  }

  const seaHour = p => { const z = Math.round(hourAt(p % W, (p / W) | 0)); return z === -12 ? 12 : z }
  // The zone anywhere: a nation's own, or solar time past its coast
  const zoneAnywhere = p => (zone[p] !== NONE ? zone[p] : seaHour(p))

  // --- the picture ----------------------------------------------------------
  // Coloured land and banded sea, gold where the hour changes and a darker line
  // where only the nation does, so the zone map stands on its own.
  const out = Buffer.alloc(W * H * 4)
  const landPal = new Map(), seaPal = new Map()
  // Where the land is, at full size, from the grey map tile.mjs writes off the
  // base drawing; the quarter-size land mask would step the coastline
  const { data: mono, info: mi } = await sharp(join(root, 'layers', 'mono.png')).raw().toBuffer({ resolveWithObject: true })
  const isLand = p => mono[p * mi.channels] > 0
  for (let p = 0; p < W * H; p++) {
    const z = zone[p]
    let c
    if (z !== NONE) {
      c = landPal.get(z)
      if (!c) landPal.set(z, (c = landColour(z)))
    } else if (isLand(p)) {
      c = UNCLAIMED
    } else {
      const h = seaHour(p)
      c = seaPal.get(h)
      if (!c) seaPal.set(h, (c = seaColour(h)))
    }
    const i = p * 4
    out[i] = c[0]; out[i + 1] = c[1]; out[i + 2] = c[2]; out[i + 3] = 255
  }
  // Gold between two nations' zones, and out at sea between two solar hours
  const goldAt = p => {
    const z = zone[p], r = zone[p + 1], d = zone[p + W]
    if (z !== NONE) return (r !== NONE && r !== z) || (d !== NONE && d !== z)
    if (r !== NONE || d !== NONE || isLand(p) || isLand(p + 1) || isLand(p + W)) return false
    const h = seaHour(p)
    return seaHour(p + 1) !== h || seaHour(p + W) !== h
  }
  for (let y = 1; y < H - 2; y++) {
    for (let x = 1; x < W - 2; x++) {
      const p = y * W + x
      // the gold border, wherever the zone changes
      if (goldAt(p)) {
        for (const q of [p - 1, p, p + 1, p + 2, p - W, p + W, p + 2 * W]) {
          const i = q * 4
          out[i] = EDGE[0]; out[i + 1] = EDGE[1]; out[i + 2] = EDGE[2]; out[i + 3] = 255
        }
        continue
      }
      const z = zone[p]
      if (z === NONE) continue
      const l = label[p]
      const lr = label[p + 1], ld = label[p + W]
      const own = comps[l].owner
      if ((lr >= 0 && comps[lr].owner && comps[lr].owner !== own) || (ld >= 0 && comps[ld].owner && comps[ld].owner !== own)) {
        for (const q of [p, p + 1]) {
          const i = q * 4
          out[i] = Math.round(out[i] * 0.72); out[i + 1] = Math.round(out[i + 1] * 0.72); out[i + 2] = Math.round(out[i + 2] * 0.72)
        }
      }
    }
  }
  await sharp(out, { raw: { width: W, height: H, channels: 4 } }).png({ compressionLevel: 9 }).toFile(join(root, 'layers', 'zones.png'))

  // --- the lookup -----------------------------------------------------------
  const look = Buffer.alloc(LOOKUP * LOOKUP)
  for (let j = 0; j < LOOKUP; j++) {
    for (let i = 0; i < LOOKUP; i++) {
      look[j * LOOKUP + i] = zoneAnywhere(Math.floor((j + 0.5) * STEP) * W + Math.floor((i + 0.5) * STEP)) + 13
    }
  }
  await sharp(look, { raw: { width: LOOKUP, height: LOOKUP, channels: 1 } }).png({ compressionLevel: 9 }).toFile(join(root, 'public', 'zones.png'))

  // --- the id tiles ---------------------------------------------------------
  // The same pyramid the picture is tiled into (256px tiles, the full 6000px
  // world at level 5), sampled nearest rather than averaged, because an average
  // of two zone ids is a third zone that is not there.
  const idDir = join(root, 'public', 'tiles', 'zoneid')
  rmSync(idDir, { recursive: true, force: true })
  const hash = createHash('sha256')
  const jobs = []
  for (let lz = 0; lz <= 5; lz++) {
    const scale = 2 ** (lz - 5)
    const n = Math.ceil((W * scale) / 256)
    for (let ty = 0; ty < n; ty++) {
      mkdirSync(join(idDir, String(lz), String(ty)), { recursive: true })
      for (let tx = 0; tx < n; tx++) {
        const buf = Buffer.alloc(256 * 256)
        for (let j = 0; j < 256; j++) {
          const Y = Math.floor((ty * 256 + j + 0.5) / scale)
          if (Y >= H) continue
          for (let i = 0; i < 256; i++) {
            const X = Math.floor((tx * 256 + i + 0.5) / scale)
            if (X >= W) continue
            buf[j * 256 + i] = zoneAnywhere(Y * W + X) + 13
          }
        }
        if (lz === 5) hash.update(buf)
        jobs.push(sharp(buf, { raw: { width: 256, height: 256, channels: 1 } })
          .png({ compressionLevel: 9 }).toFile(join(idDir, String(lz), String(ty), `${tx}.png`)))
        if (jobs.length >= 64) await Promise.all(jobs.splice(0))
      }
    }
  }
  await Promise.all(jobs)
  const idVersion = hash.digest('hex').slice(0, 16)

  // --- per city and per nation ----------------------------------------------
  const cityZones = {}
  for (const c of cities) {
    if (c.x == null || c.y == null) continue
    const z = zone[c.y * W + c.x]
    cityZones[`${c.name}|${c.nation}`] = zoneAnywhere(c.y * W + c.x)
  }
  const nationZones = {}
  for (const [n, list] of bands) {
    const zs = new Set(list.map(b => b.z))
    for (let l = 0; l < comps.length; l++) if (comps[l].owner === n && whole[l] !== NONE) zs.add(whole[l])
    // only the zones that hold real land: a band can round onto an hour no pixel ended up in
    nationZones[n] = [...zs].sort((a, b) => a - b)
  }
  // Which zones hold land at all, and which hold land at home. The line under a
  // nation's name gives only the home clocks; a colony's own hour belongs to the
  // panel, not to the name of a country it is nowhere near.
  const used = new Map(), usedHome = new Map()
  for (let p = 0; p < W * H; p += 7) {
    const z = zone[p]; if (z === NONE) continue
    const l = label[p], o = comps[l].owner
    if (!used.has(o)) { used.set(o, new Set()); usedHome.set(o, new Set()) }
    used.get(o).add(z)
    if (home[l]) usedHome.get(o).add(z)
  }
  const homeZones = {}
  for (const n of Object.keys(nationZones)) {
    nationZones[n] = nationZones[n].filter(z => used.get(n)?.has(z))
    homeZones[n] = nationZones[n].filter(z => usedHome.get(n)?.has(z))
  }

  writeFileSync(join(root, 'src', 'data', 'zones.json'), JSON.stringify({ v: idVersion, nations: nationZones, home: homeZones, cities: cityZones }) + '\n')
  const split = Object.entries(nationZones).filter(([, z]) => z.length > 1)
  return { nations: Object.keys(nationZones).length, split }
}

if (process.argv[1] && process.argv[1].endsWith('zones.mjs')) {
  const r = await writeZones()
  if (!r) {
    console.error('layers/borders.png not found')
    process.exit(1)
  }
  console.log(`zones — ${r.nations} nations; more than one zone: ` +
    r.split.map(([n, z]) => `${n} (${z.join(', ')})`).join('; '))
}
