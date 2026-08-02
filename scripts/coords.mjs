// No shebang: vite.config.ts imports this so the placer's Save can rewrite the
// table, and esbuild will not bundle a module that starts with one.
//
// Writes src/data/coordinates.tsv: every placed city and territory name with its
// geographic position, for anything that needs to know where a place is without
// running the map.
//
// Derived, never hand-edited. The x,y in cities.json and labels.json stay the
// source of truth — this file is regenerated whenever either changes, by the
// merge script and by the placer's Save.
//
// The projection is the one in src/main.ts. Avium's tilt puts the graticule on
// the map's diagonals: the equator runs bottom-left to top-right, the prime
// meridian top-left to bottom-right, and they cross at the middle of the map.
// The poles sit in the top-left and bottom-right corners, so longitude has to be
// read against the width the square actually has at that latitude rather than
// against the diagonal, or half the globe would have nowhere to be.
import { readFileSync, writeFileSync } from 'fs'
import { join, resolve } from 'path'

const CONTENT = 6000
const ORIGIN = CONTENT / 2
const R = Math.hypot(ORIGIN, ORIGIN) // half-diagonal: pole and antimeridian distance
const S = Math.SQRT1_2

function toGeo(x, y) {
  const dx = x - ORIGIN
  const dy = y - ORIGIN
  const u = (dx - dy) * S // east along the equator
  const v = -(dx + dy) * S // north along the prime meridian; y grows downward
  const halfWidth = R - Math.abs(v)
  return {
    lat: (90 * v) / R,
    lon: halfWidth < 1e-9 ? 0 : (180 * u) / halfWidth,
  }
}

// 4 decimals is about 11m at this scale, well past the 2.357km a map pixel
// covers — precise enough that nothing is lost, short enough to read
const dec = n => n.toFixed(4)
const human = g =>
  `${Math.abs(g.lat).toFixed(2)}°${g.lat >= 0 ? 'N' : 'S'} ` +
  `${Math.abs(g.lon).toFixed(2)}°${g.lon >= 0 ? 'E' : 'W'}`

const HEAD = ['KIND', 'NAME', 'NATION', 'TYPE', 'X', 'Y', 'LATITUDE', 'LONGITUDE', 'POSITION']

export function writeCoords(dataDir = resolve(import.meta.dirname, '..', 'src', 'data')) {
  const read = f => JSON.parse(readFileSync(join(dataDir, f), 'utf8'))
  const rows = []

  for (const c of read('cities.json')) {
    if (c.x == null || c.y == null) continue
    const g = toGeo(c.x, c.y)
    rows.push(['city', c.name, c.nation, '', c.x, c.y, dec(g.lat), dec(g.lon), human(g)])
  }

  // Nations, colonies, continents, oceans and seas all live in labels.json; TYPE
  // says which. A few have no coordinate because they derive their position from
  // the cities they contain, and those have nothing fixed to record.
  for (const d of read('labels.json')) {
    if (d.x == null || d.y == null) continue
    const g = toGeo(d.x, d.y)
    rows.push(['label', d.text, '', d.type, d.x, d.y, dec(g.lat), dec(g.lon), human(g)])
  }

  rows.sort((a, b) => a[0].localeCompare(b[0]) || String(a[1]).localeCompare(String(b[1])))
  const tsv = [HEAD, ...rows].map(r => r.join('\t')).join('\n') + '\n'
  writeFileSync(join(dataDir, 'coordinates.tsv'), tsv)
  return { cities: rows.filter(r => r[0] === 'city').length, labels: rows.filter(r => r[0] === 'label').length }
}

// Run directly for a one-off regeneration; imported elsewhere to keep it current
if (process.argv[1] && process.argv[1].endsWith('coords.mjs')) {
  const { cities, labels } = writeCoords()
  console.log(`coordinates.tsv — ${cities} cities, ${labels} territory names`)
}
