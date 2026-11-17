import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { SpecPage } from '@/components/spec/SpecPage'
import { orderStarts } from '@/api/corpusStart'

/* `a-project-with-no-specs-is-offered-a-start`, task `ui` (FR-2, FR-4, FR-5): the offer in the real
 * Spec page mount, fed by a stubbed `fetch` answering the corpus read and the start route with the
 * shapes `hub/hub/corpus_start.py` returns. The live drive (`scripts/drive/corpus_start_drive.py`)
 * is what shows it on a trial Hub; this pins the page's own decisions. */

vi.mock('@/hooks/useSSE', () => ({
  useSSEConnectionState: () => 'open',
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

const goTo = vi.fn()
vi.mock('@/lib/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/navigation')>()),
  goTo: (d: unknown) => goTo(d),
}))

const MAP = 'spec/changes/system-map/spec.json'

interface Corpus {
  empty: boolean
  has_code: boolean
  recommended: 'existing-code' | 'greenfield' | null
  starts: string[]
  agents: { name: string; charter: string | null }[]
  preselected_agent: string | null
  document: string | null
  unadopted: string[]
}

let corpus: Corpus
let documents: string[]
let posts: { url: string; body: unknown }[]
/** Run before the start answers: what a live event does when it lands first. */
let beforeAnswer: (() => Promise<void>) | null
let queryClient: QueryClient

const emptyWithCode = (): Corpus => ({
  empty: true,
  has_code: true,
  recommended: 'existing-code',
  starts: ['existing-code', 'greenfield'],
  agents: [
    { name: 'Alpha', charter: null },
    { name: 'Bravo', charter: 'Spec Author' },
  ],
  preselected_agent: 'Bravo',
  document: null,
  unadopted: [],
})

function route(url: string, init?: RequestInit): { status: number; body: unknown } | undefined {
  const u = new URL(url, 'http://hub.test')
  const p = u.pathname.replace(/^\/api\/v1\/projects\/[^/]+/, '')
  if (p === '/project/corpus/start' && init?.method === 'POST') {
    posts.push({ url, body: JSON.parse(String(init.body)) })
    const { start, agent } = JSON.parse(String(init.body))
    return {
      status: 200,
      body: {
        state: 'queued',
        start,
        agent,
        document: { id: 'spdoc-map', path: MAP, kind: 'system-map', title: 'System map', phase: 'exploring' },
        conversation_id: 'conv-new',
        entry_id: 'inb-1',
      },
    }
  }
  if (p === '/project/corpus') return { status: 200, body: corpus }
  if (p === '/project/specs')
    return {
      status: 200,
      body: {
        specs: documents.map((path, i) => ({ path, title: 'Some change', kind: 'change-spec', state: 'filed', parent: null, order: i, document_id: `id-${i}`, phase: 'exploring' })),
        home: null,
        manifest: { state: 'valid', version: 1 },
        missing: [],
        diagnostics: [],
      },
    }
  if (p === '/project/documents')
    return {
      status: 200,
      body: {
        documents: documents.map((path, i) => ({
          id: `id-${i}`, path, title: 'Some change', kind: 'change-spec', phase: 'exploring', rigor: 'contract', content_digest: null, explore_closed: false, updated_at: '2026-11-17T09:00:00Z',
        })),
      },
    }
  if (p === '/tasks') return { status: 200, body: { tasks: [], total: 0, has_more: false } }
  if (p === '/loops') return { status: 200, body: [] }
  return undefined
}

function openSpecTab(onAddAgent?: () => void) {
  cleanup()
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <SpecPage document={null} onOpenDocument={() => {}} onAddAgent={onAddAgent} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  cleanup()
  localStorage.clear()
  goTo.mockReset()
  corpus = emptyWithCode()
  documents = []
  posts = []
  beforeAnswer = null
  useConfigStore.setState({ apiKey: 'aw_live_TESTKEY', hubUrl: 'http://hub.test', selectedProjectId: 'proj-p', isConfigured: true, bootstrapState: 'ready', mode: 'light' })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && beforeAnswer) await beforeAnswer()
      const answer = route(url, init)
      if (answer === undefined) return new Response(JSON.stringify({ detail: 'not stubbed' }), { status: 404 })
      return new Response(JSON.stringify(answer.body), { status: answer.status, headers: { 'Content-Type': 'application/json' } })
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

const options = (offer: HTMLElement) =>
  within(offer).getAllByTestId('corpus-start-option').map((o) => [o.getAttribute('data-start'), o.getAttribute('data-recommended')])

describe('an empty corpus is offered a start on the Spec tab', () => {
  it('ac-spec-tab-offer: both starts, existing code first and marked recommended, in place of the empty page', async () => {
    openSpecTab()
    const offer = await screen.findByTestId('corpus-start-offer')
    expect(options(offer)).toEqual([
      ['existing-code', 'true'],
      ['greenfield', 'false'],
    ])
    expect(within(within(offer).getAllByTestId('corpus-start-option')[0]).getByText('Recommended')).toBeTruthy()
    expect(within(within(offer).getAllByTestId('corpus-start-option')[1]).queryByText('Recommended')).toBeNull()
    const page = screen.getByTestId('spec-page')
    expect(page.textContent).not.toContain('No documents match.')
    expect(page.textContent).not.toContain('No specification yet')
  })

  it('an empty folder recommends greenfield, and so offers it first', async () => {
    corpus = { ...emptyWithCode(), has_code: false, recommended: 'greenfield' }
    openSpecTab()
    const offer = await screen.findByTestId('corpus-start-offer')
    expect(options(offer)).toEqual([
      ['greenfield', 'true'],
      ['existing-code', 'false'],
    ])
  })

  it('a corpus that is not empty (spec files awaiting adoption) is offered nothing', async () => {
    corpus = { ...emptyWithCode(), empty: false, recommended: null, starts: [], document: 'spec/changes/x/spec.json', unadopted: ['spec/changes/x/spec.json'] }
    openSpecTab()
    await screen.findByText('No specification yet')
    expect(screen.queryByTestId('corpus-start-offer')).toBeNull()
  })

  it('a corpus read that fails says so, rather than passing for a corpus with nothing to offer', async () => {
    const stubbed = vi.mocked(fetch).getMockImplementation()!
    vi.mocked(fetch).mockImplementation(async (url, init) =>
      new URL(String(url), 'http://hub.test').pathname.endsWith('/project/corpus')
        ? new Response(JSON.stringify({ detail: 'corpus unreadable' }), { status: 500, headers: { 'Content-Type': 'application/json' } })
        : stubbed(url, init),
    )
    openSpecTab()
    await waitFor(() => expect(screen.getByTestId('spec-page').textContent).toContain('could not say how this project could start'))
    expect(screen.queryByTestId('corpus-start-offer')).toBeNull()
  })

  it('a project with documents shows its list and no offer, even if the corpus read is stale', async () => {
    documents = ['spec/changes/one/spec.json']
    openSpecTab()
    await waitFor(() => expect(screen.getAllByText('Some change').length).toBeGreaterThan(0))
    expect(screen.queryByTestId('corpus-start-offer')).toBeNull()
  })
})

describe('taking a start asks which agent (FR-4) and opens its conversation (FR-5)', () => {
  it('ac-agent-choice: the Spec Author is preselected and the other open agent can be chosen', async () => {
    openSpecTab()
    const offer = await screen.findByTestId('corpus-start-offer')
    expect(within(offer).queryByTestId('corpus-start-agent')).toBeNull()
    const existing = within(offer).getAllByTestId('corpus-start-option')[0]
    fireEvent.click(within(existing).getByTestId('corpus-start-take'))
    const picker = within(existing).getByTestId('corpus-start-agent') as HTMLSelectElement
    expect(picker.value).toBe('Bravo')
    expect(Array.from(picker.options).map((o) => o.value)).toEqual(['Alpha', 'Bravo'])
  })

  it('ac-preselect-fallback: the picker takes the Hub\'s preselection, the first open agent when none is a lone Spec Author', async () => {
    corpus = { ...emptyWithCode(), agents: [{ name: 'Alpha', charter: 'Spec Author' }, { name: 'Bravo', charter: 'Spec Author' }], preselected_agent: 'Alpha' }
    openSpecTab()
    const offer = await screen.findByTestId('corpus-start-offer')
    fireEvent.click(within(within(offer).getAllByTestId('corpus-start-option')[1]).getByTestId('corpus-start-take'))
    expect((screen.getByTestId('corpus-start-agent') as HTMLSelectElement).value).toBe('Alpha')
  })

  it('ac-start-existing: confirming posts the choice in the body and goes to the new conversation', async () => {
    openSpecTab()
    const offer = await screen.findByTestId('corpus-start-offer')
    const existing = within(offer).getAllByTestId('corpus-start-option')[0]
    fireEvent.click(within(existing).getByTestId('corpus-start-take'))
    fireEvent.change(within(existing).getByTestId('corpus-start-agent'), { target: { value: 'Alpha' } })
    fireEvent.click(within(existing).getByTestId('corpus-start-confirm'))
    await waitFor(() => expect(goTo).toHaveBeenCalled())
    expect(posts).toHaveLength(1)
    expect(new URL(posts[0].url, 'http://hub.test').search).toBe('')
    expect(posts[0].body).toEqual({ start: 'existing-code', agent: 'Alpha' })
    expect(goTo).toHaveBeenCalledWith({ kind: 'conversation', projectId: 'proj-p', agent: 'Alpha', conversationId: 'conv-new', document: MAP })
  })

  it('goes to the conversation even when the document reaches the list before the start answers', async () => {
    beforeAnswer = async () => {
      documents = [MAP]
      await queryClient.refetchQueries()
      await waitFor(() => expect(screen.queryByTestId('corpus-start-offer')).toBeNull())
    }
    openSpecTab()
    const offer = await screen.findByTestId('corpus-start-offer')
    const existing = within(offer).getAllByTestId('corpus-start-option')[0]
    fireEvent.click(within(existing).getByTestId('corpus-start-take'))
    fireEvent.click(within(existing).getByTestId('corpus-start-confirm'))
    await waitFor(() => expect(goTo).toHaveBeenCalledWith(expect.objectContaining({ kind: 'conversation', agent: 'Bravo', conversationId: 'conv-new' })))
  })

  it('ac-agent-choice (no agent): no start control, and a way to add an agent', async () => {
    corpus = { ...emptyWithCode(), agents: [], preselected_agent: null }
    const onAddAgent = vi.fn()
    openSpecTab(onAddAgent)
    const offer = await screen.findByTestId('corpus-start-offer')
    expect(within(offer).getAllByTestId('corpus-start-option')).toHaveLength(2)
    expect(within(offer).queryByTestId('corpus-start-take')).toBeNull()
    expect(within(offer).queryByTestId('corpus-start-confirm')).toBeNull()
    fireEvent.click(within(offer).getByTestId('corpus-start-add-agent'))
    expect(onAddAgent).toHaveBeenCalledTimes(1)
  })
})

describe('orderStarts', () => {
  it('puts the recommended start first and leaves the rest in order', () => {
    expect(orderStarts(['existing-code', 'greenfield'], 'greenfield')).toEqual(['greenfield', 'existing-code'])
    expect(orderStarts(['existing-code', 'greenfield'], 'existing-code')).toEqual(['existing-code', 'greenfield'])
    expect(orderStarts(['existing-code', 'greenfield'], null)).toEqual(['existing-code', 'greenfield'])
  })
})

