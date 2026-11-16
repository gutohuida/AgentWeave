import * as React from 'react'
import type { SpecTaskView } from '../model'
import { buildLevels } from '../model'
import { StatusChip } from '../SpecDocumentBody'
import { THREAD_STATES, ThreadLegend, ThreadTaskCard, threadState, useChain } from './shared'

const NODE_W = 184
const NODE_H = 56
const COL_GAP = 44
const ROW_GAP = 14

/** Columns by depth, left to right; within a column, tasks sit near the average height of what they
 *  wait on, so threads run mostly level. */
export function flowLayout(tasks: SpecTaskView[]) {
  const levels = buildLevels(tasks)
  const depth = Math.max(0, ...tasks.map((t) => levels.get(t.key) ?? 0))
  const pos = new Map<string, { col: number; slot: number }>()
  const cols: SpecTaskView[][] = Array.from({ length: depth + 1 }, () => [])
  tasks.forEach((t) => cols[levels.get(t.key) ?? 0]!.push(t))
  cols.forEach((col, c) => {
    const centre = (t: SpecTaskView) => {
      const ps = t.dependsOn.map((d) => pos.get(d)?.slot).filter((s): s is number => s !== undefined)
      return ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : Number.POSITIVE_INFINITY
    }
    const sorted = c === 0 ? col : [...col].sort((a, b) => centre(a) - centre(b))
    let next = 0
    sorted.forEach((t) => {
      const want = Number.isFinite(centre(t)) ? Math.round(centre(t)) : next
      const slot = Math.max(next, want)
      pos.set(t.key, { col: c, slot })
      next = slot + 1
    })
  })
  const rows = Math.max(1, ...[...pos.values()].map((p) => p.slot + 1))
  return { pos, cols: depth + 1, rows }
}

/** The build order as a small map above the list: what can run together reads across, what waits
 *  on what reads left to right. Selecting a node shows that task beneath the map. */
export function FlowMap({ tasks }: { tasks: SpecTaskView[] }) {
  const { pos, cols, rows } = React.useMemo(() => flowLayout(tasks), [tasks])
  const { lit, edgeLit, bind } = useChain(tasks)
  const [picked, setPicked] = React.useState<string | null>(null)
  const width = cols * NODE_W + (cols - 1) * COL_GAP
  const height = rows * NODE_H + (rows - 1) * ROW_GAP
  const at = (key: string) => {
    const p = pos.get(key)!
    return { x: p.col * (NODE_W + COL_GAP), y: p.slot * (NODE_H + ROW_GAP) }
  }
  const edges = tasks.flatMap((t) => t.dependsOn.filter((d) => pos.has(d)).map((d) => ({ from: d, to: t.key })))
  const stateOf = (key: string) => threadState(tasks.find((t) => t.key === key)?.status)
  const states = THREAD_STATES.filter((s) => edges.some((e) => stateOf(e.from) === s))
  // Several threads arriving at one node spread down its left edge rather than meeting at a point.
  const inPort = (e: { from: string; to: string }) => {
    const ins = edges.filter((x) => x.to === e.to).sort((a, b) => at(a.from).y - at(b.from).y)
    const i = ins.indexOf(e)
    return NODE_H / 2 + (i - (ins.length - 1) / 2) * 8
  }
  const outPort = (e: { from: string; to: string }) => {
    const outs = edges.filter((x) => x.from === e.from).sort((a, b) => at(a.to).y - at(b.to).y)
    const i = outs.indexOf(e)
    return NODE_H / 2 + (i - (outs.length - 1) / 2) * 8
  }
  const shown = tasks.find((t) => t.key === picked)

  return (
    <div className="aw-st">
      <ThreadLegend states={states} />
      <div className="aw-st-map-scroll">
        <div className="aw-st-map" style={{ width, height }}>
          <svg className="aw-st-map-svg" width={width} height={height} aria-hidden="true">
            {edges.map((e) => {
              const a = at(e.from)
              const b = at(e.to)
              const x1 = a.x + NODE_W
              const y1 = a.y + outPort(e)
              const x2 = b.x
              const y2 = b.y + inPort(e)
              const mid = (x2 - x1) / 2
              return (
                <path
                  key={`${e.from}->${e.to}`}
                  d={`M${x1} ${y1} C${x1 + mid} ${y1} ${x2 - mid} ${y2} ${x2} ${y2}`}
                  className="aw-st-thread"
                  data-state={stateOf(e.from)}
                  data-lit={edgeLit(e.from, e.to)}
                />
              )
            })}
          </svg>
          {tasks.map((t) => {
            const p = at(t.key)
            return (
              <button
                key={t.key}
                type="button"
                data-slot="flow-node"
                className="aw-st-node"
                data-state={threadState(t.status)}
                data-picked={picked === t.key ? 'true' : undefined}
                data-lit={lit(t.key)}
                style={{ left: p.x, top: p.y, width: NODE_W, height: NODE_H }}
                onClick={() => setPicked((k) => (k === t.key ? null : t.key))}
                {...bind(t.key)}
              >
                <span className="aw-st-node-title">{t.title}</span>
                <span className="aw-st-node-meta">
                  <StatusChip status={t.status} />
                  <span className="aw-sp-muted">{t.agent ?? 'Not handed out'}</span>
                </span>
              </button>
            )
          })}
        </div>
      </div>
      {shown ? (
        <div className="aw-sp-task aw-st-card aw-st-picked">
          <ThreadTaskCard task={shown} all={tasks} afterChips />
          <p className="aw-sp-task-desc">{shown.description}</p>
        </div>
      ) : (
        <p className="aw-st-hint">Select a task to read it here.</p>
      )}
    </div>
  )
}
