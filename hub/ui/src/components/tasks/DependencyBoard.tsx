import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { TaskBoardEdge, useTaskBoard } from '@/api/tasks'
import { useAgents } from '@/api/agents'
import { EmptyState } from '@/components/common/EmptyState'
import { Icon } from '@/components/common/Icon'
import { assignDepths, groupByDepth, isTerminalTask } from '@/lib/dependencyBoardLayout'
import { TaskCard } from './TaskCard'
import { TaskDetailDrawer } from './TaskDetailDrawer'

interface EdgeLine {
  id: string
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
 */
function useEdgeLines(
  containerRef: RefObject<HTMLDivElement | null>,
  cardRefs: Map<string, HTMLDivElement>,
  edges: TaskBoardEdge[],
  layoutKey: string,
): EdgeLine[] {
  const [lines, setLines] = useState<EdgeLine[]>([])

  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) return

    const recompute = () => {
      const containerRect = container.getBoundingClientRect()
      const next: EdgeLine[] = []
      for (const edge of edges) {
        const fromEl = cardRefs.get(edge.depends_on_task_id)
        const toEl = cardRefs.get(edge.task_id)
        if (!fromEl || !toEl) continue // off-board reference (task 8.7) — nothing on this board to draw to
        const fromRect = fromEl.getBoundingClientRect()
        const toRect = toEl.getBoundingClientRect()
        next.push({
          id: `${edge.depends_on_task_id}->${edge.task_id}`,
          x1: fromRect.left + fromRect.width / 2 - containerRect.left + container.scrollLeft,
          y1: fromRect.bottom - containerRect.top + container.scrollTop,
          x2: toRect.left + toRect.width / 2 - containerRect.left + container.scrollLeft,
          y2: toRect.top - containerRect.top + container.scrollTop,
        })
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
  }, [containerRef, edges, layoutKey])

  return lines
}

interface DependencyBoardProps {
  /** `null` names the standing "no document" board (design D9) — every hand-made task. */
  specDocumentId: string | null
  onOpenRequirement?: (documentPath: string, anchor: string) => void
}

export function DependencyBoard({ specDocumentId, onOpenRequirement }: DependencyBoardProps) {
  const { data: board, isLoading } = useTaskBoard(specDocumentId)
  const { data: agents = [] } = useAgents()
  const colorsByAgent = useMemo(
    () => new Map(agents.map((agent) => [agent.name, agent.color_index])),
    [agents],
  )
  const [openTaskId, setOpenTaskId] = useState<string | null>(null)
  // Task 8.6: a layer whose every task is terminal (approved/rejected) collapses to one row by
  // default, expandable — but a layer with even one unfinished task never collapses, since that is
  // the shape D9 rejects ("a partly finished layer" must stay legible). Keyed by depth rather than
  // by a Set of collapsed ids so a fresh layer (a document reindex adding depth) is never
  // accidentally pre-expanded by a stale override from a different layer at the same depth.
  const [expandedOverride, setExpandedOverride] = useState<Record<number, boolean>>({})

  const containerRef = useRef<HTMLDivElement | null>(null)
  const cardRefsRef = useRef<Map<string, HTMLDivElement>>(new Map())

  const tasks = board?.tasks ?? []
  const edges = board?.edges ?? []

  const layers = useMemo(() => {
    const depth = assignDepths(tasks, edges)
    return groupByDepth(tasks, depth)
    // `tasks` is a fresh array from React Query every fetch; keying on ids+edges avoids
    // recomputing layout on a refetch that changed nothing about the graph's shape.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks.map((t) => t.id).join(','), edges.map((e) => `${e.task_id}:${e.depends_on_task_id}`).join(',')])

  const layoutKey = layers.map((l) => `${l.depth}:${l.tasks.map((t) => t.id).join(',')}`).join('|')
  const lines = useEdgeLines(containerRef, cardRefsRef.current, edges, layoutKey)

  const openTask = tasks.find((t) => t.id === openTaskId) ?? null

  if (isLoading) {
    return <div className="p-6" style={{ color: 'var(--text-3)' }}>Loading tasks…</div>
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
          style={{ width: '100%', height: '100%', pointerEvents: 'none' }}
        >
          {lines.map((line) => (
            <line
              key={line.id}
              data-testid="dependency-board-edge"
              x1={line.x1}
              y1={line.y1}
              x2={line.x2}
              y2={line.y2}
              stroke="var(--border-hi)"
              strokeWidth={1.5}
            />
          ))}
        </svg>

        <div className="relative flex flex-col gap-6" style={{ zIndex: 1 }}>
          {layers.map((layer) => {
            const allTerminal = layer.tasks.length > 0 && layer.tasks.every(isTerminalTask)
            const expanded = expandedOverride[layer.depth] ?? !allTerminal
            return (
              <div key={layer.depth} data-testid={`dependency-board-layer-${layer.depth}`}>
                {/* Collapse affordance only exists on a fully-terminal layer — a partly finished
                    layer (design D9) always renders its cards, no header, unchanged from before
                    8.6. */}
                {allTerminal && (
                  <button
                    type="button"
                    data-testid={`dependency-board-layer-${layer.depth}-toggle`}
                    aria-expanded={expanded}
                    onClick={() =>
                      setExpandedOverride((prev) => ({ ...prev, [layer.depth]: !expanded }))
                    }
                    className="flex items-center gap-1 mb-2 text-xs font-medium"
                    style={{ color: 'var(--text-3)' }}
                  >
                    <Icon name={expanded ? 'expand_more' : 'chevron_right'} size={14} />
                    {layer.tasks.length} done
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
