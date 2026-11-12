import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FoldIntoCapabilityDialog } from '@/components/spec/FoldIntoCapabilityDialog'
import { ChangeCapabilities } from '@/components/spec/ChangeCapabilities'
import { CapabilityWaitingList } from '@/components/spec/CapabilityWaitingList'
import { SpecDocList } from '@/components/spec/page/SpecDocList'
import { listEntries } from '@/components/spec/page/adapt'
import type { ListPreferences } from '@/components/spec/page/model'
import type { SpecDocumentRecord } from '@/api/spec'
import { useConfigStore } from '@/store/configStore'

/**
 * `a-change-names-the-capabilities-it-changes`, the app half: every element of the CONTRACT's
 * test-id list exists and carries what the Hub returned, through the real hooks. Only `fetch` is
 * stubbed.
 */
const ALPHA = 'spec/capabilities/alpha/spec.json'
const GAMMA = 'spec/capabilities/gamma/spec.json'
const BETA = 'spec/capabilities/beta-things/spec.json'
const CHANGE = 'spec/changes/one/spec.json'

function record(overrides: Record<string, unknown>): SpecDocumentRecord {
  return {
    id: 'spdoc-x',
    updated_at: '2026-11-12T00:00:00Z',
    explore_closed: true,
    content_digest: null,
    ...overrides,
  } as SpecDocumentRecord
}

const alpha = record({
  id: 'cap-alpha',
  path: ALPHA,
  title: 'Alpha',
  kind: 'capability',
  phase: 'current',
  waiting_count: 2,
  waiting_changes: [
    { path: 'spec/changes/built/spec.json', title: 'Built one', phase: 'approved', built: true, first_approved_at: '2026-11-01T00:00:00Z' },
    { path: 'spec/changes/unbuilt/spec.json', title: 'Unbuilt one', phase: 'approved', built: false, first_approved_at: '2026-11-02T00:00:00Z' },
  ],
})
const gamma = record({ id: 'cap-gamma', path: GAMMA, title: 'Gamma', kind: 'capability', phase: 'current', waiting_count: 0, waiting_changes: [] })
const change = (capabilities: unknown, extra: Record<string, unknown> = {}) =>
  record({ id: 'chg', path: CHANGE, title: 'Change one', kind: 'change-spec', phase: 'approved', capabilities, folded_into: null, ...extra })

let documents: unknown[]
let puts: { url: string; body: unknown }[]
let posts: { url: string; body: unknown }[]

function reply(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

beforeEach(() => {
  puts = []
  posts = []
  documents = []
  useConfigStore.setState({ isConfigured: true, selectedProjectId: 'proj-1', hubUrl: '', apiKey: 'k' })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        puts.push({ url, body: JSON.parse(String(init.body)) })
        return reply(200, change({ changes: [GAMMA], creates: [] }))
      }
      if (init?.method === 'POST' && url.endsWith('/project/documents')) {
        const body = JSON.parse(String(init.body))
        posts.push({ url, body })
        documents = [...documents, record({ id: 'new', path: body.path, title: body.title, kind: 'capability', phase: 'current' })]
        return reply(201, { path: body.path, title: body.title })
      }
      if (url.endsWith('/project/documents')) return reply(200, { documents })
      if (url.includes('/fold-draft')) return reply(200, { into: '', payload: {}, requirements: [], algorithms: [], collisions: [] })
      if (url.includes('/project/spec?')) return reply(200, { path: CHANGE, content: '', fold_state: null })
      return reply(200, {})
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

describe('the change page', () => {
  it('lists what the change names, existing and new, in change-capabilities', async () => {
    documents = [alpha, gamma]
    wrap(<ChangeCapabilities record={change({ changes: [ALPHA], creates: [{ title: 'Beta things' }] }) as SpecDocumentRecord} />)
    const list = screen.getByTestId('change-capabilities')
    await waitFor(() => expect(list).toHaveTextContent('Alpha'))
    expect(list).toHaveTextContent('Beta things (new)')
    expect(screen.getByTestId('change-capabilities-edit')).toBeInTheDocument()
  })

  it('sends the edit to the capabilities route with its reason, and offers no edit once folded', async () => {
    documents = [alpha, gamma]
    const { unmount } = wrap(<ChangeCapabilities record={change({ changes: [ALPHA], creates: [] })} />)
    await userEvent.click(screen.getByTestId('change-capabilities-edit'))
    await userEvent.click(await screen.findByTestId(`change-capabilities-pick-${ALPHA}`))
    await userEvent.click(screen.getByTestId(`change-capabilities-pick-${GAMMA}`))
    await userEvent.type(screen.getByTestId('change-capabilities-reason'), 'wrong home')
    await userEvent.click(screen.getByTestId('change-capabilities-save'))
    await waitFor(() => expect(puts).toHaveLength(1))
    expect(puts[0].url).toContain(`/project/documents/${CHANGE}/capabilities`)
    expect(puts[0].body).toEqual({ changes: [GAMMA], creates: [], reason: 'wrong home' })
    unmount()

    wrap(<ChangeCapabilities record={change({ changes: [GAMMA], creates: [] }, { folded_into: GAMMA })} />)
    expect(screen.queryByTestId('change-capabilities-edit')).not.toBeInTheDocument()
    expect(screen.getByTestId('change-capabilities')).toHaveTextContent('folded into')
  })
})

describe('a capability', () => {
  it('shows its waiting list in the order the Hub gave, built on the first only', () => {
    wrap(<CapabilityWaitingList record={alpha} />)
    expect(screen.getByTestId('capability-waiting-list')).toBeInTheDocument()
    const rows = screen.getAllByTestId('capability-waiting-row')
    expect(rows.map((r) => r.getAttribute('data-path'))).toEqual(['spec/changes/built/spec.json', 'spec/changes/unbuilt/spec.json'])
    expect(rows.map((r) => r.getAttribute('data-built'))).toEqual(['true', 'false'])
    // Titles are plain text: nothing on the row looks clickable but does nothing.
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it("shows waiting_count on the spec list's capability rows", () => {
    const prefs: ListPreferences = { query: '', kind: 'capability', phase: 'any', buildingOnly: false, order: 'title' }
    const entries = listEntries(
      [
        { path: ALPHA, title: 'Alpha', document_id: 'cap-alpha' },
        { path: GAMMA, title: 'Gamma', document_id: 'cap-gamma' },
      ] as never,
      [alpha, gamma],
    )
    wrap(<SpecDocList entries={entries} active={null} prefs={prefs} onPrefsChange={vi.fn()} onOpen={vi.fn()} onNew={vi.fn()} now={new Date()} />)
    const counts = screen.getAllByTestId('capability-waiting-count')
    expect(counts.map((c) => [c.getAttribute('data-path'), c.textContent])).toEqual([
      [ALPHA, '2'],
      [GAMMA, '0'],
    ])
  })
})

describe('the fold dialog', () => {
  it('opens on the single capability the change names', async () => {
    documents = [change({ changes: [ALPHA], creates: [] }), alpha, gamma]
    wrap(<FoldIntoCapabilityDialog path={CHANGE} title="Change one" onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('fold-target')).toHaveValue(ALPHA))
    expect(screen.queryByTestId('fold-create-named')).not.toBeInTheDocument()
  })

  it('asks which when the change names several', async () => {
    documents = [change({ changes: [ALPHA, GAMMA], creates: [] }), alpha, gamma]
    wrap(<FoldIntoCapabilityDialog path={CHANGE} title="Change one" onClose={vi.fn()} />)
    await screen.findByTestId('fold-target-ask')
    expect(screen.getByTestId('fold-target')).toHaveValue('')
  })

  it('offers to create the named capability and then targets it', async () => {
    documents = [change({ changes: [], creates: [{ title: 'Beta things' }] }), alpha]
    wrap(<FoldIntoCapabilityDialog path={CHANGE} title="Change one" onClose={vi.fn()} />)
    const offer = await screen.findByTestId('fold-create-named')
    expect(offer).toHaveTextContent('Beta things')
    await userEvent.click(offer)
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].body).toEqual({ path: BETA, title: 'Beta things', kind: 'capability' })
    await waitFor(() => expect(screen.getByTestId('fold-target')).toHaveValue(BETA))
  })

  it('falls back to today\'s picker for a change that names nothing', async () => {
    documents = [change({ changes: [], creates: [] }), alpha]
    wrap(<FoldIntoCapabilityDialog path={CHANGE} title="Change one" onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('fold-target').querySelectorAll('option')).toHaveLength(2))
    expect(screen.getByTestId('fold-target')).toHaveValue('')
  })
})
