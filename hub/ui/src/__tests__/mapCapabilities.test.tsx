import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MapCapabilities } from '@/components/spec/MapCapabilities'
import { useConfigStore } from '@/store/configStore'

/**
 * `a-project-with-no-specs-is-offered-a-start` FR-8, the app half: the system map's page lists
 * each proposed capability with its draft's state, in the Hub's order, and every row with a draft
 * opens that row's draft. Only `fetch` is stubbed, with the document route's own shape.
 */
const MAP = 'spec/agentweave-map/spec.json'
const BILLING = 'spec/changes/billing/spec.json'
const AUTH = 'spec/changes/auth/spec.json'

let proposed: unknown[]
let reads: string[]

function reply(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

beforeEach(() => {
  reads = []
  useConfigStore.setState({ isConfigured: true, selectedProjectId: 'proj-1', hubUrl: '', apiKey: 'k' })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.includes('/project/spec?')) {
        reads.push(url)
        return reply(200, { path: MAP, content: '', capabilities: { changes: [], creates: [] }, proposed_capabilities: proposed })
      }
      return reply(200, {})
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

describe('the system map page', () => {
  it('shows each proposed capability with its own state and opens each row\'s draft', async () => {
    proposed = [
      { title: 'Reports', state: 'no-draft', draft: null },
      { title: 'Billing', state: 'exploring', draft: { path: BILLING, title: 'billing as built', phase: 'exploring' } },
      { title: 'Auth', state: 'current', draft: { path: AUTH, title: 'Auth', phase: 'approved' } },
    ]
    const opened: string[] = []
    wrap(<MapCapabilities path={MAP} onOpenDocument={(p) => opened.push(p)} />)
    await waitFor(() => expect(screen.getAllByTestId('map-capability-row')).toHaveLength(3))
    expect(reads[0]).toContain(encodeURIComponent(MAP))
    const rows = screen.getAllByTestId('map-capability-row')
    expect(rows.map((r) => [r.dataset.title, r.dataset.state])).toEqual([
      ['Reports', 'no-draft'],
      ['Billing', 'exploring'],
      ['Auth', 'current'],
    ])
    expect(rows.map((r) => r.dataset.draft ?? null)).toEqual([null, BILLING, AUTH])
    expect(rows[0].textContent).toContain('no draft yet')
    expect(rows[1].textContent).toContain('exploring')
    expect(rows[2].textContent).toContain('current')
    expect(within(rows[0]).queryByRole('button')).toBeNull()
    for (const row of rows.slice(1)) await userEvent.click(within(row).getByRole('button'))
    expect(opened).toEqual([BILLING, AUTH])
  })

  it('says when the map proposes nothing, and when the read failed', async () => {
    proposed = []
    const { unmount } = wrap(<MapCapabilities path={MAP} />)
    await waitFor(() => expect(screen.getByTestId('map-capabilities').textContent).toContain('none proposed'))
    unmount()
    vi.stubGlobal('fetch', vi.fn(async () => reply(500, { detail: 'down' })))
    wrap(<MapCapabilities path={MAP} />)
    await waitFor(() => expect(screen.getByTestId('map-capabilities-unread')).toBeTruthy())
  })
})
