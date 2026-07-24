#!/usr/bin/env node
import sharp from 'sharp'
import { existsSync, rmSync } from 'fs'
import { join, resolve } from 'path'

const root = resolve(import.meta.dirname, '..')
const layersDir = join(root, 'layers')
const tilesDir = join(root, 'public', 'tiles')

const OCEAN = { r: 45, g: 74, b: 94, alpha: 255 }
const CLEAR = { r: 0, g: 0, b: 0, alpha: 0 }

const LAYERS = {
  base: { skipBlanks: -1, background: OCEAN },
  // transparent overlays: skip fully-empty tiles (most of the grid)
  borders: { skipBlanks: 0, background: CLEAR },
  rivers: { skipBlanks: 0, background: CLEAR },
}

const requested = process.argv[2]
if (requested && !LAYERS[requested]) {
  console.error(`Unknown layer: ${requested}\nValid: ${Object.keys(LAYERS).join(', ')}`)
  process.exit(1)
}

const todo = requested ? { [requested]: LAYERS[requested] } : LAYERS

for (const [name, opts] of Object.entries(todo)) {
  const input = join(layersDir, `${name}.png`)
  const output = join(tilesDir, name)

  if (!existsSync(input)) {
    console.log(`skip ${name} — ${input} not found`)
    continue
  }

  if (existsSync(output)) rmSync(output, { recursive: true })

  console.log(`tiling ${name}...`)
  const t = Date.now()

  let img = sharp(input)

  if (opts.background) {
    const meta = await img.metadata()
    const maxDim = Math.max(meta.width, meta.height)
    // Leaflet CRS.Simple expects 2^z tiles per side — pad to the next power-of-2 grid
    const tileEdge = Math.pow(2, Math.ceil(Math.log2(maxDim / 256))) * 256
    img = img.extend({
      right: tileEdge - meta.width,
      bottom: tileEdge - meta.height,
      background: opts.background,
    })
  }

  await img
    .png()
    .tile({ size: 256, layout: 'google', skipBlanks: opts.skipBlanks })
    .toFile(output)

  // clean up the blank tile dzsave creates
  const blank = join(output, 'blank.png')
  if (existsSync(blank)) rmSync(blank)

  console.log(`  done (${((Date.now() - t) / 1000).toFixed(1)}s)`)
}

console.log('all layers tiled')
