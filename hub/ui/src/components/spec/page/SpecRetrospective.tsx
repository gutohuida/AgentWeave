import * as React from 'react'
import { isNoManager, useBuildRetrospectives, useReviewThisBuild, type BuildRetrospective, type RetrospectiveFinding, type RetrospectiveReport } from '@/api/manager'
import { readableApiError } from '@/api/client'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { formatDateTime, formatDuration, formatUsage } from '@/lib/format'
import { Section } from './SpecDocumentBody'
import '@/styles/spec-page.css'

const TRIGGER_LABEL: Record<string, string> = {
  requested: 'Asked for with Review this build',
  last_task_approved: 'The last task was approved',
}

const CAUSE_LABEL: Record<string, string> = {
  defect: 'Defect in the work',
  process: 'Tooling or process',
  spec: 'The spec was wrong',
}

const IMPROVEMENT_LABEL: Record<string, string> = {
  code_and_checks: "The project's code and checks",
  specs: 'How its specs are written',
  staffing_and_running: 'How its builds are staffed and run',
  tooling: 'The tooling itself',
}

const OUTCOME_LABEL: Record<string, string> = {
  written: 'Written',
  failed: 'Failed',
  empty: 'Nothing grounded',
}

function cost(micros: number | null | undefined): string {
  return micros == null ? 'not reported' : formatUsage({ cost_usd_micros: micros })
}

/** The document's retrospectives and the action that asks for one (FR-3, FR-9). Polled, because a
 *  firing is recorded as an event when it ends and nothing broadcasts it. */
export function SpecRetrospective({ path, now, flash, onCopyLink }: { path: string; now: Date; flash: string | null; onCopyLink: (anchor: string) => void }) {
  const { data, error } = useBuildRetrospectives(path)
  const review = useReviewThisBuild(path)
  const rows = data ?? []
  const newest = rows[0]?.id ?? null
  // The newest firing when a press was accepted: until the list moves on from it, one is running.
  const [askedOver, setAskedOver] = React.useState<string | null | undefined>(undefined)
  const { reset } = review
  React.useEffect(() => {
    setAskedOver((asked) => (asked === undefined || asked === newest ? asked : undefined))
    reset()
  }, [newest, reset])
  // A Hub that predates the job: a committed bundle reaches the operator's app before its restart.
  if (isNoManager(error)) return null
  return (
    <SpecRetrospectiveSection
      retrospectives={rows}
      unreadable={error ? readableApiError(error, 'The Hub did not answer.') : null}
      running={askedOver !== undefined && askedOver === newest}
      refusal={review.isError ? readableApiError(review.error, 'The Hub did not answer.') : null}
      pending={review.isPending}
      now={now}
      flash={flash}
      onCopyLink={onCopyLink}
      onReview={() => review.mutate(undefined, { onSuccess: () => setAskedOver(newest) })}
    />
  )
}

export function SpecRetrospectiveSection({
  retrospectives,
  unreadable,
  running,
  refusal,
  pending,
  now,
  flash,
  onCopyLink,
  onReview,
}: {
  /** Newest first, as the route answers. */
  retrospectives: BuildRetrospective[]
  unreadable: string | null
  running: boolean
  /** What the Hub said when it refused the press: one is in progress, or the job has no runner. */
  refusal: string | null
  pending: boolean
  now: Date
  flash: string | null
  onCopyLink: (anchor: string) => void
  onReview: () => void
}) {
  const latest = retrospectives[0]
  const unwritten = latest && latest.outcome !== 'written' ? latest : null
  const written = retrospectives.find((r) => r.outcome === 'written') ?? null
  const earlier = retrospectives.filter((r) => r !== unwritten && r !== written)
  return (
    <Section
      id="retrospective"
      title="Retrospective"
      count={retrospectives.length ? String(retrospectives.length) : undefined}
      findings={[]}
      flash={flash}
      onCopyLink={onCopyLink}
      actions={
        <Button variant="outline" size="xs" disabled={pending} onClick={onReview}>
          <Icon name="play_arrow" size={13} />
          Review this build
        </Button>
      }
    >
      {running ? (
        <p className="aw-sp-retro-note" role="status" data-testid="retro-running">
          <span className="aw-sp-live" aria-hidden="true" />A retrospective is running. It appears here when it ends.
        </p>
      ) : null}
      {refusal ? (
        <p className="aw-sp-retro-note" role="alert" data-testid="retro-refusal">
          <Icon name="info" size={14} />
          {refusal}
        </p>
      ) : null}
      {unreadable ? (
        <p className="aw-sp-retro-note" role="alert">
          <Icon name="warning" size={14} />
          The retrospectives could not be read: {unreadable}
        </p>
      ) : null}
      {unwritten ? (
        <div className="aw-sp-retro-failed" data-testid="retro-failed" data-outcome={unwritten.outcome}>
          <div className="aw-sp-retro-failed-text">
            <strong>{unwritten.outcome === 'failed' ? 'The last retrospective failed' : 'The last retrospective wrote nothing'}</strong>
            <span className="aw-sp-muted"> · {formatDateTime(unwritten.at, now)}</span>
            <p>{unwritten.detail ?? 'The Hub recorded no reason.'}</p>
          </div>
          <Button variant="outline" size="xs" disabled={pending} onClick={onReview}>
            <Icon name="refresh" size={13} />
            Run it again
          </Button>
        </div>
      ) : null}
      {written ? (
        <article data-testid="retro-newest">
          <Facts retrospective={written} now={now} />
          {written.report ? <Report report={written.report} /> : null}
        </article>
      ) : !unwritten ? (
        <div className="aw-sp-empty">
          <Icon name="history" size={18} />
          <span>No retrospective yet.</span>
        </div>
      ) : null}
      {earlier.length ? <Earlier retrospectives={earlier} now={now} /> : null}
    </Section>
  )
}

function Facts({ retrospective: r, now }: { retrospective: BuildRetrospective; now: Date }) {
  const dropped = r.report?.dropped ?? 0
  return (
    <dl className="aw-sp-retro-facts" data-testid="retro-facts">
      <Fact term="Made" value={formatDateTime(r.at, now)} />
      <Fact term="Trigger" value={TRIGGER_LABEL[r.trigger] ?? r.trigger} />
      <Fact term="Model" value={r.model ?? "The runner's own model"} />
      <Fact term="Parts" value={String(r.parts)} />
      <Fact term="Cost" value={cost(r.cost_usd_micros)} />
      {r.report ? <Fact term="Claims dropped" value={String(dropped)} /> : null}
    </dl>
  )
}

function Fact({ term, value }: { term: string; value: string }) {
  return (
    <div>
      <dt>{term}</dt>
      <dd>{value}</dd>
    </div>
  )
}

/** Every firing that is neither the written one above nor the failure above, each opened in place. */
function Earlier({ retrospectives, now }: { retrospectives: BuildRetrospective[]; now: Date }) {
  const [open, setOpen] = React.useState<string | null>(null)
  return (
    <div className="aw-sp-retro-earlier" data-testid="retro-earlier">
      <h3 className="aw-sp-retro-title">Earlier</h3>
      <ul>
        {retrospectives.map((r) => (
          <li key={r.id}>
            <button data-slot="disclosure" type="button" className="aw-sp-disclosure" aria-expanded={open === r.id} onClick={() => setOpen((o) => (o === r.id ? null : r.id))}>
              <Icon name="chevron_right" size={13} className="aw-sp-disclosure-chevron" />
              {formatDateTime(r.at, now)} · {OUTCOME_LABEL[r.outcome] ?? r.outcome}
            </button>
            {open === r.id ? (
              <div className="aw-sp-retro-earlier-body">
                <Facts retrospective={r} now={now} />
                {r.report ? <Report report={r.report} /> : <p className="aw-sp-prose">{r.detail ?? 'The Hub recorded no reason.'}</p>}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Each section the report has, in FR-7's order. An empty one says what the Hub says it had. */
function Report({ report }: { report: RetrospectiveReport }) {
  const name = (taskId: string | null | undefined) => {
    const row = report.where_time_went.per_task.find((t) => t.task_id === taskId)
    return row?.readable_id ?? taskId ?? 'no task'
  }
  const part = (key: keyof RetrospectiveReport['nothing'], title: string, children: React.ReactNode) => (
    <div className="aw-sp-retro-section" data-section={key}>
      <h3 className="aw-sp-retro-title">{title}</h3>
      {report.nothing[key] ? <p className="aw-sp-muted">{report.nothing[key]}</p> : children}
    </div>
  )
  const { where_time_went: time, spec_missed: missed, staffing, cost: spent, friction } = report
  return (
    <div className="aw-sp-retro-report">
      {part(
        'where_time_went',
        'Where the time went',
        <>
          <Findings rows={time.findings} />
          <Rows
            title="By task"
            rows={time.per_task.map((t) => ({
              key: t.task_id,
              text: `${t.readable_id ?? t.task_id} ${t.title} (${t.status}): building ${formatDuration(t.building_seconds)}, waiting for review ${formatDuration(t.waiting_for_review_seconds)}, in the check gate ${formatDuration(t.in_check_gate_seconds)}, waiting to start ${formatDuration(t.waiting_to_start_seconds)}`,
            }))}
          />
        </>,
      )}
      {part(
        'send_backs',
        'Send-backs',
        <ul className="aw-sp-retro-list">
          {report.send_backs.map((s) => (
            <li key={s.transition_id} data-testid="retro-send-back">
              <span className="aw-sp-retro-tag" data-cause={s.cause}>
                {CAUSE_LABEL[s.cause] ?? s.cause}
              </span>
              <strong>{s.readable_id ?? s.task_id}</strong>
              <span className="aw-sp-muted">
                {' '}
                sent back by {s.by}
                {s.reason_class ? ` as ${s.reason_class}` : ''}
              </span>
              <p>{s.explanation}</p>
              <Cites ids={s.cites} />
            </li>
          ))}
        </ul>,
      )}
      {part(
        'spec_missed',
        'What the spec missed',
        <>
          <Findings rows={missed.findings} />
          <Rows title="Amended or added criteria" rows={missed.amendments.map((a) => ({ key: a.id, text: amendmentText(a.detail, a.kind) }))} />
          <Rows title="Tasks added mid-build" rows={missed.tasks_added_mid_build.map((t) => ({ key: t.task_id, text: `${t.readable_id ?? t.task_id} ${t.title}` }))} />
          <Rows title="Criteria reported as unsatisfiable" rows={missed.unsatisfiable_criteria.map((a) => ({ key: a.id, text: amendmentText(a.detail, a.kind) }))} />
          <Rows title="Requirements without accepted evidence" rows={missed.requirements_without_accepted_evidence.map((id) => ({ key: id, text: id }))} />
          <Rows title="Reconcile gaps" rows={missed.reconcile_gaps.map((g, i) => ({ key: String(i), text: [g.class, g.requirement, g.where, g.summary].filter(Boolean).join(' · ') }))} />
        </>,
      )}
      {part(
        'staffing',
        'Staffing',
        <>
          <Findings rows={staffing.findings} />
          <Rows title="Builds" rows={staffing.builds.map((b) => ({ key: b.id, text: `${b.id}: ${b.driver}, ${b.level}` }))} />
          <Rows title="By agent" rows={staffing.per_agent.map((a) => ({ key: a.agent, text: `${a.agent}: ${a.runs} ${a.runs === 1 ? 'run' : 'runs'}` }))} />
        </>,
      )}
      {part(
        'cost',
        'Cost',
        <>
          <Findings rows={spent.findings} />
          <p>Total {cost(spent.totals.cost_usd_micros)} over {spent.totals.runs} {spent.totals.runs === 1 ? 'run' : 'runs'}</p>
          <Rows title="By agent" rows={spent.per_agent.map((a) => ({ key: a.agent, text: `${a.agent}: ${cost(a.cost_usd_micros)}` }))} />
          <Rows title="By task" rows={spent.per_task.map((t) => ({ key: t.task_id, text: `${name(t.task_id)}: ${cost(t.cost_usd_micros)}` }))} />
        </>,
      )}
      {part(
        'friction',
        'Friction',
        <>
          <Findings rows={friction.findings} />
          <Rows title="Stalls" rows={friction.stalls.map((s) => ({ key: s.id, text: [s.cause, s.reason, s.outcome].filter(Boolean).join(' · ') }))} />
          <Rows title="Flaky gate tests" rows={friction.flaky_send_backs.map((s) => ({ key: s.transition_id, text: `${s.readable_id ?? s.task_id}: ${s.reason ?? ''}` }))} />
          <Rows title="Operator waits" rows={friction.operator_waits.map((q) => ({ key: q.question_id, text: `${q.task_id ? `${name(q.task_id)}: ` : ''}${formatDuration(q.waited_seconds)}` }))} />
        </>,
      )}
      {part('what_worked', 'What worked', <Findings rows={report.what_worked} />)}
      {part(
        'improvements',
        'What to improve',
        <ul className="aw-sp-retro-list">
          {report.improvements.map((item, i) => (
            <li key={i} data-testid="retro-improvement">
              <span className="aw-sp-retro-tag" data-label={item.label}>
                {IMPROVEMENT_LABEL[item.label] ?? item.label}
              </span>
              <p>{item.text}</p>
              <Cites ids={item.cites} />
            </li>
          ))}
        </ul>,
      )}
      {part('lessons', 'Lessons', <Findings rows={report.lessons} />)}
      {part(
        'transcripts_read',
        'Transcripts read',
        <Rows rows={report.transcripts_read.map((r) => ({ key: r.run_id, text: `${r.run_id} · ${r.agent}${r.task_id ? ` · ${name(r.task_id)}` : ''} · ${r.flags.join(', ')}` }))} />,
      )}
    </div>
  )
}

function amendmentText(detail: Record<string, unknown> | null, kind: string): string {
  const said = ['op', 'target', 'criterion', 'reason'].map((key) => detail?.[key]).filter((v) => typeof v === 'string' && v)
  return said.length ? said.join(' · ') : kind
}

function Findings({ rows }: { rows: RetrospectiveFinding[] }) {
  if (!rows.length) return null
  return (
    <ul className="aw-sp-retro-list">
      {rows.map((f, i) => (
        <li key={i}>
          <p>{f.text}</p>
          <Cites ids={f.cites} />
        </li>
      ))}
    </ul>
  )
}

function Rows({ title, rows }: { title?: string; rows: Array<{ key: string; text: string }> }) {
  if (!rows.length) return null
  return (
    <div className="aw-sp-retro-rows">
      {title ? <div className="aw-sp-meter-title">{title}</div> : null}
      <ul>
        {rows.map((r) => (
          <li key={r.key}>{r.text}</li>
        ))}
      </ul>
    </div>
  )
}

function Cites({ ids }: { ids: string[] }) {
  return ids.length ? <p className="aw-sp-retro-cites">{ids.join(' · ')}</p> : null
}
