import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { SpecPage } from '@/components/spec/SpecPage'
import { chooseMenuOption } from './support/menuSelect'

/* `the-spec-page-redesigned`, task `wire`: the approved mock's components, fed by the real Hub's
 * routes. The Hub is a stubbed `fetch` that answers each route with the shape the route returns (the
 * list of builds newest first, the coverage rows, the tasks page), so these tests drive the page
 * from the network seam, not from a mocked hook: a hook that cannot read the route fails here. */

vi.mock('@/hooks/useSSE', () => ({
  useSSEConnectionState: () => 'open',
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

const PATH = 'spec/changes/demo/spec.json'
const ROADMAP = 'spec/changes/demo-roadmap/spec.json'
const OTHER = 'spec/changes/other/spec.json'
const DOC_ID = 'spdoc-demo'
const COUNT = 18

const payload = {
  title: 'Demo change',
  kind: 'change-spec',
  summary: 'A demo summary.',
  problem: 'A demo problem.',
  design: 'Short.',
  scope: { in_scope: ['One thing'], non_goals: ['Another thing'] },
  requirements: Array.from({ length: COUNT }, (_, i) => ({
    key: `r${i + 1}`,
    modal: 'MUST',
    statement: `Requirement number ${i + 1} holds.`,
    rationale: null,
  })),
  acceptance_criteria: Array.from({ length: COUNT }, (_, i) => i + 1)
    .filter((n) => n !== 2)
    .map((n) => ({ key: `c${n}`, requirement: `r${n}`, given: `given ${n}`, when: `when ${n}`, then: `then ${n}` })),
  // Declared out of build order on purpose: ship needs build, build needs plan.
  tasks: [
    { key: 'ship', title: 'Ship it', description: 'd', depends_on: ['build'], requirements: ['r3'] },
    { key: 'plan', title: 'Plan it', description: 'd', depends_on: [], requirements: ['r1'] },
    { key: 'build', title: 'Build it', description: 'd', depends_on: ['plan'], requirements: ['r2'] },
  ],
  open_questions: [],
}
const html = `<html><body><script type="application/agentweave-spec+json" id="aw-spec-payload">${JSON.stringify(payload)}</script></body></html>`

interface Hub {
  phase: 'exploring' | 'approved' | 'archived'
  builds: unknown[]
  checkResult: { blocking: unknown[]; warnings: unknown[] }
  checkCalls: number
  tasks: unknown[]
}

let hub: Hub
const build = (over: Record<string, unknown>) => ({
  id: 'build-1',
  state: 'finished',
  driver: 'flow',
  level: 'gated',
  builders: ['Builder'],
  reviewers: ['QA1'],
  lead: null,
  budget_cap_usd: null,
  spent_usd: 52,
  unpriced_turns: 0,
  window_start: null,
  window_end: null,
  landing: 'main',
  loop_id: null,
  stop_reason: null,
  created_at: '2026-10-16T14:02:00Z',
  stopped_at: '2026-10-16T21:28:00Z',
  ...over,
})
const FIGURES: Record<string, unknown> = {
  'build-1': {
    id: 'build-1',
    runs: 23,
    time: { building: 8040, review: 11880, checks: 3120, waiting: 3720 },
    cost: { build: 31.4, review: 20.6, lead: 0 },
  },
  'build-2': {
    id: 'build-2',
    runs: 7,
    time: { building: 1860, review: 240, checks: 360, waiting: 120 },
    cost: { build: 6.2, review: 0, lead: 1.1 },
  },
}

function task(key: string, id: string, status: string, over: Record<string, unknown> = {}) {
  return {
    id,
    project_id: 'proj-test',
    title: key,
    status,
    priority: 'medium',
    created_at: '2026-10-16T14:02:00Z',
    updated: '2026-10-16T14:02:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    spec_document_id: DOC_ID,
    spec_task_key: key,
    assignee: 'Builder',
    build_id: 'build-2',
    ...over,
  }
}

const coverage = (identifier: string, state: string, reason: string | null = null) => ({
  identifier,
  requirement_id: `req-${identifier}`,
  document_id: DOC_ID,
  state,
  integration: 'not_applicable',
  evidence_count: 0,
  accepted_count: 0,
  linked_task_ids: [],
  reason,
})

function route(url: string, init?: RequestInit): unknown {
  const u = new URL(url, 'http://hub.test')
  const p = u.pathname.replace('/api/v1/projects/proj-test', '')
  const method = init?.method ?? 'GET'
  if (p === '/project/specs')
    return {
      specs: [
        { path: ROADMAP, title: 'Demo roadmap', kind: 'roadmap', state: 'filed', parent: null, order: 0, document_id: 'spdoc-rm', phase: 'approved' },
        { path: PATH, title: 'Demo change', kind: 'change-spec', state: 'filed', parent: ROADMAP, order: 2, document_id: DOC_ID, phase: hub.phase },
        { path: OTHER, title: 'Other change', kind: 'change-spec', state: 'filed', parent: ROADMAP, order: 1, document_id: 'spdoc-other', phase: 'approved' },
        { path: 'spec/capabilities/cap/spec.json', title: 'A capability', kind: 'baseline', state: 'filed', parent: null, order: 0, document_id: 'spdoc-cap', phase: 'current' },
      ],
      home: PATH,
      manifest: { state: 'valid', version: 1 },
      missing: [],
      diagnostics: [],
    }
  if (p === '/project/documents') {
    const doc = (id: string, path: string, title: string, kind: string, phase: string, over: Record<string, unknown> = {}) => ({
      id, path, title, kind, phase, rigor: 'contract', content_digest: null, explore_closed: false, updated_at: '2026-10-17T09:00:00Z', ...over,
    })
    return {
      documents: [
        doc('spdoc-rm', ROADMAP, 'Demo roadmap', 'roadmap', 'approved'),
        doc(DOC_ID, PATH, 'Demo change', 'change-spec', hub.phase),
        doc('spdoc-other', OTHER, 'Other change', 'change-spec', 'approved', { build: { id: 'build-9', done: 2, total: 6 } }),
        doc('spdoc-cap', 'spec/capabilities/cap/spec.json', 'A capability', 'capability', 'current'),
      ],
    }
  }
  if (p === '/project/spec' && u.searchParams.get('path') === PATH)
    return { path: PATH, content: html, updated_at: '2026-10-17T09:00:00Z', content_version: 'v1', builds: hub.builds, roadmap_slice: { document: ROADMAP, slice: 'demo' } }
  if (p === '/project/spec/coverage')
    return {
      requirements: [
        coverage('FR-1', 'verified'),
        coverage('FR-2', 'evidence_awaiting_review'),
        coverage('FR-3', 'in_progress', 'held evidence only'),
        ...Array.from({ length: COUNT - 3 }, (_, i) => coverage(`FR-${i + 4}`, 'not_started')),
      ],
      diagnostics: [],
      totals: {},
      integration: {},
      unserved: [],
    }
  if (p === '/tasks') return { tasks: hub.tasks, total: hub.tasks.length, has_more: false }
  if (p === '/agents') return [{ name: 'Builder', status: 'idle', message_count: 0, active_task_count: 0 }]
  if (p === '/project/documents/check' && method === 'POST') {
    hub.checkCalls += 1
    return { id: DOC_ID, path: PATH, phase: 'exploring', ready: hub.checkResult.blocking.length === 0, content_version: 'v1', ...hub.checkResult }
  }
  const figures = /^\/project\/builds\/([^/]+)\/figures$/.exec(p)
  if (figures) return FIGURES[figures[1]!] ?? null
  if (p === '/loops') return []
  return undefined
}

function installHub() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const body = route(url, init)
      if (body === undefined) return new Response(JSON.stringify({ detail: 'not stubbed' }), { status: 404 })
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }),
  )
}

/** jsdom has no layout. A position is a hundred pixels per anchor in document order, less the
 *  scroller's offset, and `scrollTo` moves the offset and fires `scroll`, as a browser would. */
function installLayout() {
  // jsdom has no CSS.escape, which the page's jump uses to find an anchor.
  const css = ((globalThis as { CSS?: Record<string, unknown> }).CSS ??= {})
  css.escape ??= (v: string) => v
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
    const el = this as HTMLElement
    const root = el.closest('.aw-sp-scroll') as HTMLElement | null
    let top = 0
    if (el.dataset.anchor && root) {
      const all = Array.from(root.querySelectorAll('[data-anchor]'))
      top = all.indexOf(el) * 100 - (root.scrollTop || 0)
    }
    return { top, bottom: top + 90, left: 0, right: 100, width: 100, height: 90, x: 0, y: top, toJSON: () => ({}) } as DOMRect
  })
  Element.prototype.scrollTo = function (this: HTMLElement, arg?: ScrollToOptions | number) {
    Object.defineProperty(this, 'scrollTop', { value: typeof arg === 'object' ? (arg.top ?? 0) : 0, configurable: true, writable: true })
    this.dispatchEvent(new Event('scroll'))
  } as typeof Element.prototype.scrollTo
}

let queryClient: QueryClient
function renderPage(document: string | null = PATH) {
  const onOpenDocument = vi.fn()
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <SpecPage document={document} onOpenDocument={onOpenDocument} />
    </QueryClientProvider>,
  )
  return { ...utils, onOpenDocument }
}

const anchor = (id: string) => document.querySelector(`[data-anchor="${id}"]`) as HTMLElement | null

beforeEach(() => {
  cleanup()
  localStorage.clear()
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  useConfigStore.setState({ apiKey: 'aw_live_TESTKEY', hubUrl: 'http://hub.test', selectedProjectId: 'proj-test', isConfigured: true, bootstrapState: 'ready', mode: 'light' })
  hub = { phase: 'exploring', builds: [], checkResult: { blocking: [], warnings: [] }, checkCalls: 0, tasks: [] }
  installHub()
  installLayout()
})
afterEach(() => vi.unstubAllGlobals())

describe('rendered-natively (FR-3)', () => {
  it('draws the requirements and criteria as app components, not a frame, and a filter hides them without reloading', async () => {
    hub.phase = 'approved'
    const user = userEvent.setup()
    const { container } = renderPage()
    await waitFor(() => expect(anchor('FR-1')).toBeTruthy())
    expect(container.querySelector('iframe')).toBeNull()
    expect(within(anchor('FR-1')!).getByText('Requirement number 1 holds.')).toBeInTheDocument()
    expect(within(anchor('FR-1')!).getByText(/given 1/)).toBeInTheDocument()
    const frames = vi.mocked(fetch).mock.calls.length

    // FR-5: only the requirements awaiting evidence review show.
    await chooseMenuOption(user, 'Requirements by evidence', /Awaiting review/)
    expect(anchor('FR-2')).toBeTruthy()
    expect(anchor('FR-1')).toBeNull()
    expect(vi.mocked(fetch).mock.calls.length).toBe(frames)
  })

  it('shows a held requirement as held, not as rejected', async () => {
    hub.phase = 'approved'
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(anchor('FR-3')).toBeTruthy())
    await chooseMenuOption(user, 'Requirements by evidence', /Held/)
    expect(anchor('FR-3')).toBeTruthy()
    expect(anchor('FR-2')).toBeNull()
  })
})

describe('within-document-filter-order (FR-5)', () => {
  it('lists tasks in dependency order whatever order the document declared them', async () => {
    hub.phase = 'approved'
    hub.tasks = [task('ship', 't3', 'pending'), task('plan', 't1', 'approved'), task('build', 't2', 'in_progress')]
    renderPage()
    await waitFor(() => expect(anchor('task-ship')).toBeTruthy())
    const order = Array.from(document.querySelectorAll('[data-anchor^="task-"]')).map((el) => (el as HTMLElement).dataset.anchor)
    expect(order).toEqual(['task-plan', 'task-build', 'task-ship'])
  })
})

describe('one-clear-next-action and check-shows-results-in-place (FR-1, FR-2)', () => {
  it('offers only Check while the document is written, and a blocking gap shows beside its requirement without changing the phase', async () => {
    hub.checkResult = {
      blocking: [{ code: 'requirement_without_criterion', where: 'requirements[1]', message: "'r2' has no acceptance criterion" }],
      warnings: [{ code: 'task_without_reviewer', where: 'tasks[0]', message: 'No reviewer is named for this task' }],
    }
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(anchor('FR-2')).toBeTruthy())
    const header = document.querySelector('.aw-sp-head') as HTMLElement
    expect(within(header).getByRole('button', { name: 'Check' })).toBeInTheDocument()
    expect(within(header).queryByRole('button', { name: /^Approve/ })).toBeNull()
    expect(within(header).queryByRole('button', { name: /^Build/ })).toBeNull()

    await user.click(within(header).getByRole('button', { name: 'Check' }))
    await waitFor(() => expect(within(anchor('FR-2')!).getByText(/has no acceptance criterion/)).toBeInTheDocument())
    expect(within(anchor('task-ship')!).getByText(/No reviewer is named/)).toBeInTheDocument()
    expect(header.querySelector('.aw-sp-phase')).toHaveTextContent('Writing')
    expect(hub.checkCalls).toBe(1)
  })

  it('offers Approve as the primary action once a check finds nothing', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(anchor('FR-1')).toBeTruthy())
    const header = document.querySelector('.aw-sp-head') as HTMLElement
    await user.click(within(header).getByRole('button', { name: 'Check' }))
    await waitFor(() => expect(within(header).getByRole('button', { name: /^Approve/ })).toBeInTheDocument())
    expect(within(header).getByText('Nothing blocks approval')).toBeInTheDocument()
  })

  it('offers Build once approved', async () => {
    hub.phase = 'approved'
    renderPage()
    const header = await waitFor(() => {
      const h = document.querySelector('.aw-sp-head') as HTMLElement
      expect(within(h).getByRole('button', { name: /^Build/ })).toBeInTheDocument()
      return h
    })
    expect(within(header).queryByRole('button', { name: /^Approve/ })).toBeNull()
  })
})

describe('document-list-filter-order (FR-4)', () => {
  it('groups slices under their roadmap in build order, filters, and keeps the choice per project', async () => {
    hub.phase = 'approved'
    const user = userEvent.setup()
    const first = renderPage()
    const list = await waitFor(() => {
      const l = screen.getByRole('complementary', { name: 'Specification documents' })
      expect(within(l).getByText('Other change')).toBeInTheDocument()
      return l
    })
    // The roadmap's slices are in build order: Other (1) before Demo (2).
    const names = within(list).getAllByRole('button').map((b) => b.textContent ?? '')
    expect(names.findIndex((n) => n.includes('Other change'))).toBeLessThan(names.findIndex((n) => n.includes('Demo change')))
    // The running build is marked on the document that has one.
    expect(within(list).getAllByLabelText('A build is running').length).toBeGreaterThan(0)

    await user.click(within(list).getByRole('button', { name: 'Changes' }))
    expect(within(list).queryByText('A capability')).toBeNull()
    expect(JSON.parse(localStorage.getItem('aw.spec.list.proj-test') ?? '{}').kind).toBe('change-spec')

    first.unmount()
    renderPage()
    const again = await waitFor(() => screen.getByRole('complementary', { name: 'Specification documents' }))
    expect(within(again).getByRole('button', { name: 'Changes' })).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('navigation (FR-6)', () => {
  it('moves to a requirement picked in the outline, and Back returns', async () => {
    hub.phase = 'approved'
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(anchor('FR-9')).toBeTruthy())
    const outline = screen.getAllByRole('navigation').find((n) => n.className.includes('aw-sp-outline')) ?? document.querySelector('.aw-sp-rail')!
    const pick = within(outline as HTMLElement).getAllByRole('button').find((b) => /^FR-9r/.test(b.textContent ?? ''))!
    await user.click(pick)
    const scroller = document.querySelector('.aw-sp-scroll') as HTMLElement
    await waitFor(() => expect(scroller.scrollTop).toBeGreaterThan(0))
    const back = screen.getByRole('button', { name: 'Back' })
    expect(back).toBeEnabled()
    await user.click(back)
    await waitFor(() => expect(scroller.scrollTop).toBe(0))
  })
})

describe('build-progress-on-the-document (FR-7)', () => {
  it('shows each build with its driver, level, people, task counts, the four-way time split and cost by role', async () => {
    hub.phase = 'approved'
    hub.builds = [
      build({ id: 'build-2', state: 'running', driver: 'lead', level: 'fast', builders: ['Builder', 'QA2'], reviewers: [], lead: 'Architect', stopped_at: null, created_at: '2026-10-17T11:24:00Z', spent_usd: 7.3 }),
      build({}),
    ]
    hub.tasks = [task('plan', 't1', 'approved'), task('build', 't2', 'under_review'), task('ship', 't3', 'pending')]
    renderPage()
    const running = await waitFor(() => {
      const el = anchor('build-build-2')
      expect(el).toBeTruthy()
      return el!
    })
    const finished = anchor('build-build-1')!
    expect(within(running).getByText('Running')).toBeInTheDocument()
    expect(within(running).getByText('Lead agent')).toBeInTheDocument()
    expect(within(running).getByText('Fast')).toBeInTheDocument()
    expect(within(running).getByText('Architect')).toBeInTheDocument()
    expect(within(running).getByText(/1 of 3 approved/)).toBeInTheDocument()
    await waitFor(() => expect(within(running).getByText(/7 runs/)).toBeInTheDocument())
    for (const part of ['Building', 'Waiting for review', 'Checks', 'Waiting to be handed out']) {
      expect(within(running).getAllByText(part).length).toBeGreaterThan(0)
    }
    expect(within(running).getByText('Leading')).toBeInTheDocument()
    expect(within(finished).getByText('Finished')).toBeInTheDocument()
    expect(within(finished).getByText('Gated')).toBeInTheDocument()
    await waitFor(() => expect(within(finished).getByText(/23 runs/)).toBeInTheDocument())
    expect(within(finished).getByText('Reviewing')).toBeInTheDocument()
  })
})

describe('the side panel (FR-8, FR-11, FR-12)', () => {
  async function panel(props: Record<string, unknown> = {}) {
    const { SpecPanelContainer } = await import('@/components/spec/page/SpecPanelContainer')
    const onOpenDocument = vi.fn()
    const utils = render(
      <QueryClientProvider client={queryClient}>
        <SpecPanelContainer path={PATH} onOpenDocument={onOpenDocument} {...props} />
      </QueryClientProvider>,
    )
    return { ...utils, onOpenDocument }
  }

  it('moves to FR-11 then FR-12 from the strip, marks the one in view and its position, colours each item by evidence', async () => {
    hub.phase = 'approved'
    const user = userEvent.setup()
    await panel()
    await waitFor(() => expect(anchor('FR-11')).toBeTruthy())
    const strip = screen.getByRole('navigation', { name: 'Requirements' })
    expect(within(strip).getAllByRole('button', { name: /^\d+$/ })).toHaveLength(COUNT)
    // Items are coloured by their evidence state (FR-1 verified, FR-2 awaiting).
    expect(within(strip).getByTitle(/FR-1 · Verified/)).toBeInTheDocument()
    expect(within(strip).getByTitle(/FR-2 · Awaiting review/)).toBeInTheDocument()
    await user.click(within(strip).getByRole('button', { name: '11' }))
    await waitFor(() => expect(within(strip).getByText('11 of 18')).toBeInTheDocument())
    expect(within(strip).getByRole('button', { name: '11' })).toHaveAttribute('data-active', 'true')
    await user.click(within(strip).getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(within(strip).getByText('12 of 18')).toBeInTheDocument())
  })

  it('shows each active filter as a chip with a count; removing one removes only it; clear all restores the document', async () => {
    hub.phase = 'approved'
    hub.tasks = [task('plan', 't1', 'approved'), task('build', 't2', 'under_review'), task('ship', 't3', 'pending')]
    const user = userEvent.setup()
    await panel()
    await waitFor(() => expect(anchor('FR-1')).toBeTruthy())
    await user.click(screen.getByRole('button', { name: /Filter & sort/ }))
    await chooseMenuOption(user, 'Requirements by evidence', /Awaiting review/)
    await chooseMenuOption(user, 'Requirements by task', 'Build it')
    expect(screen.getByRole('button', { name: /Filter & sort/ })).toHaveTextContent('2')
    expect(anchor('FR-2')).toBeTruthy()
    // Removing the evidence chip leaves the task filter: FR-1 (not served by Build it) stays hidden.
    await user.click(screen.getByText('Awaiting review', { selector: '.aw-sp-pnav-chip *' }))
    expect(screen.getByRole('button', { name: /Filter & sort/ })).toHaveTextContent('1')
    expect(anchor('FR-1')).toBeNull()
    expect(anchor('FR-2')).toBeTruthy()
    await chooseMenuOption(user, 'Requirements by evidence', /Verified/)
    await user.click(screen.getByRole('button', { name: 'Clear all' }))
    expect(anchor('FR-1')).toBeTruthy()
    expect(anchor('FR-5')).toBeTruthy()
  })

  it('reaches the actions, outline, filters and build progress in one column', async () => {
    hub.phase = 'approved'
    hub.builds = [build({ id: 'build-2', state: 'running', created_at: '2026-10-17T11:24:00Z', stopped_at: null })]
    await panel()
    await waitFor(() => expect(anchor('FR-1')).toBeTruthy())
    const header = document.querySelector('.aw-sp-head') as HTMLElement
    expect(within(header).getByRole('button', { name: /Build 1 running/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Filter & sort/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Outline|On this page/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: /Builds/ }))
    await waitFor(() => expect(anchor('build-build-2')).toBeTruthy())
  })

  it('opens a spec from the picker: shortcuts above every document, Enter opens the first match, the attached document is unchanged', async () => {
    hub.phase = 'approved'
    const { SpecPickerContainer } = await import('@/components/spec/page/SpecPanelContainer')
    const onOpen = vi.fn()
    const user = userEvent.setup()
    render(
      <QueryClientProvider client={queryClient}>
        <SpecPickerContainer attachedPath={PATH} recent={[OTHER]} onOpen={onOpen} onNew={() => {}} />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(screen.getByText('This conversation')).toBeInTheDocument())
    expect(screen.getAllByText('Building now').length).toBeGreaterThan(1)
    expect(screen.getByText('2 of 6')).toBeInTheDocument()
    expect(screen.getByText('All specs')).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Search specs' }), 'capab')
    expect(screen.getByText('A capability', { selector: 'b' })).toBeInTheDocument()
    await user.keyboard('{Enter}')
    expect(onOpen).toHaveBeenCalledWith('spec/capabilities/cap/spec.json')
  })
})

describe('aesthetic (FR-9)', () => {
  it('states change without a literal colour in the new styles', async () => {
    const css = (await import('@/styles/spec-page.css?raw')).default
    const literal = css.split('\n').filter((l: string) => /#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/.test(l) && !/#fff\b|#ffffff\b|rgba\(0, ?0, ?0|white/.test(l))
    expect(literal).toEqual([])
  })
})
