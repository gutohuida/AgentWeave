import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import type { OverviewBody } from '@/api/overview'
import type { ProjectSetupItem } from '@/api/projects'
import { OverviewScreen } from '@/components/overview/OverviewScreen'
import { OVERVIEW_TABS_STORAGE_KEY, useOverviewTabsStore } from '@/store/overviewTabsStore'
import { useConfigStore } from '@/store/configStore'
import { useTaskFilterStore } from '@/store/taskFilterStore'

/** The live Overview (`overview-at-a-glance-with-dashboard-and-briefing-tabs`): the two tabs and the
 *  Dashboard fed by `GET /overview`. The Hub read is stubbed with bodies in the contract's shape and
 *  in the order the route answers (needs ranked, spend days oldest first, finished newest first). */

const NOW = new Date(2026, 10, 23, 15, 0, 0)
const ago = (minutes: number) => new Date(NOW.getTime() - minutes * 60_000).toISOString()
const localDay = (daysBack: number) => {
  const d = new Date(NOW.getFullYear(), NOW.getMonth(), NOW.getDate() - daysBack)
  return d.toISOString()
}

function body(over: Partial<OverviewBody> = {}): OverviewBody {
  return {
    generated_at: NOW.toISOString(),
    visit: null,
    needs: [],
    running: [],
    finished: [],
    spend: {
      days: Array.from({ length: 7 }, (_, i) => ({ day: localDay(6 - i), usd: 1, tokens: 1000, credits: null, unpriced_turns: 0 })),
      token_budget: null,
    },
    main: { state: 'green', branch: 'master', held_landings: 0, fails_on_main: 0, flaky: 0, detail: null },
    builds: [],
    note: null,
    note_writing: false,
    note_last_attempt: null,
    ...over,
  }
}

let overviewData: OverviewBody | null | undefined = body()
vi.mock('@/api/overview', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/overview')>()),
  useOverview: () => ({ data: overviewData, error: null, refetch: vi.fn(), isLoading: overviewData === undefined }),
}))

let setupItems: ProjectSetupItem[] = []
vi.mock('@/api/projects', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/projects')>()),
  useProjects: () => ({
    data: [
      { id: 'proj-a', name: 'Alpha', setup: { items: setupItems, dismissed: [] } },
      { id: 'proj-b', name: 'Beta', setup: { items: [], dismissed: [] } },
    ],
  }),
  useSetupDismissal: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/api/firstRun', () => ({ useProjectHasNoWork: () => false }))
vi.mock('@/components/overview/SetupProfilesDialog', () => ({ SetupProfilesDialog: () => null }))
vi.mock('@/api/agents', () => ({
  useAgents: () => ({
    data: [
      { name: 'Developer', status: 'running', color_index: 1, can_accept_evidence: true },
      { name: 'QA', status: 'idle', color_index: 2, can_accept_evidence: false },
    ],
    error: null,
    refetch: vi.fn(),
  }),
}))
vi.mock('@/components/overview/AgentPostureChips', () => ({
  AgentPostureChips: ({ agent }: { agent: { name: string } }) => <span data-testid={`posture-${agent.name}`}>evidence</span>,
}))
vi.mock('@/api/knownFailing', () => ({
  useKnownFailing: () => ({ data: [], error: null, refetch: vi.fn() }),
  useDisturbedRuns: () => ({ data: [] }),
  useClearStableFixTasks: () => ({ mutate: vi.fn(), isPending: false, data: undefined, error: null }),
}))
vi.mock('@/api/quarantine', () => ({
  useQuarantine: () => ({
    data: {
      threshold: 0.2,
      exit_passes: 5,
      quarantined: [
        { id: 'q1', check: 'hub-tests', test: 'test_flaky_clock', flake_rate: 0.3, entered_at: ago(60), passes: 1, passes_to_exit: 5, fix_task_id: null, fix_task: null },
      ],
      marks: [],
    },
    error: null,
    refetch: vi.fn(),
  }),
  useSetNeverQuarantine: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useRemoveNeverQuarantine: () => ({ mutate: vi.fn(), isPending: false, error: null }),
}))
// The previous Overview is the 404 fallback: its own tests cover it; here it only has to appear.
vi.mock('@/components/overview/OverviewClassicScreen', () => ({
  OverviewClassicScreen: () => <div data-testid="classic-overview">old needs list</div>,
}))
const goTo = vi.fn()
vi.mock('@/lib/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/navigation')>()),
  goTo: (destination: unknown) => goTo(destination),
}))

const onNavigate = vi.fn()
const onOpenConversation = vi.fn()
const renderScreen = () => render(<OverviewScreen onNavigate={onNavigate} onOpenConversation={onOpenConversation} />)
const selectProject = (id: string) => act(() => useConfigStore.setState({ selectedProjectId: id, isConfigured: true }))
const band = () => screen.getByRole('status', { name: /^Project health/ })
const tile = (label: string) => screen.getByRole('button', { name: new RegExp(`^${label}:`) })
const tabNames = () => screen.getAllByRole('tab').map((t) => t.textContent)

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
  window.localStorage.clear()
  useOverviewTabsStore.getState().reload()
  overviewData = body()
  setupItems = []
  goTo.mockClear()
  onNavigate.mockClear()
  onOpenConversation.mockClear()
  selectProject('proj-a')
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('ac-tabs-order: the tabs are dragged into order, per project, and survive a reload', () => {
  it('opens on Dashboard first, keeps Briefing first after a drag and a reload, and leaves another project alone', () => {
    const first = renderScreen()
    expect(tabNames()).toEqual(['Dashboard', 'Briefing'])
    expect(screen.getByRole('tab', { name: 'Dashboard' })).toHaveAttribute('aria-selected', 'true')

    const briefing = screen.getByRole('tab', { name: 'Briefing' })
    const dashboard = screen.getByRole('tab', { name: 'Dashboard' })
    fireEvent.dragStart(briefing, { dataTransfer: { setData: vi.fn(), getData: () => 'briefing', effectAllowed: '' } })
    // The held tab says it is moving while it is held.
    expect(briefing).toHaveAttribute('data-dragging', 'true')
    fireEvent.dragOver(dashboard, { dataTransfer: { dropEffect: '' } })
    fireEvent.drop(dashboard, { dataTransfer: { getData: () => 'briefing' } })
    expect(tabNames()).toEqual(['Briefing', 'Dashboard'])

    // A reload: storage is read afresh and the screen mounted again.
    first.unmount()
    act(() => useOverviewTabsStore.getState().reload())
    const stored = JSON.parse(window.localStorage.getItem(OVERVIEW_TABS_STORAGE_KEY)!)
    expect(stored['proj-a'].order).toEqual(['briefing', 'dashboard'])
    const second = renderScreen()
    expect(tabNames()).toEqual(['Briefing', 'Dashboard'])
    expect(screen.getByRole('tab', { name: 'Briefing' })).toHaveAttribute('aria-selected', 'true')
    second.unmount()

    selectProject('proj-b')
    renderScreen()
    expect(tabNames()).toEqual(['Dashboard', 'Briefing'])
    expect(screen.getByRole('tab', { name: 'Dashboard' })).toHaveAttribute('aria-selected', 'true')
  })

  it('moves a tab with the keyboard, and plain arrows switch tabs', () => {
    renderScreen()
    const dashboard = screen.getByRole('tab', { name: 'Dashboard' })
    fireEvent.keyDown(dashboard, { key: 'ArrowRight', ctrlKey: true, shiftKey: true })
    expect(tabNames()).toEqual(['Briefing', 'Dashboard'])
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Dashboard' }), { key: 'ArrowLeft' })
    expect(screen.getByRole('tab', { name: 'Briefing' })).toHaveAttribute('aria-selected', 'true')
  })
})

describe('ac-health-levels: one level and a sentence naming every cause', () => {
  const twoNeeds = [
    { id: 'n1', kind: 'question' as const, rank: 4, agent: 'Developer', title: 'Which port?', waiting_since: ago(10), action: 'Answer', target: { type: 'thread' as const, id: 'conv-1', conversation_id: 'conv-1' } },
    { id: 'n2', kind: 'review' as const, rank: 5, agent: 'QA', title: 'Port the lexer', waiting_since: ago(5), action: 'Review', target: { type: 'task' as const, id: 'task-1' } },
  ]
  it('(a) main failing and 2 needs reads Trouble naming both', () => {
    overviewData = body({ needs: twoNeeds, main: { state: 'failing', branch: 'master', held_landings: 0, fails_on_main: 1, flaky: 0, detail: null } })
    renderScreen()
    expect(band()).toHaveTextContent('Trouble')
    expect(band()).toHaveTextContent('master is failing and 2 things need you')
  })
  it('(b) 2 needs and main green reads Needs you', () => {
    overviewData = body({ needs: twoNeeds })
    renderScreen()
    expect(band()).toHaveTextContent('Needs you')
    expect(band()).toHaveTextContent('2 things need you and master is green')
  })
  it('(c) nothing waiting and main green reads Healthy', () => {
    renderScreen()
    expect(band()).toHaveTextContent('Healthy')
    expect(band()).toHaveTextContent('nothing needs you and master is green')
  })
  it('(d) 92% of the token budget reads Trouble naming the share', () => {
    overviewData = body({ spend: { ...body().spend, token_budget: { limit: 1_000_000, used: 920_000 } } })
    renderScreen()
    expect(band()).toHaveTextContent('Trouble')
    expect(band()).toHaveTextContent('spend is at 92% of the token budget')
  })
})

describe('ac-needs-kinds-ranked: every kind, in the order the Hub ranks them', () => {
  it('shows all seven with kind, profile, title, age and action, in the route order', () => {
    const needs: OverviewBody['needs'] = [
      { id: 'm', kind: 'merge', rank: 2, agent: null, title: 'Approved but not landed', waiting_since: ago(300), action: 'Try again', target: { type: 'task', id: 'task-m' } },
      { id: 's', kind: 'stall', rank: 3, agent: 'mender', title: 'A run stopped answering', waiting_since: ago(200), action: 'Open thread', target: { type: 'thread', id: 'conv-s', conversation_id: 'conv-s' } },
      { id: 'q', kind: 'question', rank: 4, agent: 'Developer', title: 'Which port?', waiting_since: ago(100), action: 'Answer', target: { type: 'thread', id: 'conv-q', conversation_id: 'conv-q' } },
      { id: 'r', kind: 'review', rank: 5, agent: 'QA', title: 'Port the lexer', waiting_since: ago(90), action: 'Review', target: { type: 'task', id: 'task-r' } },
      { id: 'p', kind: 'permission', rank: 5, agent: 'Developer', title: 'Run npm install', waiting_since: ago(30), action: 'Decide', target: { type: 'permission', id: 'perm-1', conversation_id: 'conv-p' } },
      { id: 'c', kind: 'check', rank: 6, agent: null, title: 'hub-tests could not run', waiting_since: ago(60), action: 'Open check', target: { type: 'check', id: 'hub-tests' } },
      { id: 'o', kind: 'offer', rank: 6, agent: 'Architect', title: 'Draft the next slice', waiting_since: ago(20), action: 'Draft', target: { type: 'spec', id: null, path: 'spec/changes/next/spec.json' } },
    ]
    overviewData = body({ needs })
    renderScreen()
    const section = screen.getByRole('heading', { name: 'Needs you' }).closest('section')!
    fireEvent.click(within(section).getByRole('button', { name: /See all 7/ }))
    const rows = within(section).getAllByRole('button').filter((b) => b.getAttribute('data-slot') === 'overview-need')
    expect(rows.map((r) => r.getAttribute('aria-label'))).toEqual([
      'Landing: Approved but not landed. Try again',
      'Stalled: A run stopped answering. Open thread',
      'Question: Which port?. Answer',
      'Review: Port the lexer. Review',
      'Permission: Run npm install. Decide',
      'Check: hub-tests could not run. Open check',
      'Offer: Draft the next slice. Draft',
    ])
    // Each row names its profile (when it has one), its age and its action.
    expect(rows[2]).toHaveTextContent('Developer')
    expect(rows[2]).toHaveTextContent('2h')
    expect(rows[2]).toHaveTextContent('Answer')
    expect(rows[0]).toHaveTextContent('5h')
  })
})

describe('ac-main-states: the main tile', () => {
  const cases: [string, OverviewBody['main'], OverviewBody['needs'], RegExp][] = [
    ['fails on main', { state: 'failing', branch: 'master', held_landings: 0, fails_on_main: 1, flaky: 0, detail: null }, [], /^Main and checks: Failing/],
    ['a check could not run', { state: 'failing', branch: 'master', held_landings: 0, fails_on_main: 0, flaky: 0, detail: 'hub-tests could not run' }, [], /^Main and checks: Failing/],
    ['only flaky', { state: 'green', branch: 'master', held_landings: 0, fails_on_main: 0, flaky: 3, detail: null }, [], /^Main and checks: Green/],
    ['one held landing', { state: 'held', branch: 'master', held_landings: 1, fails_on_main: 0, flaky: 0, detail: null }, [], /^Main and checks: Held/],
    ['never checked', { state: 'unknown', branch: 'master', held_landings: 0, fails_on_main: null, flaky: null, detail: null }, [], /^Main and checks: Unknown/],
    ['none of these', { state: 'green', branch: 'master', held_landings: 0, fails_on_main: 0, flaky: 0, detail: null }, [], /^Main and checks: Green/],
    [
      'main moved outside the Hub',
      { state: 'green', branch: 'master', held_landings: 0, fails_on_main: 0, flaky: 0, detail: null },
      [{ id: 'mm', kind: 'main_moved', rank: 6, agent: null, title: 'master moved outside the Hub', waiting_since: ago(15), action: 'Seen', target: { type: 'setting', id: 'landing' } }],
      /^Main and checks: Green/,
    ],
  ]
  it.each(cases)('%s', (name, main, needs, figure) => {
    overviewData = body({ main, needs })
    renderScreen()
    const t = screen.getByRole('button', { name: figure })
    if (name === 'only flaky') expect(t).toHaveTextContent('3 flaky')
    if (name === 'one held landing') expect(t).toHaveTextContent('1 landing held')
    if (name === 'main moved outside the Hub') {
      expect(screen.getByRole('button', { name: 'Main moved: master moved outside the Hub. Seen' })).toBeInTheDocument()
    }
  })
})

describe('ac-spend-units: dollars, credits, unknown, and the token budget', () => {
  it('states each day in its own unit and the share of the token budget', () => {
    overviewData = body({
      spend: {
        days: [
          { day: localDay(6), usd: 2, tokens: 5000, credits: null, unpriced_turns: 0 },
          { day: localDay(5), usd: null, tokens: 4000, credits: 12, unpriced_turns: 0 },
          { day: localDay(4), usd: null, tokens: 3000, credits: null, unpriced_turns: 2 },
          { day: localDay(3), usd: 1, tokens: 100, credits: null, unpriced_turns: 0 },
          { day: localDay(2), usd: 1, tokens: 100, credits: null, unpriced_turns: 0 },
          { day: localDay(1), usd: 1, tokens: 100, credits: null, unpriced_turns: 0 },
          { day: localDay(0), usd: 4.25, tokens: 9000, credits: null, unpriced_turns: 0 },
        ],
        token_budget: { limit: 1_000_000, used: 400_000 },
      },
    })
    renderScreen()
    const spend = tile('Spend')
    expect(spend).toHaveAccessibleName(/^Spend: \$4\.25/)
    expect(spend).toHaveTextContent('Nov 18: 12 credits')
    expect(spend).toHaveTextContent('Nov 19: unknown')
    expect(spend).not.toHaveTextContent('Nov 19: $0')
    expect(spend).toHaveTextContent('40% of the token budget used')
  })
})

describe('ac-running-duration: how long a turn has run comes from its start', () => {
  it('shows about 10 minutes for a turn started 10 minutes ago', () => {
    overviewData = body({ running: [{ run_id: 'run-1', agent: 'Developer', conversation_id: 'conv-1', task_id: 'task-1', what: 'Port the lexer', started_at: ago(10) }] })
    renderScreen()
    expect(tile('Running')).toHaveTextContent('Developer, running for 10m')
    expect(screen.getByRole('button', { name: 'Developer: Port the lexer, running for 10m. Opens it' })).toBeInTheDocument()
  })
})

describe('ac-finished-today: the tally and the timeline', () => {
  it('counts today only, and lists today with outcome, time and cost, the unpriced as not priced', () => {
    overviewData = body({
      finished: [
        { id: 'f1', task_id: 'task-1', run_id: null, agent: 'Developer', title: 'Landed task', outcome: 'landed', at: ago(30), usd: 1.5, tokens: 1000, credits: null },
        { id: 'f2', task_id: 'task-2', run_id: null, agent: 'QA', title: 'Sent back task', outcome: 'sent_back', at: ago(60), usd: 0.75, tokens: 1000, credits: null },
        { id: 'f3', task_id: 'task-3', run_id: 'run-3', agent: 'Developer', title: 'Failed task', outcome: 'failed', at: ago(90), usd: null, tokens: null, credits: null },
        { id: 'f4', task_id: 'task-4', run_id: 'run-4', agent: 'Developer', title: 'Stopped task', outcome: 'stopped', at: ago(120), usd: 0.1, tokens: 10, credits: null },
        { id: 'f5', task_id: 'task-5', run_id: null, agent: 'Developer', title: 'Yesterday task', outcome: 'landed', at: ago(60 * 24), usd: 2, tokens: 10, credits: null },
      ],
    })
    renderScreen()
    expect(tile('Finished today')).toHaveTextContent('1 landed · 1 sent back · 1 failed')
    const timeline = screen.getByRole('heading', { name: 'Activity' }).closest('section')!
    const rows = within(timeline).getAllByRole('button').filter((b) => b.getAttribute('data-slot') === 'overview-activity')
    expect(rows.map((r) => r.querySelector('.aw-od-row-title')?.textContent)).toEqual(['Landed task', 'Sent back task', 'Failed task', 'Stopped task'])
    expect(rows[0]).toHaveTextContent('Landed')
    expect(rows[0]).toHaveTextContent('$1.50')
    expect(rows[0]).toHaveTextContent('30m')
    expect(rows[1]).toHaveTextContent('Sent back')
    expect(rows[2]).toHaveTextContent('Failed')
    expect(rows[2]).toHaveTextContent('not priced')
    expect(rows[3]).toHaveTextContent('Stopped')
  })
})

describe('ac-build-stage: what each build is doing', () => {
  it('shows 7/8 checking task 8, and the waiting build flagged as needing you', () => {
    overviewData = body({
      builds: [
        { build_id: 'build-1', document_path: 'spec/changes/a/spec.json', title: 'Slice A', tasks_done: 7, tasks_total: 8, stage_words: 'Checking task 8', needs_operator: false },
        { build_id: 'build-2', document_path: 'spec/changes/b/spec.json', title: 'Slice B', tasks_done: 2, tasks_total: 5, stage_words: 'Waiting for your answer', needs_operator: true },
      ],
    })
    renderScreen()
    const a = screen.getByRole('button', { name: /^Build: Slice A/ })
    expect(a).toHaveTextContent('7/8')
    expect(a).toHaveTextContent('Checking task 8')
    expect(a).not.toHaveTextContent('Needs you')
    const b = screen.getByRole('button', { name: /^Build: Slice B/ })
    expect(b).toHaveTextContent('Waiting for your answer')
    expect(b).toHaveTextContent('Needs you')
    expect(b).toHaveAttribute('data-needs', 'true')
  })
})

describe('ac-click-through: every Dashboard item opens its detail', () => {
  it('opens the thread, task, build, request, check, setting or spec each item is about', () => {
    overviewData = body({
      needs: [
        { id: 'q', kind: 'question', rank: 4, agent: 'Developer', title: 'Which port?', waiting_since: ago(5), action: 'Answer', target: { type: 'thread', id: 'conv-q', conversation_id: 'conv-q' } },
        { id: 'r', kind: 'review', rank: 5, agent: 'QA', title: 'Port the lexer', waiting_since: ago(4), action: 'Review', target: { type: 'task', id: 'task-r' } },
        { id: 'p', kind: 'permission', rank: 5, agent: 'Developer', title: 'Run npm install', waiting_since: ago(3), action: 'Decide', target: { type: 'permission', id: 'perm-1', conversation_id: 'conv-p' } },
        { id: 'c', kind: 'check', rank: 6, agent: null, title: 'hub-tests could not run', waiting_since: ago(2), action: 'Open check', target: { type: 'check', id: 'hub-tests' } },
        { id: 'mm', kind: 'main_moved', rank: 6, agent: null, title: 'master moved', waiting_since: ago(1), action: 'Seen', target: { type: 'setting', id: 'landing' } },
      ],
      running: [{ run_id: 'run-1', agent: 'Developer', conversation_id: 'conv-run', task_id: null, what: 'Port the lexer', started_at: ago(10) }],
      finished: [{ id: 'f1', task_id: 'task-f', run_id: null, agent: 'QA', title: 'Landed task', outcome: 'landed', at: ago(30), usd: 1, tokens: 1, credits: null }],
      builds: [{ build_id: 'build-1', document_path: null, title: 'Slice A', tasks_done: 1, tasks_total: 2, stage_words: 'Building task 2', needs_operator: false }],
    })
    renderScreen()
    const click = (name: string | RegExp) => fireEvent.click(screen.getByRole('button', { name }))
    fireEvent.click(screen.getByRole('button', { name: /See all 5/ }))

    click('Question: Which port?. Answer')
    expect(onOpenConversation).toHaveBeenLastCalledWith('Developer', 'conv-q')
    click('Review: Port the lexer. Review')
    expect(useTaskFilterStore.getState().pendingOpenTaskId).toBe('task-r')
    expect(onNavigate).toHaveBeenLastCalledWith('tasks')
    click('Permission: Run npm install. Decide')
    expect(onOpenConversation).toHaveBeenLastCalledWith('Developer', 'conv-p')
    click('Check: hub-tests could not run. Open check')
    expect(goTo).toHaveBeenLastCalledWith(expect.objectContaining({ tab: 'environment', environmentSection: 'checks' }))
    click('Main moved: master moved. Seen')
    expect(goTo).toHaveBeenLastCalledWith(expect.objectContaining({ tab: 'environment', environmentSection: 'landing' }))
    click('Developer: Port the lexer, running for 10m. Opens it')
    expect(onOpenConversation).toHaveBeenLastCalledWith('Developer', 'conv-run')
    click('QA: Landed task, Landed. Opens it')
    expect(useTaskFilterStore.getState().pendingOpenTaskId).toBe('task-f')
    click(/^Build: Slice A/)
    expect(goTo).toHaveBeenLastCalledWith(expect.objectContaining({ tab: 'spec', view: 'build', focus: 'build-1' }))

    // The tiles open the page behind their figure.
    fireEvent.click(tile('Spend'))
    expect(onNavigate).toHaveBeenLastCalledWith('ledger')
    fireEvent.click(tile('Main and checks'))
    expect(goTo).toHaveBeenLastCalledWith(expect.objectContaining({ tab: 'environment', environmentSection: 'checks' }))
    fireEvent.click(tile('Running'))
    expect(onNavigate).toHaveBeenLastCalledWith('activity')
    fireEvent.click(screen.getByRole('button', { name: /Profiles/ }))
    expect(goTo).toHaveBeenLastCalledWith(expect.objectContaining({ tab: 'profiles' }))
  })
})

describe('ac-rehomed: nothing the previous Overview showed is lost', () => {
  const unfinished: ProjectSetupItem = { id: 'profiles', key: 'profiles', dismissable: true, agent: null, provider: null, reason: null, detail: null }

  it.each([
    ['setup unfinished', [unfinished], true],
    ['setup finished', [], false],
  ] as const)('%s', (_name, items, checklist) => {
    setupItems = [...items]
    renderScreen()
    if (checklist) expect(screen.getByTestId('setup-item-profiles')).toBeInTheDocument()
    else expect(screen.queryByTestId('setup-list')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Quarantine and known failures' }))
    expect(screen.getByTestId('quarantined-q1')).toHaveTextContent('test_flaky_clock')
    fireEvent.click(screen.getByRole('button', { name: 'Profile status' }))
    expect(screen.getByTestId('posture-Developer')).toBeInTheDocument()
    expect(screen.getByTestId('posture-QA')).toBeInTheDocument()
  })
})

describe('a Hub older than GET /overview', () => {
  it('says to restart the Hub and keeps the previous needs list', () => {
    overviewData = null
    renderScreen()
    expect(screen.getByText('Restart the Hub to see the new Overview.')).toBeInTheDocument()
    expect(screen.getByTestId('classic-overview')).toBeInTheDocument()
    expect(screen.queryByRole('tab')).toBeNull()
  })
})

describe('the Briefing tab before its own task lands', () => {
  it('shows a placeholder, not an empty panel', () => {
    renderScreen()
    fireEvent.click(screen.getByRole('tab', { name: 'Briefing' }))
    expect(screen.getByRole('tabpanel')).toHaveTextContent('The Briefing will tell this same picture in sentences')
  })
})
