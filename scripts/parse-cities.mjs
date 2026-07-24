#!/usr/bin/env node
import { readFileSync, writeFileSync, mkdirSync } from 'fs'
import { resolve, dirname } from 'path'

const root = resolve(import.meta.dirname, '..')
const tsvPath = process.argv[2] || resolve(root, '../../Avium/Roleplay IC/Reference/World/Cities.tsv')
const outPath = resolve(root, 'src/data/cities.json')

const tsv = readFileSync(tsvPath, 'utf-8')
const lines = tsv.split('\n').filter(l => l.trim())

// RANK | CITY | NATION | POPULATION | GRDP PPP ($) | REAL GRDP P/C ($) | NATIVE SCRIPT | IRL PARALLEL | SOURCE | ALPHA-3 CODE
const cities = lines.slice(1).map(line => {
  const c = line.split('\t')
  const num = s => parseInt((s || '').replace(/,/g, '')) || 0
  return {
    name: (c[1] || '').trim(),
    nation: (c[2] || '').trim(),
    population: num(c[3]),
    gdp: num(c[4]),
    gdpPerCapita: num(c[5]),
    nativeScript: (c[6] || '').trim().replace(/^-$/, ''),
    irlParallel: (c[7] || '').trim(),
    alpha3: (c[9] || '').trim(),
    x: null,
    y: null,
  }
})

mkdirSync(dirname(outPath), { recursive: true })
writeFileSync(outPath, JSON.stringify(cities, null, 2))
console.log(`${cities.length} cities → ${outPath}`)
