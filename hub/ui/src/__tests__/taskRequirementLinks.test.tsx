import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '@/api/tasks'
import { TaskCard } from '@/components/tasks/TaskCard'

/**
 * The board showed the prose and hid the links.
 *
 * `requirements` is what the caller typed; `requirement_links` is the checked traceability the
 * approval gate actually enforces, and evidence joins to a task *through* it. Rendering only the
 * prose meant a card could not tell you whether it was tied to the specification at all — which is
 * the same asymmetry the API had, one layer up.
 *
 * Both are shown. The prose can say things no identifier can, so it is relabelled rather than
 * replaced.
 */

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useUpdateTask: () => ({ mutate: vi.fn() }),
    useSetDivergenceHandling: () => ({ mutate: vi.fn() }),
    useStartWorkOnTask: () => ({ mutate: vi.fn() }),
    useTaskIntegrations: () => ({ data: { integrations: [] } }),
    useRetryTaskIntegration: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
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

async function renderExpanded(task: Task) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TaskCard task={task} />
    </QueryClientProvider>,
  )
  await userEvent.click(screen.getByText(task.title))
}

afterEach(cleanup)

describe('a card shows what it is checked against', () => {
  it('lists the checked links alongside the free-text requirements', async () => {
    await renderExpanded(
      makeTask({
        requirements: ['must settle to the cent'],
        requirement_ids: ['FR-1'],
        requirement_links: [
          {
            identifier: 'FR-1',
            requirement_id: 'spreq-a',
            document_id: 'spdoc-1',
            state: 'active',
            statement: 'It settles the account',
          },
        ],
      }),
    )

    expect(screen.getByTestId('task-serves-task-1')).toBeTruthy()
    expect(screen.getByText('FR-1')).toBeTruthy()
    expect(screen.getByText(/It settles the account/)).toBeTruthy()
    // The prose survives, relabelled so the two are not confused for each other.
    expect(screen.getByText('Requirements (as written)')).toBeTruthy()
    expect(screen.getByText('must settle to the cent')).toBeTruthy()
  })

  it('marks a link whose requirement is no longer active', async () => {
    await renderExpanded(
      makeTask({
        requirement_links: [
          {
            identifier: 'FR-2',
            requirement_id: 'spreq-b',
            document_id: 'spdoc-1',
            state: 'retired',
            statement: null,
          },
        ],
      }),
    )

    expect(screen.getByText('(retired)')).toBeTruthy()
  })

  it('shows a reference that resolved to nothing rather than dropping it', async () => {
    await renderExpanded(
      makeTask({
        unresolved_requirements: [{ reference: 'FR-99', reason: 'no such requirement' }],
      }),
    )

    expect(screen.getByText(/FR-99 — no such requirement/)).toBeTruthy()
  })

  it('renders no Serves block for a task that serves nothing', async () => {
    await renderExpanded(makeTask({ requirements: ['just prose'] }))

    expect(screen.queryByTestId('task-serves-task-1')).toBeNull()
    expect(screen.getByText('Requirements (as written)')).toBeTruthy()
  })
})
