import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '@/api/tasks'
import { TaskCard } from '@/components/tasks/TaskCard'

/**
 * task-dependencies task 8.15/8.16, design D12: a slow pulsing green hue around a card whose
 * task has a run executing *right now* — a different fact than the status badge (`in_progress`
 * can be true with nothing actually running; `has_open_divergence` exists for exactly that
 * disagreement). Gated on `prefers-reduced-motion`, degrading to a static hue rather than
 * disappearing, and never the sole carrier of the fact.
 */

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useUpdateTask: () => ({ mutate: vi.fn() }),
    useSetDivergenceHandling: () => ({ mutate: vi.fn() }),
    useStartWorkOnTask: () => ({ mutate: vi.fn() }),
  }
})

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'worker' }] }),
}))

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    project_id: 'proj-test',
    title: 'Ship the thing',
    status: 'in_progress',
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    ...overrides,
  }
}

function mockReducedMotion(matches: boolean) {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }) as unknown as MediaQueryList,
  )
}

function renderCard(task: Task) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TaskCard task={task} onOpen={() => {}} />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('the liveness cue (task 8.15, design D12)', () => {
  it('shows nothing when no run is executing, even with an assignee', () => {
    mockReducedMotion(false)
    renderCard(makeTask({ assignee: 'worker', assignee_status: 'idle' }))
    expect(screen.queryByTestId('task-live-task-1')).not.toBeInTheDocument()
  })

  it('shows nothing for a stalled heartbeat — that is the divergence badge’s fact, not this one', () => {
    mockReducedMotion(false)
    renderCard(makeTask({ assignee: 'worker', assignee_status: 'stalled' }))
    expect(screen.queryByTestId('task-live-task-1')).not.toBeInTheDocument()
  })

  it('marks the card when a run is executing right now', () => {
    mockReducedMotion(false)
    renderCard(makeTask({ assignee: 'worker', assignee_status: 'running' }))
    expect(screen.getByTestId('task-live-task-1')).toBeInTheDocument()
  })

  it('is not the only carrier of the fact — the status pill says it in words too', () => {
    mockReducedMotion(false)
    renderCard(makeTask({ assignee: 'worker', assignee_status: 'running' }))
    expect(screen.getByText('running')).toBeInTheDocument()
  })
})

describe('the cue is gated on prefers-reduced-motion (task 8.16, design D12)', () => {
  it('animates when motion is allowed', () => {
    mockReducedMotion(false)
    renderCard(makeTask({ assignee: 'worker', assignee_status: 'running' }))
    expect(screen.getByTestId('task-live-task-1')).toHaveClass('task-live-pulse')
  })

  it('degrades to a static hue, not to nothing, when motion is reduced', () => {
    mockReducedMotion(true)
    renderCard(makeTask({ assignee: 'worker', assignee_status: 'running' }))
    const card = screen.getByTestId('task-live-task-1')
    expect(card).not.toHaveClass('task-live-pulse')
    expect(card.style.boxShadow).not.toBe('')
  })
})
