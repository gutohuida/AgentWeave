import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { SpecPage } from '@/components/spec/SpecPage'
import { SpecPanelContainer } from '@/components/spec/page/SpecPanelContainer'

/* `the-spec-header-redesigned`, task `header`: the two-row header with every message behind one
 * count (FR-7), the condensed line (FR-4), and every control the old header and banner offered still
 * reachable (FR-5). The Hub is a stubbed `fetch` answering each route with the shape and order the
 * route returns, so the page is driven from the network seam. */

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

const payload = (kind = 'change-spec') => ({
  title: 'Demo change',
  kind,
  summary: 'A demo summary.',
  problem: 'A demo problem.',
  scope: { in_scope: ['One thing'], non_goals: ['Another thing'] },
  requirements: [1, 2, 3].map((n) => ({ key: `r${n}`, modal: 'MUST', statement: `Requirement ${n} holds.`, rationale: null })),
  acceptance_criteria: [1, 2, 3].map((n) => ({ key: `c${n}`, requirement: `r${n}`, given: 'g', when: 'w', then: 't' })),
  tasks: kind === 'change-spec' ? [{ key: 'plan', title: 'Plan it', description: 'd', depends_on: [], requirements: ['r1'] }] : [],
  open_questions: [],
})
const pageOf = (p: unknown) => `<html><body><script type="application/agentweave-spec+json" id="aw-spec-payload">${JSON.stringify(p)}</script></body></html>`

const AMENDMENT = {
  id: 'amd-1',
  op: 'add_task',
  target: 'automatic-choice',
  requirement: 'r2',
  identifier: 'FR-2',
  reason: 'The control is gated on the chapters job, so the operator cannot make this choice on the page.',
  how_to_check: 'Open Project settings, Manager: the automatic/button control shows for the job.',
  author: 'QA2',
  run_id: 'run-1',
  created_at: '2026-11-01T21:20:12Z',
  reviewed: false,
  reviewed_at: null,
  reviewed_by: null,
  relaxing: false,
  change: null,
  before: null,
  state: 'applied',
}

interface Hub {
  phase: 'exploring' | 'approved' | 'archived' | 'current'
  kind: 'change-spec' | 'capability'
  record: Record<string, unknown>
  read: Record<string, unknown>
  builds: unknown[]
  tasks: unknown[]
  check: { blocking: unknown[]; warnings: unknown[] }
  amendments: unknown[]
  requirements: unknown[]
  /** Routes that answer 500. */
  failing: string[]
  calls: string[]
}
let hub: Hub

const runningBuild = {
  id: 'build-1', state: 'running', driver: 'flow', level: 'gated', builders: ['Builder'], reviewers: ['QA1'], lead: null,
  budget_cap_usd: null, spent_usd: 4, unpriced_turns: 0, window_start: null, window_end: null, landing: 'main', loop_id: null,
  stop_reason: null, created_at: '2026-10-17T11:24:00Z', stopped_at: null,
}
const openTask = {
  id: 't1', project_id: 'proj-test', title: 'Plan it', status: 'pending', priority: 'medium', created_at: '2026-10-16T14:02:00Z',
  updated: '2026-10-16T14:02:00Z', divergence_policy: 'surface', has_open_divergence: false, spec_document_id: DOC_ID,
  spec_task_key: 'plan', assignee: 'Builder', build_id: null,
}

function route(url: string, init?: RequestInit): unknown {
  const u = new URL(url, 'http://hub.test')
  const p = u.pathname.replace('/api/v1/projects/proj-test', '')
  const method = init?.method ?? 'GET'
  hub.calls.push(`${method} ${p}`)
  if (hub.failing.includes(p)) return { __status: 500 }
  if (p === '/project/specs')
    return {
      specs: [
        { path: ROADMAP, title: 'Demo roadmap', kind: 'roadmap', state: 'filed', parent: null, order: 0, document_id: 'spdoc-rm', phase: 'approved' },
        { path: PATH, title: 'Demo change', kind: hub.kind, state: 'filed', parent: ROADMAP, order: 2, document_id: DOC_ID, phase: hub.phase },
        { path: OTHER, title: 'Other change', kind: 'change-spec', state: 'filed', parent: ROADMAP, order: 1, document_id: 'spdoc-other', phase: 'approved' },
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
        doc(DOC_ID, PATH, 'Demo change', hub.kind, hub.phase, hub.record),
        doc('spdoc-other', OTHER, 'Other change', 'change-spec', 'approved'),
      ],
    }
  }
  if (p === '/project/spec') {
    const at = u.searchParams.get('path') ?? ''
    if (at !== PATH) return undefined
    return { path: at, content: pageOf(payload(hub.kind)), updated_at: '2026-10-17T09:00:00Z', content_version: 'v1', builds: hub.builds, ...hub.read }
  }
  if (p === '/project/spec/coverage') return { requirements: [], diagnostics: [], totals: {}, integration: {}, unserved: [] }
  if (p === '/project/spec/requirements') return { requirements: hub.requirements }
  if (p === '/project/spec/drift') return { drift: [] }
  if (p === '/vault/warnings') return { warnings: [], checked: true }
  if (p === '/project/next-slice-offers') return { offers: [] }
  if (p === `/project/documents/${PATH}/amendments`) return { amendments: hub.amendments }
  if (p === `/project/documents/${PATH}/amendments/review` && method === 'POST') return { reviewed: 1 }
  if (/^\/project\/documents\/.+\/rigor-history$/.test(p)) return { events: [] }
  if (p === '/tasks') return { tasks: hub.tasks, total: hub.tasks.length, has_more: false }
  if (p === '/agents') return [{ name: 'Builder', status: 'idle', message_count: 0, active_task_count: 0 }]
  if (p === '/loops') return []
  if (p === '/project/documents/check' && method === 'POST')
    return { id: DOC_ID, path: PATH, phase: 'exploring', ready: hub.check.blocking.length === 0, content_version: 'v1', ...hub.check }
  if (/^\/project\/builds\/[^/]+\/figures$/.test(p)) return null
  return undefined
}

function installHub() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const body = route(url, init)
      if (body === undefined) return new Response(JSON.stringify({ detail: 'not stubbed' }), { status: 404 })
      if (body && typeof body === 'object' && '__status' in body) return new Response(JSON.stringify({ detail: 'broken' }), { status: 500 })
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }),
  )
}

/** jsdom has no layout: `scrollTo` moves the scroller's offset and fires `scroll`, as a browser does. */
function installLayout() {
  const css = ((globalThis as { CSS?: Record<string, unknown> }).CSS ??= {})
  css.escape ??= (v: string) => v
  Element.prototype.scrollTo = function (this: HTMLElement, arg?: ScrollToOptions | number) {
    Object.defineProperty(this, 'scrollTop', { value: typeof arg === 'object' ? (arg.top ?? 0) : 0, configurable: true, writable: true })
    this.dispatchEvent(new Event('scroll'))
  } as typeof Element.prototype.scrollTo
}

let queryClient: QueryClient
function renderIn(where: 'page' | 'panel') {
  const onOpenDocument = vi.fn()
  render(
    <QueryClientProvider client={queryClient}>
      {where === 'page' ? <SpecPage document={PATH} onOpenDocument={onOpenDocument} /> : <SpecPanelContainer path={PATH} onOpenDocument={onOpenDocument} />}
    </QueryClientProvider>,
  )
  return { onOpenDocument }
}

const header = () => screen.getByTestId('spec-document-header')
const loaded = async () => {
  await waitFor(() => expect(document.querySelector('.aw-sp-title')?.textContent).toBe('Demo change'))
  await waitFor(() => expect(document.querySelector('[data-anchor="section-summary"], [data-anchor="summary"]')).toBeTruthy())
}
const scroller = () => document.querySelector('.aw-sp-scroll') as HTMLElement

beforeEach(() => {
  cleanup()
  localStorage.clear()
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  useConfigStore.setState({ apiKey: 'aw_live_TESTKEY', hubUrl: 'http://hub.test', selectedProjectId: 'proj-test', isConfigured: true, bootstrapState: 'ready', mode: 'light' })
  hub = { phase: 'exploring', kind: 'change-spec', record: {}, read: {}, builds: [], tasks: [], check: { blocking: [], warnings: [] }, amendments: [], requirements: [], failing: [], calls: [] }
  installHub()
  installLayout()
})
afterEach(() => vi.unstubAllGlobals())

describe('messages-behind-a-count (FR-7)', () => {
  it('shows one blocking finding and three warnings as 4 in the blocking tone, adding nothing above the body, and lists all four', async () => {
    hub.check = {
      blocking: [{ code: 'requirement_without_criterion', where: 'requirements[1]', message: "'r2' has no acceptance criterion" }],
      warnings: [
        { code: 'task_without_reviewer', where: 'tasks[0]', message: 'No reviewer is named for this task' },
        { code: 'thin_rationale', where: 'requirements[0]', message: "'r1' gives no rationale" },
        { code: 'thin_rationale', where: 'requirements[2]', message: "'r3' gives no rationale" },
      ],
    }
    const user = userEvent.setup()
    renderIn('page')
    await loaded()
    const main = document.querySelector('.aw-sp-main') as HTMLElement
    const between = () => Array.from(main.children).filter((el) => el !== header() && el !== scroller())
    // No messages: no count, and nothing between the header and the body.
    expect(within(header()).queryByTestId('spec-notice-count')).toBeNull()
    expect(between()).toHaveLength(0)
    const rowsBefore = header().children.length

    await user.click(within(header()).getByRole('button', { name: 'Check' }))
    const count = await within(header()).findByTestId('spec-notice-count')
    expect(count).toHaveTextContent('4')
    expect(count).toHaveAttribute('data-tone', 'error')
    // Still nothing between the header and the body, and the header has no more rows than before.
    expect(between()).toHaveLength(0)
    expect(header().children.length).toBe(rowsBefore)
    expect(screen.queryByTestId('spec-notices')).toBeNull()

    await user.click(count)
    const list = screen.getByTestId('spec-notices')
    expect(within(list).getAllByRole('listitem')).toHaveLength(4)
    expect(within(list).getByText(/has no acceptance criterion/)).toBeInTheDocument()
    expect(within(list).getByText(/No reviewer is named/)).toBeInTheDocument()
    expect(within(list).getAllByText(/gives no rationale/)).toHaveLength(2)
    // The most urgent first, and each one's action shows it in the document.
    expect(within(list).getAllByRole('listitem')[0]).toHaveTextContent(/has no acceptance criterion/)
    expect(within(list).getAllByRole('button', { name: 'Show' })).toHaveLength(4)
  })

  it("opens an amendment to its reason, how to check it and Mark reviewed, which marks it reviewed", async () => {
    hub.phase = 'approved'
    hub.record = { amendments: { total: 1, unreviewed: 1, proposed: 0 } }
    hub.amendments = [AMENDMENT]
    hub.read = { delivery_status: { state: 'stale', agent: 'Ghost', reason: 'unknown' } }
    const user = userEvent.setup()
    renderIn('page')
    await loaded()
    const count = await within(header()).findByTestId('spec-notice-count')
    await waitFor(() => expect(count).toHaveTextContent('2'))
    expect(count).toHaveAttribute('data-tone', 'warn')
    // The amendment card and the stale strip are not stacked under the header any more.
    expect(screen.queryByText(AMENDMENT.reason)).toBeNull()
    expect(screen.queryByTestId('delivery-stale-strip')).toBeNull()

    await user.click(count)
    const row = screen.getByTestId('spec-notice-amendment-amd-1')
    expect(row).toHaveTextContent(/Added task/)
    expect(row).toHaveTextContent('automatic-choice')
    await user.click(within(row).getByRole('button', { name: /Added task/ }))
    expect(within(row).getByText(AMENDMENT.reason)).toBeInTheDocument()
    expect(within(row).getByText(AMENDMENT.how_to_check)).toBeInTheDocument()
    await user.click(within(row).getByRole('button', { name: 'Mark reviewed' }))
    await waitFor(() => expect(hub.calls).toContain(`POST /project/documents/${PATH}/amendments/review`))
    // The other message is the stale recommendation, in full when opened.
    const stale = screen.getByTestId('spec-notice-delivery-stale')
    await user.click(within(stale).getByRole('button', { name: /recommended build names Ghost/ }))
    expect(within(stale).getByText(/choose another agent in the Build dialog/)).toBeInTheDocument()
  })

  it('makes a page that could not be read, the retired requirements and a proposal each a notice', async () => {
    hub.phase = 'approved'
    hub.failing = ['/project/spec/coverage']
    hub.requirements = [{ id: 'req-9', identifier: 'FR-9', key: 'old', state: 'retired' }]
    hub.record = { amendments: { total: 1, unreviewed: 0, proposed: 1 } }
    hub.amendments = [{ ...AMENDMENT, id: 'amd-2', state: 'proposed', author: 'Architect' }]
    const user = userEvent.setup()
    renderIn('page')
    await loaded()
    const count = await within(header()).findByTestId('spec-notice-count')
    await waitFor(() => expect(count).toHaveAttribute('data-tone', 'error'))
    await user.click(count)
    const list = screen.getByTestId('spec-notices')
    expect(within(list).getByTestId('spec-unread')).toHaveTextContent(/Part of this page could not be read/)
    expect(within(list).getByTestId('spec-facts-unread')).toBeInTheDocument()
    const retired = within(list).getByTestId('spec-notice-retired')
    await user.click(within(retired).getByRole('button', { name: /1 retired requirement/ }))
    expect(within(retired).getByTestId('spec-retired-row-FR-9')).toBeInTheDocument()
    const proposal = within(list).getByTestId('spec-notice-amendment-amd-2')
    await user.click(within(proposal).getByRole('button', { name: /Proposes a task/ }))
    expect(within(proposal).getByRole('button', { name: 'Accept' })).toBeInTheDocument()
    expect(within(proposal).getByRole('button', { name: 'Decline…' })).toBeInTheDocument()
  })
})

describe('condenses-on-scroll (FR-4)', () => {
  for (const where of ['page', 'panel'] as const) {
    it(`in the ${where}: one line while scrolled, expanded back at the top and when the line is clicked`, async () => {
      hub.phase = 'approved'
      hub.read = { delivery_status: { state: 'stale', agent: 'Ghost', reason: 'unknown' } }
      const user = userEvent.setup()
      renderIn(where)
      await loaded()
      await within(header()).findByTestId('spec-notice-count')
      expect(header()).toHaveAttribute('data-condensed', 'false')
      expect(header().querySelector('.aw-sp-head-row2')).toBeTruthy()

      scroller().scrollTo({ top: 600 })
      await waitFor(() => expect(header()).toHaveAttribute('data-condensed', 'true'))
      // One line: no second row; the title, the phase, the count, the primary action and More.
      expect(header().querySelector('.aw-sp-head-row2')).toBeNull()
      const line = within(header()).getByTestId('spec-header-condensed')
      expect(line).toHaveTextContent('Demo change')
      expect(line.querySelector('.aw-sp-phase')).toHaveTextContent('Approved')
      expect(within(header()).getByTestId('spec-notice-count')).toBeInTheDocument()
      expect(within(header()).getByRole('button', { name: /^Build/ })).toBeInTheDocument()
      expect(within(header()).getByRole('button', { name: 'More actions' })).toBeInTheDocument()

      scroller().scrollTo({ top: 0 })
      await waitFor(() => expect(header()).toHaveAttribute('data-condensed', 'false'))

      scroller().scrollTo({ top: 700 })
      await waitFor(() => expect(header()).toHaveAttribute('data-condensed', 'true'))
      await user.click(within(header()).getByTestId('spec-header-condensed'))
      expect(header()).toHaveAttribute('data-condensed', 'false')
      expect(header().querySelector('.aw-sp-head-row2')).toBeTruthy()

      // What a browser does next, measured by QA in the panel at the body's maximum scroll: the
      // expanded header shrinks the scroller (813 → 745px) and scroll anchoring moves its offset by
      // +68. That move is the header's own and must leave it expanded.
      const el = scroller()
      Object.defineProperty(el, 'clientHeight', { value: 745, configurable: true })
      Object.defineProperty(el, 'scrollTop', { value: 768, configurable: true, writable: true })
      el.dispatchEvent(new Event('scroll'))
      await new Promise((r) => setTimeout(r, 20))
      expect(header()).toHaveAttribute('data-condensed', 'false')

      // The reader scrolling down again, with the scroller's height unchanged, condenses it.
      scroller().scrollTo({ top: 800 })
      await waitFor(() => expect(header()).toHaveAttribute('data-condensed', 'true'))
    })
  }
})

/* nothing-is-lost (FR-5): every control the header and the banner rendered on master, by state,
 * taken from SpecPageHeader.tsx, useSpecSurface.tsx's banner and useSpecPhaseControls.tsx at
 * f565d6d. `direct` was reachable without opening a menu and still must be; `menu` was in More;
 * `notice` is a banner message, one click away behind the count; `body` moved into the body. */
type Look = { label: RegExp | string; by?: 'button' | 'testid' | 'text' }
interface Inventory {
  direct: Look[]
  menu: string[]
  notice?: string[]
  body?: string[]
}
const ALWAYS_DIRECT: Look[] = [
  { label: 'Back' },
  { label: 'Forward' },
  { label: /Demo roadmap/ },
  { label: 'Previous slice' },
  { label: 'Next slice' },
  { label: 'More actions' },
  { label: 'spec-document-facts', by: 'testid' },
  { label: /^Changed /, by: 'text' },
]
const ALWAYS_MENU = ['Copy link to this document', 'Copy its path', 'Refresh', 'Hold…']

const STATES: Record<string, { setup: () => void; afterLoad?: (user: ReturnType<typeof userEvent.setup>) => Promise<void>; phase: string; inventory: Inventory }> = {
  writing: {
    setup: () => {
      hub.record = { step: 'requirements', journey: ['intake', 'requirements', 'tasks'], size: 'small' }
    },
    phase: 'Writing',
    inventory: {
      direct: [...ALWAYS_DIRECT, { label: 'Check' }],
      menu: [...ALWAYS_MENU, 'Archive', 'Delete…'],
      // The journey-step and size control: one click away, open as soon as the list is.
      notice: ['spec-journey', 'spec-journey-size'],
    },
  },
  ready: {
    setup: () => {},
    afterLoad: async (user) => {
      await user.click(within(header()).getByRole('button', { name: 'Check' }))
      await within(header()).findByRole('button', { name: /^Approve/ })
    },
    phase: 'Writing',
    inventory: {
      direct: [...ALWAYS_DIRECT, { label: /^Approve$/ }, { label: 'More ways to do this' }, { label: 'Check again' }, { label: /Nothing blocks approval/, by: 'text' }],
      menu: [...ALWAYS_MENU, 'Archive', 'Delete…'],
    },
  },
  approved: {
    setup: () => {
      hub.phase = 'approved'
      hub.tasks = [openTask]
      hub.read = { delivery_status: { state: 'ok', agent: 'Builder', reviewer: 'QA1', reviewer_state: 'ok' } }
    },
    phase: 'Approved',
    inventory: {
      direct: [...ALWAYS_DIRECT, { label: /^Build…/ }, { label: 'Check' }, { label: 'delivery-reviewer', by: 'testid' }],
      menu: [...ALWAYS_MENU, 'Start a flow…', 'Reopen for changes', 'Archive', 'Delete…'],
      body: ['already-built-open'],
    },
  },
  building: {
    setup: () => {
      hub.phase = 'approved'
      hub.builds = [runningBuild]
    },
    phase: 'Building',
    inventory: {
      direct: [...ALWAYS_DIRECT, { label: /Build 1 running/ }],
      // No flow declares the fixture's document, so Start a flow is offered, as it was on master.
      menu: [...ALWAYS_MENU, 'Start a flow…', 'Reopen for changes', 'Archive', 'Delete…'],
      body: ['spec-build-status', 'spec-build-stop', 'spec-build-raise'],
    },
  },
  done: {
    setup: () => {
      hub.phase = 'approved'
      hub.record = { display_phase: 'done' }
      hub.read = { fold_state: { state: 'ready', open_tasks: [], capabilities: [], reconcile: { state: 'none' } } }
    },
    phase: 'Done',
    inventory: {
      direct: [...ALWAYS_DIRECT, { label: /Fold into capability/ }],
      menu: [...ALWAYS_MENU, 'Start a flow…', 'Reopen for changes', 'Archive', 'Delete…'],
    },
  },
  archived: {
    setup: () => {
      hub.phase = 'archived'
    },
    phase: 'Archived',
    inventory: {
      direct: [...ALWAYS_DIRECT, { label: 'spec-archived-marker', by: 'testid' }],
      menu: [...ALWAYS_MENU],
    },
  },
  capability: {
    setup: () => {
      hub.phase = 'current'
      hub.kind = 'capability'
    },
    phase: 'Current',
    inventory: {
      direct: [...ALWAYS_DIRECT],
      menu: [...ALWAYS_MENU, 'Retire…'],
    },
  },
}

async function findDirect(look: Look) {
  const h = header()
  if (look.by === 'testid') return within(h).findByTestId(look.label as string)
  if (look.by === 'text') return within(h).findByText(look.label)
  return within(h).findByRole('button', { name: look.label })
}

describe('nothing-is-lost (FR-5)', () => {
  for (const [state, spec] of Object.entries(STATES)) {
    it(`a ${state} document keeps every control of the old header and banner`, async () => {
      spec.setup()
      const user = userEvent.setup()
      renderIn('page')
      await loaded()
      await spec.afterLoad?.(user)
      expect(header().querySelector('.aw-sp-phase')).toHaveTextContent(spec.phase)
      for (const look of spec.inventory.direct) expect(await findDirect(look), String(look.label)).toBeInTheDocument()

      for (const id of spec.inventory.body ?? []) {
        const found = await screen.findByTestId(id)
        expect(header().contains(found), `${id} is in the body`).toBe(false)
        expect(found.closest('.aw-sp-scroll'), `${id} is in the body`).toBeTruthy()
      }

      if (spec.inventory.notice) {
        await user.click(await within(header()).findByTestId('spec-notice-count'))
        const list = screen.getByTestId('spec-notices')
        for (const id of spec.inventory.notice) expect(within(list).getByTestId(id), id).toBeInTheDocument()
        await user.keyboard('{Escape}')
      }

      await user.click(within(header()).getByRole('button', { name: 'More actions' }))
      const menu = await screen.findByRole('menu')
      const items = within(menu).getAllByRole('menuitem').map((el) => el.textContent?.trim())
      expect(items.sort()).toEqual([...spec.inventory.menu].sort())
    })
  }

  it('moves the journey step from the notice list, a click after opening the count', async () => {
    STATES.writing!.setup()
    const user = userEvent.setup()
    renderIn('page')
    await loaded()
    await user.click(await within(header()).findByTestId('spec-notice-count'))
    expect(screen.getByTestId('spec-journey-step-requirements')).toBeDisabled()
    expect(screen.getByTestId('spec-journey-step-tasks')).toBeEnabled()
  })

  it('in the panel keeps the Specs switcher, the outline and the four navigation rows', async () => {
    hub.phase = 'approved'
    renderIn('panel')
    await loaded()
    expect(within(header()).getByRole('button', { name: /Specs/ })).toBeInTheDocument()
    expect(within(header()).getByRole('button', { name: /Outline|On this page/ })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Document/ })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Sections' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Requirements' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Filter & sort/ })).toBeInTheDocument()
  })
})
