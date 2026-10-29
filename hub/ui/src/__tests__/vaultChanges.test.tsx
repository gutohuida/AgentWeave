import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { VaultScreen } from '@/components/vault/VaultScreen'
import { Toaster } from '@/components/ui/toast'
import { useToastStore } from '@/lib/toast'
import { useConfigStore } from '@/store/configStore'

/** `vault-sources-can-be-edited-replaced-and-archived`, FR-6 and FR-13 (ac-tab-component): the tab's
 *  Edit, Replace, Archive and Restore, the changes, the marks on facts, and a refusal's reason. */

const TEXT = {
  id: 'src-txttxttxttx', name: 'Problems', type: 'note', kind: 'source', media_type: 'text/plain',
  visibility: 'tracked', created_at: '2026-10-12T10:00:00.000000Z', holder: null, available: true,
  opening: 'F-1 the map is slow: open',
}
const PDF = {
  id: 'src-pdfpdfpdfpdf', name: 'Contract', type: 'document', kind: 'source', media_type: 'application/pdf',
  visibility: 'tracked', created_at: '2026-10-12T09:00:00.000000Z', holder: null, available: true,
  opening: 'Page 1.',
}
const fact = (id: string, claim: string, extra: object = {}) => ({
  id, name: claim, type: 'fact', kind: 'fact', visibility: 'tracked', created_at: '2026-10-12T10:05:00.000000Z',
  holder: null, available: true, opening: claim, sources: [TEXT.id], disputed: false, presumed: false,
  superseded_by: null, superseded_at: null, stale: false, ...extra,
})
const SUPERSEDED = fact('fct-superseded1', 'F-1 is open', { superseded_by: TEXT.id, superseded_at: '2026-10-13T10:00:00Z' })
const STALE = fact('fct-stale000001', 'F-2 is open', { stale: true })
const ARCHIVED = {
  id: 'src-oldoldoldold', name: 'Old notes', type: 'note', kind: 'source', media_type: 'text/plain',
  visibility: 'tracked', created_at: '2026-10-01T10:00:00.000000Z', holder: null, available: true,
  opening: 'Old.', archived: true, archived_at: '2026-10-14T10:00:00Z',
}
const CHANGES = [
  { action: 'edit', at: '2026-10-13T10:00:00Z', by: { kind: 'operator' } },
  { action: 'edit', at: '2026-10-13T11:00:00Z', by: { kind: 'agent', agent: 'Scout', run_id: 'run-1' } },
]
const SETTINGS = { private_location: null, effective_private_location: 'C:/v', default_visibility: 'tracked' }

type Routed = { status: number; body: unknown; type?: string }
let vault: (url: string, init?: RequestInit) => Routed | undefined
const calls: Array<{ url: string; method: string; init?: RequestInit }> = []

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  calls.length = 0
  useToastStore.setState({ items: [] })
  useConfigStore.setState({ apiKey: 'aw_live_test', hubUrl: 'http://hub', isConfigured: true, selectedProjectId: 'proj-a' })
  vault = (url, init) => {
    if (url.endsWith('/vault/map')) return { status: 200, body: { entries: [PDF, STALE, SUPERSEDED, TEXT] } }
    if (url.endsWith('/vault/settings')) return { status: 200, body: SETTINGS }
    if (url.endsWith('/vault/archived')) return { status: 200, body: { sources: [ARCHIVED] } }
    if (url.includes('/vault/entries/src-txttxttxttx')) {
      return {
        status: 200,
        body: { ...TEXT, content: 'F-1 the map is slow: open\n', next_offset: null, note: null, version: 'v1', stale: true, changes: CHANGES },
      }
    }
    if (url.includes('/vault/entries/src-pdfpdfpdfpdf')) {
      return { status: 200, body: { ...PDF, content: 'Page 1\n', next_offset: null, note: null, version: 'v1', changes: [] } }
    }
    if (url.endsWith('/vault/sources/src-pdfpdfpdfpdf/file')) return { status: 200, body: '%PDF-1.4', type: 'application/pdf' }
    if (init?.method === 'PUT' && url.endsWith('/text')) {
      return { status: 409, body: { detail: 'The source changed since it was opened; read it again.' } }
    }
    if (init?.method === 'POST' && url.endsWith('/restore')) return { status: 200, body: ARCHIVED }
    return undefined
  }
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, method: init?.method ?? 'GET', init })
      const { status, body, type } = vault(url, init) ?? { status: 404, body: { detail: 'Not Found' } }
      return Promise.resolve(
        type
          ? new Response(body as string, { status, headers: { 'Content-Type': type } })
          : new Response(JSON.stringify(body), { status }),
      )
    }),
  )
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:http://hub/f'), revokeObjectURL: vi.fn() })
})

afterEach(() => {
  vi.unstubAllGlobals()
  Reflect.deleteProperty(URL, 'createObjectURL')
  Reflect.deleteProperty(URL, 'revokeObjectURL')
})

describe('the Vault tab, changing and archiving sources', () => {
  it('shows Edit on a text source, Replace on a file source and Archive on both', async () => {
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-txttxttxttx'))
    expect(await screen.findByTestId('vault-edit')).toBeInTheDocument()
    expect(screen.getByTestId('vault-archive')).toBeInTheDocument()
    expect(screen.queryByTestId('vault-replace')).toBeNull()
    fireEvent.click(screen.getByTestId('vault-entry-src-pdfpdfpdfpdf'))
    expect(await screen.findByTestId('vault-replace')).toBeInTheDocument()
    expect(screen.getByTestId('vault-archive')).toBeInTheDocument()
    expect(screen.queryByTestId('vault-edit')).toBeNull()
  })

  it('lists the archived source apart, with Restore, which posts to the restore route', async () => {
    render(<VaultScreen />, { wrapper })
    const archived = await screen.findByTestId('vault-archived')
    expect(archived).toHaveTextContent('Old notes')
    fireEvent.click(screen.getByTestId('vault-restore-src-oldoldoldold'))
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/vault/sources/src-oldoldoldold/restore'))).toBe(true),
    )
  })

  it("marks the superseded and the stale fact, and lists the source's changes", async () => {
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-txttxttxttx'))
    const changes = await screen.findByTestId('vault-changes')
    expect(changes.querySelectorAll('li')).toHaveLength(2)
    expect(changes).toHaveTextContent('by the operator')
    expect(changes).toHaveTextContent('by Scout')
    fireEvent.click(screen.getByRole('radio', { name: /Facts/ }))
    expect(await screen.findByTestId('vault-superseded-fct-superseded1')).toHaveTextContent('its source was changed')
    expect(screen.getByTestId('vault-stale-fct-stale000001')).toHaveTextContent('Stale')
  })

  it("sends the version read with an edit, and shows the Hub's reason when it is refused", async () => {
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-txttxttxttx'))
    await waitFor(() => expect(screen.getByTestId('vault-edit')).toBeEnabled())
    fireEvent.click(screen.getByTestId('vault-edit'))
    fireEvent.change(screen.getByTestId('vault-edit-text'), { target: { value: 'F-1 the map is slow: cleared\n' } })
    fireEvent.click(screen.getByTestId('vault-edit-save'))
    expect(await screen.findByTestId('vault-refusal')).toHaveTextContent('The source changed since it was opened')
    const put = calls.find((c) => c.method === 'PUT')!
    expect(JSON.parse(String(put.init?.body))).toEqual({ content: 'F-1 the map is slow: cleared\n', version: 'v1' })
    // The draft stays, to try again.
    expect(screen.getByTestId('vault-edit-text')).toHaveValue('F-1 the map is slow: cleared\n')
  })
})
