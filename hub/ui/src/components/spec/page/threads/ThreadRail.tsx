import * as React from 'react'
import type { SpecTaskView } from '../model'
import { THREAD_STATES, ThreadLegend, ThreadTaskCard, threadState, useChain } from './shared'

const LANE = 14
const PAD = 10
const BEND = 14

interface RailEdge {
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

/** The spec page's build order, drawn as a rail. */
export function ThreadRail({ tasks }: { tasks: SpecTaskView[] }) {
  const list = React.useRef<HTMLOListElement>(null)
  const [ys, setYs] = React.useState<Record<string, number>>({})
  const { lit, edgeLit, bind } = useChain(tasks)
  const { laneOf, edges, lanes } = React.useMemo(() => railLayout(tasks), [tasks])

  React.useLayoutEffect(() => {
    const el = list.current
    if (!el) return
    const measure = () => {
      const next: Record<string, number> = {}
      el.querySelectorAll<HTMLElement>('[data-task]').forEach((r) => {
        next[r.dataset.task!] = r.offsetTop + 20
      })
      setYs(next)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [tasks])

  const x = (lane: number) => PAD + lane * LANE
  const gutter = PAD * 2 + (lanes - 1) * LANE
  const stateOf = (key: string) => threadState(tasks.find((t) => t.key === key)?.status)
  const states = THREAD_STATES.filter((s) => edges.some((e) => stateOf(e.from) === s))

  const path = (e: RailEdge) => {
    const xs = x(laneOf.get(e.from)!)
    const xt = x(laneOf.get(e.to)!)
    const xr = x(e.lane)
    const y1 = ys[e.from]!
    const y2 = ys[e.to]!
    let d = `M${xs} ${y1}`
    if (xr !== xs) d += ` C${xs} ${y1 + BEND * 0.6} ${xr} ${y1 + BEND * 0.4} ${xr} ${y1 + BEND}`
    d += ` V${xr !== xt ? y2 - BEND : y2}`
    if (xr !== xt) d += ` C${xr} ${y2 - BEND * 0.4} ${xt} ${y2 - BEND * 0.6} ${xt} ${y2}`
    return d
  }

  return (
    <div className="aw-st">
      <ThreadLegend states={states} />
      <ol ref={list} className="aw-st-rail" style={{ '--gutter': `${gutter}px` } as React.CSSProperties}>
        <svg className="aw-st-rail-svg" width={gutter} height="100%" aria-hidden="true">
          {edges.map((e) =>
            ys[e.from] !== undefined && ys[e.to] !== undefined ? (
              <path key={`${e.from}->${e.to}`} d={path(e)} className="aw-st-thread" data-state={stateOf(e.from)} data-lit={edgeLit(e.from, e.to)} />
            ) : null,
          )}
          {tasks.map((t) =>
            ys[t.key] !== undefined ? (
              <circle key={t.key} cx={x(laneOf.get(t.key)!)} cy={ys[t.key]} r={5} className="aw-st-knot" data-status={t.status ?? 'pending'} data-lit={lit(t.key)} />
            ) : null,
          )}
        </svg>
        {tasks.map((t) => (
          <li key={t.key} className="aw-sp-task aw-st-card" data-task={t.key} data-lit={lit(t.key)} tabIndex={0} {...bind(t.key)}>
            <ThreadTaskCard task={t} all={tasks} />
          </li>
        ))}
      </ol>
    </div>
  )
}
