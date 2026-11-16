import type { SpecTaskView } from '../model'

export interface RailEdge {
  from: string
  to: string
  lane: number
}

/** Lays the tasks out like a git graph: a task continues its first prerequisite's lane when it can,
 *  so a chain is one straight line; a fork leaves on a curve into a free lane, a join curves back
 *  in. No two edges share a vertical run, and a run never passes behind another task's knot. */
export function railLayout(tasks: SpecTaskView[]) {
  const row = new Map(tasks.map((t, i) => [t.key, i]))
  const laneOf = new Map<string, number>()
  // Each lane's busy stretches: open row intervals for runs, and the knot rows.
  const runs: Array<Array<[number, number]>> = []
  const knots: Array<Set<number>> = []
  const continued = new Set<string>()
  const ensure = (l: number) => {
    while (runs.length <= l) { runs.push([]); knots.push(new Set()) }
  }
  const free = (l: number, a: number, b: number, knotAt?: number) => {
    ensure(l)
    if (knotAt !== undefined && runs[l]!.some(([x, y]) => x < knotAt && knotAt < y)) return false
    if (b - a > 0 && runs[l]!.some(([x, y]) => x < b && a < y)) return false
    for (const k of knots[l]!) if (a < k && k < b) return false
    return true
  }
  const edges: RailEdge[] = []

  tasks.forEach((t, i) => {
    const prereqs = t.dependsOn.filter((d) => row.has(d) && row.get(d)! < i).sort((a, b) => row.get(a)! - row.get(b)!)
    let lane: number | undefined
    let via: string | undefined
    // Continue a prerequisite's lane: the latest one first, so a chain stays straight.
    for (const p of [...prereqs].reverse()) {
      const l = laneOf.get(p)!
      if (!continued.has(p) && free(l, row.get(p)!, i, i)) { lane = l; via = p; break }
    }
    if (lane === undefined) {
      const top = prereqs.length ? row.get(prereqs[0]!)! : i
      for (let l = 0; lane === undefined; l++) if (free(l, top, i, i)) lane = l
    }
    ensure(lane)
    laneOf.set(t.key, lane)
    knots[lane]!.add(i)
    if (via) {
      continued.add(via)
      runs[lane]!.push([row.get(via)!, i])
      edges.push({ from: via, to: t.key, lane })
    }
    for (const p of prereqs) {
      if (p === via) continue
      const a = row.get(p)!
      const pl = laneOf.get(p)!
      // Fork into this task's lane, else join along the prerequisite's own lane, else a fresh one.
      let l = free(lane, a, i) ? lane : free(pl, a, i) && !continued.has(p) ? pl : undefined
      for (let n = 0; l === undefined; n++) if (free(n, a, i)) l = n
      ensure(l)
      runs[l]!.push([a, i])
      edges.push({ from: p, to: t.key, lane: l })
    }
  })
  return { laneOf, edges, lanes: Math.max(1, runs.length) }
}
