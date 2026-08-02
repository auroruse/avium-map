#!/usr/bin/env node
// Panel-sized crops of the city photographs.
//
// The originals are 4-5MB each and the panel shows them in a 380px 16:9 frame,
// so opening any city pulled a full-resolution photograph down to fill a strip
// the size of a postcard. Only the full view needs the original now, and that is
// a click away rather than on every panel open.
//
// Generated, never committed: the deploy workflow runs `npm run build`, which
// runs this first, so the only city image in git is the one you maintain.
import sharp from 'sharp'
import { existsSync, mkdirSync, readdirSync, rmSync, statSync } from 'fs'
import { basename, extname, join, resolve } from 'path'

const root = resolve(import.meta.dirname, '..')
const srcDir = join(root, 'src', 'assets', 'cities')
const outDir = join(root, 'src', 'assets', 'city-thumbs')

// Cropped to the frame's own ratio, so object-fit: cover has nothing left to
// throw away and no pixel in the file goes unused. 1000px covers the widest the
// frame gets (402px on a phone) at 2x and leaves room over.
const W = 1000
const H = Math.round((W * 9) / 16)
const QUALITY = 78

const IMAGE = /\.(png|jpe?g)$/i

mkdirSync(outDir, { recursive: true })

const sources = readdirSync(srcDir).filter(f => IMAGE.test(f))
const wanted = new Set(sources.map(f => basename(f, extname(f)) + '.jpg'))

// A city whose photograph was removed or renamed would otherwise keep its old
// crop forever, and the panel would go on showing it
for (const f of readdirSync(outDir)) {
  if (!wanted.has(f)) rmSync(join(outDir, f))
}

// Two files for one city collapse to one crop, and the panel and the full view
// resolve the name through separate orderings — so they can disagree about which
// photograph that city has. Worth saying out loud rather than silently keeping
// whichever sorted last.
const byName = new Map()
for (const f of sources) {
  const k = basename(f, extname(f))
  byName.set(k, [...(byName.get(k) ?? []), f])
}
for (const [name, files] of byName) {
  if (files.length > 1) console.warn(`  ! ${name} has ${files.length} images: ${files.join(', ')}`)
}

let built = 0
let bytes = 0

for (const f of sources) {
  const from = join(srcDir, f)
  const to = join(outDir, basename(f, extname(f)) + '.jpg')
  // Rebuild only what changed: a full pass over 24 photographs is slow enough to
  // notice on every dev server start
  if (!existsSync(to) || statSync(to).mtimeMs < statSync(from).mtimeMs) {
    await sharp(from)
      .resize(W, H, { fit: 'cover', position: 'centre' })
      .jpeg({ quality: QUALITY, mozjpeg: true })
      .toFile(to)
    built++
  }
  bytes += statSync(to).size
}

const avg = sources.length ? bytes / sources.length / 1024 : 0
console.log(
  `${sources.length} city thumbs at ${W}x${H} (${built} rebuilt) — ` +
    `${avg.toFixed(0)}KB average, ${(bytes / 1024 / 1024).toFixed(1)}MB total`
)
