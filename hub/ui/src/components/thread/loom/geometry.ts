import type { ThreadKnot } from '@/api/thread'

/** Where a loom lays its thread. `along` runs with time (x when horizontal, y when vertical);
 *  `across` is the thread's swing either side of the middle. */
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
  /** For a twisted thread: each strand split into the stretches behind and in front of the others. */
  strands: Array<{ under: string; over: string; madder: boolean }>
  /** Long silences between two knots, named where the thread crosses the middle. */
  gaps: LoomGap[]
}

export interface LoomOptions {
  gap: number
  pad: number
  thickness: number
  swing: number
  swell: number
  twisted: boolean
  vertical: boolean
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
    const side: 1 | -1 = index % 2 === 0 ? -1 : 1
    const reach = o.swing + o.swell * weight + 6 * jitter(knot.key)
    return { key: knot.key, index, along: o.pad + index * o.gap, across: mid + side * reach, side, weight }
  })

  // The thread enters at the middle, swings through every knot, and leaves at the middle.
  const nodes: Array<[number, number]> = [[0, mid], ...beads.map((b) => [b.along, b.across] as [number, number]), [length, mid]]
  const pt = (a: number, c: number) => (o.vertical ? `${c.toFixed(1)} ${a.toFixed(1)}` : `${a.toFixed(1)} ${c.toFixed(1)}`)
  let centre = `M ${pt(nodes[0]![0], nodes[0]![1])}`
  for (let i = 0; i < nodes.length - 1; i++) {
    const [a0, c0] = nodes[i]!
    const [a1, c1] = nodes[i + 1]!
    const h = (a1 - a0) * HANDLE
    centre += ` C ${pt(a0 + h, c0)} ${pt(a1 - h, c1)} ${pt(a1, c1)}`
  }

  // The same curve as a function, for the strands that twist around it.
  const at = (a: number): [number, number] => {
    let i = 0
    while (i < nodes.length - 2 && a > nodes[i + 1]![0]) i++
    const [a0, c0] = nodes[i]!
    const [a1, c1] = nodes[i + 1]!
    const t = a1 === a0 ? 0 : Math.min(1, Math.max(0, (a - a0) / (a1 - a0)))
    const ease = (1 - Math.cos(Math.PI * t)) / 2
    const slope = ((c1 - c0) * Math.PI * Math.sin(Math.PI * t)) / 2 / (a1 - a0 || 1)
    return [c0 + (c1 - c0) * ease, slope]
  }

  const strands: LoomGeometry['strands'] = []
  if (o.twisted) {
    const lay = 26 // one full twist every 26px, as a rope is laid
    const width = 3.4
    for (let k = 0; k < 3; k++) {
      const phase = (k * 2 * Math.PI) / 3
      let under = ''
      let over = ''
      let wasOver: boolean | null = null
      for (let a = 0; a <= length; a += 2) {
        const [c, slope] = at(a)
        const turn = (2 * Math.PI * a) / lay + phase
        const off = width * Math.sin(turn)
        const norm = Math.hypot(1, slope)
        const pa = a - (off * slope) / norm
        const pc = c + off / norm
        const isOver = Math.cos(turn) > 0
        const cmd = wasOver === isOver ? 'L' : 'M'
        if (isOver) over += `${cmd} ${pt(pa, pc)} `
        else under += `${cmd} ${pt(pa, pc)} `
        // A strand changing sides starts its new stretch where the old one ended, with no gap.
        if (wasOver !== null && wasOver !== isOver) {
          if (isOver) under += `L ${pt(pa, pc)} `
          else over += `L ${pt(pa, pc)} `
        }
        wasOver = isOver
      }
      strands.push({ under, over, madder: k === 0 })
    }
  }

  const gaps: LoomGap[] = []
  for (let i = 0; i < knots.length - 1; i++) {
    const label = silence(Date.parse(knots[i + 1]!.start) - Date.parse(knots[i]!.end))
    if (label) gaps.push({ along: (beads[i]!.along + beads[i + 1]!.along) / 2, across: mid, label })
  }

  return { length, thickness: o.thickness, beads, centre, strands, gaps }
}
