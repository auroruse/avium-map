// No shebang: tile.mjs imports this, and esbuild will not bundle a module that
// starts with one.
//
// Writes src/data/borderlines.json: every border on the map as a line, for the
// Hybrid map, which draws borders as a thin stroke over the ground and not as
// fills.
//
// Derived, never hand-edited. layers/borders.png is a flat fill per bloc with no
// line of its own, so the lines are where one fill meets another or meets
// unclaimed ground. Regenerated whenever the borders are tiled.
//
// The fills stop a pixel or two short of the sea (they cover the drawn ground,
// and the land carries the inked coastline as well), so read as they are, every
// coast would be a border with the strip of bare land beside it and no border
// would reach the water. Each fill is grown across that strip first, and only
// across it: ground more than COAST_REACH px from the sea is left alone, because
// half the land on the map is unclaimed and a fill's edge against it is a border
// that has to stay where it was drawn.
//
// What is still unclaimed after that and small (a headland the fill missed, a
// wider stretch of coastline) goes to the fills around it too. Left alone, each
// one is a speck of border on the coast, and a border that reaches the coast
// there stops short of the water by the width of it.
import sharp from 'sharp'
import { existsSync, writeFileSync } from 'fs'
import { join, resolve } from 'path'

const COAST_REACH = 3
// The largest patch of unclaimed ground, in px, that is taken for a gap in the
// drawing and not for a territory nobody holds
const POCKET = 400
// How far a line may stray from the pixel edges it was traced along. The trace
// runs between pixels, so a diagonal border is a staircase of unit steps; this
// is enough to turn a staircase into its diagonal and not enough to cut a corner
// anyone drew.
const TOLERANCE = 0.75

const E = 1
const S = 2
const W = 4
const N = 8

export async function writeBorderLines(root = resolve(import.meta.dirname, '..')) {
  const bordersPath = join(root, 'layers', 'borders.png')
  const monoPath = join(root, 'layers', 'mono.png')
  if (!existsSync(bordersPath) || !existsSync(monoPath)) return null

  const { data, info } = await sharp(bordersPath).raw().toBuffer({ resolveWithObject: true })
  const { width: w, height: h, channels: C } = info
  const n = w * h
  const mono = await sharp(monoPath).resize(w, h, { kernel: 'nearest' }).extractChannel(0).raw().toBuffer()

  // 0 for unclaimed; otherwise the packed colour plus one, so black is a colour too
  const id = new Int32Array(n)
  for (let p = 0; p < n; p++) {
    const i = p * C
    if (C === 4 && data[i + 3] < 128) continue
    id[p] = ((data[i] << 16) | (data[i + 1] << 8) | data[i + 2]) + 1
  }
  const land = new Uint8Array(n)
  for (let p = 0; p < n; p++) land[p] = mono[p] > 0 ? 1 : 0

  // The coast strip: land within COAST_REACH px of the sea
  let near = new Uint8Array(n)
  for (let p = 0; p < n; p++) near[p] = land[p] ? 0 : 1
  for (let pass = 0; pass < COAST_REACH; pass++) {
    const next = Uint8Array.from(near)
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const p = y * w + x
        if (near[p]) continue
        if ((x > 0 && near[p - 1]) || (x < w - 1 && near[p + 1]) || (y > 0 && near[p - w]) || (y < h - 1 && near[p + w])) next[p] = 1
      }
    }
    near = next
  }
  // ...and each fill grown across it, a pixel a pass, from a copy so one pass
  // cannot run the length of a coast
  for (let pass = 0; pass < COAST_REACH; pass++) {
    const from = Int32Array.from(id)
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const p = y * w + x
        if (from[p] || !land[p] || !near[p]) continue
        id[p] =
          (x > 0 && from[p - 1]) || (x < w - 1 && from[p + 1]) || (y > 0 && from[p - w]) || (y < h - 1 && from[p + w]) || 0
      }
    }
  }

  // Unclaimed ground in patches of no more than POCKET px, handed to whichever
  // fill reaches each pixel first
  const seen = new Uint8Array(n)
  const stack = new Int32Array(n)
  let pockets = []
  for (let s = 0; s < n; s++) {
    if (seen[s] || id[s] || !land[s]) continue
    let sp = 0
    let size = 0
    stack[sp++] = s
    seen[s] = 1
    const first = pockets.length
    while (sp) {
      const p = stack[--sp]
      if (size++ < POCKET) pockets.push(p)
      const x = p % w
      for (const q of [x > 0 ? p - 1 : -1, x < w - 1 ? p + 1 : -1, p - w, p + w]) {
        if (q < 0 || q >= n || seen[q] || id[q] || !land[q]) continue
        seen[q] = 1
        stack[sp++] = q
      }
    }
    if (size > POCKET) pockets.length = first
  }
  for (;;) {
    const taken = []
    for (const p of pockets) {
      const x = p % w
      const from = (x > 0 && id[p - 1]) || (x < w - 1 && id[p + 1]) || (p >= w && id[p - w]) || (p < n - w && id[p + w]) || 0
      if (from) taken.push(p, from)
    }
    if (!taken.length) break
    for (let i = 0; i < taken.length; i += 2) id[taken[i]] = taken[i + 1]
    pockets = pockets.filter(p => !id[p])
  }

  // A border runs between two land pixels of different ownership. Each such pair
  // is one unit edge on the lattice of pixel corners, kept as a bit on both of
  // its ends.
  const cw = w + 1
  const edges = new Uint8Array(cw * (h + 1))
  let units = 0
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const p = y * w + x
      if (!land[p]) continue
      if (x < w - 1 && land[p + 1] && id[p] !== id[p + 1]) {
        const c = y * cw + x + 1
        edges[c] |= S
        edges[c + cw] |= N
        units++
      }
      if (y < h - 1 && land[p + w] && id[p] !== id[p + w]) {
        const c = (y + 1) * cw + x
        edges[c] |= E
        edges[c + 1] |= W
        units++
      }
    }
  }

  const degree = c => {
    const m = edges[c]
    return (m & 1) + ((m >> 1) & 1) + ((m >> 2) & 1) + ((m >> 3) & 1)
  }
  const STEP = { [E]: 1, [S]: cw, [W]: -1, [N]: -cw }
  const BACK = { [E]: W, [S]: N, [W]: E, [N]: S }
  const DIRS = [E, S, W, N]

  // Walk from a corner along one edge until the line ends or forks, taking each
  // edge off the lattice as it is used. `stop` is what ends a walk: a corner
  // that was a junction or a loose end before anything was taken away.
  const walk = (start, dir, stop) => {
    const line = [start % cw, (start / cw) | 0]
    let c = start
    let d = dir
    for (;;) {
      edges[c] &= ~d
      c += STEP[d]
      edges[c] &= ~BACK[d]
      line.push(c % cw, (c / cw) | 0)
      if (stop[c] || !edges[c]) return line
      d = DIRS.find(k => edges[c] & k)
    }
  }

  const stop = new Uint8Array(edges.length)
  for (let c = 0; c < edges.length; c++) if (edges[c] && degree(c) !== 2) stop[c] = 1
  const lines = []
  for (let c = 0; c < edges.length; c++) {
    if (!stop[c]) continue
    for (const d of DIRS) if (edges[c] & d) lines.push(walk(c, d, stop))
  }
  // What is left has no junction and no end: closed rings, an enclave or an
  // island of unclaimed ground inside one nation
  for (let c = 0; c < edges.length; c++) {
    if (edges[c]) lines.push(walk(c, DIRS.find(k => edges[c] & k), stop))
  }

  let before = 0
  let after = 0
  const out = lines.map(l => {
    before += l.length / 2
    const s = simplify(l, TOLERANCE)
    after += s.length / 2
    return s
  })

  writeFileSync(join(root, 'src', 'data', 'borderlines.json'), JSON.stringify(out) + '\n')
  return { lines: out.length, units, before, after }
}

// Douglas-Peucker on a flat [x0, y0, x1, y1, ...] line; the ends always stay,
// so lines that met at a junction still meet there
function simplify(l, tol) {
  const n = l.length / 2
  if (n <= 2) return l
  const keep = new Uint8Array(n)
  keep[0] = keep[n - 1] = 1
  const stack = [[0, n - 1]]
  while (stack.length) {
    const [a, b] = stack.pop()
    const ax = l[a * 2]
    const ay = l[a * 2 + 1]
    const dx = l[b * 2] - ax
    const dy = l[b * 2 + 1] - ay
    const len = Math.hypot(dx, dy)
    let worst = 0
    let at = -1
    for (let i = a + 1; i < b; i++) {
      const px = l[i * 2] - ax
      const py = l[i * 2 + 1] - ay
      // a ring's two ends are the same point, so there is no chord to measure from
      const d = len ? Math.abs(px * dy - py * dx) / len : Math.hypot(px, py)
      if (d > worst) {
        worst = d
        at = i
      }
    }
    if (worst > tol) {
      keep[at] = 1
      stack.push([a, at], [at, b])
    }
  }
  const out = []
  for (let i = 0; i < n; i++) if (keep[i]) out.push(l[i * 2], l[i * 2 + 1])
  return out
}

if (process.argv[1] && resolve(process.argv[1]) === import.meta.filename) {
  const r = await writeBorderLines()
  console.log(r ? `border lines: ${r.lines} lines, ${r.before} points down to ${r.after}` : 'no borders.png or mono.png in layers/')
}
