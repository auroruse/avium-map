#!/usr/bin/env node
// Writes src/assets/flags/<nation>.png: every nation's flag, 264px wide, for the
// card beside a nation's name in its panel (66px there, so this is four times
// over and stays sharp on any screen).
//
// The flags are the Talopedia's (../The Talopedia/public/assets/flags), found by
// the nation's name as the Talopedia spells its files. Run this again when the
// Talopedia gains or changes one:  node scripts/flags.mjs
//
// A nation with no flag of its own gets no file. Its panel shows its overlord's
// instead (flagFor in src/main.ts), so a colony follows whatever its overlord
// flies without a copy to fall out of step.
//
// Three are 64px in the Talopedia and soft at this size, with no larger copy
// known (18 Nov 2026): Frederikka Islands, Kullanmaan and West Bangala.
import sharp from 'sharp'
import { mkdirSync, readFileSync, readdirSync, rmSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const TALOPEDIA = resolve(root, '../The Talopedia/public/assets/flags')
const OUT = join(root, 'src/assets/flags')
const WIDTH = 264

// As talopediaUrl in src/data/talopedia.ts: no diacritics, lower case, hyphens
const slug = name =>
  name
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')

// Where the Talopedia's file is not the map's name for the nation
const ALIAS = {
  'e-s-u': 'esu',
  barbary: 'barbarie',
  'napolyon-bonparterre-islands': 'bonparterre-islands',
  cuohpnjalla: 'cuohpajalla',
}

const lines = readFileSync(join(root, 'src/data/nations.tsv'), 'utf8').trim().split('\n')
const nameCol = lines[0].split('\t').map(s => s.trim()).indexOf('COMMON NAME')
const names = lines.slice(1).map(l => l.split('\t')[nameCol].trim()).filter(Boolean)
const have = new Map(readdirSync(TALOPEDIA).filter(f => /\.(png|jpe?g)$/i.test(f)).map(f => [f.replace(/\.[^.]+$/, ''), f]))

rmSync(OUT, { recursive: true, force: true })
mkdirSync(OUT, { recursive: true })
const none = []
for (const name of names) {
  const s = slug(name)
  const tal = have.get(ALIAS[s] ?? s)
  const src = tal ? join(TALOPEDIA, tal) : null
  if (!src) {
    none.push(name)
    continue
  }
  await sharp(src).resize({ width: WIDTH, withoutEnlargement: true }).png({ compressionLevel: 9, palette: false }).toFile(join(OUT, s + '.png'))
}
console.log(`flags: ${names.length - none.length} of ${names.length} nations`)
console.log(`  none of their own (${none.length}): ${none.join(', ')}`)
