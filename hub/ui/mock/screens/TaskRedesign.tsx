import * as React from 'react'
import type { RequirementLink, StoryEvent, Task, TaskCheckRun, TaskStory } from '@/api/tasks'
import { BoardColumn } from '@/components/tasks/BoardColumn'
import { TaskCard } from '@/components/tasks/TaskCard'
import { useQueryClient } from '@tanstack/react-query'
import { TaskDetailDrawer } from '@/components/tasks/TaskDetailDrawer'
import { toast } from '@/lib/toast'
import { PROJECT_ID } from '../fixtures'
import { Icon } from '@/components/common/Icon'
import { STAGE_LABELS } from '@/lib/taskStage'
import type { ScreenProps } from '../routes'
import '@/styles/board.css'

// mock state: hand-written tasks, one per stage the Hub reports (`hub/task_stage.py`) and both
// closes of slice loose-tasks, named after work this project really built on 2026-11-12.

const ROSTER = ['Architect', 'CodexSol', 'Developer', 'DeveloperOpus', 'DeveloperOpus2', 'DeveloperSonnet2', 'QA', 'QA2', 'mender']
const colorOf = (agent: string) => {
  const index = ROSTER.indexOf(agent)
  return index < 0 ? null : index
}

const ago = (now: Date, minutes: number) => new Date(now.getTime() - minutes * 60_000).toISOString()

interface MockTask {
  task: Task
  specTag: string
  failedChecks?: number
}

function make(now: Date, id: string, readable: string, title: string, status: string, fields: Partial<Task>): Task {
  return {
    id,
    readable_id: readable,
    project_id: 'proj-mock',
    title,
    status,
    priority: 'medium',
    created_at: ago(now, 600),
    updated: ago(now, 5),
    divergence_policy: 'surface',
    has_open_divergence: false,
    ...fields,
  } as Task
}

function tasks(now: Date): MockTask[] {
  return [
    { specTag: 'WETSV', task: make(now, 't1', 'WETSV-3', 'Session list shows each agent’s model and effort', 'pending', { stage: 'not_started', stage_since: ago(now, 95), stage_waits_on: 'WETSV-2', builder: 'DeveloperSonnet2' }) },
    { specTag: 'CNCC', task: make(now, 't2', 'CNCC-4', 'Capability page lists the changes waiting on it', 'assigned', { stage: 'not_started', stage_since: ago(now, 12), assignee: 'Developer', builder: 'Developer' }) },
    { specTag: 'TOFMF', task: make(now, 't3', 'TOFMF-1', 'Loose-task moves for the operator and piloted runs', 'in_progress', { stage: 'working', stage_since: ago(now, 14), assignee: 'DeveloperSonnet2', builder: 'DeveloperSonnet2', checker: 'QA' }) },
    { specTag: 'CNCC', task: make(now, 't4', 'CNCC-2', 'Waiting changes are ordered by first approval', 'in_progress', { stage: 'waiting_for_answer', stage_since: ago(now, 4), stage_waits_on: 'DeveloperOpus2', assignee: 'DeveloperOpus2', builder: 'DeveloperOpus2', priority: 'critical', awaiting_answer_reason: 'Order by first approval or by last approval?' }) },
    { specTag: 'FASSW', failedChecks: 3, task: make(now, 't5', 'FASSW-3', 'Settings rows hold any value the runner accepts', 'revision_needed', { stage: 'sent_back', stage_since: ago(now, 38), assignee: 'Developer', builder: 'Developer', checker: 'QA2' }) },
    { specTag: 'TOFMF', task: make(now, 't6', 'TOFMF-2', 'Close as done elsewhere, or cancel', 'completed', { stage: 'waiting_for_review', stage_since: ago(now, 7), assignee: 'DeveloperSonnet2', builder: 'DeveloperSonnet2', checker: 'QA' }) },
    { specTag: 'WETSV', task: make(now, 't7', 'WETSV-2', 'Each turn records the model it really ran on', 'under_review', { stage: 'under_review', stage_since: ago(now, 21), assignee: 'QA2', builder: 'DeveloperSonnet2', checker: 'QA2' }) },
    { specTag: 'PSWSN', task: make(now, 't8', 'PSWSN-2', 'Spec list filters by phase', 'approved', { stage: 'approved_waiting', stage_since: ago(now, 1), assignee: 'QA', builder: 'Developer' }) },
    { specTag: 'TOFMF', task: make(now, 't9', 'TOFMF-3', 'Drawer and board actions for loose tasks', 'approved', { stage: 'checking', stage_since: ago(now, 17), assignee: 'QA', builder: 'DeveloperSonnet2' }) },
    { specTag: 'CNCC', task: make(now, 't10', 'CNCC-3', 'Capability page shows when a change was built', 'approved', { stage: 'landing', stage_since: ago(now, 0.5), assignee: 'QA2', builder: 'Developer' }) },
    { specTag: 'TOFMF', task: make(now, 't11', 'TOFMF-4', 'Acceptance drive, written and failing first', 'approved', { stage: 'landing_held', stage_since: ago(now, 26), stage_waits_on: 'TOFMF-3', stage_detail: 'TOFMF-3', assignee: 'QA', builder: 'DeveloperSonnet2' }) },
    { specTag: 'SETUP', task: make(now, 't12', 'SETUP-2', 'Set-up list check', 'approved', { stage: 'did_not_land', stage_since: ago(now, 44), stage_detail: 'the project’s checkout has uncommitted changes to tracked files', assignee: 'QA2', builder: 'DeveloperOpus' }) },
    { specTag: 'GLANCE', task: make(now, 't13', 'GLANCE-1', 'Every card shows its task’s real stage', 'approved', { stage: 'on_main', stage_since: ago(now, 190), stage_detail: 'd4c8a34', assignee: 'QA2', builder: 'DeveloperSonnet2' }) },
    { specTag: 'TOFMF', task: make(now, 't14', 'TOFMF-5', 'Bulk close from the board', 'rejected', { stage: 'closed', stage_since: ago(now, 60), stage_detail: 'done by TOFMF-3', assignee: 'DeveloperSonnet2', builder: 'DeveloperSonnet2' }) },
    { specTag: 'FASSW', task: make(now, 't15', 'FASSW-4', 'Old settings page redirect', 'rejected', { stage: 'closed', stage_since: ago(now, 300), stage_detail: 'cancelled: not needed after FASSW-2', assignee: 'Developer', builder: 'Developer' }) },
  ]
}

// mock state: what the opened task shows. Each task gets a description, the requirements it serves
// in a spread of evidence states, criteria, linked tasks and its latest check run.
const STATEMENTS = [
  'A card shows only its title, its stage as a glyph and a word, time at stage, what it waits on, builder and reviewer, its spec’s tag and a failing-checks marker.',
  'Apart from its title, no card shows more than two lines of text at the board’s default width.',
  'A task whose latest checks failed shows, before review, a marker on its card naming how many checks failed.',
]

// mock state: a link's own `state` is its lifecycle (active); how its evidence stands is the
// document's coverage, seeded below. The id carries the coverage state so one fixture document can
// hold every combination.
const MOCK_DOCUMENT = { id: 'spdoc-mock', path: 'spec/changes/task-card-and-story-redesign/spec.json' }
const COVERAGE_STATES = ['verified', 'evidence_awaiting_review', 'rejected', 'in_progress']

function link(identifier: string, statement: string, coverage: string, rejected?: string): RequirementLink {
  return {
    identifier,
    requirement_id: `req-${identifier}-${coverage}`,
    document_id: MOCK_DOCUMENT.id,
    state: 'active',
    statement,
    modal: 'MUST',
    has_rejected_evidence: Boolean(rejected),
    latest_rejection_reason: rejected ?? null,
  }
}

const VERIFIED_STAGES = ['approved_waiting', 'checking', 'landing', 'landing_held', 'did_not_land', 'on_main']

function detailed(m: MockTask, all: MockTask[]): Task {
  const t = m.task
  const links =
    t.stage === 'sent_back'
      ? [
          link('FR-1', STATEMENTS[0], 'verified'),
          link('FR-2', STATEMENTS[1], 'rejected', 'The card wraps to three lines at 232px when the spec tag is long.'),
          link('FR-3', STATEMENTS[2], 'in_progress'),
        ]
      : t.stage === 'under_review'
        ? STATEMENTS.map((text, i) => link(`FR-${i + 1}`, text, 'evidence_awaiting_review'))
        : VERIFIED_STAGES.includes(t.stage ?? '')
          ? [link('FR-1', STATEMENTS[0], 'verified'), link('FR-2', STATEMENTS[1], 'verified')]
          : [link('FR-1', STATEMENTS[0], 'in_progress'), link('FR-2', STATEMENTS[1], 'in_progress')]
  const others = all.filter((o) => o.specTag === m.specTag && o.task.id !== t.id)
  const ref = (o: MockTask) => ({ id: o.task.id, readable_id: o.task.readable_id, title: o.task.title, status: o.task.status })
  return {
    ...t,
    description:
      'Rework the card so it reads at a glance. Replace the status sentence with a glyph and a word, put builder and reviewer on one line, and move everything else into the opened task.\n\nKeep the drag and keyboard moves the board has today.',
    acceptance_criteria: [
      'With one task building, one in review and one on main, the operator tells all three apart without opening one.',
      'At 232px no card shows a third line of text below its title.',
    ],
    requirement_links: links,
    prerequisites: others.slice(0, 1).map(ref),
    dependents: others.slice(1, 2).map(ref),
    notes: t.stage === 'sent_back' ? 'QA2: lint fails on the new file, and two board tests expect the old status line.' : undefined,
    assigner: 'Architect',
    level: 'reviewed',
  } as Task
}

const LINT_OUTPUT = [
  'src/components/tasks/TaskCard.tsx',
  "  42:7  error  'clock' is assigned a value but never used  @typescript-eslint/no-unused-vars",
  '',
  '1 problem (1 error, 0 warnings)',
].join('\n')
const TEST_OUTPUT = [
  'FAILED src/__tests__/taskCardCompact.test.tsx > shows the status line',
  '  Expected: "Waiting on you"',
  '  Received: null',
  '',
  '1 failed, 213 passed',
].join('\n')

function checksOf(m: MockTask, now: Date): TaskCheckRun | null {
  const stage = m.task.stage ?? ''
  if (['not_started', 'working', 'waiting_for_answer', 'closed'].includes(stage)) return null
  const failing = Boolean(m.failedChecks)
  const result = (name: string, ok: boolean, seconds: number, extra: Partial<TaskCheckRun['results'][number]> = {}) => ({
    name,
    exit_code: ok ? 0 : 1,
    timed_out: false,
    duration_seconds: seconds,
    output_tail: ok ? '' : name === 'lint' ? LINT_OUTPUT : TEST_OUTPUT,
    ...extra,
  })
  return {
    id: `run-${m.task.id}`,
    state: failing ? 'failed' : stage === 'checking' ? 'running' : 'passed',
    main_sha: 'd4c8a34',
    target_shas: ['4a87eb2'],
    merged_sha: null,
    error: '',
    started_at: ago(now, 30),
    ended_at: stage === 'checking' ? null : ago(now, 12),
    results: [
      result('hub-tests', true, 812),
      result('ui-tests', !failing, 96),
      result('lint', !failing, 31),
      result('types', true, 44),
      result('browser-tests', !failing, 230, failing ? { preexisting: true } : {}),
      result('docs', true, 0, { skipped: true }),
    ],
  }
}


const COLUMNS: Array<{ key: string; label: string; statuses: string[]; tone: string | null }> = [
  { key: 'todo', label: 'To do', statuses: ['pending', 'assigned'], tone: null },
  { key: 'doing', label: 'In progress', statuses: ['in_progress', 'blocked', 'revision_needed'], tone: 'var(--green)' },
  { key: 'review', label: 'Review', statuses: ['completed', 'under_review'], tone: 'var(--blue)' },
  { key: 'done', label: 'Approved and after', statuses: ['approved', 'rejected'], tone: 'var(--text-3)' },
]

/** A story long enough to fold: built, sent back for failing checks, rebuilt, now in review. */
function storyOf(now: Date, task: Task): TaskStory {
  let minute = 240
  let n = 0
  const at = (step = 6) => {
    minute -= step
    return ago(now, minute)
  }
  const id = () => `e${(n += 1)}`
  const transition = (from: string, to: string, actor: string, kind = 'agent', job: string | null = null): StoryEvent => ({
    kind: 'transition', id: id(), at: at(), from, to, actor_kind: kind, actor, origin: 'mcp', job, job_kind: job ? 'flow' : null, run_id: null, override_reason: null,
  })
  const run = (agent: string, seconds: number, cost: number, status = 'completed'): StoryEvent => ({
    kind: 'run', id: id(), at: at(seconds / 60 + 1), agent, status, ended_at: status === 'running' ? null : ago(now, minute - seconds / 60), duration_seconds: status === 'running' ? null : seconds,
    model: agent.startsWith('QA') ? 'claude-opus-5-5' : 'claude-sonnet-5-5', runner: 'claude', cost_usd: cost, tokens: 120_000, premium_requests: null, ai_nano_aiu: null, conversation_id: 'conv-e3aba2c5956a', error: null,
  })
  const evidence = (summary: string, decision?: 'accepted' | 'rejected'): StoryEvent => ({
    kind: 'evidence', id: id(), at: at(2),
    evidence: { id: `ev-${n}`, summary, kind: 'test_result', locator: null, actor_kind: 'agent', actor: task.builder ?? 'Developer', run_id: null, task_id: task.id, review_state: decision ?? 'awaiting', latest_review: null, produced_at: ago(now, minute), footprint: null } as never,
    reviews: decision ? [{ decision, actor_kind: 'agent', actor: 'QA2', reason: null, at: ago(now, minute) }] : [],
  })
  const builder = task.builder ?? 'DeveloperSonnet2'
  const events: StoryEvent[] = [
    { kind: 'created', id: id(), at: at(0), by: 'Architect' },
    transition('pending', 'assigned', 'build-plan', 'hub', 'Build WETSV'),
    transition('assigned', 'in_progress', builder),
    run(builder, 1260, 1.84),
    evidence('FR-1: turn rows carry the model the runner reported; 6 tests pass'),
    evidence('FR-2: the session list reads it; vitest sessionList 14 passed'),
    { kind: 'question', id: id(), at: at(3), agent: builder, question: 'Should a turn with no reported model show the agent’s configured one, or nothing?', answered: true, answer: 'Nothing, and say “not reported”.', declined: false, wait_ended_at: ago(now, minute - 2) },
    run(builder, 420, 0.61),
    transition('in_progress', 'completed', builder),
    { kind: 'check', id: id(), at: at(18), state: 'failed', ended_at: ago(now, minute - 17), results: [
      { name: 'hub-tests', passed: false, exit_code: 1 }, { name: 'ui-tests', passed: false, exit_code: 1 }, { name: 'lint', passed: false, exit_code: 1 }, { name: 'types', passed: true, exit_code: 0 },
    ], error: null, merged_sha: null },
    transition('completed', 'revision_needed', 'QA2'),
    transition('revision_needed', 'in_progress', builder),
    run(builder, 900, 1.12),
    evidence('Lint and the two failing tests fixed; hub-tests 412 passed'),
    transition('in_progress', 'completed', builder),
    { kind: 'check', id: id(), at: at(16), state: 'passed', ended_at: ago(now, minute - 15), results: [{ name: 'hub-tests', passed: true }, { name: 'ui-tests', passed: true }, { name: 'lint', passed: true }, { name: 'types', passed: true }], error: null, merged_sha: null },
    transition('completed', 'under_review', 'QA2'),
    run('QA2', 0, 0.4, 'running'),
  ]
  return {
    task: { id: task.id, title: task.title, status: task.status },
    summary: { runs: 4, cost_usd: 3.97, tokens: 480_000, premium_requests: null, ai_nano_aiu: null, evidence: { accepted: 0, rejected: 0, awaiting: 3 }, merged: [], overrides: 0 },
    events,
  }
}

/** The stages a card steps through to show its motion (FR-7). */
const PARADE = ['not_started', 'working', 'waiting_for_review', 'under_review', 'approved_waiting', 'checking', 'landing', 'on_main']

export default function TaskRedesign({ now }: ScreenProps) {
  const all = React.useMemo(() => tasks(now), [now])
  const [selectedId, setSelectedId] = React.useState('t7')
  const [parade, setParade] = React.useState(0)
  const [playing, setPlaying] = React.useState(false)
  const [drawerOpen, setDrawerOpen] = React.useState(true)
  const open = (id: string) => {
    setSelectedId(id)
    setDrawerOpen(true)
  }
  React.useEffect(() => {
    if (!playing) return
    const timer = setInterval(() => setParade((i) => (i + 1) % PARADE.length), 1400)
    return () => clearInterval(timer)
  }, [playing])

  const paradeTask: MockTask = {
    specTag: 'DEMO',
    task: make(now, 'parade', 'DEMO-1', 'A card stepping through its stages', 'in_progress', {
      stage: PARADE[parade], stage_since: ago(now, 0.2), builder: 'DeveloperSonnet2', assignee: PARADE[parade] === 'under_review' ? 'QA2' : 'DeveloperSonnet2',
    }),
  }
  const selected = all.find((m) => m.task.id === selectedId) ?? all[6]
  const sheetTask = React.useMemo(() => detailed(selected, all), [selected, all])
  const queryClient = useQueryClient()
  const story = React.useMemo(() => {
    // mock state: the summary's evidence counts follow the task's requirement states.
    const base = storyOf(now, selected.task)
    const links = sheetTask.requirement_links ?? []
    const count = (state: string) => links.filter((l) => l.requirement_id.endsWith(`-${state}`)).length
    return { ...base, summary: { ...base.summary, evidence: { accepted: count('verified'), rejected: count('rejected'), awaiting: count('evidence_awaiting_review') } } }
  }, [now, selected.task, sheetTask])
  // mock state: today's dialog reads the story and the checks through its hooks; the mock answers
  // from the cache under the same keys (mock/README.md), so the dialog on screen is the real one.
  queryClient.setQueryData(['project', PROJECT_ID, 'tasks', selected.task.id, 'story'], story)
  const checks = checksOf(selected, now)
  queryClient.setQueryData(['project', PROJECT_ID, 'specDocuments'], {
    documents: [{ ...MOCK_DOCUMENT, title: 'Task card and story redesign', kind: 'change-spec', phase: 'exploring' }],
  })
  queryClient.setQueryData(['project', PROJECT_ID, 'specCoverage', MOCK_DOCUMENT.path], {
    requirements: ['FR-1', 'FR-2', 'FR-3'].flatMap((identifier) =>
      COVERAGE_STATES.map((state) => ({ identifier, requirement_id: `req-${identifier}-${state}`, state })),
    ),
  })
  queryClient.setQueryData(['project', PROJECT_ID, 'task', selected.task.id, 'checks'], {
    configured: true,
    running: checks?.state === 'running',
    runs: checks ? [checks] : [],
  })

  return (
    <div style={{ position: 'relative', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', height: '100%', minHeight: 0, overflow: 'hidden' }}>
      <div style={{ display: 'grid', gridTemplateRows: 'auto 1fr', minHeight: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: '1px solid var(--border)' }}>
          <span style={{ fontSize: 12, color: 'var(--text-2)' }}>Motion:</span>
          <div style={{ width: 260 }}>
            <TaskCard task={paradeTask.task} specTag={paradeTask.specTag} colorOf={colorOf} now={now} onOpen={() => setPlaying((p) => !p)} />
          </div>
          <button type="button" className="aw-icon-button" style={{ width: 'auto', padding: '0 10px', gap: 6, display: 'inline-flex', alignItems: 'center', fontSize: 12 }} onClick={() => setParade((i) => (i + 1) % PARADE.length)}>
            <Icon name="arrow_forward" size={12} /> Next stage
          </button>
          <button type="button" className="aw-icon-button" style={{ width: 'auto', padding: '0 10px', gap: 6, display: 'inline-flex', alignItems: 'center', fontSize: 12 }} onClick={() => setPlaying((p) => !p)}>
            <Icon name={playing ? 'pause' : 'play_arrow'} size={12} /> {playing ? 'Stop' : 'Play'}
          </button>
          <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>{STAGE_LABELS[PARADE[parade]]}</span>
        </div>
        <div className="aw-board-scroll">
          <div className="aw-board-columns">
            {COLUMNS.map((column) => {
              const cards = all.filter((m) => column.statuses.includes(m.task.status))
              return (
                <BoardColumn key={column.key} id={column.key} label={column.label} tone={column.tone} count={cards.length} folded={false} onToggleFold={() => undefined}>
                  {cards.map((m) => (
                    <TaskCard
                      key={m.task.id}
                      task={m.task}
                      specTag={m.specTag}
                      failedChecks={m.failedChecks}
                      colorOf={colorOf}
                      now={now}
                      selected={m.task.id === selectedId}
                      onOpen={open}
                    />
                  ))}
                </BoardColumn>
              )
            })}
          </div>
        </div>
      </div>
      {drawerOpen ? (
        <TaskDetailDrawer
          key={selected.task.id}
          task={sheetTask}
          onClose={() => setDrawerOpen(false)}
          onOpenRequirement={(path, anchor) => toast({ title: `Opens ${anchor}`, description: `In ${path}. Mock: nothing navigates.` })}
        />
      ) : null}
    </div>
  )
}
