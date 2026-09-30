import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecProposalsPanel } from '@/components/spec/SpecProposalsPanel'
import { useConfigStore } from '@/store/configStore'

/**
 * F428: rejecting a proposal in the app left it on screen, with live buttons, until something
 * else refetched. The real mutation and the real query run here; only the HTTP calls are faked.
 */

let pending: Array<Record<string, unknown>> = []
const getJson = vi.fn()
const postJson = vi.fn()

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    getJson: (path: string) => getJson(path),
    postJson: (path: string, body: unknown) => postJson(path, body),
  }
})

const PATH = 'spec/changes/demo/spec.html'

beforeEach(() => {
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-1',
    isConfigured: true,
    bootstrapState: 'ready',
  })
  pending = [
    {
      id: 'spprop-1',
      unit_kind: 'requirement',
      unit_key: 'alpha',
      change_kind: 'modify',
      position_after_key: null,
      proposed_payload: { statement: 'It responds within 100ms' },
      previous_payload: { statement: 'It responds within 200ms' },
      status: 'pending',
      expected_digest: 'd1',
      proposer_actor_kind: 'agent',
      proposer_actor_name: 'claude-1',
      created_at: '2026-09-30T10:00:00Z',
      resolved_at: null,
      resolved_by_actor_name: null,
      resolution_reason: '',
    },
  ]
  getJson.mockReset()
  postJson.mockReset()
  getJson.mockImplementation(async () => ({ proposals: pending }))
  postJson.mockImplementation(async () => {
    pending = []
    return { proposal: { id: 'spprop-1', status: 'rejected' } }
  })
})

describe('a decided proposal leaves the list in the tab that decided it', () => {
  it('drops a rejected row without waiting for another refetch', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <SpecProposalsPanel path={PATH} />
      </QueryClientProvider>,
    )
    await screen.findByTestId('proposal-row-alpha')

    await userEvent.click(screen.getByText('Reject'))
    await userEvent.click(screen.getByText('Confirm reject'))

    await waitFor(() => expect(screen.queryByTestId('proposal-row-alpha')).toBeNull())
  })
})
