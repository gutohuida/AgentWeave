/**
 * Starting a flow from the document page and finding it again
 * (`a-flow-is-configured-from-its-own-tab`, tasks 3.4 and 3.5 d/e/f). Fed a `GET /loops`-shaped
 * list through the real `useLoops`/`useDocumentFlow`, so the phase bar's answer is the one a
 * route's ordering would produce.
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { useConfigStore } from '@/store/configStore'

const posts: Array<{ path: string; body: unknown }> = []
let loops: unknown[] = []
let documents: unknown[] = []

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    getJson: vi.fn(async (path: string) => {
      if (path.includes('/loops')) return loops
      if (path.includes('/documents')) return { documents }
      return []
    }),
    postJson: vi.fn(async (path: string, body: unknown) => {
      posts.push({ path, body })
      return { id: 'job-new' }
    }),
  }
})
vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'A' }, { name: 'B' }] }),
}))

function doc(overrides: Record<string, unknown> = {}) {
  return {
    id: 'spdoc-1',
    path: 'spec/changes/demo/spec.json',
    title: 'Demo',
    kind: 'change-spec',
    phase: 'approved',
    rigor: 'sketch',
    content_digest: null,
    explore_closed: true,
    updated_at: '2026-09-27T00:00:00Z',
    ...overrides,
  }
}

function loop(overrides: Record<string, unknown> = {}) {
  return {
    id: 'loop-1',
    label: 'Demo flow',
    agent: 'A',
    spec_document_id: 'spdoc-1',
    ending_state: null,
    archived_at: null,
    ...overrides,
  }
}

let client: QueryClient

function renderBar(onOpenLoop?: (l: unknown) => void) {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecPhaseBar path="spec/changes/demo/spec.json" onOpenLoop={onOpenLoop} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  posts.length = 0
  loops = []
  documents = [doc()]
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-test',
    isConfigured: true,
    bootstrapState: 'ready',
  })
})
afterEach(() => cleanup())

describe('the phase bar and the flow', () => {
  it('(e) links to the flow when a loop declares the document, even an ended one', async () => {
    // A `GET /loops` list: no archived rows, oldest first, a documentless loop before the flow.
    loops = [
      loop({ id: 'loop-0', label: 'Housekeeping', spec_document_id: null }),
      loop({ ending_state: 'ended' }),
    ]
    const open = vi.fn()
    renderBar(open)
    const link = await screen.findByTestId('spec-flow-link')
    expect(link).toHaveTextContent('Flow: Demo flow')
    fireEvent.click(link)
    expect(open).toHaveBeenCalledWith(expect.objectContaining({ id: 'loop-1' }))
    expect(screen.queryByTestId('spec-start-flow')).not.toBeInTheDocument()
  })

  it('(e) offers Start a flow… when no loop declares the document', async () => {
    loops = [loop({ id: 'loop-0', spec_document_id: 'spdoc-other' })]
    renderBar(vi.fn())
    expect(await screen.findByTestId('spec-start-flow')).toHaveTextContent('Start a flow…')
    expect(screen.queryByTestId('spec-flow-link')).not.toBeInTheDocument()
  })

  it('shows the flow as text, not a dead link, when the host gave no way to open it', async () => {
    loops = [loop()]
    renderBar()
    const label = await screen.findByTestId('spec-flow-link')
    expect(label.tagName).not.toBe('BUTTON')
  })

  it.each([
    ['exploring', 'change-spec'],
    ['proposed', 'change-spec'],
    ['archived', 'change-spec'],
    ['approved', 'baseline'],
  ])('offers no flow on a %s %s', async (phase, kind) => {
    documents = [doc({ phase, kind })]
    renderBar(vi.fn())
    await screen.findByTestId('spec-phase')
    expect(screen.queryByTestId('spec-start-flow')).not.toBeInTheDocument()
    expect(screen.queryByTestId('spec-flow-link')).not.toBeInTheDocument()
  })
})

describe('StartFlowDialog', () => {
  async function openDialog() {
    renderBar(vi.fn())
    fireEvent.click(await screen.findByTestId('spec-start-flow'))
    return screen.findByRole('dialog')
  }
  const chooseAgent = () =>
    fireEvent.change(screen.getByLabelText('Default agent'), { target: { value: 'B' } })
  const start = () => fireEvent.click(screen.getByRole('button', { name: 'Start flow' }))

  it('(d) posts the document, the queue stop, an empty purpose and no work_needs_evidence', async () => {
    await openDialog()
    chooseAgent()
    start()
    await waitFor(() => expect(posts).toHaveLength(1))
    const body = posts[0].body as Record<string, unknown>
    expect(posts[0].path).toContain('/projects/proj-test/jobs')
    expect(body).toMatchObject({
      spec_document_id: 'spdoc-1',
      stop_when_queue_empties: true,
      purpose: '',
      agent: 'B',
      name: 'Demo',
    })
    expect(body).not.toHaveProperty('work_needs_evidence')
    expect(body).not.toHaveProperty('session_mode')
  })

  it('(d) sends nothing with both stops cleared, and says why', async () => {
    await openDialog()
    chooseAgent()
    fireEvent.click(screen.getByLabelText('When the queue empties'))
    start()
    expect(await screen.findByRole('alert')).toHaveTextContent('needs a stop condition')
    expect(posts).toHaveLength(0)
  })

  it('does not preselect an agent when there is more than one', async () => {
    await openDialog()
    start()
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose the agent')
    expect(posts).toHaveLength(0)
  })

  it('(f) re-reads the loops after a successful create', async () => {
    await openDialog()
    const spy = vi.spyOn(client, 'invalidateQueries')
    chooseAgent()
    start()
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({ queryKey: ['project', 'proj-test', 'loops'] }),
    )
  })
})
