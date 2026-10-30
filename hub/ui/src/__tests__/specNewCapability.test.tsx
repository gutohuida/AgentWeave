import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FoldIntoCapabilityDialog } from '@/components/spec/FoldIntoCapabilityDialog'
import { SpecDocList } from '@/components/spec/page/SpecDocList'
import { capabilityPathFor, type ListPreferences } from '@/components/spec/page/model'
import { useConfigStore } from '@/store/configStore'

/**
 * The spec list creating a capability, through the real hook and the real query cache: only `fetch`
 * is stubbed, answering with what `POST /project/documents` returned from a live Hub on 2026-10-30.
 */
const PATH = 'spec/capabilities/spec-builds/spec.json'
const CREATED = {
  id: 'spdoc-db58da6270f4',
  path: PATH,
  title: 'Spec builds',
  kind: 'capability',
  phase: 'current',
  display_phase: 'current',
  content_digest: '5acedf8cdf43eeea18c38509a467b21e5904335d6f3a0f9cf64a9eeb90162f9c',
  explore_closed: false,
  step: null,
  size: null,
  journey: null,
  updated_at: '2026-10-30T11:49:23.208121+00:00',
  blocking: [],
  warnings: [{ code: 'no_requirements', where: 'requirements', message: 'a document with no requirements asserts nothing that can be satisfied or violated' }],
}
const REFUSED = { detail: { message: `a document already exists at ${PATH}`, code: 'document_exists' } }
const CHANGE = 'spec/changes/slice-one/spec.json'

const prefs: ListPreferences = { query: '', kind: 'capability', phase: 'any', buildingOnly: false, order: 'title' }

let documents: unknown[]
let posts: unknown[]
let answer: { status: number; body: unknown }

function reply(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

beforeEach(() => {
  documents = []
  posts = []
  answer = { status: 201, body: CREATED }
  useConfigStore.setState({ isConfigured: true, selectedProjectId: 'proj-1', hubUrl: '', apiKey: 'k' })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url.endsWith('/project/documents')) {
        posts.push(JSON.parse(String(init.body)))
        if (answer.status === 201) documents = [CREATED]
        return reply(answer.status, answer.body)
      }
      if (url.endsWith('/project/documents')) return reply(200, { documents })
      if (url.includes('/project/spec?')) return reply(200, { path: CHANGE, content: '', fold_state: null })
      return reply(200, {})
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

function renderList(kind: ListPreferences['kind'] = 'capability', onOpen = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <SpecDocList entries={[]} active={null} prefs={{ ...prefs, kind }} onPrefsChange={vi.fn()} onOpen={onOpen} onNew={vi.fn()} now={new Date()} />
    </QueryClientProvider>,
  )
  return { client, onOpen }
}

describe('New capability', () => {
  it('derives the path as the Hub folds a name, and none from a title with nothing in it', () => {
    expect(capabilityPathFor('Spec builds')).toBe(PATH)
    expect(capabilityPathFor('  Côté: A/B  ')).toBe('spec/capabilities/cote-a-b/spec.json')
    expect(capabilityPathFor('???')).toBeNull()
  })

  it('is offered with the Capabilities filter on, and not with another', () => {
    renderList('roadmap')
    expect(screen.queryByTestId('new-capability')).not.toBeInTheDocument()
  })

  it('shows the path, posts kind capability with it and the title, then opens what the Hub created', async () => {
    const { onOpen } = renderList()
    await userEvent.click(screen.getByTestId('new-capability'))
    expect(screen.getByTestId('new-capability-confirm')).toBeDisabled()
    await userEvent.type(screen.getByTestId('new-capability-title'), 'Spec builds')
    expect(screen.getByTestId('new-capability-path')).toHaveTextContent(PATH)
    await userEvent.click(screen.getByTestId('new-capability-confirm'))
    await waitFor(() => expect(onOpen).toHaveBeenCalledWith(PATH))
    expect(posts).toEqual([{ path: PATH, title: 'Spec builds', kind: 'capability' }])
    expect(screen.queryByTestId('new-capability-title')).not.toBeInTheDocument()
  })

  it("shows the Hub's refusal in the dialog, keeps it open and opens nothing", async () => {
    answer = { status: 409, body: REFUSED }
    const { onOpen } = renderList()
    await userEvent.click(screen.getByTestId('new-capability'))
    await userEvent.type(screen.getByTestId('new-capability-title'), 'Spec builds')
    await userEvent.click(screen.getByTestId('new-capability-confirm'))
    expect(await screen.findByTestId('new-capability-error')).toHaveTextContent(`a document already exists at ${PATH}`)
    expect(screen.getByTestId('new-capability-title')).toBeInTheDocument()
    expect(onOpen).not.toHaveBeenCalled()
  })

  it('is listed in Fold into capability once created, with no reload', async () => {
    const { client } = renderList()
    render(
      <QueryClientProvider client={client}>
        <FoldIntoCapabilityDialog path={CHANGE} title="Slice one" onClose={vi.fn()} />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('fold-capability').querySelectorAll('option')).toHaveLength(1))
    await userEvent.click(screen.getByTestId('new-capability'))
    await userEvent.type(screen.getByTestId('new-capability-title'), 'Spec builds')
    await userEvent.click(screen.getByTestId('new-capability-confirm'))
    expect(await screen.findByRole('option', { name: 'Spec builds', hidden: true })).toHaveValue(PATH)
  })
})
