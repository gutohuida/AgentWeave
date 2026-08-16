import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '@/api/tasks'
import { TaskCard } from '@/components/tasks/TaskCard'
import { TaskCardHost } from './testUtils/TaskCardHost'

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

vi.mock('@/api/spec', () => ({
  useSpecDocuments: () => ({
    data: {
      documents: [
        {
          id: 'spdoc-1',
          path: 'spec/example.html',
          title: 'Example',
          kind: 'baseline',
          phase: 'approved',
          rigor: 'sketch',
          content_digest: null,
          explore_closed: false,
          updated_at: '2026-08-16T00:00:00Z',
        },
      ],
    },
  }),
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

// The "Serves" block moved into the drawer along with the rest of the inline expansion (F5,
// `design.md` D8) — opened the same way the operator would, via the card's explicit "open"
// affordance.
async function renderExpanded(task: Task) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TaskCardHost task={task} />
    </QueryClientProvider>,
  )
  await userEvent.click(screen.getByTestId(`task-open-${task.id}`))
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
    // "FR-1" now also renders as a header chip (F4) — scope this assertion to the "Serves" block.
    expect(within(screen.getByTestId('task-serves-task-1')).getByText('FR-1')).toBeTruthy()
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

/**
 * F4's other half: which requirement(s) a task serves, visible on the collapsed card, and a way
 * to land on the requirement in its document from there.
 */
describe('the requirement chip row (F4)', () => {
  function renderCollapsed(task: Task, onOpenRequirement?: (path: string, anchor: string) => void) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(
      <QueryClientProvider client={client}>
        <TaskCard task={task} onOpenRequirement={onOpenRequirement} onOpen={() => {}} />
      </QueryClientProvider>,
    )
  }

  it('renders one chip per requirement_ids entry without expanding the card', () => {
    renderCollapsed(
      makeTask({
        requirement_ids: ['FR-1', 'FR-2'],
        requirement_links: [
          {
            identifier: 'FR-1',
            requirement_id: 'spreq-a',
            document_id: 'spdoc-1',
            state: 'active',
            statement: 'Settle to the cent',
          },
          {
            identifier: 'FR-2',
            requirement_id: 'spreq-b',
            document_id: 'spdoc-1',
            state: 'active',
            statement: 'Round consistently',
          },
        ],
      }),
    )

    expect(screen.getByTestId('task-requirement-chip-task-1-FR-1')).toBeTruthy()
    expect(screen.getByTestId('task-requirement-chip-task-1-FR-2')).toBeTruthy()
    // Not expanded — the "Serves" block, which lists the same links with their full statement,
    // is not rendered until the card is opened.
    expect(screen.queryByTestId('task-serves-task-1')).toBeNull()
  })

  it('renders nothing when requirement_ids is empty or absent', () => {
    renderCollapsed(makeTask({ requirements: ['just prose'] }))

    expect(screen.queryByTestId(/task-requirement-chip/)).toBeNull()
  })

  it('gives a chip whose requirement has rejected evidence the rejected tone', () => {
    renderCollapsed(
      makeTask({
        requirement_ids: ['FR-1', 'FR-2'],
        requirement_links: [
          {
            identifier: 'FR-1',
            requirement_id: 'spreq-a',
            document_id: 'spdoc-1',
            state: 'active',
            statement: 'Settle to the cent',
            has_rejected_evidence: true,
          },
          {
            identifier: 'FR-2',
            requirement_id: 'spreq-b',
            document_id: 'spdoc-1',
            state: 'active',
            statement: 'Round consistently',
            has_rejected_evidence: false,
          },
        ],
      }),
    )

    const rejectedChip = screen.getByTestId('task-requirement-chip-task-1-FR-1')
    const okChip = screen.getByTestId('task-requirement-chip-task-1-FR-2')
    expect(rejectedChip.style.color).toBe('var(--red)')
    expect(okChip.style.color).not.toBe('var(--red)')
  })

  it('clicking a chip resolves the document from document_id and navigates with the anchor', async () => {
    const onOpenRequirement = vi.fn()
    renderCollapsed(
      makeTask({
        requirement_ids: ['FR-1'],
        requirement_links: [
          {
            identifier: 'FR-1',
            requirement_id: 'spreq-a',
            document_id: 'spdoc-1',
            state: 'active',
            statement: 'Settle to the cent',
            anchor: '#FR-1',
          },
        ],
      }),
      onOpenRequirement,
    )

    await userEvent.click(screen.getByTestId('task-requirement-chip-task-1-FR-1'))

    expect(onOpenRequirement).toHaveBeenCalledWith('spec/example.html', 'FR-1')
  })

  it('is not clickable when the requirement resolves to no document', async () => {
    const onOpenRequirement = vi.fn()
    renderCollapsed(
      makeTask({
        requirement_ids: ['FR-9'],
        requirement_links: [
          {
            identifier: 'FR-9',
            requirement_id: 'spreq-z',
            document_id: 'spdoc-missing',
            state: 'active',
            statement: null,
          },
        ],
      }),
      onOpenRequirement,
    )

    const chip = screen.getByTestId('task-requirement-chip-task-1-FR-9')
    expect(chip).toBeDisabled()
    await userEvent.click(chip)
    expect(onOpenRequirement).not.toHaveBeenCalled()
  })
})
