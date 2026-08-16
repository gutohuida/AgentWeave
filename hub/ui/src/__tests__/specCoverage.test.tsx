import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, cleanup, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'

/* Coverage on the Spec view.
 *
 * Two properties are load-bearing and both are easy to lose in a redesign. A coverage state is
 * never shown without its integration answer — "verified" alone is true of a branch and false of
 * the product. And a requirement that could not be given a state at all is shown as broken rather
 * than quietly counted among the ones nobody has built yet.
 */

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

import { SpecCoverageBar } from '@/components/spec/SpecCoverageBar'

const PATH = 'spec/changes/demo/spec.html'

function entry(overrides: Record<string, unknown> = {}) {
  return {
    identifier: 'FR-1',
    requirement_id: 'spreq-1',
    document_id: 'spdoc-1',
    state: 'verified',
    integration: 'integrated',
    evidence_count: 1,
    accepted_count: 1,
    linked_task_ids: ['task-1'],
    ...overrides,
  }
}

function mount(payload: Record<string, unknown>, onOpenTasks?: (taskIds: string[]) => void) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => payload,
      text: async () => JSON.stringify(payload),
      headers: new Headers({ 'content-type': 'application/json' }),
    })),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecCoverageBar path={PATH} onOpenTasks={onOpenTasks} />
    </QueryClientProvider>,
  )
}

describe('coverage on the spec view', () => {
  beforeEach(() => {
    cleanup()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-a',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('counts each state the document is actually in', async () => {
    mount({
      requirements: [entry(), entry({ identifier: 'FR-2', requirement_id: 'spreq-2', state: 'unserved', integration: 'not_applicable', evidence_count: 0, accepted_count: 0, linked_task_ids: [] })],
      diagnostics: [],
      totals: { verified: 1, unserved: 1 },
      integration: { integrated: 1, not_applicable: 1 },
      unserved: ['FR-2'],
    })

    expect(await screen.findByTestId('coverage-count-verified')).toHaveTextContent('1 verified')
    expect(screen.getByTestId('coverage-count-unserved')).toHaveTextContent('1 no work linked')
  })

  it('surfaces verified work that is not in the main line without being opened', async () => {
    mount({
      requirements: [entry({ integration: 'not_integrated' })],
      diagnostics: [],
      totals: { verified: 1 },
      integration: { not_integrated: 1 },
      unserved: [],
    })

    const banner = await screen.findByTestId('coverage-not-integrated')
    expect(banner).toHaveTextContent('1 verified, not in the main line')
    expect(banner).toHaveTextContent('FR-1')
  })

  it('does not claim work is unintegrated when there is no main line to compare against', async () => {
    mount({
      requirements: [entry({ integration: 'unknown' })],
      diagnostics: [],
      totals: { verified: 1 },
      integration: { unknown: 1 },
      unserved: [],
    })

    await screen.findByTestId('coverage-count-verified')
    expect(screen.queryByTestId('coverage-not-integrated')).toBeNull()
  })

  it('shows a broken requirement as broken rather than as unserved', async () => {
    mount({
      requirements: [],
      diagnostics: [
        {
          requirement_id: 'spreq-9',
          identifier: 'FR-9',
          document_id: 'spdoc-1',
          problem: 'carries no semantic digest',
        },
      ],
      totals: {},
      integration: {},
      unserved: [],
    })

    expect(await screen.findByTestId('coverage-diagnostics')).toHaveTextContent('1 broken')
    expect(screen.queryByTestId('coverage-count-unserved')).toBeNull()
  })

  it('shows a rejected requirement as rejected, not in_progress, in the summary bar', async () => {
    mount({
      requirements: [
        entry({
          state: 'rejected',
          integration: 'not_applicable',
          accepted_count: 0,
          linked_task_ids: [],
        }),
      ],
      diagnostics: [],
      totals: { rejected: 1 },
      integration: { not_applicable: 1 },
      unserved: [],
    })

    expect(await screen.findByTestId('coverage-count-rejected')).toHaveTextContent('1 rejected')
    expect(screen.queryByTestId('coverage-count-in_progress')).toBeNull()
  })

  it('shows a rejected requirement as rejected, not in_progress, in the expanded row', async () => {
    const { getByRole } = mount({
      requirements: [
        entry({
          state: 'rejected',
          integration: 'not_applicable',
          accepted_count: 0,
          linked_task_ids: [],
        }),
      ],
      diagnostics: [],
      totals: { rejected: 1 },
      integration: { not_applicable: 1 },
      unserved: [],
    })

    await screen.findByTestId('coverage-count-rejected')
    getByRole('button').click()

    const row = await screen.findByTestId('coverage-row-FR-1')
    expect(row).toHaveTextContent('Rejected')
    expect(row).not.toHaveTextContent('In progress')
  })

  it('turns the task-count into a link that hands back the linked task ids', async () => {
    const onOpenTasks = vi.fn()
    const { getByRole } = mount(
      {
        requirements: [entry({ linked_task_ids: ['task-1', 'task-2'] })],
        diagnostics: [],
        totals: { verified: 1 },
        integration: { integrated: 1 },
        unserved: [],
      },
      onOpenTasks,
    )

    await screen.findByTestId('coverage-count-verified')
    getByRole('button').click()

    const link = await screen.findByTestId('coverage-tasks-link-FR-1')
    expect(link.tagName).toBe('BUTTON')
    link.click()

    expect(onOpenTasks).toHaveBeenCalledWith(['task-1', 'task-2'])
  })

  it('renders the count as plain text, not a link, when there is nowhere to route to', async () => {
    mount({
      requirements: [entry({ linked_task_ids: ['task-1'] })],
      diagnostics: [],
      totals: { verified: 1 },
      integration: { integrated: 1 },
      unserved: [],
    })

    await screen.findByTestId('coverage-count-verified')
    screen.getByRole('button').click()

    const row = await screen.findByTestId('coverage-row-FR-1')
    expect(row).toHaveTextContent('1 task')
    expect(screen.queryByTestId('coverage-tasks-link-FR-1')).toBeNull()
  })

  it('renders nothing at all for a document with no requirements', async () => {
    const { container } = mount({
      requirements: [],
      diagnostics: [],
      totals: {},
      integration: {},
      unserved: [],
    })

    await waitFor(() => expect(container.querySelector('[data-testid="spec-coverage"]')).toBeNull())
  })
})
