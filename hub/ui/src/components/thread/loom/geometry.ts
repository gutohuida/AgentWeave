import type { ThreadKnot } from '@/api/thread'

/** Where a loom lays its thread. `along` runs with time, left to right; `across` is the thread's
 *  swing either side of the middle. */
export interface LoomBead {
  key: string
  index: number
  along: number
  across: number
  /** Which side of the middle the thread swings to at this knot: labels sit beyond it. */
  side: 1 | -1
  /** 0..1, how much the knot holds, on a log scale: heavier knots swing the thread further. */
  weight: number
}

export interface LoomGap {
  along: number
  across: number
  label: string
}

export interface LoomGeometry {
  length: number
  thickness: number
  beads: LoomBead[]
  /** The thread's centre line, a smooth wave that crests and troughs at the knots. */
  centre: string
  /** Long silences between two knots, named where the thread crosses the middle. */
  gaps: LoomGap[]
}

export interface LoomOptions {
  gap: number
  pad: number
  thickness: number
  swing: number
  swell: number
  /** Which side the first knot swings to (0 above, 1 below): a thread that gains an older page of
   *  odd length keeps every knot it already had on the side it was on. */
  phase?: number
}

const DAY = 86_400_000

function silence(ms: number): string | null {
  const days = Math.round(ms / DAY)
  if (days < 10) return null
  if (days < 45) return `${Math.round(days / 7)} weeks later`
  return `${Math.round(days / 30)} months later`
}

/** A small, stable jitter per knot so the wave is a hand's, not a sine table's. */
function jitter(key: string): number {
  let h = 2166136261
  for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 16777619)
  return ((h >>> 0) % 1000) / 1000 - 0.5
}

/** The cosine ease that a cubic with handles at 0.3642 of the span approximates closely. */
const HANDLE = 0.3642

export function weave(knots: readonly ThreadKnot[], o: LoomOptions): LoomGeometry {
  const mid = o.thickness / 2
  const length = o.pad * 2 + Math.max(0, knots.length - 1) * o.gap
  const beads: LoomBead[] = knots.map((knot, index) => {
    const weight = Math.min(1, Math.log10(1 + knot.descendant_count) / 2.6)
    const side: 1 | -1 = (index + (o.phase ?? 0)) % 2 === 0 ? -1 : 1
    const reach = o.swing + o.swell * weight + 6 * jitter(knot.key)
    return { key: knot.key, index, along: o.pad + index * o.gap, across: mid + side * reach, side, weight }
  })

  // The thread enters at the middle, swings through every knot, and leaves at the middle.
  const nodes: Array<[number, number]> = [[0, mid], ...beads.map((b) => [b.along, b.across] as [number, number]), [length, mid]]
  const pt = (a: number, c: number) => `${a.toFixed(1)} ${c.toFixed(1)}`
  let centre = `M ${pt(nodes[0]![0], nodes[0]![1])}`
  for (let i = 0; i < nodes.length - 1; i++) {
    const [a0, c0] = nodes[i]!
    const [a1, c1] = nodes[i + 1]!
    const h = (a1 - a0) * HANDLE
    centre += ` C ${pt(a0 + h, c0)} ${pt(a1 - h, c1)} ${pt(a1, c1)}`
  }

  const gaps: LoomGap[] = []
  for (let i = 0; i < knots.length - 1; i++) {
    const label = silence(Date.parse(knots[i + 1]!.start) - Date.parse(knots[i]!.end))
    if (label) gaps.push({ along: (beads[i]!.along + beads[i + 1]!.along) / 2, across: mid, label })
  }

  return { length, thickness: o.thickness, beads, centre, gaps }
}
