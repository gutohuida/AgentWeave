import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { VaultScreen } from '@/components/vault/VaultScreen'
import { useConfigStore } from '@/store/configStore'

/** `the-vault-map-is-shaped-by-what-agents-ask-for`, requirement wiki-counts (task
 *  access-tuning-tab-impl). The map lists `fetches` and `last_fetched_at`; the page shows them and
 *  shows nothing when a Hub that predates them leaves the fields out. */

const READ = {
  id: 'src-readreadread', name: 'Read often', type: 'transcript', kind: 'source', media_type: 'text/plain',
  visibility: 'tracked', created_at: '2026-10-12T10:02:00.000000Z', holder: null, available: true,
  opening: 'Read twice.', fetches: 2, last_fetched_at: '2026-10-12T11:00:00.000000Z',
  // One of the two reads is named (F901, migration 0140); the other predates the record.
  readers: [{ agent: 'Builder', count: 1, last_read_at: '2026-10-12T11:00:00.000000Z' }],
}
const UNREAD = {
  id: 'src-unreadunread', name: 'Never read', type: 'document', kind: 'source', media_type: 'text/plain',
  visibility: 'tracked', created_at: '2026-10-12T10:01:00.000000Z', holder: null, available: true,
  opening: 'Nobody asked.', fetches: 0, last_fetched_at: null,
}
const OLD_HUB = {
  id: 'src-oldhuboldhub', name: 'From an old Hub', type: 'note', kind: 'source', media_type: 'text/plain',
  visibility: 'tracked', created_at: '2026-10-12T10:00:00.000000Z', holder: null, available: true,
  opening: 'No count field.',
}
// A fact is listed under its source, and counted like a source.
const FACT_READ = {
  id: 'fct-readreadread', name: 'Fact read', type: 'note', kind: 'fact', sources: ['src-readreadread'],
  visibility: 'tracked', created_at: '2026-10-12T10:03:00.000000Z', holder: null, available: true,
  opening: 'Refunds up to 450 euros.', fetches: 3, last_fetched_at: '2026-10-12T11:00:00.000000Z',
}
const FACT_UNREAD = {
  id: 'fct-unreadunread', name: 'Fact unread', type: 'note', kind: 'fact', sources: ['src-readreadread'],
  visibility: 'tracked', created_at: '2026-10-12T10:04:00.000000Z', holder: null, available: true,
  opening: 'Shipping is free over 75.', fetches: 0, last_fetched_at: null,
}
const SETTINGS = {
  private_location: null,
  effective_private_location: 'C:/Users/me/.agentweave/hub/vaults/proj-a',
  default_visibility: 'tracked',
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function respond(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

beforeEach(() => {
  useConfigStore.setState({ apiKey: 'aw_live_test', hubUrl: 'http://hub', isConfigured: true, selectedProjectId: 'proj-a' })
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url.endsWith('/vault/map')) return respond(200, { entries: [READ, FACT_READ, FACT_UNREAD, UNREAD, OLD_HUB] })
    if (url.endsWith('/vault/settings')) return respond(200, SETTINGS)
    const entry = [READ, UNREAD, OLD_HUB].find((candidate) => url.includes(`/vault/entries/${candidate.id}`))
    if (entry) return respond(200, { ...entry, content: 'text\n', next_offset: null, note: null })
    return respond(404, { detail: 'Not Found' })
  }))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the Vault tab, agent read counts', () => {
  it('badges an entry agents have read with the count, and leaves the rest bare', async () => {
    render(<VaultScreen />, { wrapper })
    const badge = await screen.findByTestId('vault-fetches-src-readreadread')
    expect(badge).toHaveTextContent(/^Read 2×$/)
    expect(screen.queryByTestId('vault-fetches-src-unreadunread')).toBeNull()
    expect(screen.queryByTestId('vault-fetches-src-oldhuboldhub')).toBeNull()
  })

  it('badges a fact in the fact list of its source, in the map order, and not an unread one', async () => {
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-readreadread'))
    fireEvent.click(await screen.findByRole('radio', { name: /Facts/ }))
    const read = await screen.findByTestId('vault-fetches-fct-readreadread')
    expect(read).toHaveTextContent(/^Read 3×$/)
    expect(screen.queryByTestId('vault-fetches-fct-unreadunread')).toBeNull()
    const facts = screen.getAllByTestId(/^vault-fact-fct-/).map((el) => el.dataset.testid)
    expect(facts).toEqual(['vault-fact-fct-readreadread', 'vault-fact-fct-unreadunread'])
  })

  it('says on the selected entry how many times agents read it', async () => {
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-readreadread'))
    const line = await screen.findByTestId('vault-entry-fetches')
    expect(line).toHaveTextContent('2 times')
    expect(line).not.toHaveTextContent('Not yet')
  })

  it('names the agents that read an entry, and says how many reads predate the record (F901)', async () => {
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-readreadread'))
    await screen.findByTestId('vault-entry-text')
    fireEvent.click(screen.getByRole('radio', { name: 'Used by' }))
    expect(await screen.findByTestId('vault-reader-Builder')).toHaveTextContent('Builder1 time')
    expect(screen.getByTestId('vault-readers-unnamed')).toHaveTextContent('1 earlier read was recorded before')
  })

  it('says a never-read entry has not been read by agents yet', async () => {
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-unreadunread'))
    expect(await screen.findByTestId('vault-entry-fetches')).toHaveTextContent('Not yet')
  })

  it('shows no read line at all when the Hub sends no count', async () => {
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-oldhuboldhub'))
    await screen.findByTestId('vault-entry-text')
    expect(screen.queryByTestId('vault-entry-fetches')).toBeNull()
  })
})
