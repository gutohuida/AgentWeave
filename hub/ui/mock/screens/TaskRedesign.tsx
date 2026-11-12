import * as React from 'react'
import type { StoryEvent, Task, TaskStory } from '@/api/tasks'
import { BoardColumn } from '@/components/tasks/BoardColumn'
import { TaskCard } from '@/components/tasks/TaskCard'
import { TaskSummaryHeader } from '@/components/tasks/TaskSummaryHeader'
import { TaskTimeline } from '@/components/tasks/TaskTimeline'
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
    divergence_policy: 'notify',
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
    model: agent.startsWith('QA') ? 'claude-opus-5-5' : 'claude-sonnet-5-5', runner: 'claude', cost_usd: cost, tokens: 120_000, premium_requests: null, ai_nano_aiu: null, conversation_id: null, error: null,
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
  const story = React.useMemo(() => storyOf(now, selected.task), [now, selected.task])

  return (
    <div style={{ display: 'grid', gridTemplateColumns: drawerOpen ? 'minmax(0, 1fr) 400px' : 'minmax(0, 1fr)', height: '100%', minHeight: 0 }}>
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
      <aside style={{ borderLeft: '1px solid var(--border)', overflow: 'auto', background: 'var(--surface)' }} aria-label="Task drawer">
        <button type="button" className="aw-icon-button" aria-label="Close the task" title="Close" style={{ float: 'right', margin: '10px 10px 0 0' }} onClick={() => setDrawerOpen(false)}>
          <Icon name="close" size={14} />
        </button>
        <div style={{ padding: '14px 16px 0', display: 'grid', gap: 2 }}>
          <span style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 11, color: 'var(--text-2)' }}>{selected.task.readable_id}</span>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600, lineHeight: 1.35 }}>{selected.task.title}</h2>
        </div>
        <TaskSummaryHeader task={selected.task} summary={story.summary} specTag={selected.specTag} failedChecks={selected.failedChecks} colorOf={colorOf} now={now} />
        <div style={{ padding: '12px 16px 0', fontSize: 10.5, fontWeight: 500, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-3)' }}>Story</div>
        <TaskTimeline key={selected.task.id} events={story.events} now={now} />
      </aside>
      ) : null}
    </div>
  )
}
