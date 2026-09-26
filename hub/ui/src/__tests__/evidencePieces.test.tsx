import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'

/* The operator's evidence decision, on the coverage bar's rows. The fixture is in the order the
 * list route returns — oldest first — so reversing it must move the *latest* label. */

vi.mock('@/hooks/useSSE', () => ({
  useSSEConnectionState: () => 'open',
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

import { EvidencePieces } from '@/components/spec/EvidencePieces'
import { useDecideEvidence } from '@/api/spec'

const PATH = 'spec/changes/demo/spec.html'

function piece(overrides: Record<string, unknown> = {}) {
  return {
    id: 'ev-1',
    summary: 'ran the tests',
    kind: 'test',
    locator: null,
    actor_kind: 'agent',
    actor: 'builder',
    run_id: 'run-1',
    task_id: null,
    review_state: 'awaiting',
    latest_review: null,
    produced_at: '2026-09-26T00:00:00Z',
    footprint: {
      kind: 'git',
      branch: 'task/x',
      commit_sha: 'abcdef0123456789',
      outside_workspace_writes: [],
    },
    ...overrides,
  }
}

let calls: Array<{ url: string; method: string; body: string | null }> = []

function stubHub(pieces: unknown[], decision?: { status: number; body: unknown }) {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, method: init?.method ?? 'GET', body: (init?.body as string) ?? null })
      const isDecision = (init?.method ?? 'GET') === 'POST'
      const status = isDecision && decision ? decision.status : 200
      const payload = isDecision ? (decision?.body ?? piece()) : { evidence: pieces }
      return {
        ok: status < 400,
        status,
        json: async () => payload,
        text: async () => JSON.stringify(payload),
        headers: new Headers({ 'content-type': 'application/json' }),
      }
    }),
  )
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <EvidencePieces path={PATH} identifier="FR-1" />
    </QueryClientProvider>,
  )
}

describe('evidence pieces on a requirement', () => {
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

  it('renders each piece in the route order and labels the last as latest', async () => {
    stubHub([
      piece({ id: 'ev-old', summary: 'first try' }),
      piece({
        id: 'ev-new',
        summary: 'second try',
        footprint: {
          kind: 'git',
          branch: 'task/y',
          commit_sha: '1234567890abcdef',
          outside_workspace_writes: [],
        },
      }),
    ])
    mount()
    const second = await screen.findByTestId('evidence-piece-ev-new')
    expect(second).toHaveTextContent('second try')
    expect(second).toHaveTextContent('builder')
    expect(second).toHaveTextContent('1234567890ab on task/y')
    expect(screen.getByTestId('evidence-piece-ev-old')).toHaveTextContent('abcdef012345 on task/x')
    expect(screen.getByTestId('evidence-latest-ev-new')).toBeInTheDocument()
    expect(screen.queryByTestId('evidence-latest-ev-old')).toBeNull()
    expect(calls[0].url).toContain('identifier=FR-1')
    expect(calls[0].url).toContain(`document=${encodeURIComponent(PATH)}`)
  })

  it('posts an accept for the clicked piece and says what accepting may merge', async () => {
    stubHub([piece()])
    mount()
    await screen.findByTestId('evidence-piece-ev-1')
    expect(screen.getByTestId('evidence-merge-note-ev-1')).toHaveTextContent(
      'may merge commit abcdef012345 into main',
    )
    fireEvent.click(screen.getByText('Accept'))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    const post = calls.find((c) => c.method === 'POST')!
    expect(post.url).toContain('/spec/evidence/ev-1/decision')
    expect(JSON.parse(post.body!)).toEqual({ decision: 'accepted', reason: '' })
  })

  it('carries no merge sentence for a piece with no commit or one already decided', async () => {
    stubHub([
      piece({
        id: 'ev-paths',
        footprint: { kind: 'paths', branch: null, commit_sha: null, outside_workspace_writes: null },
      }),
      piece({
        id: 'ev-done',
        review_state: 'accepted',
        latest_review: { decision: 'accepted', reason: 'fine', actor_kind: 'operator', actor: 'operator' },
      }),
    ])
    mount()
    await screen.findByTestId('evidence-piece-ev-paths')
    expect(screen.queryByTestId('evidence-merge-note-ev-paths')).toBeNull()
    expect(screen.queryByTestId('evidence-merge-note-ev-done')).toBeNull()
    expect(screen.getByTestId('evidence-piece-ev-done')).toHaveTextContent(
      'accepted by operator: fine',
    )
  })

  it('needs a reason to reject, and posts it', async () => {
    stubHub([piece()])
    mount()
    await screen.findByTestId('evidence-piece-ev-1')
    fireEvent.click(screen.getByText('Reject…'))
    const reject = screen.getByText('Reject')
    expect(reject).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Reason for rejecting'), {
      target: { value: 'wrong tree' },
    })
    expect(reject).not.toBeDisabled()
    fireEvent.click(reject)
    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    expect(JSON.parse(calls.find((c) => c.method === 'POST')!.body!)).toEqual({
      decision: 'rejected',
      reason: 'wrong tree',
    })
  })

  it('renders the refusal beside the piece and keeps Accept', async () => {
    stubHub([piece()], {
      status: 409,
      body: { detail: { code: 'recording_run_live', message: 'It is still being recorded.' } },
    })
    mount()
    await screen.findByTestId('evidence-piece-ev-1')
    fireEvent.click(screen.getByText('Accept'))
    expect(await screen.findByTestId('evidence-error-ev-1')).toHaveTextContent(
      'It is still being recorded.',
    )
    expect(screen.getByText('Accept')).toBeInTheDocument()
  })

  it('greys a piece whose recording run is live', async () => {
    stubHub([piece({ recording_run_live: true })])
    mount()
    expect(await screen.findByTestId('evidence-held-ev-1')).toHaveTextContent(
      'still being recorded by run run-1',
    )
    expect(screen.getByText('Accept')).toBeDisabled()
    expect(screen.getByText('Reject…')).toBeDisabled()
  })

  it('invalidates coverage, evidence and the task keys when a decision lands', async () => {
    stubHub([piece()])
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const spy = vi.spyOn(client, 'invalidateQueries')
    function Probe() {
      const decide = useDecideEvidence(PATH, 'FR-1')
      return (
        <button onClick={() => decide.mutate({ id: 'ev-1', decision: 'accepted', reason: '' })}>
          go
        </button>
      )
    }
    render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    )
    fireEvent.click(screen.getByText('go'))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    const keys = spy.mock.calls.map((c) =>
      JSON.stringify((c[0] as { queryKey: unknown[] }).queryKey),
    )
    expect(keys).toEqual(
      expect.arrayContaining([
        JSON.stringify(['project', 'proj-a', 'specCoverage']),
        JSON.stringify(['project', 'proj-a', 'specEvidence', PATH, 'FR-1']),
        JSON.stringify(['project', 'proj-a', 'task']),
        JSON.stringify(['project', 'proj-a', 'tasks']),
      ]),
    )
  })
})
