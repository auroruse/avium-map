#!/usr/bin/env node
// Merges a TSV file into cities.json, preserving existing coordinates.
// Usage: node scripts/merge-tsv.mjs [path/to/cities.tsv]
// Defaults to src/data/cities.tsv if no argument given.

import { readFileSync, writeFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { writeCoords } from './coords.mjs'
import { writeAreas } from './areas.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const tsvPath = resolve(process.argv[2] || `${root}/src/data/cities.tsv`)
const jsonPath = resolve(root, 'src/data/cities.json')

const colMap = {
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

const numFields = new Set(['population', 'gdp', 'gdpPerCapita'])

const tsv = readFileSync(tsvPath, 'utf8')
const lines = tsv.trim().split('\n')
const headers = lines[0].split('\t').map(h => h.trim())
const cols = headers.map(h => colMap[h.toLowerCase()] ?? null)
const nameCol = cols.indexOf('name')
if (nameCol < 0) { console.error('TSV needs a "Name" column'); process.exit(1) }

// Load existing coords, keyed on name AND nation. Name alone collides: seven
// cities share a name with one in a different nation, and whichever lacked
// coordinates was silently handed the other's, landing it on the wrong continent.
//
// A rename still has to carry its placements over, so a name that is unique on
// both sides falls back to matching on name alone — that is what let a hundred
// colonies lose their "Arvernois " prefix without being unplaced. A name that
// appears more than once never falls back, which is what stops a repaired
// duplicate from being broken again by the next merge.
//
// When the name itself is what changed, the IRL parallel is the thing that
// survives: Kōzo became Ōgiya and Kanase became Kotodai, but both kept Jeonju
// and Chungju, along with their population and output. Same uniqueness rule, and
// it still earns its keep — Saalegiri and Chemeketa are both modelled on Salem,
// so neither of them can ever carry a placement this way.
const existing = JSON.parse(readFileSync(jsonPath, 'utf8'))
const key = c => `${c.name}\t${c.nation}`
const par = c => c.irlParallel || null

const coordMap = new Map()
const soloCoord = new Map()
const parCoord = new Map()
const oldNameCount = new Map()
const oldParCount = new Map()
for (const c of existing) {
  oldNameCount.set(c.name, (oldNameCount.get(c.name) ?? 0) + 1)
  if (par(c)) oldParCount.set(par(c), (oldParCount.get(par(c)) ?? 0) + 1)
  if (c.x == null || c.y == null) continue
  coordMap.set(key(c), [c.x, c.y])
  soloCoord.set(c.name, [c.x, c.y])
  if (par(c)) parCoord.set(par(c), [c.x, c.y])
}

const cities = []
for (let i = 1; i < lines.length; i++) {
  const vals = lines[i].split('\t').map(v => v.trim())
  if (!vals[nameCol]) continue

  const city = {
    name: '', nation: '', population: 0, gdp: 0, gdpPerCapita: 0,
    nativeScript: '', irlParallel: '', alpha3: '', x: null, y: null,
  }
  for (let j = 0; j < cols.length; j++) {
    const field = cols[j]
    if (!field || !vals[j]) continue
    // Both of the sheet's ways of writing "there isn't one" become the empty
    // string, so the map never has to render a city whose real-world model is
    // the letters N slash A
    city[field] = numFields.has(field)
      ? parseFloat(vals[j].replace(/,/g, '')) || 0
      : (vals[j] === '-' || vals[j] === 'N/A' ? '' : vals[j])
  }

  cities.push(city)
}

// Second pass: the fallback needs to know whether a name is unique in the new
// data too, which isn't known until every row has been read
const newNameCount = new Map()
const newParCount = new Map()
for (const c of cities) {
  newNameCount.set(c.name, (newNameCount.get(c.name) ?? 0) + 1)
  if (par(c)) newParCount.set(par(c), (newParCount.get(par(c)) ?? 0) + 1)
}

let renamed = 0
let reparented = 0
for (const city of cities) {
  let coords = coordMap.get(key(city))
  if (!coords && oldNameCount.get(city.name) === 1 && newNameCount.get(city.name) === 1) {
    coords = soloCoord.get(city.name)
    if (coords) renamed++
  }
  if (!coords && par(city) && oldParCount.get(par(city)) === 1 && newParCount.get(par(city)) === 1) {
    coords = parCoord.get(par(city))
    if (coords) reparented++
  }
  if (coords) { city.x = coords[0]; city.y = coords[1] }
}

writeFileSync(jsonPath, JSON.stringify(cities, null, 2) + '\n')

// Positions just changed, so the derived table has to follow them
writeCoords()

// A nation's territory is worked out from the cities standing in it, so adding,
// moving or dropping any of them can change who owns what. Silent when the
// drawing is not on this machine, which is every checkout that is not the one it
// was drawn on.
const areas = await writeAreas()

const placed = cities.filter(c => c.x != null).length
const added = cities.filter(c => !coordMap.has(key(c))).length
const dropped = existing.filter(c => !cities.find(n => key(n) === key(c))).length
console.log(
  `${cities.length} cities (${placed} placed, ${added} new, ${dropped} dropped, ` +
    `${renamed} matched by name after a nation rename, ${reparented} by IRL parallel after a city rename)`
)
if (areas) console.log(`areas.json — ${areas.nations} nations, ${(areas.measured / 1e6).toFixed(2)}M km²`)
