import * as React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { SpecPage } from '@/components/spec/SpecPage'
import { readLastDocument } from '@/components/spec/lastDocument'

/* Spec `spec-page-remembers-readable-task-threads-retrospective-after-landing`, FR-1..FR-4: the
 * Spec tab reopens the document last opened in the project. The Hub is a stubbed `fetch`; the host
 * is a stateful wrapper that follows `onOpenDocument` as the app's destination does. */

vi.mock('@/hooks/useSSE', () => ({
  useSSEConnectionState: () => 'open',
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

const B = 'spec/changes/bee/spec.json'
const C = 'spec/changes/cee/spec.json'
const D = 'spec/changes/dee/spec.json'
const HOME = 'spec/changes/home/spec.json'
const TITLES: Record<string, string> = { [B]: 'Bee change', [C]: 'Cee change', [D]: 'Dee change', [HOME]: 'Home change' }

const pageOf = (title: string) =>
  `<html><body><script type="application/agentweave-spec+json" id="aw-spec-payload">${JSON.stringify({
    title,
    kind: 'change-spec',
    summary: `${title} summary.`,
    problem: 'p',
    scope: { in_scope: ['x'], non_goals: ['y'] },
    requirements: [],
    tasks: [],
    acceptance_criteria: [],
    open_questions: [],
  })}</script></body></html>`

let present: string[]

function route(url: string): unknown {
  const u = new URL(url, 'http://hub.test')
  const p = u.pathname.replace(/^\/api\/v1\/projects\/[^/]+/, '')
  if (p === '/project/specs')
    return {
      specs: present.map((path, i) => ({ path, title: TITLES[path], kind: 'change-spec', state: 'filed', parent: null, order: i, document_id: `id-${i}`, phase: 'approved' })),
      home: HOME,
      manifest: { state: 'valid', version: 1 },
      missing: [],
      diagnostics: [],
    }
  if (p === '/project/documents')
    return {
      documents: present.map((path, i) => ({
        id: `id-${i}`, path, title: TITLES[path], kind: 'change-spec', phase: 'approved', rigor: 'contract', content_digest: null, explore_closed: false, updated_at: '2026-10-17T09:00:00Z',
      })),
    }
  if (p === '/project/spec') {
    const at = u.searchParams.get('path') ?? ''
    if (!present.includes(at)) return undefined
    return { path: at, content: pageOf(TITLES[at]), updated_at: '2026-10-17T09:00:00Z', content_version: 'v1', builds: [] }
  }
  if (p === '/project/spec/coverage') return { requirements: [], diagnostics: [], totals: {}, integration: {}, unserved: [] }
  if (p === '/tasks') return { tasks: [], total: 0, has_more: false }
  if (p === '/loops') return []
  return undefined
}

let queryClient: QueryClient

function Host({ initial }: { initial: string | null }) {
  const [doc, setDoc] = React.useState<string | null>(initial)
  return <SpecPage document={doc} onOpenDocument={setDoc} />
}

/** The Spec tab opened in a fresh mount: what closing and reopening the app does. */
function openSpecTab(initial: string | null = null) {
  cleanup()
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <Host initial={initial} />
    </QueryClientProvider>,
  )
}

const inProject = (projectId: string) =>
  useConfigStore.setState({ apiKey: 'aw_live_TESTKEY', hubUrl: 'http://hub.test', selectedProjectId: projectId, isConfigured: true, bootstrapState: 'ready', mode: 'light' })

const shown = async (title: string) => {
  await waitFor(() => expect(screen.getByTestId('spec-document-header')).toHaveTextContent(title))
}
const listOnly = async () => {
  await screen.findByText('Pick a document')
  expect(screen.queryByTestId('spec-document-header')).toBeNull()
}

beforeEach(() => {
  cleanup()
  localStorage.clear()
  present = [B, C, D, HOME]
  inProject('proj-p')
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body = route(url)
      if (body === undefined) return new Response(JSON.stringify({ detail: 'not stubbed' }), { status: 404 })
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

describe('the Spec tab reopens the last document', () => {
  it('ac-reopen: a bare Spec tab shows the document opened before the app was closed', async () => {
    openSpecTab(B)
    await shown('Bee change')
    openSpecTab(null)
    await shown('Bee change')
  })

  it('ac-reopen: with nothing remembered the manifest home opens, as before', async () => {
    openSpecTab(null)
    await shown('Home change')
  })

  it('ac-per-project: each project reopens its own document', async () => {
    openSpecTab(B)
    await shown('Bee change')
    inProject('proj-q')
    openSpecTab(C)
    await shown('Cee change')
    openSpecTab(null)
    await shown('Cee change')
    inProject('proj-p')
    openSpecTab(null)
    await shown('Bee change')
  })

  it('ac-url: a link naming a document wins and is what the next bare open shows', async () => {
    openSpecTab(B)
    await shown('Bee change')
    openSpecTab(D)
    await shown('Dee change')
    expect(readLastDocument('proj-p')).toBe(D)
    openSpecTab(null)
    await shown('Dee change')
  })

  it('ac-url: a link naming a document the project lacks does not displace the remembered one', async () => {
    openSpecTab(B)
    await shown('Bee change')
    present = [B, C, HOME]
    openSpecTab(D)
    await new Promise((resolve) => setTimeout(resolve, 200))
    expect(readLastDocument('proj-p')).toBe(B)
  })

  it('ac-missing: a remembered document that is gone shows the list without an error, and so does the next bare open', async () => {
    openSpecTab(B)
    await shown('Bee change')
    present = [C, D, HOME]
    openSpecTab(null)
    await listOnly()
    expect(screen.queryByTestId('spec-unread')).toBeNull()
    expect(readLastDocument('proj-p')).toBe('')
    openSpecTab(null)
    await listOnly()
  })

  it('ac-missing: opening a document from the list after a miss is remembered again', async () => {
    localStorage.setItem('aw.spec.last.proj-p', B)
    present = [C, D, HOME]
    openSpecTab(null)
    await listOnly()
    fireEvent.click(await screen.findByText('Cee change'))
    await shown('Cee change')
    openSpecTab(null)
    await shown('Cee change')
  })

  it('ac-list: one click on the list control shows the list, and the Spec tab then reopens the document', async () => {
    openSpecTab(B)
    await shown('Bee change')
    fireEvent.click(screen.getByTestId('spec-list-control'))
    await listOnly()
    expect(readLastDocument('proj-p')).toBe(B)
    openSpecTab(null)
    await shown('Bee change')
  })
})
