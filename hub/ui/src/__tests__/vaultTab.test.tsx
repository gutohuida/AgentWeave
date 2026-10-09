import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
})
