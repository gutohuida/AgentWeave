import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThreadScreen } from '@/components/thread/ThreadScreen'
import { joinPage, refreshEnd, linkTarget } from '@/lib/threadKnots'
import { parseDestination, serializeDestination, PROJECT_TABS, threadDestination } from '@/lib/navigation'
import type { LoadedLevel, ThreadKnot } from '@/api/thread'
import { useConfigStore } from '@/store/configStore'

const getJson = vi.fn()
const postJson = vi.fn()
vi.mock('@/api/client', () => ({
  getJson: (path: string) => getJson(path),
  postJson: (path: string) => postJson(path),
  readableApiError: (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback),
}))
const sse = vi.hoisted(() => ({ handler: null as null | ((event: { type: string; data: unknown }) => void) }))
vi.mock('@/hooks/useSSE', () => ({
  useSSE: (handler: (event: { type: string; data: unknown }) => void) => {
    sse.handler = handler
  },
}))

function knot(key: string, kind: ThreadKnot['kind'], title: string, start: string, children = 0): ThreadKnot {
  return {
    key, address: key, kind, fold_of: null, word: kind === 'document' ? 'Document' : kind === 'task' ? 'Task' : 'Run',
    title, start, end: start, actors: ['Operator'], child_count: children, descendant_count: children, link: null,
  }
}
const page = (knots: ThreadKnot[], extra = {}) => ({
  knots, total: knots.length, has_before: false, has_after: false,
  before_cursor: knots[0] ? `${knots[0].start}|${knots[0].key}` : null,
  after_cursor: knots.length ? `${knots[knots.length - 1].start}|${knots[knots.length - 1].key}` : null,
  under: 'surface', ...extra,
})
const level = (knots: ThreadKnot[]): LoadedLevel => ({
  knots, hasBefore: false, hasAfter: false, beforeCursor: null, afterCursor: null,
})

const doc = knot('document:d1', 'document', 'First change', '2026-09-01T09:00:00+00:00', 1)
const tsk = knot('task:t1', 'task', 'Build it', '2026-09-02T09:00:00+00:00', 1)
const run = knot('run:r1', 'run', 'Builder worked', '2026-09-03T09:00:00+00:00')

beforeEach(() => {
  useConfigStore.setState({ apiKey: 'aw_live_test', hubUrl: 'http://hub', isConfigured: true, selectedProjectId: 'proj-a' })
  postJson.mockReset()
  getJson.mockReset()
  getJson.mockImplementation(async (path: string) => {
    const url = new URL(path, 'http://hub')
    if (url.pathname.endsWith('/thread/knot')) return { knot: run, ancestors: ['document:d1', 'task:t1'] }
    const under = url.searchParams.get('under')
    if (under === 'document:d1') return page([tsk])
    if (under === 'task:t1') return page([run])
    return page([doc])
  })
})

function mount(props: Partial<React.ComponentProps<typeof ThreadScreen>> = {}) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ThreadScreen projectId="proj-a" knot={null} onAddress={() => undefined} onOpenLink={() => undefined} {...props} />
    </QueryClientProvider>,
  )
}

describe('ThreadScreen', () => {
  it('asks for its own project only, newest page first, and fetches a level when a knot opens', async () => {
    const onAddress = vi.fn()
    mount({ onAddress })
    const head = await screen.findByText('First change')
    expect(getJson.mock.calls[0][0]).toMatch(/^\/api\/v1\/projects\/proj-a\/thread\?limit=40$/)
    fireEvent.click(head)
    await screen.findByText('Build it')
    expect(getJson.mock.calls.some(([p]) => p.includes('under=document%3Ad1') && p.includes('first=true'))).toBe(true)
    expect(onAddress).toHaveBeenCalledWith('document:d1')
  })

  it('opens every ancestor of an address and focuses the knot', async () => {
    mount({ knot: 'run:r1' })
    const head = await screen.findByText('Builder worked')
    await waitFor(() => expect(document.activeElement?.closest('[data-knot-key]')?.getAttribute('data-knot-key')).toBe('run:r1'))
    expect(head).toBeTruthy()
    expect(screen.getByText('Build it')).toBeTruthy()
    const around = getJson.mock.calls.map(([p]) => p).filter((p) => p.includes('around='))
    expect(around).toHaveLength(3)
  })

  it('opens the addressed knot itself when it holds knots, keeping focus on its head', async () => {
    const heldRun = { ...run, child_count: 1, descendant_count: 1 }
    const step = knot('run:r1/step', 'run', 'Read the spec', '2026-09-03T09:05:00+00:00')
    getJson.mockImplementation(async (path: string) => {
      const url = new URL(path, 'http://hub')
      if (url.pathname.endsWith('/thread/knot')) return { knot: heldRun, ancestors: ['document:d1', 'task:t1'] }
      const under = url.searchParams.get('under')
      if (under === 'document:d1') return page([tsk])
      if (under === 'task:t1') return page([heldRun])
      if (under === 'run:r1') return page([step])
      return page([doc])
    })
    const { container } = mount({ knot: 'run:r1' })
    await screen.findByText('Read the spec')
    for (const key of ['document:d1', 'task:t1', 'run:r1']) {
      expect(container.querySelector(`[data-knot-key="${key}"]`)?.getAttribute('data-open')).toBe('true')
    }
    await waitFor(() => expect(document.activeElement?.closest('[data-knot-key]')?.getAttribute('data-knot-key')).toBe('run:r1'))
  })

  it('jump to the beginning asks for the first page', async () => {
    getJson.mockImplementation(async (path: string) =>
      path.includes('first=true') ? page([doc]) : page([tsk], { has_before: true }),
    )
    mount()
    await screen.findByText('Build it')
    fireEvent.click(screen.getByText('Jump to the beginning'))
    await screen.findByText('First change')
  })
})

describe('ThreadScreen chapters and the Weave button', () => {
  const chapter = (key: string, title: string, start: string, summary: string): ThreadKnot => ({
    ...knot(key, 'chapter', title, start, 1), word: 'Chapter', actors: ['manager'], summary,
  })
  const one = chapter('chapter:ch-1', 'Foundations', '2026-03-07T09:00:00+00:00', 'The first months.')
  const two = chapter('chapter:ch-2', 'The Hub arrives', '2026-10-01T09:00:00+00:00', 'Specs and flows.')

  it('shows each chapter with title, summary, span and author, and opens one into its knots', async () => {
    getJson.mockImplementation(async (path: string) => {
      const under = new URL(path, 'http://hub').searchParams.get('under')
      return under === 'chapter:ch-1' ? page([doc]) : page([one, two])
    })
    mount()
    await screen.findByText('Foundations')
    expect(screen.getByText('The first months.')).toBeTruthy()
    expect(screen.getByText('Specs and flows.')).toBeTruthy()
    expect(screen.getAllByText('manager')).toHaveLength(2)
    const titles = screen.getAllByText(/Foundations|The Hub arrives/).map((n) => n.textContent)
    expect(titles).toEqual(['Foundations', 'The Hub arrives'])
    fireEvent.click(screen.getByText('Foundations'))
    await screen.findByText('First change')
  })

  it('draws a chapter from before the Hub with release tags and commits beneath', async () => {
    const release = { ...knot('tag:ch-1|v1.0.0', 'release', 'v1.0.0', '2026-03-08T09:00:00+00:00', 1), word: 'Release' }
    const commit = { ...knot('commit:ch-1|abc', 'commit', 'Add the CLI', '2026-03-08T09:00:00+00:00'), word: 'Commit', actors: ['Ada'] }
    getJson.mockImplementation(async (path: string) => {
      const under = new URL(path, 'http://hub').searchParams.get('under')
      if (under === 'chapter:ch-1') return page([release])
      if (under === release.key) return page([commit])
      return page([one])
    })
    mount()
    fireEvent.click(await screen.findByText('Foundations'))
    fireEvent.click(await screen.findByText('v1.0.0'))
    await screen.findByText('Add the CLI')
    expect(screen.getByText('Ada')).toBeTruthy()
  })

  it('offers Weave the thread only while the feed says the job is on, and presses it', async () => {
    getJson.mockImplementation(async () => page([one], { can_weave: false }))
    const off = mount()
    await screen.findByText('Foundations')
    expect(screen.queryByText('Weave the thread')).toBeNull()
    off.unmount()

    getJson.mockImplementation(async () => page([one], { can_weave: true }))
    postJson.mockResolvedValue({ started: true })
    mount()
    fireEvent.click(await screen.findByText('Weave the thread'))
    await waitFor(() => expect(postJson).toHaveBeenCalledWith('/api/v1/projects/proj-a/manager/jobs/chapters/run'))
    await screen.findByText(/Weaving the thread/)
  })

  it('refreshes when a chapters version is saved, and not for another project', async () => {
    // task-219208c952ad: it listened for `job_fired`, which no manager firing sends; a save says
    // `chapters_updated` (hub/hub/chapters.py), stamped with its project as the stream does.
    mount()
    await screen.findByText('First change')
    const surfaceReads = () => getJson.mock.calls.filter(([path]) => !String(path).includes('under=')).length
    const before = surfaceReads()

    sse.handler?.({ type: 'chapters_updated', data: { project_id: 'proj-b', version: 2 } })
    await new Promise((resolve) => setTimeout(resolve, 600))
    expect(surfaceReads()).toBe(before)

    sse.handler?.({ type: 'chapters_updated', data: { project_id: 'proj-a', version: 2 } })
    await waitFor(() => expect(surfaceReads()).toBeGreaterThan(before))
  })

  it('says why a press was refused', async () => {
    getJson.mockImplementation(async () => page([one], { can_weave: true }))
    postJson.mockRejectedValue(new Error('The chapters job has no runner.'))
    mount()
    fireEvent.click(await screen.findByText('Weave the thread'))
    await screen.findByText('The chapters job has no runner.')
  })
})

describe('thread helpers', () => {
  it('joins an earlier page without drawing a knot twice, in time order', () => {
    const joined = joinPage(level([tsk, run]), { ...level([doc, tsk]), hasBefore: true, beforeCursor: 'c' }, 'before')
    expect(joined.knots.map((k) => k.key)).toEqual(['document:d1', 'task:t1', 'run:r1'])
    expect(joined.hasBefore).toBe(true)
  })

  it('a refresh at the present end replaces what the newest page covers and keeps what lies before', () => {
    const changed = { ...run, title: 'Builder finished' }
    const fresh = refreshEnd(level([doc, tsk, run]), level([changed]))
    expect(fresh.knots.map((k) => k.title)).toEqual(['First change', 'Build it', 'Builder finished'])
  })

  it('a run link leads to its conversation', () => {
    expect(linkTarget({ object: 'run', id: 'r', agent: 'builder', conversation: 'conv-1' })).toEqual({
      to: 'conversation', agent: 'builder', conversation: 'conv-1',
    })
  })

  it('the tab follows Overview and its address survives the URL', () => {
    expect(PROJECT_TABS.indexOf('thread')).toBe(PROJECT_TABS.indexOf('overview') + 1)
    const search = serializeDestination(threadDestination('p', 'task:t1'))
    expect(parseDestination(search)).toEqual(threadDestination('p', 'task:t1'))
  })
})
