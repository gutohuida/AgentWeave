import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
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
const sse = vi.hoisted(() => ({ handlers: [] as Array<(event: { type: string; data: unknown }) => void> }))
vi.mock('@/hooks/useSSE', () => ({
  useSSE: (handler?: (event: { type: string; data: unknown }) => void) => {
    if (handler) sse.handlers.push(handler)
  },
}))
const emit = (type: string, data: unknown) => sse.handlers.forEach((h) => h({ type, data }))

const WORD: Partial<Record<ThreadKnot['kind'], string>> = {
  document: 'Document', task: 'Task', run: 'Run', chapter: 'Chapter', conversation: 'Conversation',
}
function knot(key: string, kind: ThreadKnot['kind'], title: string, start: string, children = 0, extra: Partial<ThreadKnot> = {}): ThreadKnot {
  return {
    key, address: key, kind, fold_of: null, word: WORD[kind] ?? 'Run',
    title, start, end: start, actors: ['Operator'], child_count: children, descendant_count: children, link: null, ...extra,
  }
}
const cursor = (k: ThreadKnot) => `${k.start}|${k.key}`
/** A page as `GET /thread` answers it: oldest first, cursors from its first and last knot. */
const page = (knots: ThreadKnot[], extra: Record<string, unknown> = {}) => ({
  knots, total: knots.length, has_before: false, has_after: false,
  before_cursor: knots[0] ? cursor(knots[0]) : null,
  after_cursor: knots.length ? cursor(knots[knots.length - 1]!) : null,
  under: 'surface', ...extra,
})
const level = (knots: ThreadKnot[]): LoadedLevel => ({
  knots, hasBefore: false, hasAfter: false, beforeCursor: null, afterCursor: null,
})
const day = (n: number) => new Date(Date.UTC(2026, 2, 7) + n * 86_400_000).toISOString().slice(0, 10)
const chapter = (n: number, holds = 3): ThreadKnot =>
  knot(`chapter:ch-${n}`, 'chapter', `Chapter title ${n}`, `${day(n * 2)}T00:00:00+00:00`, holds, {
    end: `${day(n * 2)}T23:59:59+00:00`, actors: ['manager'], summary: `What happened in ${n}.`,
  })
const inside = (n: number, i: number): ThreadKnot =>
  knot(`conversation:c${n}-${i}`, 'conversation', `Conversation ${n}.${i}`, `${day(n * 2)}T0${i}:00:00+00:00`, 0, {
    actors: ['Builder'], link: { object: 'conversation', id: `c${n}-${i}`, agent: 'Builder' },
  })

const bead = (key: string) => {
  const found = Array.from(document.querySelectorAll<HTMLElement>('[data-slot="loom-bead"]')).filter((el) => el.dataset.key === key)
  return found[0]
}
const surfaceBeads = () => Array.from(document.querySelectorAll<HTMLElement>('.aw-loom-main [data-slot="loom-bead"]'))
/** The panel's kind line, as read: 'Chapter 17 of 17'. */
const position = () => {
  const kind = document.querySelector('.aw-loom-detail-kind')
  const of = kind?.querySelector('.aw-loom-detail-of')?.textContent ?? ''
  return `${(kind?.textContent ?? '').slice(0, -of.length || undefined)} ${of}`.trim()
}
const selectedOnSurface = () => surfaceBeads().find((el) => el.getAttribute('aria-selected') === 'true')?.dataset.key

beforeEach(() => {
  sse.handlers = []
  useConfigStore.setState({ apiKey: 'aw_live_test', hubUrl: 'http://hub', isConfigured: true, selectedProjectId: 'proj-a' })
  postJson.mockReset()
  getJson.mockReset()
})
afterEach(() => {
  vi.useRealTimers()
})

/** Routes for a project of `n` chapters, each holding three conversations, plus one newer loose knot. */
function chaptered(n: number, extra: Record<string, unknown> = {}) {
  const chapters = Array.from({ length: n }, (_, i) => chapter(i + 1))
  const loose = knot('conversation:loose', 'conversation', 'A newer conversation', '2026-10-25T09:00:00+00:00')
  const surface = [...chapters, loose]
  getJson.mockImplementation(async (path: string) => {
    const url = new URL(path, 'http://hub')
    if (url.pathname.endsWith('/agents')) return [{ name: 'Builder', color_index: 3 }]
    const under = url.searchParams.get('under')
    if (under?.startsWith('chapter:ch-')) {
      const c = Number(under.slice('chapter:ch-'.length))
      return page([1, 2, 3].map((i) => inside(c, i)), { under })
    }
    return page(surface, extra)
  })
  return { chapters, loose, surface }
}

function mount(props: Partial<React.ComponentProps<typeof ThreadScreen>> = {}) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ThreadScreen projectId="proj-a" knot={null} onAddress={() => undefined} onOpenLink={() => undefined} {...props} />
    </QueryClientProvider>,
  )
}

describe('ThreadScreen: the loom', () => {
  it('opens on the newest surface knot, oldest at the left, and the beginning selects chapter 1', async () => {
    const { chapters, loose } = chaptered(17)
    const onAddress = vi.fn()
    mount({ onAddress })
    await waitFor(() => expect(selectedOnSurface()).toBe(loose.key))
    expect(getJson.mock.calls.find(([p]) => String(p).includes('/thread?'))?.[0]).toMatch(/^\/api\/v1\/projects\/proj-a\/thread\?limit=40$/)
    // Left to right in the route's order, evenly spaced.
    const lefts = surfaceBeads().map((el) => parseFloat(el.style.left))
    expect(surfaceBeads().map((el) => el.dataset.key)).toEqual([...chapters.map((c) => c.key), loose.key])
    const steps = new Set(lefts.slice(1).map((l, i) => l - lefts[i]!))
    expect([...steps]).toEqual([196])
    expect(screen.getByText('17 chapters')).toBeTruthy()
    expect(screen.getByText(/1 newer knot not in a chapter yet/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /The beginning/ }))
    expect(selectedOnSurface()).toBe(chapters[0]!.key)
    expect(onAddress).toHaveBeenLastCalledWith(chapters[0]!.key)
    expect(position()).toBe('Chapter 1 of 17')
  })

  it('reads what a chosen chapter holds and draws it as the smaller thread', async () => {
    const { chapters } = chaptered(3)
    mount()
    await waitFor(() => expect(surfaceBeads()).toHaveLength(4))
    fireEvent.click(bead(chapters[1]!.key)!)
    await waitFor(() => expect(document.querySelectorAll('.aw-loom-inner [data-slot="loom-bead"]')).toHaveLength(3))
    expect(getJson.mock.calls.some(([p]) => String(p).includes('under=chapter%3Ach-2') && String(p).includes('first=true'))).toBe(true)
    // The registered colour of the agent in it, not one by order of appearance.
    await waitFor(() => {
      const fresh = Array.from(document.querySelectorAll<HTMLElement>('.aw-loom-actor')).find((el) => el.textContent === 'Builder')
      expect(fresh?.style.getPropertyValue('--actor')).toBe('var(--agent-4)')
    })
  })

  it('counts and places what a knot holds over all of it, not the 40 knots a page loads', async () => {
    // QA, 134c767: the panel read 'Made of: 40 documents' and 'Document 3 of 40' for a knot holding
    // 41, and the header counted loaded chapters. The route pages every level by 40, as the Hub does.
    const chapters = Array.from({ length: 45 }, (_, i) => chapter(i + 1))
    const loose = knot('conversation:loose', 'conversation', 'A newer conversation', '2026-10-25T09:00:00+00:00')
    const surface = [...chapters, loose]
    const held = [
      ...Array.from({ length: 47 }, (_, i) =>
        knot(`conversation:big-${i + 1}`, 'conversation', `Talk ${i + 1}`, `${day(90)}T00:${String(i).padStart(2, '0')}:00+00:00`, 0, {
          actors: [i === 46 ? 'Reviewer' : 'Builder'],
        }),
      ),
      knot('document:big', 'document', 'The design', `${day(90)}T01:00:00+00:00`),
    ]
    const levels: Record<string, ThreadKnot[]> = { surface, 'chapter:ch-45': held }
    // What the Hub adds to every knot and page: figures over the whole level.
    const placed = (all: ThreadKnot[]) =>
      all.map((k) => ({ ...k, place: { n: all.filter((o) => o.kind === k.kind).indexOf(k) + 1, of: all.filter((o) => o.kind === k.kind).length } }))
    const big = { ...chapters[44]!, child_count: 48, descendant_count: 48, made_of: [
      { kind: 'conversation' as const, word: 'Conversation', count: 47 }, { kind: 'document' as const, word: 'Document', count: 1 },
    ], people: ['manager', 'Builder', 'Reviewer'] }
    levels.surface = surface.map((k) => (k.key === big.key ? big : k))
    getJson.mockImplementation(async (path: string) => {
      const url = new URL(path, 'http://hub')
      if (url.pathname.endsWith('/agents')) return [{ name: 'Builder', color_index: 3 }]
      const under = url.searchParams.get('under') ?? 'surface'
      const all = placed(levels[under] ?? [])
      const limit = Number(url.searchParams.get('limit'))
      const after = url.searchParams.get('after')
      const before = url.searchParams.get('before')
      const at = (c: string) => all.findIndex((k) => cursor(k) === c)
      const lo = url.searchParams.get('first') ? 0 : after ? at(after) + 1 : before ? Math.max(0, at(before) - limit) : Math.max(0, all.length - limit)
      const hi = before ? at(before) : Math.min(all.length, lo + limit)
      const counts: Record<string, number> = {}
      for (const k of all) counts[k.kind] = (counts[k.kind] ?? 0) + 1
      const spanned = all.filter((k) => k.kind === 'chapter')
      return page(all.slice(lo, hi), {
        under, total: all.length, has_before: lo > 0, has_after: hi < all.length, counts,
        span: { start: spanned[0]?.start ?? all[0]!.start, end: spanned[spanned.length - 1]?.end ?? all[all.length - 1]!.end },
      })
    })
    mount()
    await waitFor(() => expect(surfaceBeads()).toHaveLength(40))
    expect(screen.getByText('45 chapters')).toBeTruthy()
    expect(screen.getByText(/1 newer knot not in a chapter yet/)).toBeTruthy()
    // The span the chapters cover, not the loose knot after them (FR-3).
    expect(document.querySelector('.aw-loom-bar-span')?.textContent).toMatch(/^Mar 9 to Jun 5/)

    fireEvent.click(bead(big.key)!)
    expect(position()).toBe('Chapter 45 of 45')
    await waitFor(() => expect(document.querySelectorAll('.aw-loom-inner [data-slot="loom-bead"]')).toHaveLength(40))
    const panel = document.querySelector('.aw-loom-detail')!.textContent ?? ''
    expect(panel).toContain('48 knots')
    expect(panel).toContain('47 conversations')
    expect(panel).toContain('1 document')
    expect(Array.from(document.querySelectorAll('.aw-loom-actor')).map((el) => el.textContent)).toEqual(['manager', 'Builder', 'Reviewer'])

    fireEvent.click(document.querySelectorAll<HTMLElement>('.aw-loom-inner [data-slot="loom-bead"]')[2]!)
    expect(position()).toBe('Conversation 3 of 47')
  })

  it('the panel steps to the knot after, and has no after on the last knot', async () => {
    // FR-4: 'the knot before and after it' on its own thread. Here chapter 17 is the newest surface
    // knot; where a newer knot lies in no chapter, 'after' on chapter 17 goes on to it.
    const { chapters, loose } = chaptered(17)
    getJson.mockImplementation(async (path: string) =>
      new URL(path, 'http://hub').pathname.endsWith('/agents') ? [] : page(chapters),
    )
    mount()
    await waitFor(() => expect(surfaceBeads()).toHaveLength(17))
    expect(loose.key).not.toBe(chapters[16]!.key)
    fireEvent.click(bead(chapters[15]!.key)!)
    fireEvent.click(screen.getByRole('button', { name: 'The knot after' }))
    expect(selectedOnSurface()).toBe(chapters[16]!.key)
    expect(position()).toBe('Chapter 17 of 17')
    expect(screen.getByRole('button', { name: 'The knot after' })).toBeDisabled()
  })

  it('Right, Enter, Escape: chapter 11, its first knot, chapter 11 again, focus following each time', async () => {
    const { chapters } = chaptered(17)
    mount()
    await waitFor(() => expect(surfaceBeads()).toHaveLength(18))
    fireEvent.click(bead(chapters[9]!.key)!)
    bead(chapters[9]!.key)!.focus()

    fireEvent.keyDown(document.activeElement!, { key: 'ArrowRight' })
    expect(selectedOnSurface()).toBe(chapters[10]!.key)
    expect((document.activeElement as HTMLElement).dataset.key).toBe(chapters[10]!.key)
    await waitFor(() => expect(document.querySelectorAll('.aw-loom-inner [data-slot="loom-bead"]')).toHaveLength(3))

    fireEvent.keyDown(document.activeElement!, { key: 'Enter' })
    await waitFor(() => expect(position()).toBe('Conversation 1 of 3'))
    await waitFor(() => expect((document.activeElement as HTMLElement).dataset.key).toBe('conversation:c11-1'))
    expect(document.activeElement?.closest('.aw-loom-inner')).toBeTruthy()

    fireEvent.keyDown(document.activeElement!, { key: 'Escape' })
    await waitFor(() => expect(position()).toBe('Chapter 11 of 17'))
    await waitFor(() => expect((document.activeElement as HTMLElement).dataset.key).toBe(chapters[10]!.key))
    expect(document.activeElement?.closest('.aw-loom-main')).toBeTruthy()
  })

  it('a drag along the thread scrolls it and does not choose the knot it started on', async () => {
    const { chapters, loose } = chaptered(5)
    mount()
    await waitFor(() => expect(selectedOnSurface()).toBe(loose.key))
    const scroller = document.querySelector<HTMLElement>('.aw-loom-main .aw-loom')!
    scroller.scrollLeft = 400
    const start = bead(chapters[2]!.key)!
    fireEvent.pointerDown(start, { button: 0, clientX: 500 })
    fireEvent.pointerMove(start, { clientX: 300 })
    fireEvent.pointerUp(start, { clientX: 300 })
    fireEvent.click(start)
    expect(scroller.scrollLeft).toBe(600)
    expect(selectedOnSurface()).toBe(loose.key)
  })

  it('opens an address three levels below a chapter with the trail, in view and focused', async () => {
    const ch = chapter(4, 1)
    const conv = knot('conversation:c', 'conversation', 'The conversation', '2026-03-15T09:00:00+00:00', 1)
    const turn = knot('run:turn', 'run', 'A turn', '2026-03-15T09:10:00+00:00', 2)
    const run = knot('run:r1', 'run', 'Builder worked', '2026-03-15T09:11:00+00:00')
    const sibling = knot('run:r2', 'run', 'Builder checked', '2026-03-15T09:12:00+00:00')
    getJson.mockImplementation(async (path: string) => {
      const url = new URL(path, 'http://hub')
      if (url.pathname.endsWith('/agents')) return []
      if (url.pathname.endsWith('/thread/knot')) return { knot: run, ancestors: [ch.key, conv.key, turn.key] }
      const under = url.searchParams.get('under')
      if (under === ch.key) return page([conv], { under })
      if (under === conv.key) return page([turn], { under })
      if (under === turn.key) return page([run, sibling], { under })
      return page([chapter(3), ch, chapter(5)])
    })
    mount({ knot: 'run:r1' })
    await waitFor(() => expect(position()).toBe('Run 1 of 2'))
    const crumbs = screen.getAllByRole('button').filter((b) => b.getAttribute('data-slot') === 'loom-crumb')
    expect(crumbs.map((c) => c.textContent)).toEqual(['Chapter title 4', 'The conversation', 'A turn'])
    expect(selectedOnSurface()).toBe(ch.key)
    const inner = Array.from(document.querySelectorAll<HTMLElement>('.aw-loom-inner [data-slot="loom-bead"]'))
    expect(inner.find((el) => el.getAttribute('aria-selected') === 'true')?.dataset.key).toBe('run:r1')
    await waitFor(() => expect((document.activeElement as HTMLElement).dataset.key).toBe('run:r1'))
    const around = getJson.mock.calls.map(([p]) => String(p)).filter((p) => p.includes('around='))
    expect(around).toHaveLength(4)
    // The trail selects the chapter again.
    fireEvent.click(crumbs[0]!)
    expect(position()).toBe('Chapter 2 of 3')
  })

  it('asks for the older page within one screen width of the left end and keeps the view where it was', async () => {
    // 165 surface knots, the newest 40 loaded, the 40th selected.
    const all = Array.from({ length: 165 }, (_, i) =>
      knot(`run:${String(i).padStart(3, '0')}`, 'run', `Run ${i}`, new Date(Date.UTC(2026, 5, 1) + i * 3_600_000).toISOString()),
    )
    getJson.mockImplementation(async (path: string) => {
      const url = new URL(path, 'http://hub')
      if (url.pathname.endsWith('/agents')) return []
      const before = url.searchParams.get('before')
      if (before) {
        const at = all.findIndex((k) => cursor(k) === before)
        const shown = all.slice(Math.max(0, at - 40), at)
        return page(shown, { total: 165, has_before: at - 40 > 0, has_after: true })
      }
      return page(all.slice(125), { total: 165, has_before: true })
    })
    const width = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(1000)
    mount()
    await waitFor(() => expect(selectedOnSurface()).toBe('run:164'))
    expect(screen.getByText('165 knots')).toBeTruthy()
    const scroller = document.querySelector<HTMLElement>('.aw-loom-main .aw-loom')!
    const olderAsked = () => getJson.mock.calls.filter(([p]) => String(p).includes('before=')).map(([p]) => String(p))

    scroller.scrollLeft = 5000
    fireEvent.scroll(scroller)
    expect(olderAsked()).toHaveLength(0)

    scroller.scrollLeft = 600
    fireEvent.scroll(scroller)
    await waitFor(() => expect(surfaceBeads()).toHaveLength(80))
    expect(olderAsked()[0]).toContain(`before=${encodeURIComponent(cursor(all[125]!))}`)
    expect(selectedOnSurface()).toBe('run:164')
    // Forty knots joined on the left: the view moved right by as much, so nothing in view moved.
    expect(scroller.scrollLeft).toBe(600 + 40 * 196)
    expect(surfaceBeads()[0]!.dataset.key).toBe('run:085')
    width.mockRestore()
  })

  it('takes new activity onto the present end without moving the selection', async () => {
    const { chapters, surface } = chaptered(3)
    mount()
    await waitFor(() => expect(surfaceBeads()).toHaveLength(4))
    fireEvent.click(screen.getByRole('button', { name: /The beginning/ }))
    expect(selectedOnSurface()).toBe(chapters[0]!.key)

    const fresh = knot('run:new', 'run', 'Builder started', '2026-10-25T10:00:00+00:00')
    getJson.mockImplementation(async (path: string) =>
      new URL(path, 'http://hub').pathname.endsWith('/agents') ? [] : page([...surface, fresh]),
    )
    emit('run_started', { project_id: 'proj-b' })
    await new Promise((resolve) => setTimeout(resolve, 600))
    expect(surfaceBeads()).toHaveLength(4)

    emit('run_started', { project_id: 'proj-a' })
    await waitFor(() => expect(surfaceBeads()).toHaveLength(5))
    expect(surfaceBeads()[4]!.dataset.key).toBe('run:new')
    expect(selectedOnSurface()).toBe(chapters[0]!.key)
  })

  it('refreshes when a chapters version is saved, and not for another project', async () => {
    // task-219208c952ad: it listened for `job_fired`, which no manager firing sends; a save says
    // `chapters_updated` (hub/hub/chapters.py), stamped with its project as the stream does.
    chaptered(2)
    mount()
    await waitFor(() => expect(surfaceBeads()).toHaveLength(3))
    const surfaceReads = () => getJson.mock.calls.filter(([path]) => String(path).includes('/thread?') && !String(path).includes('under=')).length
    const before = surfaceReads()
    emit('chapters_updated', { project_id: 'proj-b', version: 2 })
    await new Promise((resolve) => setTimeout(resolve, 600))
    expect(surfaceReads()).toBe(before)
    emit('chapters_updated', { project_id: 'proj-a', version: 2 })
    await waitFor(() => expect(surfaceReads()).toBeGreaterThan(before))
  })

  it('says the thread could not be read when the route fails', async () => {
    getJson.mockImplementation(async (path: string) => {
      if (new URL(path, 'http://hub').pathname.endsWith('/agents')) return []
      throw new Error('500 Internal Server Error')
    })
    mount()
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe('The thread could not be read. Reload to try again.')
  })

  it('says when the agents cannot be read and still draws the thread, chips uncoloured', async () => {
    const { loose } = chaptered(3)
    const base = getJson.getMockImplementation()!
    getJson.mockImplementation(async (path: string) => {
      if (new URL(path, 'http://hub').pathname.endsWith('/agents')) throw new Error('500 Internal Server Error')
      return base(path)
    })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ThreadScreen projectId="proj-a" knot={null} onAddress={() => undefined} onOpenLink={() => undefined} />
      </QueryClientProvider>,
    )
    expect(
      await screen.findByText('The agents could not be read, so they are shown without their colours.'),
    ).toBeTruthy()
    expect(screen.getAllByText(loose.title).length).toBeGreaterThan(0)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('offers Weave the thread only while the feed says the job is on, and presses it', async () => {
    chaptered(1, { can_weave: false })
    const off = mount()
    await waitFor(() => expect(surfaceBeads()).toHaveLength(2))
    expect(screen.queryByText('Weave the thread')).toBeNull()
    off.unmount()

    chaptered(1, { can_weave: true })
    postJson.mockResolvedValue({ started: true })
    mount()
    fireEvent.click(await screen.findByText('Weave the thread'))
    await waitFor(() => expect(postJson).toHaveBeenCalledWith('/api/v1/projects/proj-a/manager/jobs/chapters/run'))
    await screen.findByText(/Weaving the thread/)
  })

  it('says why a weave was refused', async () => {
    chaptered(1, { can_weave: true })
    postJson.mockRejectedValue(new Error('The chapters job has no runner.'))
    mount()
    fireEvent.click(await screen.findByText('Weave the thread'))
    await screen.findByText('The chapters job has no runner.')
  })

  it('opens what a knot stands for through the panel', async () => {
    const { chapters } = chaptered(2)
    const onOpenLink = vi.fn()
    mount({ onOpenLink })
    await waitFor(() => expect(surfaceBeads()).toHaveLength(3))
    fireEvent.click(bead(chapters[0]!.key)!)
    await waitFor(() => expect(document.querySelectorAll('.aw-loom-inner [data-slot="loom-bead"]')).toHaveLength(3))
    await act(async () => {
      fireEvent.click(bead('conversation:c1-2')!)
    })
    fireEvent.click(screen.getByRole('button', { name: /Open the conversation/ }))
    expect(onOpenLink).toHaveBeenCalledWith({ object: 'conversation', id: 'c1-2', agent: 'Builder' })
    expect(linkTarget(onOpenLink.mock.calls[0]![0])).toEqual({ to: 'conversation', agent: 'Builder', conversation: 'c1-2' })
  })
})

describe('thread helpers', () => {
  it('joins an earlier page without drawing a knot twice, in the route order', () => {
    const doc = knot('document:d1', 'document', 'First change', '2026-09-01T09:00:00+00:00', 1)
    const tsk = knot('task:t1', 'task', 'Build it', '2026-09-02T09:00:00+00:00', 1)
    const run = knot('run:r1', 'run', 'Builder worked', '2026-09-03T09:00:00+00:00')
    const joined = joinPage(level([tsk, run]), { ...level([doc, tsk]), hasBefore: true, beforeCursor: 'c' }, 'before')
    expect(joined.knots.map((k) => k.key)).toEqual(['document:d1', 'task:t1', 'run:r1'])
    expect(joined.hasBefore).toBe(true)
  })

  it('keeps a chaptered surface in position order: a loose knot older than a chapter stays after it', () => {
    const ch = chapter(1)
    const older = knot('conversation:early', 'conversation', 'Early but loose', '2026-01-01T09:00:00+00:00')
    const later = knot('conversation:later', 'conversation', 'Later', '2026-11-01T09:00:00+00:00')
    const joined = joinPage(level([older]), level([later]), 'after')
    expect(joinPage(level([older]), level([ch]), 'before').knots.map((k) => k.key)).toEqual([ch.key, older.key])
    expect(joined.knots.map((k) => k.key)).toEqual([older.key, later.key])
  })

  it('a refresh at the present end replaces what the newest page covers and keeps what lies before', () => {
    const doc = knot('document:d1', 'document', 'First change', '2026-09-01T09:00:00+00:00', 1)
    const tsk = knot('task:t1', 'task', 'Build it', '2026-09-02T09:00:00+00:00', 1)
    const run = knot('run:r1', 'run', 'Builder worked', '2026-09-03T09:00:00+00:00')
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
