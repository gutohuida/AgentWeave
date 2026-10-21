import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { VaultScreen } from '@/components/vault/VaultScreen'
import { Toaster } from '@/components/ui/toast'
import { formatDay } from '@/lib/format'
import { useToastStore } from '@/lib/toast'
import { useConfigStore } from '@/store/configStore'

/** `a-vault-the-operator-fills-with-text-and-agents-can-read`, task vault-tab. The routes are
 *  stubbed at `fetch`, so the hooks, their 404 handling and the request bodies are the real ones. */

// Newest first, the order `GET /vault/map` returns.
const ENTRIES = [
  {
    id: 'src-bbbbbbbbbbbb', name: 'Contact habits', type: 'note', visibility: 'private',
    created_at: '2026-10-09T15:02:00.000000Z', holder: 'colleague-laptop', available: false, opening: null,
  },
  {
    id: 'src-aaaaaaaaaaaa', name: 'Acme kickoff', type: 'transcript', visibility: 'tracked',
    created_at: '2026-10-09T15:01:00.000000Z', holder: null, available: true,
    opening: 'Kickoff meeting with Acme Retail.',
  },
]
const SETTINGS = {
  private_location: null,
  effective_private_location: 'C:/Users/me/.agentweave/hub/vaults/proj-a',
  default_visibility: 'private',
}

type Route = (url: string, init?: RequestInit) => { status: number; body: unknown } | undefined
let vault: Route
const sent: Array<{ url: string; method: string; body: unknown }> = []

function respond(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster />
    </QueryClientProvider>
  )
}

/** Choose an option from a menu select: it opens from the keyboard, as Radix triggers do. */
function choose(testId: string, label: string) {
  fireEvent.keyDown(screen.getByTestId(testId), { key: 'Enter' })
  fireEvent.click(screen.getByRole('menuitemradio', { name: new RegExp(`^${label}`) }))
}

/** Open the Add dialog on its paste-text form. */
function openPasteText() {
  fireEvent.click(screen.getByTestId('vault-upload-open'))
  fireEvent.click(screen.getByRole('radio', { name: 'Paste text' }))
}

beforeEach(() => {
  sent.length = 0
  useToastStore.setState({ items: [] })
  useConfigStore.setState({
    apiKey: 'aw_live_test', hubUrl: 'http://hub', isConfigured: true, selectedProjectId: 'proj-a',
  })
  vault = (url) => {
    if (url.endsWith('/vault/map')) return { status: 200, body: { entries: ENTRIES } }
    if (url.endsWith('/vault/settings')) return { status: 200, body: SETTINGS }
    return undefined
  }
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    if (method !== 'GET') sent.push({ url, method, body: JSON.parse(String(init?.body)) })
    const routed = vault(url, init)
    if (routed) return respond(routed.status, routed.body)
    return respond(404, { detail: 'Not Found' })
  }))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the Vault tab', () => {
  it('says the Hub has no vault yet when its routes answer 404', async () => {
    vault = () => undefined
    render(<VaultScreen />, { wrapper })
    expect(await screen.findByTestId('vault-none')).toHaveTextContent('This Hub has no vault yet')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('lists the entries in the order the map returns them, within each kind', async () => {
    // Grouped by kind; inside a kind, the map's order (newest first) is kept. Two notes, so a
    // reversed map would reverse them.
    const older = { ...ENTRIES[0], id: 'src-dddddddddddd', name: 'Older note', available: true, holder: null, opening: 'Older.' }
    const routed = vault
    vault = (url, init) =>
      url.endsWith('/vault/map') ? { status: 200, body: { entries: [ENTRIES[0], ENTRIES[1], older] } } : routed(url, init)
    render(<VaultScreen />, { wrapper })
    await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')
    const rows = screen.getAllByTestId(/^vault-entry-src-/)
    expect(rows.map((row) => row.dataset.testid)).toEqual([
      // Transcripts come before notes.
      'vault-entry-src-aaaaaaaaaaaa',
      'vault-entry-src-bbbbbbbbbbbb',
      'vault-entry-src-dddddddddddd',
    ])
    expect(rows[1]).toHaveTextContent('Held on colleague-laptop')
    expect(rows[0]).toHaveTextContent('Kickoff meeting with Acme Retail.')
  })

  it('says which agent added a source by path, and nothing for the operator\'s own', async () => {
    // `agents-add-files-to-the-vault-by-path`: the map carries added_by, null for an upload.
    const added = { ...ENTRIES[1], id: 'src-cccccccccccc', name: 'inbox/notes.md', added_by: 'alpha' }
    const routed = vault
    vault = (url, init) => {
      if (url.endsWith('/vault/map')) {
        return { status: 200, body: { entries: [added, { ...ENTRIES[1], added_by: null }] } }
      }
      if (url.includes('/vault/entries/src-cccccccccccc?offset=0')) {
        return { status: 200, body: { ...added, content: 'Kickoff.', next_offset: null, note: null } }
      }
      return routed(url, init)
    }
    render(<VaultScreen />, { wrapper })
    expect(await screen.findByTestId('vault-added-by-src-cccccccccccc')).toHaveTextContent('by alpha')
    expect(screen.queryByTestId('vault-added-by-src-aaaaaaaaaaaa')).toBeNull()
    expect(screen.getByTestId('vault-entry-src-aaaaaaaaaaaa')).not.toHaveTextContent('by alpha')
    fireEvent.click(screen.getByTestId('vault-entry-src-cccccccccccc'))
    // The folder is shown above the name, not as part of it.
    const reader = await screen.findByRole('article', { name: 'inbox/notes.md' })
    expect(within(reader).getByRole('heading', { name: 'notes.md' })).toBeInTheDocument()
    expect(reader).toHaveTextContent('inbox/')
    expect(reader).toHaveTextContent('by alpha')
  })

  it('opens an entry and reads every page of its text', async () => {
    const routed = vault
    vault = (url, init) => {
      if (url.includes('/vault/entries/src-aaaaaaaaaaaa?offset=0')) {
        return { status: 200, body: { ...ENTRIES[1], content: 'Dana: the limit is ', next_offset: 19, note: null } }
      }
      if (url.includes('/vault/entries/src-aaaaaaaaaaaa?offset=19')) {
        return { status: 200, body: { ...ENTRIES[1], content: '437 euros.', next_offset: null, note: null } }
      }
      return routed(url, init)
    }
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa'))
    // A transcript reads as turns: the speaker, then what they said.
    const text = await screen.findByTestId('vault-entry-text')
    expect(text).toHaveTextContent('Dana')
    expect(text).toHaveTextContent('the limit is')
    expect(text).not.toHaveTextContent('437 euros.')
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }))
    await waitFor(() => expect(screen.getByTestId('vault-entry-text')).toHaveTextContent('the limit is 437 euros.'))
    expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull()
  })

  it('says whose machine holds a private entry it cannot show', async () => {
    const routed = vault
    vault = (url, init) => {
      if (url.includes('/vault/entries/src-bbbbbbbbbbbb')) {
        return {
          status: 200,
          body: { ...ENTRIES[0], content: null, next_offset: null, note: 'Held on colleague-laptop, not here.' },
        }
      }
      return routed(url, init)
    }
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-bbbbbbbbbbbb'))
    expect(await screen.findByText('Held on colleague-laptop, not here.')).toBeInTheDocument()
    expect(screen.queryByTestId('vault-entry-text')).toBeNull()
  })

  it('uploads with the project default visibility unless changed', async () => {
    const routed = vault
    vault = (url, init) => {
      if (url.endsWith('/vault/sources') && init?.method === 'POST') {
        return { status: 201, body: { ...ENTRIES[1], id: 'src-cccccccccccc', name: 'Rules' } }
      }
      return routed(url, init)
    }
    render(<VaultScreen />, { wrapper })
    await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')
    openPasteText()
    fireEvent.change(screen.getByTestId('vault-upload-name'), { target: { value: 'Rules' } })
    choose('vault-upload-type', 'Rule')
    fireEvent.change(screen.getByTestId('vault-upload-content'), { target: { value: 'Refunds over 437 need a manager.' } })
    expect(screen.getByTestId('vault-upload-visibility')).toHaveTextContent('Private, this machine')
    fireEvent.click(screen.getByTestId('vault-upload-submit'))
    await waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0]).toEqual({
      url: 'http://hub/api/v1/projects/proj-a/vault/sources',
      method: 'POST',
      body: { name: 'Rules', type: 'rules', content: 'Refunds over 437 need a manager.', visibility: 'private' },
    })
    // Added: the dialog closes and says so.
    expect(await screen.findByText('Added “Rules”')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByTestId('vault-upload-submit')).toBeNull())
  })

  it("keeps the dialog and the text when the Hub refuses an upload, and says why", async () => {
    const routed = vault
    vault = (url, init) =>
      url.endsWith('/vault/sources') && init?.method === 'POST'
        ? { status: 400, body: { detail: 'dated must be a day, YYYY-MM-DD.' } }
        : routed(url, init)
    render(<VaultScreen />, { wrapper })
    await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')
    openPasteText()
    fireEvent.change(screen.getByTestId('vault-upload-name'), { target: { value: 'Call' } })
    fireEvent.change(screen.getByTestId('vault-upload-content'), { target: { value: 'Dana: 300.' } })
    fireEvent.click(screen.getByTestId('vault-upload-submit'))
    expect(await screen.findByRole('alert')).toHaveTextContent('dated must be a day')
    expect(screen.getByTestId('vault-upload-content')).toHaveValue('Dana: 300.')
  })

  // `the-manager-distils-vault-sources-into-cited-facts`, task tab-facts. The map lists each
  // source followed by its facts, as `GET /vault/map` returns them.
  const SOURCE = { ...ENTRIES[1], kind: 'source' }
  const REFUND = {
    id: 'fct-111111111111', kind: 'fact', name: 'Refunds up to 437 euros need no approval.', type: 'fact',
    visibility: 'tracked', created_at: '2026-10-09T15:03:00.000000Z', holder: null, available: true,
    opening: 'Refunds up to 437 euros need no approval.', sources: ['src-aaaaaaaaaaaa'],
  }
  const RETURNS = {
    ...REFUND, id: 'fct-222222222222', name: 'Goods may be returned within 30 days.',
    opening: 'Goods may be returned within 30 days.',
  }
  function withFacts(extra?: Route): Route {
    return (url, init) => {
      const answered = extra?.(url, init)
      if (answered) return answered
      if (url.endsWith('/vault/map')) return { status: 200, body: { entries: [SOURCE, REFUND, RETURNS] } }
      if (url.includes('/vault/entries/src-aaaaaaaaaaaa?offset=0')) {
        return {
          status: 200,
          body: { ...SOURCE, content: 'Kickoff.\nSmall talk.\nDana: the refund limit is 437 euros.\n', next_offset: null, note: null },
        }
      }
      if (url.includes('/vault/entries/fct-111111111111')) {
        return {
          status: 200,
          body: {
            ...REFUND, claim: REFUND.opening, content: 'Fact: ...', next_offset: null, note: null,
            citations: [{ source: 'src-aaaaaaaaaaaa', quote: 'the refund limit is 437 euros.', line_start: 3, line_end: 3 }],
          },
        }
      }
      if (url.endsWith('/vault/settings')) return { status: 200, body: SETTINGS }
      return undefined
    }
  }

  it("lists a source's facts under it and highlights a fact's cited lines", async () => {
    vault = withFacts()
    render(<VaultScreen />, { wrapper })
    // Facts sit under their source, not as rows of their own in the entry list.
    expect(await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')).toHaveTextContent('2 facts')
    expect(screen.queryByTestId('vault-entry-fct-111111111111')).toBeNull()
    fireEvent.click(screen.getByTestId('vault-entry-src-aaaaaaaaaaaa'))
    // Read formatted until a citation is asked for: no numbered lines.
    await screen.findByTestId('vault-entry-text')
    expect(screen.queryByTestId('vault-line-3')).toBeNull()

    fireEvent.click(screen.getByRole('radio', { name: /Facts/ }))
    expect(await screen.findByTestId('vault-fact-fct-111111111111')).toHaveTextContent('437 euros need no approval')
    expect(screen.getByTestId('vault-fact-fct-222222222222')).toHaveTextContent('within 30 days')
    // The quote the Hub found is shown with the fact.
    await waitFor(() => expect(screen.getByTestId('vault-fact-fct-111111111111')).toHaveTextContent('Line 3'))

    fireEvent.click(screen.getByTestId('vault-fact-link-fct-111111111111'))
    await waitFor(() => expect(screen.getByTestId('vault-line-3')).toHaveAttribute('data-highlighted', 'true'))
    expect(screen.getByTestId('vault-line-3')).toHaveTextContent('437 euros')
    expect(screen.getByTestId('vault-line-1')).toHaveAttribute('data-highlighted', 'false')
  })

  it('distils a source on request and shows why the Hub refused', async () => {
    vault = withFacts((url, init) =>
      url.endsWith('/vault/sources/src-aaaaaaaaaaaa/distil') && init?.method === 'POST'
        ? { status: 409, body: { detail: 'The vault distillation job is disabled. Enable it on the Manager page.' } }
        : undefined,
    )
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa'))
    fireEvent.click(await screen.findByTestId('vault-distil'))
    expect(await screen.findByText(/Enable it on the Manager page/)).toBeInTheDocument()
    expect(screen.getByText('Could not extract facts')).toBeInTheDocument()
    expect(sent[0]).toMatchObject({
      url: 'http://hub/api/v1/projects/proj-a/vault/sources/src-aaaaaaaaaaaa/distil',
      method: 'POST',
    })
  })

  it('says the extraction is running once the Hub accepts it, and when its facts arrive', async () => {
    let facts: unknown[] = []
    vault = withFacts((url, init) => {
      if (url.endsWith('/vault/sources/src-aaaaaaaaaaaa/distil') && init?.method === 'POST') {
        return { status: 202, body: { source: 'src-aaaaaaaaaaaa', queued: true } }
      }
      if (url.endsWith('/vault/map')) return { status: 200, body: { entries: [SOURCE, ...facts] } }
      return undefined
    })
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa'))
    fireEvent.click(await screen.findByTestId('vault-distil'))
    expect(await screen.findByText('Extracting facts in the background')).toBeInTheDocument()
    expect(screen.getByTestId('vault-distil')).toBeDisabled()
    // The map is re-read every few seconds; when it lists a new fact, the extraction is done.
    facts = [REFUND]
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 3200))
    })
    expect(await screen.findByText('Facts extracted')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('vault-distil')).toBeEnabled())
  }, 10_000)

  it("shows the Hub's reason when it refuses a private location", async () => {
    const routed = vault
    vault = (url, init) => {
      if (url.endsWith('/vault/settings') && init?.method === 'PUT') {
        return { status: 400, body: { detail: 'C:/repo/private is inside the project\'s directory' } }
      }
      return routed(url, init)
    }
    render(<VaultScreen />, { wrapper })
    await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')
    fireEvent.click(screen.getByRole('button', { name: 'Vault storage' }))
    fireEvent.change(await screen.findByTestId('vault-settings-location'), { target: { value: 'C:/repo/private' } })
    fireEvent.click(screen.getByTestId('vault-settings-save'))
    expect(await screen.findByRole('alert')).toHaveTextContent("inside the project's directory")
    // Only what changed is sent; the default stays as it was.
    expect(sent[0]).toEqual({
      url: 'http://hub/api/v1/projects/proj-a/vault/settings',
      method: 'PUT',
      body: { private_location: 'C:/repo/private' },
    })
    // Refused: the dialog stays open with what was typed.
    expect(screen.getByTestId('vault-settings-location')).toHaveValue('C:/repo/private')
  })

  it('changes where new sources go', async () => {
    const routed = vault
    vault = (url, init) =>
      url.endsWith('/vault/settings') && init?.method === 'PUT'
        ? { status: 200, body: { ...SETTINGS, default_visibility: 'tracked' } }
        : routed(url, init)
    render(<VaultScreen />, { wrapper })
    await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')
    fireEvent.click(screen.getByRole('button', { name: 'Vault storage' }))
    choose('vault-settings-default', 'In the repository')
    fireEvent.click(screen.getByTestId('vault-settings-save'))
    await waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0]).toMatchObject({ method: 'PUT', body: { default_visibility: 'tracked' } })
    expect(await screen.findByText('Vault storage saved')).toBeInTheDocument()
  })

  // `sources-that-disagree-are-pointed-out`, task tab-contradictions. The list is open first, as
  // `GET /vault/contradictions` returns it; each side carries the claim and date the Hub found.
  const OPEN_CTR = {
    id: 'ctr-aaaaaaaaaaaa', facts: ['fct-111111111111', 'fct-222222222222'], presumed: 'fct-111111111111',
    explanation: 'One says 437 euros, the other 300.', status: 'open', visibility: 'tracked', resolution: null,
    sides: [
      { id: 'fct-111111111111', claim: 'Refunds up to 300 euros need no approval.', source: 'src-aaaaaaaaaaaa', date: '2026-10-01', presumed: true },
      { id: 'fct-222222222222', claim: 'Refunds up to 437 euros need no approval.', source: 'src-cccccccccccc', date: '2026-09-01', presumed: false },
    ],
  }
  const RESOLVED_CTR = {
    ...OPEN_CTR, id: 'ctr-bbbbbbbbbbbb', status: 'resolved', presumed: null,
    resolution: { stands: 'fct-111111111111', note: 'Finance lowered it.', decision: 'src-dddddddddddd', resolved_at: '2026-10-10T10:00:00Z' },
  }
  function withContradictions(list: unknown[], extra?: Route): Route {
    return (url, init) => {
      const answered = extra?.(url, init)
      if (answered) return answered
      if (url.endsWith('/vault/contradictions')) return { status: 200, body: { contradictions: list } }
      return withFacts()(url, init)
    }
  }
  async function openDisagreements() {
    fireEvent.click(await screen.findByTestId('vault-review-contradictions'))
  }

  it('says a side whose fact is gone is gone, not held on another machine (F617)', async () => {
    vault = withContradictions([
      {
        ...RESOLVED_CTR,
        sides: [
          RESOLVED_CTR.sides[0],
          { id: 'fct-gonegonegone', claim: null, source: null, date: null, presumed: false, missing: true },
        ],
      },
    ])
    render(<VaultScreen />, { wrapper })
    await openDisagreements()
    const side = await screen.findByTestId('vault-contradiction-side-fct-gonegonegone')
    expect(side).toHaveTextContent('no longer in the vault')
    expect(side).not.toHaveTextContent('another machine')
  })

  it('lists an open contradiction with both claims, their dates, and the presumed side', async () => {
    vault = withContradictions([OPEN_CTR, RESOLVED_CTR])
    render(<VaultScreen />, { wrapper })
    // The review row counts what is still open.
    expect(await screen.findByTestId('vault-review-contradictions')).toHaveTextContent('1')
    await openDisagreements()
    const open = await screen.findByTestId('vault-contradiction-ctr-aaaaaaaaaaaa')
    expect(open).toHaveTextContent('One says 437 euros, the other 300.')
    expect(open).toHaveTextContent('Refunds up to 300 euros need no approval.')
    expect(open).toHaveTextContent(formatDay('2026-10-01'))
    expect(open).toHaveTextContent('Refunds up to 437 euros need no approval.')
    // A side's source is named, never shown by id.
    expect(open).toHaveTextContent('Acme kickoff')
    expect(open).not.toHaveTextContent('src-aaaaaaaaaaaa')
    expect(within(open).getByTestId('vault-contradiction-side-fct-111111111111')).toHaveTextContent('presumed')
    expect(within(open).getByTestId('vault-contradiction-side-fct-222222222222')).not.toHaveTextContent('presumed')
    expect(within(open).getByTestId('vault-resolve-ctr-aaaaaaaaaaaa-submit')).toBeInTheDocument()
    // A resolved one reads as settled: what stood, and why, and no form.
    const resolved = screen.getByTestId('vault-contradiction-ctr-bbbbbbbbbbbb')
    expect(resolved).toHaveTextContent('Resolved')
    expect(resolved).toHaveTextContent('Finance lowered it.')
    expect(screen.queryByTestId('vault-resolve-ctr-bbbbbbbbbbbb-submit')).toBeNull()
  })

  it('resolves for one fact with a note', async () => {
    vault = withContradictions([OPEN_CTR], (url, init) =>
      url.endsWith('/vault/contradictions/ctr-aaaaaaaaaaaa/resolve') && init?.method === 'POST'
        ? { status: 200, body: { ...OPEN_CTR, status: 'resolved' } }
        : undefined,
    )
    render(<VaultScreen />, { wrapper })
    await openDisagreements()
    // Each side can be chosen, and so can neither; the presumed side is chosen to begin with.
    const first = await screen.findByTestId('vault-resolve-ctr-aaaaaaaaaaaa-stand-fct-111111111111')
    const second = screen.getByTestId('vault-resolve-ctr-aaaaaaaaaaaa-stand-fct-222222222222')
    const neither = screen.getByTestId('vault-resolve-ctr-aaaaaaaaaaaa-neither')
    expect(first).toHaveAttribute('aria-checked', 'true')
    expect(second).toHaveAttribute('aria-checked', 'false')
    expect(neither).toHaveAttribute('aria-checked', 'false')
    // A decision without a reason is not recorded.
    expect(screen.getByTestId('vault-resolve-ctr-aaaaaaaaaaaa-submit')).toBeDisabled()
    fireEvent.click(second)
    fireEvent.click(first)
    fireEvent.change(screen.getByTestId('vault-resolve-ctr-aaaaaaaaaaaa-note'), { target: { value: 'Finance lowered it.' } })
    fireEvent.click(screen.getByTestId('vault-resolve-ctr-aaaaaaaaaaaa-submit'))
    await waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0]).toEqual({
      url: 'http://hub/api/v1/projects/proj-a/vault/contradictions/ctr-aaaaaaaaaaaa/resolve',
      method: 'POST',
      body: { stands: 'fct-111111111111', note: 'Finance lowered it.' },
    })
  })

  it('sends null for neither and shows the reason the Hub gives when it refuses', async () => {
    vault = withContradictions([OPEN_CTR], (url, init) =>
      url.endsWith('/resolve') && init?.method === 'POST'
        ? { status: 409, body: { detail: 'Contradiction ctr-aaaaaaaaaaaa is already resolved.' } }
        : undefined,
    )
    render(<VaultScreen />, { wrapper })
    await openDisagreements()
    fireEvent.click(await screen.findByTestId('vault-resolve-ctr-aaaaaaaaaaaa-neither'))
    fireEvent.change(screen.getByTestId('vault-resolve-ctr-aaaaaaaaaaaa-note'), { target: { value: 'Both are stale.' } })
    fireEvent.click(screen.getByTestId('vault-resolve-ctr-aaaaaaaaaaaa-submit'))
    expect(await screen.findByRole('alert')).toHaveTextContent('already resolved')
    expect(sent[0].body).toEqual({ stands: null, note: 'Both are stale.' })
  })

  it('shows no form for a contradiction held on another machine', async () => {
    vault = withContradictions([
      {
        ...OPEN_CTR, status: null, presumed: null, visibility: 'private', holder: 'colleague-laptop',
        sides: [
          { id: 'fct-111111111111', claim: null, source: null, date: null, presumed: false },
          { id: 'fct-222222222222', claim: null, source: null, date: null, presumed: false },
        ],
      },
    ])
    render(<VaultScreen />, { wrapper })
    await openDisagreements()
    const held = await screen.findByTestId('vault-contradiction-ctr-aaaaaaaaaaaa')
    expect(held).toHaveTextContent('colleague-laptop')
    expect(screen.queryByTestId('vault-resolve-ctr-aaaaaaaaaaaa-submit')).toBeNull()
  })

  it('shows an open contradiction about a source in its Facts view too', async () => {
    vault = withContradictions([OPEN_CTR])
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa'))
    fireEvent.click(await screen.findByRole('radio', { name: /Facts/ }))
    expect(await screen.findByTestId('vault-contradiction-ctr-aaaaaaaaaaaa')).toBeInTheDocument()
  })

  it('reads a 404 from the contradictions route as no section, and the rest of the tab stays', async () => {
    vault = withContradictions([], (url) =>
      url.endsWith('/vault/contradictions') ? { status: 404, body: { detail: 'Not Found' } } : undefined,
    )
    render(<VaultScreen />, { wrapper })
    await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')
    expect(screen.queryByTestId('vault-none')).toBeNull()
    expect(screen.queryByTestId('vault-review-contradictions')).toBeNull()
    expect(screen.queryByText(/Disagreements/)).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('marks a disputed fact and says it was superseded once a decision set it aside', async () => {
    const marked = { ...REFUND, disputed: true, presumed: true }
    const setAside = { ...RETURNS, superseded_by: 'src-dddddddddddd' }
    vault = withContradictions([], (url) =>
      url.endsWith('/vault/map') ? { status: 200, body: { entries: [SOURCE, marked, setAside] } } : undefined,
    )
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa'))
    fireEvent.click(await screen.findByRole('radio', { name: /Facts/ }))
    const disputed = await screen.findByTestId('vault-fact-fct-111111111111')
    expect(disputed).toHaveAttribute('data-disputed', 'true')
    expect(disputed).toHaveTextContent('Disputed, presumed to hold')
    const plain = screen.getByTestId('vault-fact-fct-222222222222')
    expect(plain).toHaveAttribute('data-disputed', 'false')
    expect(plain).toHaveAttribute('data-superseded', 'true')
    expect(plain).toHaveTextContent('Superseded by a decision')
  })

  // `a-working-agent-tells-the-manager-an-entry-is-wrong`, task reports-tab. The list is open
  // first, as `GET /vault/reports` returns it.
  const REPORTER = { agent: 'helper', run_id: 'run-1' }
  const CORRECTED_RPT = {
    id: 'rpt-aaaaaaaaaaaa', entry: 'fct-111111111111', entry_kind: 'fact', entry_name: 'Refunds up to 437 euros need no approval.',
    message: 'The call says 300, not 437.', reporter: REPORTER, status: 'corrected',
    answer: 'The source says 300; a corrected fact was written.', replaced_by: 'fct-333333333333',
    replaced_by_claim: 'Refunds up to 300 euros need no approval.', close: null,
  }
  const REFERRED_RPT = {
    ...CORRECTED_RPT, id: 'rpt-bbbbbbbbbbbb', entry: 'fct-222222222222', entry_name: 'Goods may be returned within 30 days.',
    message: 'I think it is 14 days.', status: 'referred', answer: 'Cannot tell from the source; the operator should look.',
    replaced_by: null, replaced_by_claim: null,
  }
  function withReports(list: unknown[], extra?: Route): Route {
    return (url, init) => {
      const answered = extra?.(url, init)
      if (answered) return answered
      if (url.endsWith('/vault/reports')) return { status: 200, body: { reports: list } }
      return withFacts()(url, init)
    }
  }
  async function openReports() {
    fireEvent.click(await screen.findByTestId('vault-review-reports'))
  }

  it('lists reports with message, reporter, status and answer; only a referred one has the form', async () => {
    vault = withReports([REFERRED_RPT, CORRECTED_RPT])
    render(<VaultScreen />, { wrapper })
    // The review row counts what waits for the operator.
    expect(await screen.findByTestId('vault-review-reports')).toHaveTextContent('1')
    await openReports()
    const referred = await screen.findByTestId('vault-report-rpt-bbbbbbbbbbbb')
    expect(referred).toHaveTextContent('I think it is 14 days.')
    expect(referred).toHaveTextContent('helper')
    expect(referred).toHaveTextContent('Referred to you')
    expect(referred).toHaveTextContent('Cannot tell from the source')
    expect(within(referred).getByTestId('vault-report-rpt-bbbbbbbbbbbb-close')).toBeInTheDocument()
    const corrected = screen.getByTestId('vault-report-rpt-aaaaaaaaaaaa')
    expect(corrected).toHaveTextContent('The call says 300, not 437.')
    expect(corrected).toHaveTextContent('Corrected')
    expect(corrected).toHaveTextContent('Refunds up to 300 euros need no approval.')
    expect(within(corrected).getByTestId('vault-report-link-rpt-aaaaaaaaaaaa')).toBeInTheDocument()
    expect(screen.queryByTestId('vault-report-rpt-aaaaaaaaaaaa-close')).toBeNull()
    expect(screen.queryByTestId('vault-report-rpt-aaaaaaaaaaaa-note')).toBeNull()
  })

  it("opens a report's corrected fact under its source, marked", async () => {
    const corrected = { ...REFUND, id: 'fct-333333333333', opening: 'Refunds up to 300 euros need no approval.' }
    vault = withReports([CORRECTED_RPT], (url) =>
      url.endsWith('/vault/map') ? { status: 200, body: { entries: [SOURCE, REFUND, corrected] } } : undefined,
    )
    render(<VaultScreen />, { wrapper })
    await openReports()
    fireEvent.click(await screen.findByTestId('vault-report-link-rpt-aaaaaaaaaaaa'))
    expect(await screen.findByRole('article', { name: 'Acme kickoff' })).toBeInTheDocument()
    expect(await screen.findByTestId('vault-fact-fct-333333333333')).toHaveAttribute('data-focused', 'true')
    expect(screen.getByTestId('vault-fact-fct-111111111111')).toHaveAttribute('data-focused', 'false')
  })

  it('closes a referred report with a note and shows the reason when the Hub refuses', async () => {
    vault = withReports([REFERRED_RPT], (url, init) =>
      url.endsWith('/vault/reports/rpt-bbbbbbbbbbbb/close') && init?.method === 'POST'
        ? { status: 409, body: { detail: 'Report rpt-bbbbbbbbbbbb is already closed.' } }
        : undefined,
    )
    render(<VaultScreen />, { wrapper })
    await openReports()
    // A close without a note is not sent.
    expect(await screen.findByTestId('vault-report-rpt-bbbbbbbbbbbb-close')).toBeDisabled()
    fireEvent.change(screen.getByTestId('vault-report-rpt-bbbbbbbbbbbb-note'), { target: { value: 'Checked: it is 30.' } })
    fireEvent.click(screen.getByTestId('vault-report-rpt-bbbbbbbbbbbb-close'))
    expect(await screen.findByRole('alert')).toHaveTextContent('already closed')
    expect(sent[0]).toEqual({
      url: 'http://hub/api/v1/projects/proj-a/vault/reports/rpt-bbbbbbbbbbbb/close',
      method: 'POST',
      body: { note: 'Checked: it is 30.' },
    })
  })

  it('looks into a pending report again on request and shows why the Hub refused (F801)', async () => {
    const PENDING_RPT = { ...REFERRED_RPT, id: 'rpt-cccccccccccc', status: 'pending', answer: null }
    vault = withReports([PENDING_RPT, REFERRED_RPT], (url, init) =>
      url.endsWith('/vault/reports/rpt-cccccccccccc/review') && init?.method === 'POST'
        ? { status: 409, body: { detail: 'The vault reports job has no runner.' } }
        : undefined,
    )
    render(<VaultScreen />, { wrapper })
    await openReports()
    // Only a pending report has the door; a referred one has the close form.
    expect(await screen.findByTestId('vault-report-rpt-bbbbbbbbbbbb-close')).toBeInTheDocument()
    expect(screen.queryByTestId('vault-report-rpt-bbbbbbbbbbbb-review')).toBeNull()
    fireEvent.click(screen.getByTestId('vault-report-rpt-cccccccccccc-review'))
    expect(await screen.findByRole('alert')).toHaveTextContent('has no runner')
    expect(sent[0]).toMatchObject({
      url: 'http://hub/api/v1/projects/proj-a/vault/reports/rpt-cccccccccccc/review',
      method: 'POST',
    })
  })

  it('reads a 404 from the reports route as no section', async () => {
    vault = withReports([], (url) => (url.endsWith('/vault/reports') ? { status: 404, body: { detail: 'Not Found' } } : undefined))
    render(<VaultScreen />, { wrapper })
    await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')
    expect(screen.queryByTestId('vault-review-reports')).toBeNull()
    expect(screen.queryByTestId('vault-reports')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('says a fact was superseded by a corrected fact when a report set it aside', async () => {
    const setAside = { ...REFUND, superseded_by: 'fct-333333333333' }
    vault = withReports([], (url) =>
      url.endsWith('/vault/map') ? { status: 200, body: { entries: [SOURCE, setAside, RETURNS] } } : undefined,
    )
    render(<VaultScreen />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa'))
    fireEvent.click(await screen.findByRole('radio', { name: /Facts/ }))
    const mark = await screen.findByTestId('vault-fact-fct-111111111111')
    expect(mark).toHaveAttribute('data-superseded', 'true')
    expect(mark).toHaveTextContent('Superseded by a corrected fact')
  })

  it('sends the day a source was said when one is given', async () => {
    const routed = vault
    vault = (url, init) =>
      url.endsWith('/vault/sources') && init?.method === 'POST'
        ? { status: 201, body: { ...ENTRIES[1], id: 'src-cccccccccccc' } }
        : routed(url, init)
    render(<VaultScreen />, { wrapper })
    await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')
    openPasteText()
    fireEvent.change(screen.getByTestId('vault-upload-name'), { target: { value: 'October call' } })
    fireEvent.change(screen.getByTestId('vault-upload-content'), { target: { value: 'Dana: 300 euros.' } })
    fireEvent.change(screen.getByTestId('vault-upload-dated'), { target: { value: '2026-10-01' } })
    fireEvent.click(screen.getByTestId('vault-upload-submit'))
    await waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0].body).toMatchObject({ name: 'October call', dated: '2026-10-01' })
  })

  it('will not add a source said on a day that is not written as one', async () => {
    render(<VaultScreen />, { wrapper })
    await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')
    openPasteText()
    fireEvent.change(screen.getByTestId('vault-upload-name'), { target: { value: 'October call' } })
    fireEvent.change(screen.getByTestId('vault-upload-content'), { target: { value: 'Dana: 300 euros.' } })
    fireEvent.change(screen.getByTestId('vault-upload-dated'), { target: { value: '10/01/2026' } })
    expect(screen.getByTestId('vault-upload-submit')).toBeDisabled()
    expect(screen.getByText('Fix the date first.')).toBeInTheDocument()
  })
})
