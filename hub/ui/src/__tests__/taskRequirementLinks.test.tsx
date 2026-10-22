import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '@/api/tasks'
import { useSpecDocuments } from '@/api/spec'
import { TaskCardCompact } from '@/components/tasks/TaskCardCompact'
import { useRequirementTallies } from '@/hooks/useRequirementTallies'
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

// A path's coverage, settable per test — mutated directly rather than reassigned, since the
// `vi.mock` factory below closes over this same object identity.
const coverageByPath: Record<string, unknown> = {}

vi.mock('@/api/spec', () => ({
  useSpecDocuments: () => ({
    data: {
      documents: [
        {
          id: 'spdoc-1',
          path: 'spec/example.json',
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
  useSpecCoverageMany: (paths: string[]) => paths.map((path) => ({ data: coverageByPath[path], dataUpdatedAt: 0 })),
}))

function coverageEntry(overrides: Record<string, unknown> = {}) {
  return {
    identifier: 'FR-1',
    requirement_id: 'spreq-a',
    document_id: 'spdoc-1',
    state: 'verified',
    integration: 'integrated',
    evidence_count: 1,
    accepted_count: 1,
    linked_task_ids: [],
    ...overrides,
  }
}

function setCoverage(path: string, requirements: Record<string, unknown>[]) {
  coverageByPath[path] = { requirements, diagnostics: [], totals: {}, integration: {}, unserved: [] }
}

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

// The "Serves" block lives in the drawer (F5, `design.md` D8) — opened the same way the operator
// would, by clicking the card.
async function renderExpanded(task: Task, onOpenRequirement?: (path: string, anchor: string) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TaskCardHost task={task} onOpenRequirement={onOpenRequirement} />
    </QueryClientProvider>,
  )
  await userEvent.click(screen.getByTestId(`task-open-${task.id}`))
}

afterEach(() => {
  cleanup()
  for (const key of Object.keys(coverageByPath)) delete coverageByPath[key]
})

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
 * F4's other half: how a task's requirements stand, visible on the collapsed card, and a way to
 * land on a requirement in its document. The compact card carries one tally ("N/M FR", read from
 * each requirement's document coverage, the full count in its title); the requirements one by
 * one, each a link into its document, are the drawer's "Serves" list.
 */
describe('the requirement tally on the card (F4)', () => {
  /** The board's own read: `useRequirementTallies` over the tasks and the loaded documents. */
  function CardOnBoard({ task }: { task: Task }) {
    const { data } = useSpecDocuments()
    const tallies = useRequirementTallies([task], data?.documents ?? [])
    return <TaskCardCompact task={task} tally={tallies[task.id]} onOpen={() => {}} />
  }

  function renderCollapsed(task: Task) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(
      <QueryClientProvider client={client}>
        <CardOnBoard task={task} />
      </QueryClientProvider>,
    )
  }

  const tally = () => document.querySelector('.aw-task-card-reqs') as HTMLElement | null

  const links = (ids: string[], overrides: Record<string, Partial<NonNullable<Task['requirement_links']>[number]>> = {}) =>
    ids.map((identifier) => ({
      identifier,
      requirement_id: `spreq-${identifier}`,
      document_id: 'spdoc-1',
      state: 'active',
      statement: null,
      ...overrides[identifier],
    }))

  it('counts every requirement_ids entry without expanding the card', () => {
    renderCollapsed(makeTask({ requirement_ids: ['FR-1', 'FR-2'], requirement_links: links(['FR-1', 'FR-2']) }))

    expect(tally()).toHaveTextContent('0/2 FR')
    // Not expanded — the "Serves" block, which lists the same links with their full statement,
    // is not rendered until the card is opened.
    expect(screen.queryByTestId('task-serves-task-1')).toBeNull()
  })

  it('renders nothing when requirement_ids is empty or absent', () => {
    renderCollapsed(makeTask({ requirements: ['just prose'] }))

    expect(tally()).toBeNull()
  })

  it('reads verified and rejected from document coverage, not requirement_links[].state', () => {
    // Both links carry the same lifecycle state (`active`) — if the tally read `state`, as the
    // chips' first draft wrongly did (R1), the two could not be told apart.
    setCoverage('spec/example.json', [
      coverageEntry({ identifier: 'FR-1', state: 'rejected' }),
      coverageEntry({ identifier: 'FR-2', state: 'verified' }),
    ])
    renderCollapsed(makeTask({ requirement_ids: ['FR-1', 'FR-2'], requirement_links: links(['FR-1', 'FR-2']) }))

    expect(tally()).toHaveTextContent('1/2 FR')
    expect(tally()).toHaveAttribute('data-rejected', 'true')
    expect(tally()).toHaveAttribute('data-complete', 'false')
    expect(tally()).toHaveAttribute('title', '1 of 2 requirements verified, 1 rejected')
  })

  it('does not count a requirement awaiting review, or one with no coverage row, as verified', () => {
    setCoverage('spec/example.json', [coverageEntry({ identifier: 'FR-1', state: 'evidence_awaiting_review' })])
    renderCollapsed(
      makeTask({
        requirement_ids: ['FR-1', 'FR-2'],
        // FR-2 is retired: a retired requirement has no document-coverage row at all.
        requirement_links: links(['FR-1', 'FR-2'], { 'FR-2': { state: 'retired' } }),
      }),
    )

    expect(tally()).toHaveTextContent('0/2 FR')
    expect(tally()).toHaveAttribute('data-rejected', 'false')
  })

  it('names a requirement awaiting review in the tally, apart from the unproven ones (F903)', () => {
    setCoverage('spec/example.json', [
      coverageEntry({ identifier: 'FR-1', state: 'evidence_awaiting_review' }),
      coverageEntry({ identifier: 'FR-2', state: 'verified' }),
    ])
    renderCollapsed(makeTask({ requirement_ids: ['FR-1', 'FR-2'], requirement_links: links(['FR-1', 'FR-2']) }))

    expect(tally()).toHaveAttribute('data-awaiting-review', 'true')
    expect(tally()).toHaveAttribute('title', '1 of 2 requirements verified, 1 awaiting review')
  })

  it('states the whole count by coverage state, however many requirements there are', () => {
    setCoverage('spec/example.json', [
      coverageEntry({ identifier: 'FR-1', state: 'verified' }),
      coverageEntry({ identifier: 'FR-2', state: 'verified' }),
      coverageEntry({ identifier: 'FR-3', state: 'rejected' }),
      coverageEntry({ identifier: 'FR-4', state: 'evidence_awaiting_review' }),
      coverageEntry({ identifier: 'FR-5', state: 'not_started' }),
    ])
    const ids = ['FR-1', 'FR-2', 'FR-3', 'FR-4', 'FR-5']
    renderCollapsed(makeTask({ requirement_ids: ids, requirement_links: links(ids) }))

    expect(tally()).toHaveTextContent('2/5 FR')
    expect(tally()).toHaveAttribute('title', '2 of 5 requirements verified, 1 rejected, 1 awaiting review')
  })

  it('marks the tally complete once every requirement is verified', () => {
    setCoverage('spec/example.json', [
      coverageEntry({ identifier: 'FR-1', state: 'verified' }),
      coverageEntry({ identifier: 'FR-2', state: 'verified' }),
    ])
    renderCollapsed(makeTask({ requirement_ids: ['FR-1', 'FR-2'], requirement_links: links(['FR-1', 'FR-2']) }))

    expect(tally()).toHaveAttribute('data-complete', 'true')
    expect(tally()).toHaveAttribute('title', '2 of 2 requirements verified')
  })
})

describe('a requirement opens in its document from the drawer (F4)', () => {
  it('resolves the document from document_id and navigates with the anchor', async () => {
    const onOpenRequirement = vi.fn()
    await renderExpanded(
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

    await userEvent.click(within(screen.getByTestId('task-serves-task-1')).getByRole('button', { name: /FR-1/ }))

    expect(onOpenRequirement).toHaveBeenCalledWith('spec/example.json', 'FR-1')
  })

  it('is not clickable when the requirement resolves to no document', async () => {
    const onOpenRequirement = vi.fn()
    await renderExpanded(
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

    const link = within(screen.getByTestId('task-serves-task-1')).getByRole('button', { name: /FR-9/ })
    expect(link).toBeDisabled()
    await userEvent.click(link)
    expect(onOpenRequirement).not.toHaveBeenCalled()
  })
})
