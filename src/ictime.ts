// In-character time. IC time runs faster than real time at a rate set per
// epoch, and an epoch can also jump the calendar (a timeskip). IC times here are
// milliseconds on the IC calendar at UTC, the meridian through the two poles.
//
// This table is the canonical one: the Time Counter that used to keep it now
// lives in the map's Time tab. Add a row here for a timeskip or a rate change.

interface Epoch {
  ooc: string // real date the epoch starts
  ic: string // IC date it starts at
  daysPerYear: number // real days per IC year
}

const EPOCHS: Epoch[] = [
  { ooc: '2026-06-28T00:00:00Z', ic: '1931-06-01T00:00:00Z', daysPerYear: 52 }, // Initial
  { ooc: '2026-07-05T00:00:00Z', ic: '1931-12-24T00:00:00Z', daysPerYear: 26 }, // WC
  { ooc: '2026-07-20T00:00:00Z', ic: '1933-01-01T00:00:00Z', daysPerYear: 26 }, // NY
  { ooc: '2026-07-27T00:00:00Z', ic: '1933-04-08T00:00:00Z', daysPerYear: 52 }, // Slowdown
  { ooc: '2026-08-08T00:00:00Z', ic: '1934-01-01T00:00:00Z', daysPerYear: 52 }, // NY 1934
]

const DAY_MS = 86_400_000
const YEAR_MS = 365.2425 * DAY_MS

const multOf = (e: Epoch) => YEAR_MS / (e.daysPerYear * DAY_MS)

function epochAt(realMs: number): Epoch {
  let e = EPOCHS[0]
  for (const ep of EPOCHS) if (realMs >= Date.parse(ep.ooc)) e = ep
  return e
}

export function icAt(realMs: number): number {
  const e = epochAt(realMs)
  return Date.parse(e.ic) + (realMs - Date.parse(e.ooc)) * multOf(e)
}

export function icNow(): number {
  return icAt(Date.now())
}

// How fast IC time runs right now: IC seconds per real second, and real days
// to one IC year
export function rateNow(): { mult: number; daysPerYear: number } {
  const e = epochAt(Date.now())
  return { mult: multOf(e), daysPerYear: e.daysPerYear }
}

export const IC_START = Date.parse(EPOCHS[0].ic)

// The real moment an IC time fell on. 'before' for anything earlier than
// recorded time, 'skipped' for a stretch a timeskip jumped over.
export function realAt(icMs: number): number | 'before' | 'skipped' {
  if (icMs < IC_START) return 'before'
  for (let i = 0; i < EPOCHS.length; i++) {
    const e = EPOCHS[i]
    const start = Date.parse(e.ic)
    const next = EPOCHS[i + 1]
    if (next) {
      // where this epoch's clock had got to when the next one took over;
      // anything after that but before the next epoch's start was skipped
      const end = start + (Date.parse(next.ooc) - Date.parse(e.ooc)) * multOf(e)
      if (icMs <= end) return Date.parse(e.ooc) + (icMs - start) / multOf(e)
      if (icMs < Date.parse(next.ic)) return 'skipped'
    } else {
      return Date.parse(e.ooc) + (icMs - start) / multOf(e)
    }
  }
  return 'skipped'
}
