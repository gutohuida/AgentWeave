import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { Task, TaskBoardEdge, useTaskBoard, useTaskBoards } from '@/api/tasks'
import { useAgents } from '@/api/agents'
import { EmptyState } from '@/components/common/EmptyState'
import { Icon } from '@/components/common/Icon'
import {
  assignDepths,
  dependencyStallState,
  groupByDepth,
  isTerminalTask,
  offBoardPrerequisites,
} from '@/lib/dependencyBoardLayout'
import { TaskCard } from './TaskCard'
import { TaskDetailDrawer } from './TaskDetailDrawer'

/** Task 8.8's per-layer sentence — design D8's mitigation for its main risk: three states that
 *  look alike as "a card that will not start" get named separately, at the layer, not only per
 *  card ("Layer N is waiting on M reviews" is the design's own example). */
function layerStallSummary(tasks: Task[]): string | null {
  let gated = 0
  let waitingOnReview = 0
  let gatedOnRejected = 0
  for (const task of tasks) {
    const state = dependencyStallState(task)
    if (state === 'gated') gated++
    else if (state === 'waiting_on_review') waitingOnReview++
    else if (state === 'gated_on_rejected') gatedOnRejected++
  }
  const parts: string[] = []
  if (waitingOnReview > 0) {
    parts.push(`waiting on ${waitingOnReview} review${waitingOnReview === 1 ? '' : 's'}`)
  }
  if (gated > 0) parts.push(`${gated} gated on an unmet prerequisite`)
  if (gatedOnRejected > 0) {
    parts.push(`${gatedOnRejected} gated on a rejected prerequisite`)
  }
  return parts.length > 0 ? parts.join(', ') : null
}

interface EdgeLine {
  id: string
  fromTaskId: string
  toTaskId: string
  /** A `ghost` line has one end inside a folded layer — see the stub logic in `useEdgeLines`. It
   *  carries no semantic colour because its endpoint's state is exactly what is not on screen. */
  kind: 'edge' | 'ghost'
  x1: number
  y1: number
  x2: number
  y2: number
}

/**
 * Measures where each edge's two cards actually sit, after layout, and turns that into line
 * coordinates relative to the scrolling container. Recomputed on mount, on window resize, and
 * whenever a card's own size changes (a `ResizeObserver` per card, since a layer reflowing can
 * move every card below it without the container itself resizing).
 *
 * Task 8.12 defers crossing minimisation as unbounded polish; this draws the direct line between
 * each pair; "good enough" for now is that no edge is silently omitted, not that they never cross.
 *
 * A folded layer (task 8.6) unmounts its cards, so its edges have no endpoint left to measure and
 * used to disappear without trace — the operator's actual complaint about collapse: the graph stops
 * making sense rather than merely getting shorter. Those edges are drawn as ghost stubs instead,
 * running between the layer's own collapse toggle and whichever end is still on screen, so the
 * connection still lands somewhere the eye can follow back. An edge with *both* ends folded away
 * draws nothing: there is no visible end to anchor a stub to, and the count on the toggle already
 * says how many links the fold is holding.
 */
function useEdgeLines(
  containerRef: RefObject<HTMLDivElement | null>,
  cardRefs: Map<string, HTMLDivElement>,
  toggleRefs: Map<number, HTMLButtonElement>,
  edges: TaskBoardEdge[],
  foldedTaskDepth: Map<string, number>,
  layoutKey: string,
): EdgeLine[] {
  const [lines, setLines] = useState<EdgeLine[]>([])

  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) return

    const recompute = () => {
      const containerRect = container.getBoundingClientRect()
      // Content space, not viewport space: the svg scrolls with the cards, so both ends of every
      // line have to be measured from the top of the scrolled content.
      const topOf = (rect: DOMRect) => rect.top - containerRect.top + container.scrollTop
      const bottomOf = (rect: DOMRect) => rect.bottom - containerRect.top + container.scrollTop
      const centreOf = (rect: DOMRect) => rect.left + rect.width / 2 - containerRect.left + container.scrollLeft

      const next: EdgeLine[] = []
      for (const edge of edges) {
        const fromEl = cardRefs.get(edge.depends_on_task_id)
        const toEl = cardRefs.get(edge.task_id)
        const id = `${edge.depends_on_task_id}->${edge.task_id}`

        if (fromEl && toEl) {
          next.push({
            id,
            fromTaskId: edge.depends_on_task_id,
            toTaskId: edge.task_id,
            kind: 'edge',
            x1: centreOf(fromEl.getBoundingClientRect()),
            y1: bottomOf(fromEl.getBoundingClientRect()),
            x2: centreOf(toEl.getBoundingClientRect()),
            y2: topOf(toEl.getBoundingClientRect()),
          })
          continue
        }

        const fromFoldedAt = foldedTaskDepth.get(edge.depends_on_task_id)
        const toFoldedAt = foldedTaskDepth.get(edge.task_id)
        // A prerequisite folded away: stub down from its layer's toggle to the dependent still
        // on screen.
        if (fromFoldedAt !== undefined && toEl) {
          const toggle = toggleRefs.get(fromFoldedAt)
          if (!toggle) continue
          const toggleRect = toggle.getBoundingClientRect()
          const toRect = toEl.getBoundingClientRect()
          next.push({
            id: `${id}:ghost`,
            fromTaskId: edge.depends_on_task_id,
            toTaskId: edge.task_id,
            kind: 'ghost',
            x1: toggleRect.left + 14 - containerRect.left + container.scrollLeft,
            y1: bottomOf(toggleRect),
            x2: centreOf(toRect),
            y2: topOf(toRect),
          })
          continue
        }
        // The dependent folded away: stub down from the visible prerequisite to its layer's toggle.
        if (toFoldedAt !== undefined && fromEl) {
          const toggle = toggleRefs.get(toFoldedAt)
          if (!toggle) continue
          const toggleRect = toggle.getBoundingClientRect()
          const fromRect = fromEl.getBoundingClientRect()
          next.push({
            id: `${id}:ghost`,
            fromTaskId: edge.depends_on_task_id,
            toTaskId: edge.task_id,
            kind: 'ghost',
            x1: centreOf(fromRect),
            y1: bottomOf(fromRect),
            x2: toggleRect.left + 14 - containerRect.left + container.scrollLeft,
            y2: topOf(toggleRect),
          })
          continue
        }
        // Otherwise an off-board reference (task 8.7) — nothing on this board to draw to.
      }
      setLines(next)
    }

    recompute()

    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(recompute)
    observer.observe(container)
    for (const el of cardRefs.values()) observer.observe(el)
    window.addEventListener('resize', recompute)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', recompute)
    }
    // `layoutKey` stands in for "the set of cards actually mounted" — cardRefs is a mutable Map
    // and does not itself trigger a re-run.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerRef, edges, foldedTaskDepth, layoutKey])

  return lines
}

/** Which marker a line's arrowhead uses. There is one marker per edge class rather than one shared
 *  grey head, because an SVG marker cannot inherit the referencing path's `stroke`/`currentColor`
 *  through `marker-end` in every engine — so a single marker means a single colour, and the head is
 *  the highest-contrast part of a directed edge, exactly where the eye lands. A grey head on a red
 *  edge undoes the colour coding at the only point that is read at a glance. */
function markerIdFor(edgeClass: string, isLineage: boolean): string {
  if (isLineage) return 'dependency-arrow-lineage'
  return `dependency-arrow-${edgeClass.replace('dependency-edge-', '')}`
}

interface DependencyBoardProps {
  /** `null` names the standing "no document" board (design D9) — every hand-made task. */
  specDocumentId: string | null
  onOpenRequirement?: (documentPath: string, anchor: string) => void
  /** Select the owning document when an off-board prerequisite is followed. */
  onSelectBoard?: (specDocumentId: string) => void
}

export function DependencyBoard({ specDocumentId, onOpenRequirement, onSelectBoard }: DependencyBoardProps) {
  const { data: board, isLoading } = useTaskBoard(specDocumentId)
  const { data: agents = [] } = useAgents()
  // Task 8.7: an off-board reference names the document it lives in, not just its id — the
  // picker's own boards list already carries every document's title (task 7.4), so this is a
  // cache hit, not a second round trip.
  const { data: boardsData } = useTaskBoards()
  const documentTitleById = useMemo(() => {
    const map = new Map<string, string>()
    for (const summary of boardsData?.boards ?? []) {
      if (summary.spec_document_id) map.set(summary.spec_document_id, summary.title || 'Untitled')
    }
    return map
  }, [boardsData])
  const colorsByAgent = useMemo(
    () => new Map(agents.map((agent) => [agent.name, agent.color_index])),
    [agents],
  )
  const [openTaskId, setOpenTaskId] = useState<string | null>(null)
  const [hoveredTaskId, setHoveredTaskId] = useState<string | null>(null)
  // Task 8.6: a layer whose every task is terminal (approved/rejected) collapses to one row by
  // default, expandable — but a layer with even one unfinished task never collapses, since that is
  // the shape D9 rejects ("a partly finished layer" must stay legible). Keyed by depth rather than
  // by a Set of collapsed ids so a fresh layer (a document reindex adding depth) is never
  // accidentally pre-expanded by a stale override from a different layer at the same depth.
  const [expandedOverride, setExpandedOverride] = useState<Record<number, boolean>>({})

  const containerRef = useRef<HTMLDivElement | null>(null)
  const cardRefsRef = useRef<Map<string, HTMLDivElement>>(new Map())
  const toggleRefsRef = useRef<Map<number, HTMLButtonElement>>(new Map())

  const tasks = useMemo(() => board?.tasks ?? [], [board?.tasks])
  const edges = useMemo(() => board?.edges ?? [], [board?.edges])
  const taskById = useMemo(() => new Map(tasks.map((task) => [task.id, task])), [tasks])

  const layers = useMemo(() => {
    const depth = assignDepths(tasks, edges)
    return groupByDepth(tasks, depth)
    // `tasks` is a fresh array from React Query every fetch; keying on ids+edges avoids
    // recomputing layout on a refetch that changed nothing about the graph's shape.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks.map((t) => t.id).join(','), edges.map((e) => `${e.task_id}:${e.depends_on_task_id}`).join(',')])

  // Which layers are folded, hoisted out of the render loop because the edge measurement needs it
  // too — a folded layer's cards are unmounted, and the ghost stubs are how those edges stay
  // legible. Same rule as before (task 8.6): a fully terminal layer folds by default, a partly
  // finished one never folds, and an explicit override outranks both.
  const collapsedDepths = useMemo(() => {
    const folded = new Set<number>()
    for (const layer of layers) {
      const allTerminal = layer.tasks.length > 0 && layer.tasks.every(isTerminalTask)
      if (!(expandedOverride[layer.depth] ?? !allTerminal)) folded.add(layer.depth)
    }
    return folded
  }, [layers, expandedOverride])

  const foldedTaskDepth = useMemo(() => {
    const byTask = new Map<string, number>()
    for (const layer of layers) {
      if (!collapsedDepths.has(layer.depth)) continue
      for (const task of layer.tasks) byTask.set(task.id, layer.depth)
    }
    return byTask
  }, [layers, collapsedDepths])

  const layoutKey = `${layers.map((l) => `${l.depth}:${l.tasks.map((t) => t.id).join(',')}`).join('|')}|${[...collapsedDepths].join(',')}`
  const lines = useEdgeLines(containerRef, cardRefsRef.current, toggleRefsRef.current, edges, foldedTaskDepth, layoutKey)

  // The lineage hint (S4 finding 5) is only true of a card that actually has an edge — promising a
  // trace on an isolated node would be an affordance that does nothing.
  const connectedTaskIds = useMemo(() => {
    const connected = new Set<string>()
    for (const edge of edges) {
      connected.add(edge.task_id)
      connected.add(edge.depends_on_task_id)
    }
    return connected
  }, [edges])

  const lineageIds = useMemo(() => {
    if (!hoveredTaskId) return null
    const incoming = new Map<string, string[]>()
    const outgoing = new Map<string, string[]>()
    for (const edge of edges) {
      incoming.set(edge.task_id, [...(incoming.get(edge.task_id) ?? []), edge.depends_on_task_id])
      outgoing.set(edge.depends_on_task_id, [...(outgoing.get(edge.depends_on_task_id) ?? []), edge.task_id])
    }
    const related = new Set([hoveredTaskId])
    const visit = (start: string, graph: Map<string, string[]>) => {
      const queue = [start]
      while (queue.length) {
        const current = queue.shift()!
        for (const next of graph.get(current) ?? []) {
          if (related.has(next)) continue
          related.add(next)
          queue.push(next)
        }
      }
    }
    visit(hoveredTaskId, incoming)
    visit(hoveredTaskId, outgoing)
    return related
  }, [edges, hoveredTaskId])

  // Task 8.7: every off-board reference this board's own tasks name — no layer of their own
  // (they are not on this board to lay out), drawn once above everything else instead. Cheap
  // enough (one pass over already-fetched data) that memoising it is not worth a second dependency
  // list to keep in step with `tasks`.
  const offBoardRefs = offBoardPrerequisites(tasks)

  const openTask = tasks.find((t) => t.id === openTaskId) ?? null

  if (isLoading) {
    return (
      <div className="space-y-6 p-4" aria-label="Loading dependency tasks">
        {[0, 1, 2].map((layer) => (
          <div key={layer} className="space-y-2">
            <div className="skeleton h-3 w-36" />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="skeleton h-24" />
              <div className="skeleton h-24" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (tasks.length === 0) {
    return (
      <div className="p-6">
        <EmptyState
          icon="task_alt"
          title="No tasks on this board"
          description="Tasks a specification document declares, and the dependencies between them, appear here."
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div
        ref={containerRef}
        data-testid="dependency-board"
        className="relative flex-1 overflow-auto p-4"
      >
        <svg
          data-testid="dependency-board-edges"
          className="absolute inset-0"
          // `overflow: visible`, and it is load-bearing. `inset-0` + `height: 100%` inside an
          // `overflow-auto` scrollport resolves against the *padding box* — the visible height —
          // while every path coordinate above is in content space (`+ scrollTop`). The svg is
          // anchored at content y=0 and scrolls with the cards, so it draws correctly down to one
          // viewport height and an svg root clips to its viewport: every edge below the fold was
          // simply absent. Measured in Chromium on a 400px-tall scrollport over 1064px of content —
          // the last edge sat at y=940, the svg was 400 tall, nothing was drawn past the first
          // screen. `overflow: visible` un-clips it without changing the box, so it adds nothing to
          // `scrollHeight` (verified unchanged at 1064) and cannot feed back into the measurement.
          // The scrollport's own `overflow-auto` still bounds what paints.
          style={{ width: '100%', height: '100%', overflow: 'visible', pointerEvents: 'none' }}
        >
          <defs>
            {/* One marker per edge class — see `markerIdFor`. `context-stroke` would collapse
                these into one, but it is not supported everywhere this ships. */}
            {[
              ['normal', 'var(--border-hi)'],
              ['gated', 'color-mix(in srgb, var(--amber) 60%, var(--border-hi))'],
              ['rejected', 'color-mix(in srgb, var(--red) 65%, var(--border-hi))'],
              ['live', 'var(--green)'],
              ['lineage', 'var(--ring)'],
              ['ghost', 'var(--border)'],
            ].map(([name, fill]) => (
              <marker
                key={name}
                id={`dependency-arrow-${name}`}
                markerWidth="7"
                markerHeight="7"
                refX="6"
                refY="3.5"
                orient="auto"
              >
                <path d="M0,0 L7,3.5 L0,7 Z" fill={fill} />
              </marker>
            ))}
          </defs>
          {lines.map((line) => {
            const edgeClass =
              line.kind === 'ghost'
                ? 'dependency-edge-ghost'
                : taskById.get(line.fromTaskId)?.assignee_status === 'running'
                  ? 'dependency-edge-live'
                  : taskById.get(line.toTaskId)?.dependency_state === 'gated_on_rejected'
                    ? 'dependency-edge-rejected'
                    : taskById.get(line.toTaskId)?.dependency_state === 'gated'
                      ? 'dependency-edge-gated'
                      : 'dependency-edge-normal'
            // A ghost never joins a lineage trace: its far end is folded away, so claiming it is
            // part of the highlighted path would assert something the operator cannot see.
            const isLineage =
              line.kind === 'edge' &&
              Boolean(lineageIds?.has(line.fromTaskId) && lineageIds.has(line.toTaskId))
            return (
              <path
                key={line.id}
                data-testid={line.kind === 'ghost' ? 'dependency-board-ghost-edge' : 'dependency-board-edge'}
                d={`M ${line.x1} ${line.y1} V ${(line.y1 + line.y2) / 2} H ${line.x2} V ${line.y2}`}
                markerEnd={`url(#${markerIdFor(edgeClass, isLineage)})`}
                className={[
                  'dependency-edge',
                  edgeClass,
                  lineageIds && line.kind === 'edge' ? (isLineage ? 'lineage-active' : 'lineage-dim') : '',
                ].filter(Boolean).join(' ')}
              />
            )
          })}
        </svg>

        <div className="relative flex flex-col gap-6" style={{ zIndex: 1 }}>
          {/* Task 8.7: an imported entry resolved to a task outside this document — named, not
              hidden, since a dependent that never starts and never says why looks like a bug. No
              layer of its own: these are not laid out, only referenced. */}
          {offBoardRefs.length > 0 && (
            <div
              data-testid="dependency-board-offboard-refs"
              className="flex flex-wrap items-center gap-1.5"
            >
              {offBoardRefs.map((ref) => (
                <button
                  key={ref.id}
                  type="button"
                  data-testid={`dependency-board-offboard-ref-${ref.id}`}
                  title={`${ref.title} — ${ref.status}`}
                  disabled={!ref.spec_document_id || !onSelectBoard}
                  onClick={() => {
                    if (ref.spec_document_id) onSelectBoard?.(ref.spec_document_id)
                  }}
                  className="flex items-center gap-1 px-2 py-1 rounded text-xs"
                  style={{
                    border: '1px dashed var(--border)',
                    color: 'var(--text-3)',
                    cursor: ref.spec_document_id && onSelectBoard ? 'pointer' : 'default',
                    background: 'transparent',
                  }}
                >
                  <Icon name="link" size={13} />
                  {ref.title}
                  <span style={{ color: 'var(--text-3)' }}>
                    — in {ref.spec_document_id ? documentTitleById.get(ref.spec_document_id) ?? 'another document' : 'another document'}
                  </span>
                </button>
              ))}
            </div>
          )}
          {layers.map((layer) => {
            const allTerminal = layer.tasks.length > 0 && layer.tasks.every(isTerminalTask)
            const expanded = !collapsedDepths.has(layer.depth)
            const stallSummary = layerStallSummary(layer.tasks)
            return (
              <div key={layer.depth} data-testid={`dependency-board-layer-${layer.depth}`}>
                {/* Task 8.8, design D8's main risk mitigation: name the layer's stalled state,
                    not only each card's — "gated" and "waiting on review" look identical as "a
                    card that will not start" and have different remedies. */}
                {stallSummary && (
                  <p
                    data-testid={`dependency-board-layer-${layer.depth}-stall-summary`}
                    className="dependency-stall-summary text-xs mb-2 px-2 py-1.5"
                    style={{ color: 'var(--text-3)' }}
                  >
                    <Icon name="warning" size={13} style={{ color: 'var(--amber)', marginTop: 1 }} />
                    Layer {layer.depth} is {stallSummary}.
                  </p>
                )}
                {/* Collapse affordance only exists on a fully-terminal layer — a partly finished
                    layer (design D9) always renders its cards, no header, unchanged from before
                    8.6. */}
                {allTerminal && (
                  <button
                    type="button"
                    data-testid={`dependency-board-layer-${layer.depth}-toggle`}
                    aria-expanded={expanded}
                    // The ghost stubs anchor here, so the toggle has to be measurable — it is the
                    // only thing left on screen standing for the layer's folded-away cards.
                    ref={(el) => {
                      if (el) toggleRefsRef.current.set(layer.depth, el)
                      else toggleRefsRef.current.delete(layer.depth)
                    }}
                    onClick={() =>
                      setExpandedOverride((prev) => ({ ...prev, [layer.depth]: !expanded }))
                    }
                    className="dependency-layer-toggle flex items-center gap-1 mb-2 text-xs font-medium"
                    style={{ color: 'var(--text-3)' }}
                  >
                    <Icon name={expanded ? 'expand_more' : 'chevron_right'} size={14} />
                    {layer.tasks.length} done
                    {!expanded && (() => {
                      const hidden = edges.filter((edge) =>
                        layer.tasks.some((task) => task.id === edge.task_id || task.id === edge.depends_on_task_id),
                      ).length
                      return (
                        <span style={{ color: 'var(--text-3)' }}>
                          · {hidden} link{hidden === 1 ? '' : 's'} hidden
                        </span>
                      )
                    })()}
                  </button>
                )}
                {expanded && (
                  <div
                    className="flex flex-wrap items-start gap-3"
                    style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}
                  >
                    {layer.tasks.map((task) => (
                      <div
                        key={task.id}
                        onMouseEnter={() => setHoveredTaskId(task.id)}
                        onMouseLeave={() => setHoveredTaskId(null)}
                        className={lineageIds ? (lineageIds.has(task.id) ? 'lineage-active' : 'lineage-dim') : undefined}
                        ref={(el) => {
                          if (el) cardRefsRef.current.set(task.id, el)
                          else cardRefsRef.current.delete(task.id)
                        }}
                      >
                        <TaskCard
                          task={task}
                          assigneeColorIndex={colorsByAgent.get(task.assignee ?? '')}
                          onOpenRequirement={onOpenRequirement}
                          onOpen={() => setOpenTaskId(task.id)}
                          showLineageHint={connectedTaskIds.has(task.id)}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      <TaskDetailDrawer
        task={openTask}
        onClose={() => setOpenTaskId(null)}
        onOpenRequirement={onOpenRequirement}
      />
    </div>
  )
}
