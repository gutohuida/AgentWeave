import * as React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AgentPoolEntry } from '@/api/agentPool'
import type { NeverQuarantineMark, QuarantinedTest } from '@/api/quarantine'
import type { ModelCatalogResponse } from '@/api/modelCatalog'
import type { Task } from '@/api/tasks'
import type { AgentSummary } from '@/api/agents'
import { PoolEditor } from '@/components/agents/pool/PoolEditor'
import { cliLabel, entryLabel } from '@/components/agents/pool/poolModel'
import { Icon, ProviderMark } from '@/components/common/Icon'
import { ConversationComposerDock } from '@/components/conversation/ConversationComposerDock'
import { NewConversationIntro } from '@/components/conversation/NewConversationIntro'
import { TopBar } from '@/components/layout/TopBar'
import { FirstRunPath, QuickstartLink } from '@/components/overview/FirstRunPath'
import { QuarantineList } from '@/components/overview/QuarantineList'
import { SetupList, type SetupItem } from '@/components/overview/SetupList'
import { describeSetupItem } from '@/components/overview/setupItems'
import { ProfilesIndex } from '@/components/profiles/ProfilesIndex'
import { BoardView } from '@/components/tasks/BoardView'
import { Button } from '@/components/ui/button'
import { toast } from '@/lib/toast'
import { PROJECT_TABS } from '@/lib/navigation'
import { agents, MOCK_NOW, PROJECT_ID, project, projects, tasks as fixtureTasks } from '../fixtures'
import modelCatalog from '../fixtures/model_catalog.json'
import { POOL_CATALOG } from '../poolMock'
import { PROFILE_ITEMS } from '../profilesMock'
import type { ScreenProps } from '../routes'
import '@/styles/overview.css'
import '@/styles/setup.css'
import '@/styles/conversation.css'
import '@/styles/profile-pool.css'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
queryClient.setQueryData(['model-catalog'], modelCatalog as unknown as ModelCatalogResponse)

const noop = () => undefined

// -- shared furniture ---------------------------------------------------------------------------

function Panel({ id, title, lede, children }: { id: string; title: string; lede?: string; children: React.ReactNode }) {
  return (
    <section className="mock-frp-panel" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {lede ? <p>{lede}</p> : null}
      {children}
    </section>
  )
}

/** One state: today beside proposed. */
function Pair({ state, today, proposed, stack = false }: { state?: string; today: React.ReactNode; proposed: React.ReactNode; stack?: boolean }) {
  return (
    <div>
      {state ? <p className="mock-frp-cap" style={{ color: 'var(--text-2)' }}>{state}</p> : null}
      <div className="mock-frp-pair" data-stack={stack ? 'true' : undefined}>
        <div className="mock-frp-box">
          <p className="mock-frp-cap">Today</p>
          {today}
        </div>
        <div className="mock-frp-box">
          <p className="mock-frp-cap" data-kind="proposed">Proposed</p>
          {proposed}
        </div>
      </div>
    </div>
  )
}

/** A fixed content width, so a layout can be judged at 1200, 850 or 650 px whatever the window. */
function Width({ px, children, zoom }: { px: number; children: React.ReactNode; zoom?: number }) {
  return (
    <div className="mock-frp-scroll">
      <div style={{ width: px, zoom }}>{children}</div>
    </div>
  )
}

// -- 1. Quarantined tests -----------------------------------------------------------------------

const minutesAgo = (m: number) => new Date(MOCK_NOW.getTime() - m * 60_000).toISOString()
const LONG_ID = 'tests/integration/test_landing_queue.py::TestLandingQueue::test_a_task_that_lands_while_another_is_rebasing_keeps_its_own_checks'
const QUARANTINED: QuarantinedTest[] = [
  {
    id: 'q1',
    check: 'hub-tests',
    test: 'tests/test_watcher.py::test_folder_watch_debounce',
    flake_rate: 0.18,
    flips: 4,
    entered_at: minutesAgo(26 * 60),
    passes: 3,
    passes_to_exit: 10,
    fix_task_id: 'task-fix-1',
    fix_task: { id: 'task-fix-1', display_id: 'AW-212', title: 'Stabilise the watcher debounce test', status: 'in_progress' },
  },
]
const MARKS: NeverQuarantineMark[] = [
  { id: 'm1', check: 'hub-tests', test: 'tests/test_landing.py::test_a_landing_never_loses_a_commit', marked_at: minutesAgo(3 * 24 * 60) },
]
const LONG: QuarantinedTest[] = [{ ...QUARANTINED[0]!, id: 'q2', test: LONG_ID, fix_task_id: null, fix_task: null }]
const LONG_MARKS: NeverQuarantineMark[] = [{ id: 'm2', check: 'hub-tests', test: LONG_ID, marked_at: minutesAgo(3 * 24 * 60) }]

/** mock: the section as it was (old markup, old classes), since the component itself has changed. */
function TodayQuarantine({ quarantined, marks }: { quarantined: QuarantinedTest[]; marks: NeverQuarantineMark[] }) {
  return (
    <section className="aw-ov-section" style={{ marginTop: 0 }}>
      <h2 className="aw-ov-heading">
        Quarantined tests {quarantined.length ? <span className="aw-ov-count" data-tone="amber">{quarantined.length}</span> : null}
      </h2>
      {quarantined.length === 0 ? (
        <div className="aw-ov-calm">
          <Icon name="check_circle" size={15} /> No test is quarantined.
        </div>
      ) : (
        <ul className="aw-ov-list">
          {quarantined.map((e) => (
            <li key={e.id} className="aw-ov-row aw-ov-kf-row">
              <span className="aw-ov-row-icon" data-kind="flaky" aria-hidden="true" />
              <span className="aw-ov-row-text">
                <span className="aw-ov-row-title" title={e.test}>{e.test}</span>
                <span className="aw-ov-row-detail">
                  {e.check} · flake rate {e.flake_rate?.toFixed(2)} on entry · {e.passes} of {e.passes_to_exit} passes to leave
                </span>
              </span>
              <span className="aw-ov-row-end">
                <button type="button" className="aw-overview-link">Never quarantine</button>
                <span>{e.fix_task ? `${e.fix_task.display_id} · ${e.fix_task.status?.replace('_', ' ')}` : 'No fix task'}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      <div className="aw-ov-kf-disturbed">
        <h3 className="aw-ov-row-detail">Never quarantined</h3>
        {marks.length === 0 ? (
          <p className="aw-ov-row-detail">No test is marked.</p>
        ) : (
          <ul className="aw-ov-list">
            {marks.map((m) => (
              <li key={m.id} className="aw-ov-row">
                <span className="aw-ov-row-text">
                  <span className="aw-ov-row-title" title={m.test}>{m.test}</span>
                  <span className="aw-ov-row-detail">{m.check}</span>
                </span>
                <span className="aw-ov-row-end">
                  <button type="button" className="aw-overview-link">Remove mark</button>
                </span>
              </li>
            ))}
          </ul>
        )}
        <form className="aw-ov-row-detail" onSubmit={(e) => e.preventDefault()}>
          <input aria-label="Check name (today)" placeholder="check" /> <input aria-label="Test id (today)" placeholder="test id" />{' '}
          <button type="submit" className="aw-overview-link">Never quarantine a test</button>
        </form>
      </div>
    </section>
  )
}

function Quarantine({ quarantined, marks }: { quarantined: QuarantinedTest[]; marks: NeverQuarantineMark[] }) {
  return (
    <QuarantineList
      quarantined={quarantined}
      marks={marks}
      onSetMark={(c, t) => toast({ title: 'Marked never to be quarantined', description: `${c}: ${t}`, tone: 'success' })}
      onRemoveMark={() => toast({ title: 'Mark removed' })}
      onOpenTask={() => toast({ title: 'Opens the fix task' })}
      now={MOCK_NOW}
    />
  )
}

function QuarantinePanel() {
  return (
    <Panel
      id="frp-q"
      title="1. Quarantined tests read like the rest of the Overview"
      lede="Real inputs and Button, a label above each field, the never-quarantined marks in the same rows with their action at the row end, a real icon, and long ids cut with the whole id on hover."
    >
      <Pair state="Nothing quarantined, nothing marked" today={<TodayQuarantine quarantined={[]} marks={[]} />} proposed={<Quarantine quarantined={[]} marks={[]} />} />
      <Pair state="One quarantined, one marked" today={<TodayQuarantine quarantined={QUARANTINED} marks={MARKS} />} proposed={<Quarantine quarantined={QUARANTINED} marks={MARKS} />} />
      <Pair
        state="A long test id, at a narrow width (360 px)"
        today={<Width px={360}><TodayQuarantine quarantined={LONG} marks={LONG_MARKS} /></Width>}
        proposed={<Width px={360}><Quarantine quarantined={LONG} marks={LONG_MARKS} /></Width>}
      />
    </Panel>
  )
}

// -- 2. One merged first-run checklist ----------------------------------------------------------

const item = (key: SetupItem['key']): SetupItem => {
  const described = describeSetupItem(
    { id: key, key, dismissable: true, agent: null, provider: null, reason: null, detail: null },
    PROJECT_ID,
    () => toast({ title: 'Opens the setup offer’s dialog' }),
  )
  return { ...described, action: { ...described.action, onClick: () => toast({ title: described.action.label }) } }
}
const PROFILES_ITEM = item('profiles')
const SPEC_ITEM = item('specification')
const dismiss = (i: SetupItem) => toast({ title: 'Dismissed for this project', description: i.title })

/** mock: the Welcome card as it was (`FirstRunPanel`, now gone): its path and its two buttons. */
function TodayWelcome({ agent }: { agent: string | null }) {
  return (
    <section className="aw-setup" aria-label="Getting started">
      <header className="aw-setup-head">
        <h2 className="aw-setup-title">Welcome. Here is how work gets done in a project</h2>
      </header>
      <FirstRunPath current={agent ? 1 : 0} />
      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 14, paddingBottom: 8 }}>
        <Button variant="primary" size="sm" onClick={noop}>{agent ? `Ask ${agent} for a change` : 'Add a profile'}</Button>
        <a className="aw-link aw-link-inline" href="#first-run-polish" onClick={(e) => e.preventDefault()}>
          Read the quickstart <Icon name="arrow_forward" size={12} />
        </a>
      </div>
    </section>
  )
}

function Setup({ items, path }: { items: SetupItem[]; path?: number }) {
  return <SetupList place="overview" items={items} path={path === undefined ? undefined : { current: path }} onDismiss={dismiss} />
}

function ChecklistPanel() {
  return (
    <Panel
      id="frp-c"
      title="2. One first-run card, not two"
      lede="The set-up card lists only what still applies and carries the path as a quiet line, with the current step marked. No second card, no repeated Add a profile or Ask for a change button. When nothing is left, only the quickstart link stays."
    >
      <Pair
        state="No profiles"
        today={<><Setup items={[PROFILES_ITEM, SPEC_ITEM]} /><TodayWelcome agent={null} /></>}
        proposed={<Setup items={[PROFILES_ITEM, SPEC_ITEM]} path={0} />}
      />
      <Pair
        state="Profiles added"
        today={<><Setup items={[SPEC_ITEM]} /><TodayWelcome agent="Builder" /></>}
        proposed={<Setup items={[SPEC_ITEM]} path={1} />}
      />
      <Pair state="Everything done or marked Not for this project" today={<TodayWelcome agent="Builder" />} proposed={<QuickstartLink />} />
    </Panel>
  )
}

// -- 3. Model and CLI said once -----------------------------------------------------------------

const BUILDER: AgentSummary = agents.find((a) => a.name === 'Builder') ?? agents[0]!
const STARTERS = [{ label: 'Pick up the next task', message: 'Look at the open tasks assigned to you and start on the most important one.', icon: 'task_alt' }]

/** mock: the intro as it was; only its "runs on" line differed, so the rest is the real component. */
function NewThread({ proposed }: { proposed: boolean }) {
  return (
    <div className="flex flex-col overflow-hidden" style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
      <div className={proposed ? undefined : 'mock-frp-today-intro'} style={{ padding: '8px 0 4px' }}>
        <NewConversationIntro agent={BUILDER} runnerLabel="Claude Code" starters={STARTERS} onPick={noop} />
      </div>
      <ConversationComposerDock
        selected={[]}
        onToggleOption={noop}
        composer={{
          key: proposed ? 'p' : 't',
          agent: BUILDER.name,
          projectId: PROJECT_ID,
          conversationId: null,
          isRunning: false,
          onSubmit: async () => toast({ title: 'Sent', tone: 'success' }),
          runner: 'claude',
          effectiveModel: 'claude-haiku-5-5',
        }}
      />
    </div>
  )
}

const POOL_CATALOG_45: ModelCatalogResponse = {
  providers: POOL_CATALOG.providers.map((p) =>
    p.provider === 'claude'
      ? { ...p, models: [...p.models, { id: 'claude-haiku-4-5', label: 'Haiku 4.5', aliases: [], context_window: 200_000, default: false }] }
      : p,
  ),
}
const entry = (id: string, runnerName: string, cli: 'claude' | 'codex', model: string, effort: string | null, isDefault = false): AgentPoolEntry => ({
  id,
  runner_id: `runner-${id}`,
  runner_name: runnerName,
  cli,
  model,
  effort,
  default: isDefault,
})
const POOL: AgentPoolEntry[] = [
  entry('a', 'Claude Code — Haiku 5.5', 'claude', 'claude-haiku-5-5', null, true),
  entry('b', 'Claude Code — Haiku 4.5', 'claude', 'claude-haiku-4-5', 'high'),
  entry('c', 'Codex — GPT-6-Luna', 'codex', 'gpt-6-luna', null),
]

/** mock: the pool rows as they were: the runner's name, a dot, the CLI. */
function TodayPool() {
  return (
    <ul className="aw-pool-list" aria-label="Models Builder may run on" style={{ margin: 0 }}>
      {POOL.map((e) => (
        <li key={e.id} className="aw-pool-entry" data-default={e.default ? 'true' : undefined}>
          <ProviderMark provider={e.cli} label={cliLabel(e.cli)} size={16} />
          <span className="aw-pool-entry-text">
            <span className="aw-pool-entry-label">{entryLabel(POOL_CATALOG_45, e)}</span>
            <span className="aw-pool-entry-detail">{e.runner_name} · {cliLabel(e.cli)}</span>
          </span>
          {e.default ? (
            <span className="aw-pool-default"><Icon name="check" size={12} /> Default</span>
          ) : (
            <Button variant="ghost" size="xs" onClick={noop}>Make default</Button>
          )}
          <button data-slot="icon-button" type="button" className="aw-icon-button" aria-label="Remove"><Icon name="close" size={13} /></button>
        </li>
      ))}
    </ul>
  )
}

function RepetitionPanel() {
  return (
    <Panel
      id="frp-r"
      title="3. The model and the CLI are said once"
      lede="The new-thread intro keeps to what the composer’s chips do not say. A pool row names the model and effort in its title and the CLI once in its detail."
    >
      <Pair state="3a. The new-thread intro, with the composer’s chips under it" today={<NewThread proposed={false} />} proposed={<NewThread proposed />} />
      <Pair
        state="3b. Pool rows on a profile’s Models tab"
        today={<TodayPool />}
        proposed={<PoolEditor agentName="Builder" pool={POOL} catalog={POOL_CATALOG_45} onAdd={noop} onRemove={noop} onMakeDefault={noop} />}
      />
    </Panel>
  )
}

// -- 4. Top bar ---------------------------------------------------------------------------------

function TopBarPanel() {
  const [mode] = React.useState<'dark' | 'light'>(() => (document.documentElement.dataset.mode === 'light' ? 'light' : 'dark'))
  return (
    <Panel
      id="frp-t"
      title="4. The Thread tab is called Chapters"
      lede="Its label only: the route, the address and the ids still say thread. Today the bar read Overview, Thread, Tasks and so on."
    >
      <div className="mock-frp-frame">
        <TopBar
          project={{ id: project.id, name: project.name, path: project.working_directory }}
          projects={projects.map((p) => ({ id: p.id, name: p.name, path: p.working_directory }))}
          tabs={PROJECT_TABS}
          active="thread"
          onSelectTab={noop}
          onSelectProject={noop}
          onOpenPalette={noop}
          onOpenSettings={noop}
          mode={mode}
          onToggleMode={noop}
        />
      </div>
    </Panel>
  )
}

// -- 5. Tasks filter bar ------------------------------------------------------------------------

const NAMES = ['Builder', 'Checker', 'QA']
const BAR_AGENTS: AgentSummary[] = NAMES.map((name, i) => ({ ...(agents[i] ?? agents[0]!), name }))
// mock state: the first dozen recorded tasks, shared among the three profiles; the last three are on main.
const BAR_TASKS: Task[] = fixtureTasks.slice(0, 12).map((t, i) => ({
  ...t,
  assignee: NAMES[i % 3]!,
  ...(i >= 9 ? { stage: 'on_main' } : {}),
}))
const NO_WORK: ReadonlySet<string> = new Set()

function Bar({ today, px }: { today?: boolean; px: number }) {
  const [view, setView] = React.useState<'board' | 'dependencies'>('board')
  return (
    <Width px={px} zoom={px > 1000 ? 0.9 : undefined}>
      <div className={`mock-frp-frame mock-frp-board${today ? ' mock-today-board' : ''}`}>
        <BoardView
          tasks={BAR_TASKS}
          agents={BAR_AGENTS}
          workingTaskIds={NO_WORK}
          view={view}
          onViewChange={setView}
          folds={{}}
          onFoldsChange={noop}
          onOpenTask={noop}
          onRetryIntegration={noop}
          now={MOCK_NOW}
        />
      </div>
    </Width>
  )
}

function TasksBarPanel() {
  return (
    <Panel
      id="frp-b"
      title="5. The tasks filter bar never clips"
      lede="Three profiles: Builder, Checker and QA. When the bar does not fit it wraps to a second row, search and Select keep a usable width, no label wraps inside its control, and the hidden-finished line lines up with the cards."
    >
      {[1200, 850, 650].map((px) => (
        <Pair stack key={px} state={`${px} px of content${px > 1000 ? ' (shown at 90 % so it fits this page)' : ''}`} today={<Bar today px={px} />} proposed={<Bar px={px} />} />
      ))}
    </Panel>
  )
}

// -- 6. Profiles index count --------------------------------------------------------------------

const ACTIVE = PROFILE_ITEMS.filter((p) => !p.archived)
const ARCHIVED = PROFILE_ITEMS.find((p) => p.archived)!

function IndexPanel() {
  const withArchived = [ACTIVE[0]!, ARCHIVED]
  const bothActive = [ACTIVE[0]!, ACTIVE[1]!]
  const index = (items: typeof withArchived) => (
    <div className="mock-frp-frame">
      <ProfilesIndex items={items} query="" onQueryChange={noop} onOpen={noop} onNewThread={noop} onAdd={noop} now={MOCK_NOW} />
    </div>
  )
  return (
    <Panel id="frp-i" title="6. The Profiles count is of the profiles in play" lede="An archived profile has its own counted group below, so the line above the list does not add it in.">
      <Pair
        state="Two profiles, one archived"
        stack
        today={<div className="mock-frp-today-count">{index(withArchived)}</div>}
        proposed={index(withArchived)}
      />
      <Pair stack state="Two profiles, none archived (unchanged)" today={index(bothActive)} proposed={index(bothActive)} />
    </Panel>
  )
}

export default function FirstRunPolish(props: ScreenProps) {
  void props
  return (
    <QueryClientProvider client={queryClient}>
      <div className="mock-frp">
        <QuarantinePanel />
        <ChecklistPanel />
        <RepetitionPanel />
        <TopBarPanel />
        <TasksBarPanel />
        <IndexPanel />
      </div>
    </QueryClientProvider>
  )
}
