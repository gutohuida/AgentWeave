import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'

/* The rigor control.
 *
 * Two properties. It is visibly not the phase control — they answer different questions and an
 * operator reading one will assume the other. And a refused promotion says *what* is wrong: a
 * document that cannot be read cannot be enforced, and "refused" alone leaves the operator guessing
 * among several possible causes.
 */

vi.mock('@/hooks/useSSE', () => ({
  // The rail's live dot reads this; a whole-module mock has to carry it or Sidebar throws.
  useSSEConnectionState: () => 'open',
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'

const PATH = 'spec/changes/demo/spec.html'

function document_(overrides: Record<string, unknown> = {}) {
  return {
    id: 'spdoc-1',
    path: PATH,
    title: 'Demo',
    kind: 'change-spec',
    phase: 'approved',
    rigor: 'sketch',
    content_digest: 'abc123',
    explore_closed: true,
    updated_at: '2026-08-13T00:00:00+00:00',
    ...overrides,
  }
}

let posted: Array<{ url: string; body: unknown }> = []

function mount(record: Record<string, unknown>, postResponse?: { ok: boolean; text: string }) {
  posted = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options: RequestInit = {}) => {
      if ((options.method ?? 'GET') === 'POST') {
        posted.push({ url, body: JSON.parse(String(options.body)) })
        const response = postResponse ?? { ok: true, text: JSON.stringify(record) }
        return {
          ok: response.ok,
          status: response.ok ? 200 : 409,
          json: async () => JSON.parse(response.text),
          text: async () => response.text,
          headers: new Headers({ 'content-type': 'application/json' }),
        }
      }
      // The phase bar also asks for the loops (to find the document's flow); a real route answers
      // that with a list, and this test has no flows. And for the rigor history, which here has
      // nothing in it.
      const payload = url.includes('/loops')
        ? []
        : url.includes('/rigor-history')
          ? { events: [] }
          : { documents: [record] }
      return {
        ok: true,
        status: 200,
        json: async () => payload,
        text: async () => JSON.stringify(payload),
        headers: new Headers({ 'content-type': 'application/json' }),
      }
    }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecPhaseBar path={PATH} />
    </QueryClientProvider>,
  )
}

/** A rigor change is confirmed, not posted on change (design D2); a promotion needs no reason. */
async function choose(rigor: string) {
  fireEvent.change(await screen.findByTestId('spec-rigor'), { target: { value: rigor } })
  fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }))
}

describe('setting a document rigor', () => {
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

  it('shows the rigor the document carries, separately from its phase', async () => {
    mount(document_({ rigor: 'gate', phase: 'approved' }))

    const control = (await screen.findByTestId('spec-rigor')) as HTMLSelectElement
    expect(control.value).toBe('gate')
    expect(screen.getByTestId('spec-phase')).toHaveTextContent('approved')
  })

  it('sends the digest it read, so the change cannot land on an edited document', async () => {
    mount(document_())

    await choose('gate')

    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0].url).toContain('/rigor')
    expect(posted[0].body).toMatchObject({ rigor: 'gate', reason: '', expected_digest: 'abc123' })
  })

  it('says what is wrong when a promotion is refused', async () => {
    mount(document_(), {
      ok: false,
      text: JSON.stringify({
        detail: {
          code: 'document_not_enforceable',
          message: 'this document cannot be enforced as it stands',
          blocking: ['these requirements hold no identifier yet: alpha'],
        },
      }),
    })

    await choose('gate')

    const refusal = await screen.findByTestId('spec-rigor-refusal')
    expect(refusal).toHaveTextContent('hold no identifier yet: alpha')
  })

  it('still shows something readable when the refusal is not structured', async () => {
    mount(document_(), { ok: false, text: 'the document changed since you read it' })

    await choose('gate')

    const refusal = await screen.findByTestId('spec-rigor-refusal')
    expect(refusal).toHaveTextContent('the document changed since you read it')
  })
})
