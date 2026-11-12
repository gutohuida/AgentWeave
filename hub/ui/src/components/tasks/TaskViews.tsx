import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { DIVERGENCE_POLICY_LABELS, type RequirementLink, type Task, type TaskCheckResult, type TaskCheckRun, type TaskDependencyRef } from '@/api/tasks'
import { formatAgo, formatDateTime } from '@/lib/format'
import { stageVisual } from '@/lib/taskStageVisual'
import '@/styles/task-redesign.css'
import '@/styles/task-views.css'

/** The opened task's Work and Details views (`task-card-and-story-redesign`): today's dialog and its
 *  Story view stay as they are; these replace the single Details view, splitting what the task is
 *  checked against (Work) from what it is (Details). Presentational: the drawer passes the task and
 *  its latest check run. */

// ── Work ─────────────────────────────────────────────────────────────────

const REQUIREMENT_STATE: Record<string, { glyph: string; word: string; tone: string }> = {
  verified: { glyph: 'circle_check_big', word: 'Accepted', tone: 'done' },
  evidence_awaiting_review: { glyph: 'hourglass', word: 'Evidence waits for review', tone: 'info' },
  rejected: { glyph: 'error', word: 'Evidence rejected', tone: 'failed' },
}

/** How a requirement's evidence stands. `coverage` is the requirement's state in its document's
 *  coverage (the same read the card's tally makes); `link.state` is the requirement's own lifecycle
 *  (active or retired), never its evidence. */
function requirementState(link: RequirementLink, coverage: string | undefined) {
  if (link.has_rejected_evidence && coverage !== 'verified') return REQUIREMENT_STATE.rejected
  return (coverage ? REQUIREMENT_STATE[coverage] : undefined) ?? { glyph: 'circle_dashed', word: 'No evidence yet', tone: 'idle' }
}

function isFailure(result: TaskCheckResult): boolean {
  return !result.skipped && (result.timed_out || result.exit_code !== 0)
}

/** What the task is checked against and how that stands: each requirement with its evidence, the
 *  acceptance criteria, the latest run of the project's checks (a failure opens to its output) and
 *  a sentence on its landing. */
export function TaskWorkView({
  task,
  checks,
  checksError,
  now,
  onRerunChecks,
  coverage,
  onOpenRequirement,
  canOpenRequirement,
}: {
  task: Task
  checks: TaskCheckRun | null
  /** Why the checks could not be read; shown instead of claiming they have not run. */
  checksError?: string | null
  now?: Date
  onRerunChecks?: () => void
  /** Each requirement's state in its document's coverage, by requirement id. */
  coverage?: ReadonlyMap<string, string>
  /** Opens the requirement in its document; absent, the identifier is plain text. */
  onOpenRequirement?: (link: RequirementLink) => void
  /** Whether a requirement resolves to a document it can open in; one that does not is disabled. */
  canOpenRequirement?: (link: RequirementLink) => boolean
}) {
  const links = task.requirement_links ?? []
  const criteria = task.acceptance_criteria ?? []
  return (
    <div className="aw-tview-sections">
      <Section testId={`task-serves-${task.id}`} title="Requirements" aside={links.length ? `${links.filter((l) => coverage?.get(l.requirement_id) === 'verified').length} of ${links.length} accepted` : undefined}>
        {links.length === 0 ? (
          <p className="aw-tview-empty">This task serves no requirement.</p>
        ) : (
          <ul className="aw-tview-list">
            {links.map((link) => {
              const state = requirementState(link, coverage?.get(link.requirement_id))
              return (
                <li key={link.requirement_id} className="aw-tview-req" data-tone={state.tone}>
                  <Icon name={state.glyph} size={14} />
                  <div>
                    <span className="aw-tview-req-head">
                      {onOpenRequirement ? (
                        <button
                          type="button"
                          data-slot="requirement-link"
                          className="aw-tcard-id aw-tview-req-link"
                          disabled={canOpenRequirement ? !canOpenRequirement(link) : false}
                          onClick={() => onOpenRequirement(link)}
                          title="Open it in its document"
                        >
                          {link.identifier}
                        </button>
                      ) : (
                        <span className="aw-tcard-id">{link.identifier}</span>
                      )}
                      <span className="aw-tview-req-state">{state.word}</span>
                      {link.state !== 'active' ? <span className="aw-tview-req-life">({link.state})</span> : null}
                    </span>
                    {link.statement ? <p className="aw-tview-req-text">{link.statement}</p> : null}
                    {link.has_rejected_evidence && link.latest_rejection_reason ? <p className="aw-tview-req-why">{link.latest_rejection_reason}</p> : null}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </Section>

      {criteria.length ? (
        <Section title="Acceptance criteria">
          <ul className="aw-tview-criteria">
            {criteria.map((criterion, index) => (
              <li key={index}>{criterion}</li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section
        title="Checks"
        aside={checks?.ended_at ? formatAgo(checks.ended_at, now) : checks?.state === 'running' ? 'running now' : undefined}
        action={checks && checks.state !== 'running' && onRerunChecks ? { label: 'Run again', glyph: 'refresh', onClick: onRerunChecks } : undefined}
      >
        {!checks && checksError ? (
          <p className="aw-tview-empty" role="alert">The checks could not be read: {checksError}</p>
        ) : !checks ? (
          <p className="aw-tview-empty">The project’s checks have not run on this work yet.</p>
        ) : (
          <ul className="aw-tview-list">
            {checks.results.map((result) => (
              <CheckRow key={result.name} result={result} />
            ))}
          </ul>
        )}
      </Section>

      <Section title="Landing">
        <p className="aw-tview-landing">
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
    <li className="aw-tview-check" data-tone={tone}>
      <button type="button" data-slot="check-row" className="aw-tview-check-head" aria-expanded={failed ? open : undefined} disabled={!failed} onClick={() => setOpen((o) => !o)}>
        <Icon name={result.skipped ? 'circle_dashed' : failed ? 'x' : 'check'} size={13} />
        <span className="aw-tview-check-name">{result.name}</span>
        <span className="aw-tview-check-word">{word}</span>
        <span className="aw-tview-check-time">{Math.round(result.duration_seconds)}s</span>
        {failed ? <Icon name={open ? 'expand_less' : 'expand_more'} size={12} /> : null}
      </button>
      {open ? <pre className="aw-tview-output">{result.output_tail}</pre> : null}
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

/** The rest of the task: its description, what it waits on and what waits on it, notes, and the
 *  facts. The drawer keeps today's controls beside them (status, prerequisites, escalation). */
export function TaskDetailsView({ task, now, onOpenTask }: { task: Task; now?: Date; onOpenTask?: (taskId: string) => void }) {
  return (
    <div className="aw-tview-sections">
      <Section title="Description">
        {task.description ? <p className="aw-tview-prose">{task.description}</p> : <p className="aw-tview-empty">No description.</p>}
      </Section>
      {task.prerequisites?.length || task.dependents?.length ? (
        <Section title="Linked tasks">
          <div className="aw-tview-links">
            {task.prerequisites?.length ? <Links label="Waits on" refs={task.prerequisites} onOpenTask={onOpenTask} /> : null}
            {task.dependents?.length ? <Links label="Needed by" refs={task.dependents} onOpenTask={onOpenTask} /> : null}
          </div>
        </Section>
      ) : null}
      {task.notes ? (
        <Section title="Notes">
          <p className="aw-tview-prose">{task.notes}</p>
        </Section>
      ) : null}
      <Section title="Facts">
        <dl className="aw-tview-facts">
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
    <div className="aw-tview-links-group">
      <span className="aw-tview-links-label">{label}</span>
      {refs.map((ref) => (
        <button key={ref.id} type="button" data-slot="task-link" className="aw-tview-link" onClick={() => onOpenTask?.(ref.id)}>
          <Icon name={ref.status === 'approved' ? 'circle_check_big' : 'circle_dashed'} size={12} />
          {ref.readable_id ? <span className="aw-tcard-id">{ref.readable_id}</span> : null}
          <span className="aw-tview-link-title">{ref.title}</span>
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

function Section({ title, aside, action, testId, children }: { title: string; testId?: string; aside?: string; action?: { label: string; glyph: string; onClick: () => void }; children: React.ReactNode }) {
  return (
    <section className="aw-tview-section" data-testid={testId}>
      <header>
        <h3>{title}</h3>
        {aside ? <span className="aw-tview-aside">{aside}</span> : null}
        {action ? (
          <button type="button" data-slot="mini-action" className="aw-tview-mini" onClick={action.onClick}>
            <Icon name={action.glyph} size={12} />
            {action.label}
          </button>
        ) : null}
      </header>
      {children}
    </section>
  )
}
