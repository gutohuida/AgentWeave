import { describe, expect, it, vi, afterEach } from 'vitest'
import { cleanup, render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { Task, TaskBoardEdge } from '@/api/tasks'
import {
  assignDepths,
  dependencyStallState,
  groupByDepth,
  offBoardPrerequisites,
} from '@/lib/dependencyBoardLayout'

/**
 * `task-dependencies` task 8.1 (longest-path layer assignment), 8.2 (top-to-bottom layout with
 * edges drawn) and 8.3 (reusing `TaskCard` rather than growing a second card component).
 */

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'worker', color_index: 0 }] }),
}))

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    project_id: 'proj-test',
    title: 'Ship the thing',
    status: 'pending',
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    ...overrides,
  }
}

afterEach(cleanup)

describe('assignDepths', () => {
  it('gives a task with no prerequisites depth 0', () => {
    const tasks = [makeTask({ id: 'a' })]
    expect(assignDepths(tasks, [])).toEqual(new Map([['a', 0]]))
  })

  it('walks a chain one layer per hop', () => {
    const tasks = [makeTask({ id: 'a' }), makeTask({ id: 'b' }), makeTask({ id: 'c' })]
    const edges: TaskBoardEdge[] = [
      { task_id: 'b', depends_on_task_id: 'a' },
      { task_id: 'c', depends_on_task_id: 'b' },
    ]
    const depth = assignDepths(tasks, edges)
    expect(depth.get('a')).toBe(0)
    expect(depth.get('b')).toBe(1)
    expect(depth.get('c')).toBe(2)
  })

  it('uses the LONGEST path, not the first-declared prerequisite', () => {
    // a -> b -> d, and a -> d directly. d must sit below b (depth 2), not just below a (depth 1),
    // even though the a->d edge would place it there on its own.
    const tasks = [
      makeTask({ id: 'a' }),
      makeTask({ id: 'b' }),
      makeTask({ id: 'd' }),
    ]
    const edges: TaskBoardEdge[] = [
      { task_id: 'b', depends_on_task_id: 'a' },
      { task_id: 'd', depends_on_task_id: 'a' },
      { task_id: 'd', depends_on_task_id: 'b' },
    ]
    const depth = assignDepths(tasks, edges)
    expect(depth.get('a')).toBe(0)
    expect(depth.get('b')).toBe(1)
    expect(depth.get('d')).toBe(2)
  })

  it('does not hang on a cycle, and assigns something rather than nothing', () => {
    // Should never happen — `spec_completeness` refuses `dependency_cycle` before it reaches the
    // board — but the guard is what stands between a bad row and a hung tab.
    const tasks = [makeTask({ id: 'a' }), makeTask({ id: 'b' })]
    const edges: TaskBoardEdge[] = [
      { task_id: 'a', depends_on_task_id: 'b' },
      { task_id: 'b', depends_on_task_id: 'a' },
    ]
    const depth = assignDepths(tasks, edges)
    expect(depth.get('a')).toBeDefined()
    expect(depth.get('b')).toBeDefined()
  })

  it('ignores a prerequisite that is off this board (an import, task 8.7)', () => {
    const tasks = [makeTask({ id: 'a' })]
    const edges: TaskBoardEdge[] = [{ task_id: 'a', depends_on_task_id: 'somewhere-else' }]
    expect(assignDepths(tasks, edges).get('a')).toBe(0)
  })
})

describe('groupByDepth', () => {
  it('groups shallowest first', () => {
    const tasks = [makeTask({ id: 'a' }), makeTask({ id: 'b' }), makeTask({ id: 'c' })]
    const depth = new Map([['a', 1], ['b', 0], ['c', 1]])
    const layers = groupByDepth(tasks, depth)
    expect(layers.map((l) => l.depth)).toEqual([0, 1])
    expect(layers[0].tasks.map((t) => t.id)).toEqual(['b'])
    expect(layers[1].tasks.map((t) => t.id)).toEqual(['a', 'c'])
  })
})

describe('offBoardPrerequisites', () => {
  it('finds a prerequisite named on an on-board task but not itself on the board', () => {
    const tasks = [
      makeTask({
        id: 'a',
        prerequisites: [{ id: 'ext', title: 'Elsewhere', status: 'pending', spec_document_id: 'doc-x' }],
      }),
    ]
    expect(offBoardPrerequisites(tasks)).toEqual([
      { id: 'ext', title: 'Elsewhere', status: 'pending', spec_document_id: 'doc-x' },
    ])
  })

  it('excludes a prerequisite that is itself on the board', () => {
    const tasks = [
      makeTask({ id: 'a', prerequisites: [{ id: 'b', title: 'On board', status: 'pending' }] }),
      makeTask({ id: 'b' }),
    ]
    expect(offBoardPrerequisites(tasks)).toEqual([])
  })

  it('dedupes an off-board prerequisite shared by two on-board tasks', () => {
    const shared = { id: 'ext', title: 'Shared', status: 'pending', spec_document_id: 'doc-x' }
    const tasks = [
      makeTask({ id: 'a', prerequisites: [shared] }),
      makeTask({ id: 'b', prerequisites: [shared] }),
    ]
    expect(offBoardPrerequisites(tasks)).toHaveLength(1)
  })
})

describe('dependencyStallState', () => {
  it('is null when there is no dependency state at all', () => {
    expect(dependencyStallState(makeTask({ dependency_state: null }))).toBeNull()
  })

  it('is null for a running task whose prerequisite regressed — that is task 8.9, not a stall', () => {
    expect(dependencyStallState(makeTask({ dependency_state: 'running_on_regressed' }))).toBeNull()
  })

  it('is gated_on_rejected when a prerequisite was rejected', () => {
    expect(dependencyStallState(makeTask({ dependency_state: 'gated_on_rejected' }))).toBe(
      'gated_on_rejected',
    )
  })

  it('is waiting_on_review when every unmet prerequisite is done but unreviewed', () => {
    const task = makeTask({
      dependency_state: 'gated',
      prerequisites: [
        { id: 'p1', title: 'p1', status: 'completed' },
        { id: 'p2', title: 'p2', status: 'under_review' },
      ],
    })
    expect(dependencyStallState(task)).toBe('waiting_on_review')
  })

  it('is plain gated when at least one unmet prerequisite is still being worked', () => {
    const task = makeTask({
      dependency_state: 'gated',
      prerequisites: [
        { id: 'p1', title: 'p1', status: 'completed' },
        { id: 'p2', title: 'p2', status: 'in_progress' },
      ],
    })
    expect(dependencyStallState(task)).toBe('gated')
  })
})

function renderBoard(
  tasks: Task[],
  edges: TaskBoardEdge[],
  boards: { spec_document_id: string | null; title: string | null; total: number; outstanding: number }[] = [],
) {
  vi.doMock('@/api/tasks', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/api/tasks')>()
    return {
      ...actual,
      useTaskBoard: () => ({ data: { spec_document_id: 'spdoc-1', tasks, edges }, isLoading: false }),
      useTaskBoards: () => ({ data: { boards } }),
    }
  })
}

describe('DependencyBoard', () => {
  it('renders each task inside the layer row matching its longest-path depth, via TaskCard', async () => {
    vi.resetModules()
    renderBoard(
      [
        makeTask({ id: 'a', title: 'Root task' }),
        makeTask({ id: 'b', title: 'Middle task' }),
        makeTask({ id: 'c', title: 'Leaf task' }),
      ],
      [
        { task_id: 'b', depends_on_task_id: 'a' },
        { task_id: 'c', depends_on_task_id: 'b' },
      ],
    )
    const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Board specDocumentId="spdoc-1" />
      </QueryClientProvider>,
    )

    expect(screen.getByTestId('dependency-board-layer-0')).toHaveTextContent('Root task')
    expect(screen.getByTestId('dependency-board-layer-1')).toHaveTextContent('Middle task')
    expect(screen.getByTestId('dependency-board-layer-2')).toHaveTextContent('Leaf task')

    // TaskCard's own status badge is present — confirms the real card is reused, not a
    // stand-in that only prints a title.
    expect(screen.getAllByText(/pending/i).length).toBeGreaterThan(0)

    // Clicking the card opens the same TaskDetailDrawer TaskCard always opens (F5).
    fireEvent.click(screen.getByText('Root task'))
    expect(screen.getByTestId('task-open-a')).toBeInTheDocument()
  })

  it('draws a directed orthogonal path per edge whose two ends are both on the board', async () => {
    vi.resetModules()
    renderBoard(
      [makeTask({ id: 'a', title: 'Root task' }), makeTask({ id: 'b', title: 'Middle task' })],
      [
        { task_id: 'b', depends_on_task_id: 'a' },
        // Off-board reference (task 8.7's territory) — must not blow up, and draws no line yet.
        { task_id: 'b', depends_on_task_id: 'somewhere-else' },
      ],
    )
    const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Board specDocumentId="spdoc-1" />
      </QueryClientProvider>,
    )

    const drawn = screen.getAllByTestId('dependency-board-edge')
    expect(drawn).toHaveLength(1)
    expect(drawn[0].tagName).toBe('path')
    // One marker per edge class, not one shared grey head — see `markerIdFor`.
    expect(drawn[0]).toHaveAttribute('marker-end', 'url(#dependency-arrow-normal)')
    expect(drawn[0].getAttribute('d')).toMatch(/^M .* V .* H .* V /)
  })

  it('highlights the hovered task lineage and dims unrelated work', async () => {
    vi.resetModules()
    renderBoard(
      [
        makeTask({ id: 'a', title: 'Root task' }),
        makeTask({ id: 'b', title: 'Leaf task' }),
        makeTask({ id: 'c', title: 'Disconnected task' }),
      ],
      [{ task_id: 'b', depends_on_task_id: 'a' }],
    )
    const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Board specDocumentId="spdoc-1" />
      </QueryClientProvider>,
    )

    fireEvent.mouseEnter(screen.getByText('Leaf task'))
    expect(screen.getByText('Root task').closest('.lineage-active')).not.toBeNull()
    expect(screen.getByText('Leaf task').closest('.lineage-active')).not.toBeNull()
    expect(screen.getByText('Disconnected task').closest('.lineage-dim')).not.toBeNull()
    expect(screen.getByTestId('dependency-board-edge')).toHaveClass('lineage-active')
  })

  it('shows an empty state when the board has no tasks', async () => {
    vi.resetModules()
    renderBoard([], [])
    const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Board specDocumentId="spdoc-1" />
      </QueryClientProvider>,
    )

    expect(screen.getByText('No tasks on this board')).toBeInTheDocument()
  })

  // Task 8.4: the status badge (TaskCard.tsx:235) must read correctly with no status column —
  // the dependency board repurposes position for depth (design D8), so the badge is the only
  // place a card's status is stated at all.
  it('shows each task\'s own status badge with no status column beside it (task 8.4)', async () => {
    vi.resetModules()
    renderBoard(
      [
        makeTask({ id: 'a', title: 'First card', status: 'pending' }),
        makeTask({ id: 'b', title: 'Second card', status: 'in_progress' }),
      ],
      [],
    )
    const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Board specDocumentId="spdoc-1" />
      </QueryClientProvider>,
    )

    // Both statuses read directly off their own card — nothing about the layer (depth 0 for
    // both, since neither depends on the other) says which is which; only the badge does.
    expect(screen.getByTestId('task-open-a').closest('.cursor-pointer')).toHaveTextContent(/pending/i)
    expect(screen.getByTestId('task-open-b').closest('.cursor-pointer')).toHaveTextContent(/in progress/i)
  })

  describe('task 8.6 — collapsing a terminal layer', () => {
    it('collapses a layer whose every task is terminal (approved/rejected), by default', async () => {
      vi.resetModules()
      renderBoard(
        [
          makeTask({ id: 'a', title: 'Done task one', status: 'approved' }),
          makeTask({ id: 'b', title: 'Done task two', status: 'rejected' }),
        ],
        [],
      )
      const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={client}>
          <Board specDocumentId="spdoc-1" />
        </QueryClientProvider>,
      )

      expect(screen.queryByText('Done task one')).not.toBeInTheDocument()
      expect(screen.queryByText('Done task two')).not.toBeInTheDocument()
      const toggle = screen.getByTestId('dependency-board-layer-0-toggle')
      expect(toggle).toHaveAttribute('aria-expanded', 'false')
      expect(toggle).toHaveTextContent('2 done')

      fireEvent.click(toggle)
      expect(screen.getByText('Done task one')).toBeInTheDocument()
      expect(screen.getByText('Done task two')).toBeInTheDocument()
      expect(toggle).toHaveAttribute('aria-expanded', 'true')
    })

    it('never collapses a layer with even one unfinished task (design D9)', async () => {
      vi.resetModules()
      renderBoard(
        [
          makeTask({ id: 'a', title: 'Done task', status: 'approved' }),
          makeTask({ id: 'b', title: 'Still going', status: 'in_progress' }),
        ],
        [],
      )
      const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={client}>
          <Board specDocumentId="spdoc-1" />
        </QueryClientProvider>,
      )

      expect(screen.getByText('Done task')).toBeInTheDocument()
      expect(screen.getByText('Still going')).toBeInTheDocument()
      expect(screen.queryByTestId('dependency-board-layer-0-toggle')).not.toBeInTheDocument()
    })
  })

  describe('task 8.7 — an imported entry draws as an off-board reference', () => {
    it('names the off-board prerequisite and the document it lives in', async () => {
      vi.resetModules()
      renderBoard(
        [
          makeTask({
            id: 'b',
            title: 'Depends on something elsewhere',
            prerequisites: [
              { id: 'ext-1', title: 'External prerequisite', status: 'approved', spec_document_id: 'doc-other' },
            ],
          }),
        ],
        [{ task_id: 'b', depends_on_task_id: 'ext-1' }],
        [{ spec_document_id: 'doc-other', title: 'The Other Document', total: 1, outstanding: 0 }],
      )
      const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      const onSelectBoard = vi.fn()
      render(
        <QueryClientProvider client={client}>
          <Board specDocumentId="spdoc-1" onSelectBoard={onSelectBoard} />
        </QueryClientProvider>,
      )

      const ref = screen.getByTestId('dependency-board-offboard-ref-ext-1')
      expect(ref).toHaveTextContent('External prerequisite')
      expect(ref).toHaveTextContent('The Other Document')
      fireEvent.click(ref)
      expect(onSelectBoard).toHaveBeenCalledWith('doc-other')
    })

    it('draws nothing when every prerequisite is on this board', async () => {
      vi.resetModules()
      renderBoard(
        [makeTask({ id: 'a', title: 'Root' }), makeTask({ id: 'b', title: 'Leaf' })],
        [{ task_id: 'b', depends_on_task_id: 'a' }],
      )
      const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={client}>
          <Board specDocumentId="spdoc-1" />
        </QueryClientProvider>,
      )

      expect(screen.queryByTestId('dependency-board-offboard-refs')).not.toBeInTheDocument()
    })
  })

  describe('task 8.8 — the layer names its own stalled state (design D8)', () => {
    it('says a layer is waiting on N reviews when prerequisites are done but unreviewed', async () => {
      vi.resetModules()
      renderBoard(
        [
          makeTask({
            id: 'a',
            title: 'Blocked on review',
            dependency_state: 'gated',
            prerequisites: [{ id: 'p1', title: 'Prereq', status: 'completed' }],
          }),
        ],
        [],
      )
      const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={client}>
          <Board specDocumentId="spdoc-1" />
        </QueryClientProvider>,
      )

      expect(screen.getByTestId('dependency-board-layer-0-stall-summary')).toHaveTextContent(
        'waiting on 1 review',
      )
    })

    it('distinguishes gated from gated-on-rejected in the same layer', async () => {
      vi.resetModules()
      renderBoard(
        [
          makeTask({
            id: 'a',
            dependency_state: 'gated',
            prerequisites: [{ id: 'p1', title: 'Prereq', status: 'pending' }],
          }),
          makeTask({
            id: 'b',
            dependency_state: 'gated_on_rejected',
            prerequisites: [{ id: 'p2', title: 'Prereq 2', status: 'rejected' }],
          }),
        ],
        [],
      )
      const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={client}>
          <Board specDocumentId="spdoc-1" />
        </QueryClientProvider>,
      )

      const summary = screen.getByTestId('dependency-board-layer-0-stall-summary')
      expect(summary).toHaveTextContent('1 gated on an unmet prerequisite')
      expect(summary).toHaveTextContent('1 gated on a rejected prerequisite')
    })

    it('says nothing when nothing in the layer is stalled', async () => {
      vi.resetModules()
      renderBoard([makeTask({ id: 'a', dependency_state: null })], [])
      const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={client}>
          <Board specDocumentId="spdoc-1" />
        </QueryClientProvider>,
      )

      expect(screen.queryByTestId('dependency-board-layer-0-stall-summary')).not.toBeInTheDocument()
    })
  })

  // S4 `considered` remediation: the approved mock's edge treatment, which shipped as the
  // `restrained` variant (one grey arrowhead, a bare hidden-link count, no lineage affordance).
  describe('S4 — the edge colour coding reaches the arrowhead', () => {
    it('gives each edge class its own marker rather than one shared grey head', async () => {
      vi.resetModules()
      renderBoard(
        [
          // Deliberately non-terminal, so layer 0 stays open and its edges are real, not ghosts.
          makeTask({ id: 'a', title: 'Live prerequisite', status: 'in_progress' }),
          makeTask({ id: 'b', title: 'Blocked by a rejection', dependency_state: 'gated_on_rejected' }),
          makeTask({ id: 'c', title: 'Merely gated', dependency_state: 'gated' }),
        ],
        [
          { task_id: 'b', depends_on_task_id: 'a' },
          { task_id: 'c', depends_on_task_id: 'a' },
        ],
      )
      const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={client}>
          <Board specDocumentId="spdoc-1" />
        </QueryClientProvider>,
      )

      const drawn = screen.getAllByTestId('dependency-board-edge')
      const markers = drawn.map((path) => path.getAttribute('marker-end'))
      expect(markers).toContain('url(#dependency-arrow-rejected)')
      expect(markers).toContain('url(#dependency-arrow-gated)')
      // Every referenced marker is actually defined — a dangling `marker-end` renders no head at
      // all, which is worse than the grey one this replaces.
      for (const marker of markers) {
        const id = marker!.slice('url(#'.length, -1)
        expect(document.getElementById(id)).not.toBeNull()
      }
    })

    it('switches the arrowhead to the lineage marker while a trace is highlighted', async () => {
      vi.resetModules()
      renderBoard(
        [makeTask({ id: 'a', title: 'Root task' }), makeTask({ id: 'b', title: 'Leaf task' })],
        [{ task_id: 'b', depends_on_task_id: 'a' }],
      )
      const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={client}>
          <Board specDocumentId="spdoc-1" />
        </QueryClientProvider>,
      )

      const edge = screen.getByTestId('dependency-board-edge')
      expect(edge).toHaveAttribute('marker-end', 'url(#dependency-arrow-normal)')
      fireEvent.mouseEnter(screen.getByText('Leaf task'))
      expect(edge).toHaveAttribute('marker-end', 'url(#dependency-arrow-lineage)')
    })

    it('draws a ghost stub for a link a collapsed layer is hiding, not just a count', async () => {
      vi.resetModules()
      renderBoard(
        [
          // Layer 0 is entirely terminal, so it folds by default (task 8.6) and takes its card —
          // and therefore its edge's upper endpoint — off the board.
          makeTask({ id: 'a', title: 'Done prerequisite', status: 'approved' }),
          makeTask({ id: 'b', title: 'Still going', status: 'in_progress' }),
        ],
        [{ task_id: 'b', depends_on_task_id: 'a' }],
      )
      const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={client}>
          <Board specDocumentId="spdoc-1" />
        </QueryClientProvider>,
      )

      expect(screen.queryByText('Done prerequisite')).not.toBeInTheDocument()
      // The count still reports it, and the stub now shows where it went.
      expect(screen.getByTestId('dependency-board-layer-0-toggle')).toHaveTextContent('1 link hidden')
      const ghost = screen.getByTestId('dependency-board-ghost-edge')
      expect(ghost).toHaveClass('dependency-edge-ghost')
      expect(ghost).toHaveAttribute('marker-end', 'url(#dependency-arrow-ghost)')
      // A ghost is never claimed by a lineage trace — its far end is not on screen.
      expect(ghost).not.toHaveClass('lineage-active')

      // Expanding restores the real edge and retires the stub.
      fireEvent.click(screen.getByTestId('dependency-board-layer-0-toggle'))
      expect(screen.queryByTestId('dependency-board-ghost-edge')).not.toBeInTheDocument()
      expect(screen.getByTestId('dependency-board-edge')).toBeInTheDocument()
    })

    it('tells the operator the lineage trace exists, but only on a card that has one', async () => {
      vi.resetModules()
      renderBoard(
        [
          makeTask({ id: 'a', title: 'Root task' }),
          makeTask({ id: 'b', title: 'Leaf task' }),
          makeTask({ id: 'c', title: 'Disconnected task' }),
        ],
        [{ task_id: 'b', depends_on_task_id: 'a' }],
      )
      const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={client}>
          <Board specDocumentId="spdoc-1" />
        </QueryClientProvider>,
      )

      expect(screen.getByTestId('task-lineage-hint-a')).toHaveTextContent('hover to trace lineage')
      expect(screen.getByTestId('task-lineage-hint-b')).toBeInTheDocument()
      expect(screen.queryByTestId('task-lineage-hint-c')).not.toBeInTheDocument()
    })

    it('marks a rejected card as the cause the red edges point at', async () => {
      vi.resetModules()
      renderBoard([makeTask({ id: 'a', title: 'Rejected task', status: 'rejected' })], [])
      const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={client}>
          <Board specDocumentId="spdoc-1" />
        </QueryClientProvider>,
      )

      // A single-task layer of terminal work folds by default; open it to see the card.
      fireEvent.click(screen.getByTestId('dependency-board-layer-0-toggle'))
      const card = screen.getByTestId('task-open-a').closest('.task-card-refined') as HTMLElement
      expect(card.style.border).toContain('var(--red)')
    })
  })
})
