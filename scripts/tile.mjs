#!/usr/bin/env node
import sharp from 'sharp'
import { existsSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { createHash } from 'crypto'
import { join, resolve } from 'path'

const root = resolve(import.meta.dirname, '..')
const layersDir = join(root, 'layers')
const tilesDir = join(root, 'public', 'tiles')

// npm run dev and npm run build both call this with no arguments, so dropping a
// redrawn layer into layers/ is the whole of it — the next run picks it up. That
// only works if the common case is free, hence the stamp: a layer whose drawing
// and settings hash the same as last time is left alone.
//
// Naming a layer on the command line always tiles it, stamp or not. "Retile the
// base" should mean what it says.
//
// The stamp is local state and stays that way. layers/*.PNG is gitignored, so a
// checkout has the tiles but not the drawings they came from, and a CI build
// finds no layers at all and quietly skips every one of them. The committed
// tiles are what deploys.
const stampPath = join(root, '.tilestamp.json')
const stamp = existsSync(stampPath) ? JSON.parse(readFileSync(stampPath, 'utf8')) : {}

// The sea itself, sampled from base.PNG. Edge tiles are padded with it and
// #map's CSS background is the same value, so the strip of padding past the
// 6000px world and the page behind that are indistinguishable from the water —
// the white hairline is what marks where the world actually stops. Change the
// base map's palette and both of these move together, or a band appears down the
// right and bottom edges.
const OCEAN = { r: 62, g: 78, b: 111, alpha: 255 }
const CLEAR = { r: 0, g: 0, b: 0, alpha: 0 }

// The base map is drawn with a pure white coastline, and white is the one value
// it cannot afford to spend there. It outranks the city labels and the markers'
// own white halo, so the eye reads the outline before the content, and its width
// wanders between 4 and 36 pixels, which makes it a deposit rather than a line.
//
// So it is turned into a dark line of even weight on the way to the tiles. Keep
// drawing the coast in white — this is what the white is for. Nothing else in the
// pipeline sees the change: layers/base.PNG stays exactly as drawn, which is also
// what keeps nudge.mjs reading the same geometry it always has.
const COAST = [43, 51, 72]
// How much of the white band survives, measured inward from the land it hugs
const COAST_PX = 2
const LAND = [180, 179, 191]
const TOLERANCE = 14

const LAYERS = {
  base: { skipBlanks: -1, background: OCEAN, coastline: true },
  // transparent overlays: skip fully-empty tiles (most of the grid)
  borders: { skipBlanks: 0, background: CLEAR },
  rivers: { skipBlanks: 0, background: CLEAR },
}

// Recolours the white coastline and trims it to an even width.
//
// The trimming happens from the sea side only. The land edge never moves, so the
// hundreds of cities nudged against this geometry keep standing exactly where
// they were put, and a city that was on land is still on land.
//
// A white region with no land anywhere in it is left at full width rather than
// trimmed away. An islet can be too small to hold anything but its own coastline
// — Bidau stands on one — and thinning that to nothing would sink the island.
async function inkCoastline(input, keep) {
  const { data, info } = await sharp(input).raw().toBuffer({ resolveWithObject: true })
  const { width: W, height: H, channels: C } = info
  const N = W * H

  const WHITE = 1
  const GROUND = 2
  const kind = new Uint8Array(N)
  let whiteN = 0
  for (let p = 0; p < N; p++) {
    const i = p * C
    if (data[i] > 230 && data[i + 1] > 230 && data[i + 2] > 230) {
      kind[p] = WHITE
      whiteN++
    } else if (
      Math.abs(data[i] - LAND[0]) < TOLERANCE &&
      Math.abs(data[i + 1] - LAND[1]) < TOLERANCE &&
      Math.abs(data[i + 2] - LAND[2]) < TOLERANCE
    ) {
      kind[p] = GROUND
    }
  }
  if (!whiteN) return sharp(data, { raw: { width: W, height: H, channels: C } })

  const disc = []
  for (let dy = -keep; dy <= keep; dy++)
    for (let dx = -keep; dx <= keep; dx++) if (dx * dx + dy * dy <= keep * keep) disc.push([dx, dy])

  // One component swallows most of the world's coastline, so both of these are
  // sized for every white pixel at once rather than grown
  const seen = new Uint8Array(N)
  const stack = new Int32Array(whiteN)
  const members = new Int32Array(whiteN)
  const paint = (p, c) => {
    const i = p * C
    data[i] = c[0]
    data[i + 1] = c[1]
    data[i + 2] = c[2]
  }

  let kept = 0
  let sunk = 0
  let islets = 0
  for (let s = 0; s < N; s++) {
    if (kind[s] !== WHITE || seen[s]) continue
    let sp = 0
    let mn = 0
    let touchesLand = false
    stack[sp++] = s
    seen[s] = 1
    while (sp) {
      const p = stack[--sp]
      members[mn++] = p
      const x = p % W
      const y = (p / W) | 0
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx
          const ny = y + dy
          if ((!dx && !dy) || nx < 0 || ny < 0 || nx >= W || ny >= H) continue
          const q = ny * W + nx
          if (kind[q] === GROUND) touchesLand = true
          else if (kind[q] === WHITE && !seen[q]) {
            seen[q] = 1
            stack[sp++] = q
          }
        }
      }
    }

    if (!touchesLand) {
      islets++
      for (let m = 0; m < mn; m++) paint(members[m], COAST)
      kept += mn
      continue
    }
    for (let m = 0; m < mn; m++) {
      const p = members[m]
      const x = p % W
      const y = (p / W) | 0
      let nearLand = false
      for (const [dx, dy] of disc) {
        const nx = x + dx
        const ny = y + dy
        if (nx < 0 || ny < 0 || nx >= W || ny >= H) continue
        if (kind[ny * W + nx] === GROUND) {
          nearLand = true
          break
        }
      }
      if (nearLand) {
        paint(p, COAST)
        kept++
      } else {
        paint(p, [OCEAN.r, OCEAN.g, OCEAN.b])
        sunk++
      }
    }
  }

  console.log(
    `  coastline: ${whiteN} white px -> ${kept} inked at ${keep}px, ${sunk} returned to the sea` +
      (islets ? `, ${islets} all-coast islet${islets > 1 ? 's' : ''} left at full width` : '')
  )
  return sharp(data, { raw: { width: W, height: H, channels: C } })
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

  // The settings go into the hash alongside the drawing, so changing COAST or
  // COAST_PX retiles too rather than leaving the old line in place. Only the
  // layer that draws a coastline is hashed against them; borders and rivers have
  // no business being rebuilt because the sea colour moved.
  const sig = createHash('sha256')
    .update(readFileSync(input))
    .update(JSON.stringify([opts, opts.coastline ? [COAST, COAST_PX] : null]))
    .digest('hex')
    .slice(0, 16)
  if (!requested && stamp[name] === sig && existsSync(output)) {
    console.log(`skip ${name} — unchanged since the last tiling`)
    continue
  }

  if (existsSync(output)) rmSync(output, { recursive: true })

  console.log(`tiling ${name}...`)
  const t = Date.now()

  let img = opts.coastline ? await inkCoastline(input, COAST_PX) : sharp(input)

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

  stamp[name] = sig
  writeFileSync(stampPath, JSON.stringify(stamp, null, 2) + '\n')

  console.log(`  done (${((Date.now() - t) / 1000).toFixed(1)}s)`)
}

console.log('all layers tiled')
