import * as React from 'react'
import type { SpecTaskView } from '../model'
import { TASK_STATUS_LABEL, type TaskStatus } from '../model'
import { THREAD_STATES, ThreadLegend, ThreadTaskCard, threadState, useChain, type GraphNode } from './shared'

const NODE_H = 56
const MIN_NODE_W = 150
const ROW_GAP = 14

/** One node of the map. `outside` names the document a prerequisite belongs to when it is drawn
 *  only so a thread has somewhere to start; it is shown faint and cannot be opened from here. */
export interface FlowNode extends GraphNode {
  title: string
  status?: TaskStatus | string | null
  agent?: string | null
  ref?: string | null
  outside?: string | null
  /** A word on the node beside the status: waiting on the operator, working now. */
  flag?: string | null
}

const STATUS_LABEL: Record<string, string> = { ...TASK_STATUS_LABEL, blocked: 'Waiting on you' }

/** Columns by depth, left to right; within a column, tasks sit near the average height of what they
 *  wait on, so threads run mostly level. */
export function flowLayout(nodes: GraphNode[], late: Set<string> = new Set()) {
  const byKey = new Map(nodes.map((n) => [n.key, n]))
  const depth = new Map<string, number>()
  const visit = (key: string, seen: Set<string>): number => {
    const known = depth.get(key)
    if (known !== undefined) return known
    if (seen.has(key)) return 0
    seen.add(key)
    const d = Math.max(-1, ...(byKey.get(key)?.dependsOn ?? []).filter((k) => byKey.has(k)).map((k) => visit(k, seen))) + 1
    depth.set(key, d)
    return d
  }
  nodes.forEach((n) => visit(n.key, new Set()))
  // A node drawn only as a thread's start sits just left of the first task that needs it, so its
  // thread is short instead of crossing the map from the far edge.
  for (const key of late) {
    const needs = nodes.filter((n) => n.dependsOn.includes(key)).map((n) => depth.get(n.key) ?? 1)
    if (needs.length) depth.set(key, Math.max(0, Math.min(...needs) - 1))
  }
  const last = Math.max(0, ...depth.values())
  const pos = new Map<string, { col: number; slot: number }>()
  const cols: GraphNode[][] = Array.from({ length: last + 1 }, () => [])
  nodes.forEach((n) => cols[depth.get(n.key) ?? 0]!.push(n))
  cols.forEach((col, c) => {
    const centre = (n: GraphNode) => {
      const ps = n.dependsOn.map((d) => pos.get(d)?.slot).filter((s): s is number => s !== undefined)
      return ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : Number.POSITIVE_INFINITY
    }
    const sorted = c === 0 ? col : [...col].sort((a, b) => centre(a) - centre(b))
    let next = 0
    sorted.forEach((n) => {
      const want = Number.isFinite(centre(n)) ? Math.round(centre(n)) : next
      const slot = Math.max(next, want)
      pos.set(n.key, { col: c, slot })
      next = slot + 1
    })
  })
  const rows = Math.max(1, ...[...pos.values()].map((p) => p.slot + 1))
  return { pos, cols: last + 1, rows }
}

/** The graph itself: nodes in columns by depth, threads coloured by their prerequisite's state. */
export function FlowGraph({
  nodes,
  selected,
  onSelect,
  nodeWidth: widest = 184,
  columnGap = 44,
  legend = true,
}: {
  nodes: FlowNode[]
  selected?: string | null
  onSelect: (key: string) => void
  nodeWidth?: number
  columnGap?: number
  legend?: boolean
}) {
  const late = React.useMemo(() => new Set(nodes.filter((n) => n.outside).map((n) => n.key)), [nodes])
  const { pos, cols, rows } = React.useMemo(() => flowLayout(nodes, late), [nodes, late])
  const { lit, edgeLit, bind } = useChain(nodes)
  // Nodes narrow to fit the space, down to a floor below which titles stop reading; past it, scroll.
  const scroller = React.useRef<HTMLDivElement>(null)
  const [room, setRoom] = React.useState<number | null>(null)
  React.useLayoutEffect(() => {
    const el = scroller.current
    if (!el) return
    const measure = () => setRoom(el.clientWidth - 4)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  const fit = room === null ? widest : Math.floor((room - (cols - 1) * columnGap) / cols)
  const nodeWidth = Math.max(MIN_NODE_W, Math.min(widest, fit))
  const width = cols * nodeWidth + (cols - 1) * columnGap
  const height = rows * NODE_H + (rows - 1) * ROW_GAP
  const at = (key: string) => {
    const p = pos.get(key)!
    return { x: p.col * (nodeWidth + columnGap), y: p.slot * (NODE_H + ROW_GAP) }
  }
  const edges = nodes.flatMap((n) => n.dependsOn.filter((d) => pos.has(d)).map((d) => ({ from: d, to: n.key })))
  const stateOf = (key: string) => threadState(nodes.find((n) => n.key === key)?.status)
  const states = THREAD_STATES.filter((s) => edges.some((e) => stateOf(e.from) === s))
  // Several threads arriving at one node spread down its left edge rather than meeting at a point.
  const port = (e: { from: string; to: string }, end: 'from' | 'to') => {
    const other = end === 'to' ? 'from' : 'to'
    const peers = edges.filter((x) => x[end] === e[end]).sort((a, b) => at(a[other]).y - at(b[other]).y)
    return NODE_H / 2 + (peers.indexOf(e) - (peers.length - 1) / 2) * 8
  }

  return (
    <div className="aw-st">
      {legend ? <ThreadLegend states={states} /> : null}
      <div ref={scroller} className="aw-st-map-scroll">
        <div className="aw-st-map" style={{ width, height }}>
          <svg className="aw-st-map-svg" width={width} height={height} aria-hidden="true">
            {edges.map((e) => {
              const a = at(e.from)
              const b = at(e.to)
              const x1 = a.x + nodeWidth
              const y1 = a.y + port(e, 'from')
              const x2 = b.x
              const y2 = b.y + port(e, 'to')
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
          {nodes.map((n) => {
            const p = at(n.key)
            const status = n.status ?? 'pending'
            return (
              <button
                key={n.key}
                type="button"
                data-slot="flow-node"
                className="aw-st-node"
                data-state={threadState(n.status)}
                data-outside={n.outside ? 'true' : undefined}
                data-picked={selected === n.key ? 'true' : undefined}
                data-lit={lit(n.key)}
                disabled={Boolean(n.outside)}
                title={n.outside ? `${n.title}, in ${n.outside}` : n.title}
                style={{ left: p.x, top: p.y, width: nodeWidth, height: NODE_H }}
                onClick={() => onSelect(n.key)}
                {...bind(n.key)}
              >
                <span className="aw-st-node-title">
                  {n.ref ? <span className="aw-st-node-ref">{n.ref}</span> : null}
                  {n.title}
                </span>
                <span className="aw-st-node-meta">
                  <span className="aw-sp-status" data-status={status}>
                    {STATUS_LABEL[status] ?? status}
                  </span>
                  {n.outside ? (
                    <span className="aw-sp-muted">in {n.outside}</span>
                  ) : n.flag ? (
                    <span className="aw-st-node-flag">{n.flag}</span>
                  ) : (
                    <span className="aw-sp-muted">{n.agent ?? 'Not handed out'}</span>
                  )}
                </span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/** The spec page's build order as a small map: what can run together reads down a column, what
 *  waits on what reads across. Selecting a node shows that task beneath the map. */
export function FlowMap({ tasks }: { tasks: SpecTaskView[] }) {
  const [picked, setPicked] = React.useState<string | null>(null)
  const shown = tasks.find((t) => t.key === picked)
  return (
    <>
      <FlowGraph nodes={tasks} selected={picked} onSelect={(k) => setPicked((p) => (p === k ? null : k))} />
      {shown ? (
        <div className="aw-sp-task aw-st-card aw-st-picked">
          <ThreadTaskCard task={shown} all={tasks} afterChips />
          <p className="aw-sp-task-desc">{shown.description}</p>
        </div>
      ) : (
        <p className="aw-st-hint">Select a task to read it here.</p>
      )}
    </>
  )
}
