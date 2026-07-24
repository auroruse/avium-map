#!/usr/bin/env node
// Merges a TSV file into cities.json, preserving existing coordinates.
// Usage: node scripts/merge-tsv.mjs [path/to/cities.tsv]
// Defaults to src/data/cities.tsv if no argument given.

import { readFileSync, writeFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

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

// Load existing coords
const existing = JSON.parse(readFileSync(jsonPath, 'utf8'))
const coordMap = new Map()
for (const c of existing) {
  if (c.x != null && c.y != null) coordMap.set(c.name, [c.x, c.y])
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
    city[field] = numFields.has(field)
      ? parseFloat(vals[j].replace(/,/g, '')) || 0
      : (vals[j] === '-' ? '' : vals[j])
  }

  const coords = coordMap.get(city.name)
  if (coords) { city.x = coords[0]; city.y = coords[1] }
  cities.push(city)
}

writeFileSync(jsonPath, JSON.stringify(cities, null, 2) + '\n')

const placed = cities.filter(c => c.x != null).length
const added = cities.filter(c => !coordMap.has(c.name)).length
const dropped = existing.filter(c => !cities.find(n => n.name === c.name)).length
console.log(`${cities.length} cities (${placed} placed, ${added} new, ${dropped} dropped)`)
