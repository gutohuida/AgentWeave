import * as React from 'react'
import type { SpecTaskView } from '../model'
import { THREAD_STATES, threadState, useChain } from './threadModel'
import { ThreadLegend, ThreadTaskCard } from './shared'
import { railLayout, type RailEdge } from './railLayout'

const LANE = 14
const PAD = 10
const BEND = 14

/** The spec page's build order, drawn as a rail. */
export function ThreadRail({
  tasks,
  renderCard,
  itemProps,
}: {
  tasks: SpecTaskView[]
  /** The card's content; defaults to the plain mock card. */
  renderCard?: (task: SpecTaskView, index: number) => React.ReactNode
  /** Extra attributes for a task's list item (anchor id, flash, finding). */
  itemProps?: (task: SpecTaskView, index: number) => React.LiHTMLAttributes<HTMLLIElement> & Record<string, unknown>
}) {
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
        {tasks.map((t, i) => {
          const extra = itemProps?.(t, i) ?? {}
          return (
            <li
              key={t.key}
              {...extra}
              className={`aw-sp-task aw-st-card ${extra.className ?? ''}`.trim()}
              data-task={t.key}
              data-lit={lit(t.key)}
              tabIndex={0}
              {...bind(t.key)}
            >
              {renderCard ? renderCard(t, i) : <ThreadTaskCard task={t} all={tasks} />}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
