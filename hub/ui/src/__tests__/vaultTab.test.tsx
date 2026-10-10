import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { VaultPage } from '@/components/vault/VaultPage'
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
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  sent.length = 0
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
    render(<VaultPage />, { wrapper })
    expect(await screen.findByTestId('vault-none')).toHaveTextContent('This Hub has no vault yet')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('lists the entries in the order the map returns them', async () => {
    render(<VaultPage />, { wrapper })
    await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')
    const rows = screen.getAllByTestId(/^vault-entry-src-/)
    expect(rows.map((row) => row.dataset.testid)).toEqual([
      'vault-entry-src-bbbbbbbbbbbb',
      'vault-entry-src-aaaaaaaaaaaa',
    ])
    expect(rows[0]).toHaveTextContent('Held on colleague-laptop')
    expect(rows[1]).toHaveTextContent('Kickoff meeting with Acme Retail.')
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
    render(<VaultPage />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa'))
    expect(await screen.findByTestId('vault-entry-text')).toHaveTextContent('Dana: the limit is')
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }))
    await waitFor(() =>
      expect(screen.getByTestId('vault-entry-text')).toHaveTextContent('Dana: the limit is 437 euros.'),
    )
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
    render(<VaultPage />, { wrapper })
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
    render(<VaultPage />, { wrapper })
    await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')
    fireEvent.click(screen.getByTestId('vault-upload-open'))
    fireEvent.change(screen.getByTestId('vault-upload-name'), { target: { value: 'Rules' } })
    fireEvent.change(screen.getByTestId('vault-upload-type'), { target: { value: 'rules' } })
    fireEvent.change(screen.getByTestId('vault-upload-content'), { target: { value: 'Refunds over 437 need a manager.' } })
    expect(screen.getByTestId('vault-upload-visibility')).toHaveValue('private')
    fireEvent.click(screen.getByTestId('vault-upload-submit'))
    await waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0]).toEqual({
      url: 'http://hub/api/v1/projects/proj-a/vault/sources',
      method: 'POST',
      body: { name: 'Rules', type: 'rules', content: 'Refunds over 437 need a manager.', visibility: 'private' },
    })
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
    render(<VaultPage />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa'))
    expect(await screen.findByTestId('vault-fact-fct-111111111111')).toHaveTextContent('437 euros need no approval')
    expect(screen.getByTestId('vault-fact-fct-222222222222')).toHaveTextContent('within 30 days')
    // Facts sit under their source, not as rows of their own in the entry list.
    expect(screen.queryByTestId('vault-entry-fct-111111111111')).toBeNull()
    expect(screen.getByTestId('vault-entry-src-aaaaaaaaaaaa')).toHaveTextContent('2 facts')

    expect(await screen.findByTestId('vault-line-3')).toHaveAttribute('data-highlighted', 'false')
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
    render(<VaultPage />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa'))
    fireEvent.click(await screen.findByTestId('vault-distil'))
    expect(await screen.findByRole('alert')).toHaveTextContent('Enable it on the Manager page')
    expect(sent[0]).toMatchObject({
      url: 'http://hub/api/v1/projects/proj-a/vault/sources/src-aaaaaaaaaaaa/distil',
      method: 'POST',
    })
  })

  it("shows the Hub's reason when it refuses a private location", async () => {
    const routed = vault
    vault = (url, init) => {
      if (url.endsWith('/vault/settings') && init?.method === 'PUT') {
        return { status: 400, body: { detail: 'C:/repo/private is inside the project\'s directory' } }
      }
      return routed(url, init)
    }
    render(<VaultPage />, { wrapper })
    fireEvent.change(await screen.findByTestId('vault-settings-location'), { target: { value: 'C:/repo/private' } })
    fireEvent.click(screen.getByTestId('vault-settings-save'))
    expect(await screen.findByRole('alert')).toHaveTextContent("inside the project's directory")
    expect(sent[0]).toMatchObject({ method: 'PUT', body: { private_location: 'C:/repo/private' } })
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

  it('lists an open contradiction with both claims, their dates, and the presumed side', async () => {
    vault = withContradictions([OPEN_CTR, RESOLVED_CTR])
    render(<VaultPage />, { wrapper })
    const open = await screen.findByTestId('vault-contradiction-ctr-aaaaaaaaaaaa')
    expect(open).toHaveTextContent('One says 437 euros, the other 300.')
    expect(open).toHaveTextContent('Refunds up to 300 euros need no approval.')
    expect(open).toHaveTextContent('2026-10-01')
    expect(open).toHaveTextContent('Refunds up to 437 euros need no approval.')
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
    render(<VaultPage />, { wrapper })
    const stands = (await screen.findByTestId('vault-resolve-ctr-aaaaaaaaaaaa-stands')) as HTMLSelectElement
    expect([...stands.options].map((option) => option.value)).toEqual(['fct-111111111111', 'fct-222222222222', ''])
    // A decision without a reason is not recorded.
    expect(screen.getByTestId('vault-resolve-ctr-aaaaaaaaaaaa-submit')).toBeDisabled()
    fireEvent.change(stands, { target: { value: 'fct-111111111111' } })
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
    render(<VaultPage />, { wrapper })
    fireEvent.change(await screen.findByTestId('vault-resolve-ctr-aaaaaaaaaaaa-stands'), { target: { value: '' } })
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
    render(<VaultPage />, { wrapper })
    const held = await screen.findByTestId('vault-contradiction-ctr-aaaaaaaaaaaa')
    expect(held).toHaveTextContent('colleague-laptop')
    expect(screen.queryByTestId('vault-resolve-ctr-aaaaaaaaaaaa-submit')).toBeNull()
  })

  it('reads a 404 from the contradictions route as no section, and the rest of the tab stays', async () => {
    vault = withContradictions([], (url) =>
      url.endsWith('/vault/contradictions') ? { status: 404, body: { detail: 'Not Found' } } : undefined,
    )
    render(<VaultPage />, { wrapper })
    await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')
    expect(screen.queryByTestId('vault-none')).toBeNull()
    expect(screen.queryByText(/Contradictions/)).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('marks a disputed fact and says it was superseded once a decision set it aside', async () => {
    const marked = { ...REFUND, disputed: true, presumed: true }
    const setAside = { ...RETURNS, superseded_by: 'src-dddddddddddd' }
    vault = withContradictions([], (url) =>
      url.endsWith('/vault/map') ? { status: 200, body: { entries: [SOURCE, marked, setAside] } } : undefined,
    )
    render(<VaultPage />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa'))
    const disputed = await screen.findByTestId('vault-fact-fct-111111111111')
    expect(disputed).toHaveAttribute('data-disputed', 'true')
    expect(disputed).toHaveTextContent('disputed')
    const plain = screen.getByTestId('vault-fact-fct-222222222222')
    expect(plain).toHaveAttribute('data-disputed', 'false')
    expect(plain).toHaveAttribute('data-superseded', 'true')
    expect(plain).toHaveTextContent('superseded')
  })

  it('sends the day a source was said when one is given', async () => {
    const routed = vault
    vault = (url, init) =>
      url.endsWith('/vault/sources') && init?.method === 'POST'
        ? { status: 201, body: { ...ENTRIES[1], id: 'src-cccccccccccc' } }
        : routed(url, init)
    render(<VaultPage />, { wrapper })
    await screen.findByTestId('vault-entry-src-aaaaaaaaaaaa')
    fireEvent.click(screen.getByTestId('vault-upload-open'))
    fireEvent.change(screen.getByTestId('vault-upload-name'), { target: { value: 'October call' } })
    fireEvent.change(screen.getByTestId('vault-upload-content'), { target: { value: 'Dana: 300 euros.' } })
    fireEvent.change(screen.getByTestId('vault-upload-dated'), { target: { value: '2026-10-01' } })
    fireEvent.click(screen.getByTestId('vault-upload-submit'))
    await waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0].body).toMatchObject({ name: 'October call', dated: '2026-10-01' })
  })
})
