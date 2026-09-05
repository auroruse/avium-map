#!/usr/bin/env node
import sharp from 'sharp'
import { existsSync, readFileSync, rmSync, statSync, writeFileSync } from 'fs'
import { createHash } from 'crypto'
import { join, resolve } from 'path'
import { writeAreas } from './areas.mjs'

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
const versionPath = join(root, 'src/data/tiles.json')
// The stamp is gitignored, so a fresh checkout starts empty and would tile
// everything from scratch. The committed copy is what it starts from instead —
// the two hold the same signatures, and only the tracked one ships.
const stamp = existsSync(stampPath)
  ? JSON.parse(readFileSync(stampPath, 'utf8'))
  : existsSync(versionPath)
    ? JSON.parse(readFileSync(versionPath, 'utf8'))
    : {}

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
// Bumped when the mask format changes, so an old landmask.png is not left in place
const MASK_VERSION = 1
const LAND = [180, 179, 191]
const TOLERANCE = 14

const LAYERS = {
  base: { skipBlanks: -1, background: OCEAN, coastline: true },
  // transparent overlays: skip fully-empty tiles (most of the grid)
  borders: { skipBlanks: 0, background: CLEAR, areas: true },
  rivers: { skipBlanks: 0, background: CLEAR },
}

// What every pixel of the drawing is: land, the white coastline, or sea. Both the
// coastline ink and the land mask are read off this, so the two can never come to
// different conclusions about where the ground is.
const WHITE = 1
const GROUND = 2
function classify(data, { width: W, height: H, channels: C }) {
  const kind = new Uint8Array(W * H)
  let whiteN = 0
  for (let p = 0; p < W * H; p++) {
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
  return { kind, whiteN }
}

// One byte per MASK_CELL square of the drawing, holding how much of that square
// is land. The measure tool reads it to say how much of a shape the user drew is
// ground and how much is water, which the tiles cannot answer — they are pictures
// by the time they reach the browser, and at low zoom they are not even the right
// pixels any more.
//
// A fraction rather than a flag. A coastal cell is mostly one thing and a little
// of the other, and rounding that to all-or-nothing is where a land area starts
// disagreeing with itself depending on how the polygon was drawn.
const MASK_CELL = 4
const maskPath = join(root, 'public', 'landmask.png')

// The white coastline sits between the two things being counted, so it has to be
// split between them: a stroke pixel counts as whichever of land or sea is
// nearer, ties to land. Left whole on one side of the ledger it would be worth
// about three percent of the world's land area, decided by a drawing convention.
function sideOf(kind, W, H, x, y, limit = 12) {
  for (let r = 1; r <= limit; r++) {
    let sea = false
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        if (Math.max(Math.abs(dx), Math.abs(dy)) !== r) continue
        const nx = x + dx
        const ny = y + dy
        if (nx < 0 || ny < 0 || nx >= W || ny >= H) continue
        const k = kind[ny * W + nx]
        if (k === GROUND) return GROUND
        if (k === 0) sea = true
      }
    }
    if (sea) return 0
  }
  return GROUND
}

async function writeLandMask(kind, { width: W, height: H }) {
  const MW = Math.ceil(W / MASK_CELL)
  const MH = Math.ceil(H / MASK_CELL)
  const cells = MASK_CELL * MASK_CELL
  const out = Buffer.alloc(MW * MH)
  let landPx = 0
  for (let my = 0; my < MH; my++) {
    for (let mx = 0; mx < MW; mx++) {
      let land = 0
      for (let dy = 0; dy < MASK_CELL; dy++) {
        const y = my * MASK_CELL + dy
        if (y >= H) continue
        for (let dx = 0; dx < MASK_CELL; dx++) {
          const x = mx * MASK_CELL + dx
          if (x >= W) continue
          const k = kind[y * W + x]
          if (k === GROUND || (k === WHITE && sideOf(kind, W, H, x, y) === GROUND)) land++
        }
      }
      landPx += land
      out[my * MW + mx] = Math.round((land * 255) / cells)
    }
  }
  // Greyscale on disk as well as in intent — left to sharp's default the single
  // channel is encoded as sRGB and the file carries three copies of itself
  await sharp(out, { raw: { width: MW, height: MH, channels: 1 } })
    .toColourspace('b-w')
    .png({ compressionLevel: 9 })
    .toFile(maskPath)
  const { size } = statSync(maskPath)
  console.log(
    `  land mask: ${MW}x${MH} at ${MASK_CELL}px/cell, ${(100 * landPx / (W * H)).toFixed(2)}% land, ` +
      `${(size / 1024).toFixed(0)}KB`
  )
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
function inkCoastline(data, kind, info, whiteN, keep) {
  const { width: W, height: H, channels: C } = info
  const N = W * H
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
    .update(JSON.stringify([opts, opts.coastline ? [COAST, COAST_PX, MASK_CELL, MASK_VERSION] : null]))
    .digest('hex')
    .slice(0, 16)
  if (!requested && stamp[name] === sig && existsSync(output)) {
    console.log(`skip ${name} — unchanged since the last tiling`)
    continue
  }

  if (existsSync(output)) rmSync(output, { recursive: true })

  console.log(`tiling ${name}...`)
  const t = Date.now()

  // One read of the drawing feeds both the coastline ink and the land mask, and
  // one classification decides where the ground is for both of them
  let img
  if (opts.coastline) {
    const { data, info } = await sharp(input).raw().toBuffer({ resolveWithObject: true })
    const { kind, whiteN } = classify(data, info)
    await writeLandMask(kind, info)
    img = inkCoastline(data, kind, info, whiteN, COAST_PX)
  } else {
    img = sharp(input)
  }

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

  // The nation areas are read off this drawing, so they are only ever as current
  // as the tiles are
  if (opts.areas) {
    const r = await writeAreas(root)
    if (r) console.log(`  areas: ${r.nations} nations, ${(r.measured / 1e6).toFixed(2)}M km²`)
  }

  stamp[name] = sig
  writeFileSync(stampPath, JSON.stringify(stamp, null, 2) + '\n')
  // The same signatures again, this time into the repo. A tile keeps its path
  // for the life of the map, so a browser that fetched tiles/borders/5/7/15.png
  // once will go on serving that copy from its cache after every retile there
  // ever is — which is how a border that had moved months ago came back on one
  // zoom level and not the next. The app hangs this on the tile URL, so a
  // retiled layer is a new URL and a layer that did not change is not.
  writeFileSync(versionPath, JSON.stringify(stamp, null, 2) + '\n')

  console.log(`  done (${((Date.now() - t) / 1000).toFixed(1)}s)`)
}

console.log('all layers tiled')
