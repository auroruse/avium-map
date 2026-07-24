// Downscale city banners to what the panel actually displays.
// The card is 400px wide (full-width on mobile) and the banner is 150px tall
// with object-fit: cover, so anything past ~1200px is bytes nobody sees.
// Originals are moved to banners-original/ (gitignored) before overwriting.
//
//   node scripts/optimize-banners.mjs
//
// Re-runnable: images already at or under MAX_W are skipped.

import { readdir, mkdir, rename, stat } from 'node:fs/promises'
import { join, extname, basename } from 'node:path'
import sharp from 'sharp'

const SRC = 'src/assets/cities'
const ORIG = 'banners-original'
const MAX_W = 1200
const QUALITY = 82

const mb = n => (n / 1048576).toFixed(2) + ' MB'

await mkdir(ORIG, { recursive: true })

const files = (await readdir(SRC)).filter(f => /\.(png|jpe?g)$/i.test(f))
let before = 0
let after = 0
let skipped = 0

for (const file of files) {
  const path = join(SRC, file)
  const meta = await sharp(path).metadata()
  if (meta.width <= MAX_W) {
    skipped++
    continue
  }

  const sizeBefore = (await stat(path)).size
  // sharp cannot stream a file onto itself, so buffer the result first
  const out = await sharp(path)
    .resize({ width: MAX_W, withoutEnlargement: true })
    .jpeg({ quality: QUALITY, mozjpeg: true })
    .toBuffer()

  await rename(path, join(ORIG, file))
  const dest = join(SRC, basename(file, extname(file)) + '.jpeg')
  await sharp(out).toFile(dest)

  before += sizeBefore
  after += out.length
  console.log(
    `${file.padEnd(24)} ${meta.width}x${meta.height} ${mb(sizeBefore)}  ->  ${MAX_W}px ${mb(out.length)}`
  )
}

if (skipped) console.log(`${skipped} already optimized, skipped`)
if (before) {
  console.log(`\nTotal ${mb(before)} -> ${mb(after)} (${((1 - after / before) * 100).toFixed(1)}% smaller)`)
  console.log(`Originals moved to ${ORIG}/`)
}
