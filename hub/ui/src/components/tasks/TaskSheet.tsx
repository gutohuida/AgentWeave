import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { buttonVariants } from '@/components/ui/buttonVariants'
import { Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger } from '@/components/ui/menu'
import { DIVERGENCE_POLICY_LABELS, type RequirementLink, type Task, type TaskCheckResult, type TaskCheckRun, type TaskDependencyRef, type TaskStory } from '@/api/tasks'
import { formatAgo, formatDateTime } from '@/lib/format'
import { stageVisual } from '@/lib/taskStageVisual'
import { TaskSummaryHeader } from './TaskSummaryHeader'
import { TaskTimeline } from './TaskTimeline'
import '@/styles/task-redesign.css'
import '@/styles/task-sheet.css'

/** What the operator can do from the opened task. The container maps each to its mutation. */
export type TaskSheetAction =
  | 'start'
  | 'open-conversation'
  | 'answer'
  | 'hand-to-reviewer'
  | 'approve'
  | 'send-back'
  | 'retry-landing'
  | 'reopen'
  | 'move'
  | 'close-done-elsewhere'
  | 'cancel'
  | 'priority'
  | 'rerun-checks'
  | 'rename'
  | 'copy-id'
  | 'delete'

export type TaskSheetTab = 'story' | 'work' | 'details'

/** The opened task, redesigned (`task-card-and-story-redesign`): the same side sheet the board
 *  opens today, rebuilt around where the task stands.
 *
 *  Top to bottom: its name; a line that needs the operator, when one does (a question, a landing
 *  that did not happen, failing checks); where it stands (the summary); the one action its stage
 *  calls for, beside a menu of every other move; then three tabs. Story is the timeline. Work is
 *  what it is checked against and how that stands: requirements with their evidence, acceptance
 *  criteria, the latest checks and the landing. Details holds the rest: description, what it waits
 *  on and what waits on it, notes, and the facts. Presentational: the container passes the task,
 *  its story and its latest check run, and maps actions to mutations. */
export function TaskSheet({
  task,
  story,
  checks,
  specTag,
  colorOf,
  now,
  initialTab = 'story',
  onAction,
  onOpenTask,
  onClose,
}: {
  task: Task
  story?: TaskStory | null
  checks?: TaskCheckRun | null
  specTag?: string
  colorOf?: (agent: string) => number | null | undefined
  now?: Date
  initialTab?: TaskSheetTab
  onAction: (action: TaskSheetAction) => void
  onOpenTask?: (taskId: string) => void
  onClose: () => void
}) {
  const [tab, setTab] = React.useState<TaskSheetTab>(initialTab)
  const failed = (checks?.results ?? []).filter(isFailure)
  const failedChecks = checks && (checks.state === 'failed' || checks.state === 'error') ? failed.length : 0
  const links = task.requirement_links ?? []
  const met = links.filter((link) => link.state === 'verified').length
  const primary = primaryAction(task)
  const attention = attentionOf(task, failedChecks)
  return (
    <section className="aw-sheet" aria-label={`Task ${task.readable_id ?? ''} ${task.title}`}>
      <header className="aw-sheet-head">
        <div className="aw-sheet-ids">
          {task.readable_id ? <span className="aw-tcard-id">{task.readable_id}</span> : null}
          {specTag ? <span className="aw-tcard-tag">{specTag}</span> : null}
          {task.priority === 'critical' ? (
            <span className="aw-tcard-marker" data-kind="critical">
              <Icon name="flag" size={11} /> Critical
            </span>
          ) : null}
          <button type="button" data-slot="icon-button" className="aw-icon-button aw-sheet-close" aria-label="Close" title="Close" onClick={onClose}>
            <Icon name="close" size={15} />
          </button>
        </div>
        <h2 className="aw-sheet-title">
          <button type="button" data-slot="drawer-title" title="Rename" onClick={() => onAction('rename')}>
            {task.title}
          </button>
        </h2>
      </header>

      {attention ? (
        <div className="aw-sheet-attention" data-tone={attention.tone} role="status">
          <Icon name={attention.glyph} size={14} />
          <div>
            <strong>{attention.title}</strong>
            {attention.text ? <p>{attention.text}</p> : null}
          </div>
        </div>
      ) : null}

      <TaskSummaryHeader task={task} summary={story?.summary} specTag={undefined} failedChecks={failedChecks} colorOf={colorOf} now={now} />

      <div className="aw-sheet-actions">
        {primary ? (
          <Button variant="primary" size="sm" onClick={() => onAction(primary.action)}>
            <Icon name={primary.glyph} size={13} />
            {primary.label}
          </Button>
        ) : (
          <span className="aw-sheet-nothing">{nothingToDo(task)}</span>
        )}
        {task.stage === 'under_review' ? (
          <Button variant="outline" size="sm" onClick={() => onAction('send-back')}>
            <Icon name="restart_alt" size={13} />
            Send back
          </Button>
        ) : null}
        <Menu>
          <MenuTrigger data-slot="menu-trigger" className={`${buttonVariants({ variant: 'ghost', size: 'sm' })} aw-sheet-more`} aria-label="More actions">
            <Icon name="more_horiz" size={14} />
            More
          </MenuTrigger>
          <MenuContent align="end">
            <MenuLabel>Move this task</MenuLabel>
            <MenuItem icon="arrow_forward" onSelect={() => onAction('move')}>Move to another status…</MenuItem>
            <MenuItem icon="task_alt" onSelect={() => onAction('close-done-elsewhere')}>Close as done elsewhere…</MenuItem>
            <MenuItem icon="remove_circle" onSelect={() => onAction('cancel')}>Cancel this task…</MenuItem>
            <MenuLabel>Change</MenuLabel>
            <MenuItem icon="flag" onSelect={() => onAction('priority')}>Change priority…</MenuItem>
            <MenuItem icon="edit" onSelect={() => onAction('rename')}>Rename</MenuItem>
            <MenuItem icon="content_copy" onSelect={() => onAction('copy-id')}>Copy its id</MenuItem>
            <MenuItem icon="delete" onSelect={() => onAction('delete')}>Delete…</MenuItem>
          </MenuContent>
        </Menu>
      </div>

      <div className="aw-sheet-tabs" role="tablist" aria-label="Task view">
        <Tab id="story" current={tab} onSelect={setTab} label="Story" count={story?.events.length} />
        <Tab id="work" current={tab} onSelect={setTab} label="Work" count={links.length ? `${met}/${links.length}` : undefined} alert={failedChecks > 0 || links.some((l) => l.has_rejected_evidence)} />
        <Tab id="details" current={tab} onSelect={setTab} label="Details" />
      </div>

      <div className="aw-sheet-body" role="tabpanel">
        {tab === 'story' ? (
          story ? <TaskTimeline key={task.id} events={story.events} now={now} /> : <p className="aw-sheet-empty">No story yet.</p>
        ) : tab === 'work' ? (
          <WorkTab task={task} checks={checks ?? null} now={now} onAction={onAction} />
        ) : (
          <DetailsTab task={task} now={now} onOpenTask={onOpenTask} />
        )}
      </div>
    </section>
  )
}

function Tab({ id, current, onSelect, label, count, alert }: { id: TaskSheetTab; current: TaskSheetTab; onSelect: (tab: TaskSheetTab) => void; label: string; count?: number | string; alert?: boolean }) {
  return (
    <button type="button" data-slot="tab" role="tab" aria-selected={current === id} className="aw-sheet-tab" onClick={() => onSelect(id)}>
      {label}
      {count != null ? <span className="aw-sheet-tab-count">{count}</span> : null}
      {alert ? <span className="aw-sheet-tab-alert" aria-label="needs attention" /> : null}
    </button>
  )
}

// ── What the stage calls for ─────────────────────────────────────────────

function primaryAction(task: Task): { action: TaskSheetAction; label: string; glyph: string } | null {
  switch (task.stage) {
    case 'not_started':
      return { action: 'start', label: 'Start work', glyph: 'play_arrow' }
    case 'working':
    case 'sent_back':
      return { action: 'open-conversation', label: `Open ${task.assignee ?? 'the'} conversation`, glyph: 'chat' }
    case 'waiting_for_answer':
      return { action: 'answer', label: 'Answer the question', glyph: 'help_circle' }
    case 'waiting_for_review':
      return { action: 'hand-to-reviewer', label: 'Hand to a reviewer', glyph: 'visibility' }
    case 'under_review':
      return { action: 'approve', label: 'Approve', glyph: 'stamp' }
    case 'did_not_land':
      return { action: 'retry-landing', label: 'Try landing again', glyph: 'refresh' }
    case 'closed':
      return { action: 'reopen', label: 'Reopen', glyph: 'restart_alt' }
    default:
      return null
  }
}

function nothingToDo(task: Task): string {
  switch (task.stage) {
    case 'approved_waiting':
    case 'checking':
    case 'landing':
      return 'Nothing to do: it is on its way to main.'
    case 'landing_held':
      return `Nothing to do: it lands after ${task.stage_waits_on ?? 'the work ahead of it'}.`
    case 'on_main':
      return 'Done: its work is on main.'
    default:
      return ''
  }
}

function attentionOf(task: Task, failedChecks: number): { tone: string; glyph: string; title: string; text?: string | null } | null {
  if (task.stage === 'waiting_for_answer') {
    return { tone: 'needs-you', glyph: 'hand', title: `${task.stage_waits_on ?? 'An agent'} asks you`, text: task.awaiting_answer_reason ?? task.blocked_reason }
  }
  if (task.stage === 'did_not_land') {
    return { tone: 'failed', glyph: 'error', title: 'Its work did not land on main', text: task.stage_detail }
  }
  if (failedChecks > 0 && (task.stage === 'sent_back' || task.stage === 'working' || task.stage === 'waiting_for_review')) {
    return { tone: 'failed', glyph: 'x', title: `${failedChecks} ${failedChecks === 1 ? 'check' : 'checks'} failed on the latest run`, text: 'See which under Work.' }
  }
  return null
}

// ── Work ─────────────────────────────────────────────────────────────────

const REQUIREMENT_STATE: Record<string, { glyph: string; word: string; tone: string }> = {
  verified: { glyph: 'circle_check_big', word: 'Accepted', tone: 'done' },
  evidence_awaiting_review: { glyph: 'hourglass', word: 'Evidence waits for review', tone: 'info' },
  rejected: { glyph: 'error', word: 'Evidence rejected', tone: 'failed' },
}

function requirementState(link: RequirementLink) {
  if (link.has_rejected_evidence && link.state !== 'verified') return REQUIREMENT_STATE.rejected
  return REQUIREMENT_STATE[link.state] ?? { glyph: 'circle_dashed', word: 'No evidence yet', tone: 'idle' }
}

function isFailure(result: TaskCheckResult): boolean {
  return !result.skipped && (result.timed_out || result.exit_code !== 0)
}

function WorkTab({ task, checks, now, onAction }: { task: Task; checks: TaskCheckRun | null; now?: Date; onAction: (action: TaskSheetAction) => void }) {
  const links = task.requirement_links ?? []
  const criteria = task.acceptance_criteria ?? []
  return (
    <div className="aw-sheet-sections">
      <Section title="Requirements" aside={links.length ? `${links.filter((l) => l.state === 'verified').length} of ${links.length} accepted` : undefined}>
        {links.length === 0 ? (
          <p className="aw-sheet-empty">This task serves no requirement.</p>
        ) : (
          <ul className="aw-sheet-list">
            {links.map((link) => {
              const state = requirementState(link)
              return (
                <li key={link.requirement_id} className="aw-sheet-req" data-tone={state.tone}>
                  <Icon name={state.glyph} size={14} />
                  <div>
                    <span className="aw-sheet-req-head">
                      <span className="aw-tcard-id">{link.identifier}</span>
                      <span className="aw-sheet-req-state">{state.word}</span>
                    </span>
                    {link.statement ? <p className="aw-sheet-req-text">{link.statement}</p> : null}
                    {link.has_rejected_evidence && link.latest_rejection_reason ? <p className="aw-sheet-req-why">{link.latest_rejection_reason}</p> : null}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </Section>

      {criteria.length ? (
        <Section title="Acceptance criteria">
          <ul className="aw-sheet-criteria">
            {criteria.map((criterion, index) => (
              <li key={index}>{criterion}</li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section
        title="Checks"
        aside={checks?.ended_at ? formatAgo(checks.ended_at, now) : checks?.state === 'running' ? 'running now' : undefined}
        action={checks && checks.state !== 'running' ? { label: 'Run again', glyph: 'refresh', onClick: () => onAction('rerun-checks') } : undefined}
      >
        {!checks ? (
          <p className="aw-sheet-empty">The project’s checks have not run on this work yet.</p>
        ) : (
          <ul className="aw-sheet-list">
            {checks.results.map((result) => (
              <CheckRow key={result.name} result={result} />
            ))}
          </ul>
        )}
      </Section>

      <Section title="Landing">
        <p className="aw-sheet-landing">
          <Icon name={stageVisual(task.stage).glyph} size={13} />
          <span>{landingSentence(task)}</span>
        </p>
      </Section>
    </div>
  )
}

function CheckRow({ result }: { result: TaskCheckResult }) {
  const [open, setOpen] = React.useState(false)
  const failed = isFailure(result)
  const tone = result.skipped ? 'idle' : failed ? (result.preexisting ? 'needs-you' : 'failed') : 'done'
  const word = result.skipped ? 'skipped' : result.timed_out ? 'timed out' : failed ? (result.preexisting ? 'fails on main too' : 'failed') : 'passed'
  return (
    <li className="aw-sheet-check" data-tone={tone}>
      <button type="button" data-slot="check-row" className="aw-sheet-check-head" aria-expanded={failed ? open : undefined} disabled={!failed} onClick={() => setOpen((o) => !o)}>
        <Icon name={result.skipped ? 'circle_dashed' : failed ? 'x' : 'check'} size={13} />
        <span className="aw-sheet-check-name">{result.name}</span>
        <span className="aw-sheet-check-word">{word}</span>
        <span className="aw-sheet-check-time">{Math.round(result.duration_seconds)}s</span>
        {failed ? <Icon name={open ? 'expand_less' : 'expand_more'} size={12} /> : null}
      </button>
      {open ? <pre className="aw-sheet-output">{result.output_tail}</pre> : null}
    </li>
  )
}

function landingSentence(task: Task): string {
  switch (task.stage) {
    case 'on_main':
      return `On main${task.stage_detail ? ` as ${task.stage_detail}` : ''}.`
    case 'did_not_land':
      return `Did not land: ${task.stage_detail ?? 'see the story'}.`
    case 'landing_held':
      return `Approved; lands after ${task.stage_waits_on ?? 'the work ahead of it'}.`
    case 'checking':
      return 'Approved; the checks are running on it together with main.'
    case 'landing':
      return 'Approved and checked; moving onto main now.'
    case 'approved_waiting':
      return 'Approved; waiting for its turn in the landing queue.'
    case 'closed':
      return 'Closed without landing.'
    default:
      return 'Lands on main once it is approved.'
  }
}

// ── Details ──────────────────────────────────────────────────────────────

function DetailsTab({ task, now, onOpenTask }: { task: Task; now?: Date; onOpenTask?: (taskId: string) => void }) {
  return (
    <div className="aw-sheet-sections">
      <Section title="Description">
        {task.description ? <p className="aw-sheet-prose">{task.description}</p> : <p className="aw-sheet-empty">No description.</p>}
      </Section>
      {task.prerequisites?.length || task.dependents?.length ? (
        <Section title="Linked tasks">
          <div className="aw-sheet-links">
            {task.prerequisites?.length ? <Links label="Waits on" refs={task.prerequisites} onOpenTask={onOpenTask} /> : null}
            {task.dependents?.length ? <Links label="Needed by" refs={task.dependents} onOpenTask={onOpenTask} /> : null}
          </div>
        </Section>
      ) : null}
      {task.notes ? (
        <Section title="Notes">
          <p className="aw-sheet-prose">{task.notes}</p>
        </Section>
      ) : null}
      <Section title="Facts">
        <dl className="aw-sheet-facts">
          <Fact label="Created">{formatDateTime(task.created_at, now)}</Fact>
          <Fact label="Updated">{formatAgo(task.updated, now)}</Fact>
          {task.assigner ? <Fact label="Assigned by">{task.assigner}</Fact> : null}
          <Fact label="Priority">{task.priority}</Fact>
          {task.level ? <Fact label="Build level">{task.level}</Fact> : null}
          <Fact label="If a run ends without moving it">{DIVERGENCE_POLICY_LABELS[task.divergence_policy] ?? task.divergence_policy}</Fact>
          <Fact label="Id">
            <code>{task.id}</code>
          </Fact>
        </dl>
      </Section>
    </div>
  )
}

function Links({ label, refs, onOpenTask }: { label: string; refs: TaskDependencyRef[]; onOpenTask?: (taskId: string) => void }) {
  return (
    <div className="aw-sheet-links-group">
      <span className="aw-sheet-links-label">{label}</span>
      {refs.map((ref) => (
        <button key={ref.id} type="button" data-slot="task-link" className="aw-sheet-link" onClick={() => onOpenTask?.(ref.id)}>
          <Icon name={ref.status === 'approved' ? 'circle_check_big' : 'circle_dashed'} size={12} />
          {ref.readable_id ? <span className="aw-tcard-id">{ref.readable_id}</span> : null}
          <span className="aw-sheet-link-title">{ref.title}</span>
        </button>
      ))}
    </div>
  )
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function Section({ title, aside, action, children }: { title: string; aside?: string; action?: { label: string; glyph: string; onClick: () => void }; children: React.ReactNode }) {
  return (
    <section className="aw-sheet-section">
      <header>
        <h3>{title}</h3>
        {aside ? <span className="aw-sheet-aside">{aside}</span> : null}
        {action ? (
          <button type="button" data-slot="mini-action" className="aw-sheet-mini" onClick={action.onClick}>
            <Icon name={action.glyph} size={12} />
            {action.label}
          </button>
        ) : null}
      </header>
      {children}
    </section>
  )
}
