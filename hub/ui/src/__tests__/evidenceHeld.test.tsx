import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, cleanup, within, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'

/* K (`each-piece-of-evidence-is-judged-on-its-own`): a send-back rejects only the pieces it names as
 * failing and holds the rest. A held piece must read as held -- its own state, reason and decider --
 * never as a rejection. The fixture is the list route's payload (`spec._evidence_view`'s keys), in
 * its order: oldest first. Two send-backs of the same task: the first named this requirement's piece
 * as failing (R3), the second sent the work back for lint and named nothing, holding it (S). */

vi.mock('@/hooks/useSSE', () => ({
  useSSEConnectionState: () => 'open',
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

import { EvidencePieces } from '@/components/spec/EvidencePieces'
import { EvidenceReviews } from '@/components/evidence/EvidenceProof'

const PATH = 'spec/changes/demo/spec.json'
const R3 = 'the test asserts the count, not the order FR-3 requires'
const S = 'lint fails'

function routePiece(id: string, state: string, review: { decision: string; reason: string } | null, sha: string) {
  return {
    recording_run_live: false,
    id,
    requirement_id: 'spreq-3',
    digest: 'd3',
    kind: 'test_result',
    locator: '',
    summary: `ran the test for FR-3 at ${sha.slice(0, 7)}`,
    actor_kind: 'agent',
    actor: 'builder',
    run_id: 'run-b',
    task_id: 'task-k',
    review_state: state,
    latest_review: review
      ? { ...review, actor_kind: 'agent', actor: 'reviewer', created_at: '2026-10-27T10:00:00+00:00' }
      : null,
    artifact_removed: false,
    produced_at: '2026-10-27T09:00:00+00:00',
    footprint: { kind: 'git', branch: 'agentweave/task/task-k', commit_sha: sha, outside_workspace_writes: [] },
    command: null,
    output: null,
    covers: null,
    requirement: null,
    superseded_by: null,
    for_current_wording: true,
  }
}

const PAYLOAD = {
  evidence: [
    routePiece('ev-first', 'rejected', { decision: 'rejected', reason: R3 }, 'aaaaaaaaaaaa1111'),
    routePiece('ev-second', 'held', { decision: 'held', reason: S }, 'bbbbbbbbbbbb2222'),
  ],
}

let calls: Array<{ url: string; method: string; body: string }> = []

function posts() {
  return calls.filter((call) => call.method === 'POST')
}

function stubHub() {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, method: init?.method ?? 'GET', body: (init?.body as string) ?? '' })
      const payload = (init?.method ?? 'GET') === 'POST' ? PAYLOAD.evidence[1] : PAYLOAD
      return {
        ok: true,
        status: 200,
        json: async () => payload,
        text: async () => JSON.stringify(payload),
        headers: new Headers({ 'content-type': 'application/json' }),
      }
    }),
  )
}

describe('a held piece of evidence', () => {
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

  it('reads as held with its own reason and decider, distinct from the rejected one', async () => {
    stubHub()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <EvidencePieces path={PATH} identifier="FR-3" />
      </QueryClientProvider>,
    )

    const held = await screen.findByTestId('evidence-piece-ev-second')
    const rejected = screen.getByTestId('evidence-piece-ev-first')
    expect(screen.getByTestId('evidence-outcome-ev-second')).toHaveAttribute('data-state', 'held')
    expect(screen.getByTestId('evidence-outcome-ev-first')).toHaveAttribute('data-state', 'rejected')
    expect(held).toHaveTextContent(`held by reviewer: ${S}`)
    expect(screen.getByTestId('evidence-outcome-ev-second')).toHaveTextContent(/^held$/)
    expect(held).not.toHaveTextContent(/rejected by/)
    expect(rejected).toHaveTextContent(`rejected by reviewer: ${R3}`)
    expect(screen.getByTestId('evidence-held-at-commit-ev-second')).toHaveTextContent(
      'records it again at the next commit',
    )
    expect(screen.queryByTestId('evidence-held-at-commit-ev-first')).toBeNull()
    // The latest label follows the route's order: the held piece is the newer one.
    expect(screen.getByTestId('evidence-latest-ev-second')).toBeInTheDocument()
    // A held piece is not a decision to overturn; the rejected one is.
    expect(within(held).queryByText('Overturn…')).toBeNull()
    expect(within(rejected).getByText('Overturn…')).toBeInTheDocument()
  })

  it('offers the operator Accept, and Reject with a reason, on a held piece', async () => {
    stubHub()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <EvidencePieces path={PATH} identifier="FR-3" />
      </QueryClientProvider>,
    )
    const held = await screen.findByTestId('evidence-piece-ev-second')
    expect(within(held).getByText('Accept')).toBeInTheDocument()
    fireEvent.click(within(held).getByText('Reject…'))
    const reject = within(held).getByText('Reject')
    expect(reject).toBeDisabled()
    fireEvent.change(within(held).getByLabelText('Reason for rejecting'), {
      target: { value: 'it never ran' },
    })
    fireEvent.click(reject)
    await waitFor(() => expect(posts()).toHaveLength(1))
    expect(posts()[0].url).toContain('/spec/evidence/ev-second/decision')
    expect(JSON.parse(posts()[0].body)).toEqual({ decision: 'rejected', reason: 'it never ran' })
    // The rejected piece is a decision: it still offers Overturn, not Accept.
    const rejected = screen.getByTestId('evidence-piece-ev-first')
    expect(within(rejected).queryByText('Accept')).toBeNull()
  })

  it('is never shown as a rejection in a piece’s review history', () => {
    render(
      <EvidenceReviews
        reviews={[
          { decision: 'rejected', actor_kind: 'agent', actor: 'reviewer', reason: R3, at: '2026-10-27T10:00:00Z' },
          { decision: 'held', actor_kind: 'agent', actor: 'reviewer', reason: S, at: '2026-10-27T11:00:00Z' },
        ]}
      />,
    )
    const held = screen.getByTestId('evidence-review-held')
    expect(held).toHaveTextContent(`Held by reviewer — ${S}`)
    expect(held).not.toHaveTextContent('Rejected')
    expect(screen.getByText(`Rejected by reviewer`)).toBeInTheDocument()
  })
})
