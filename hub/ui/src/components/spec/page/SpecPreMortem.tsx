import * as React from 'react'
import { isNoManager, useManagerJobs, usePreMortems, useRunPreMortem, type PreMortem, type PreMortemFinding } from '@/api/manager'
import { readableApiError } from '@/api/client'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { formatDateTime, formatUsage } from '@/lib/format'
import { environmentDestination, goTo } from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'
import { Section } from './SpecDocumentBody'
import '@/styles/spec-page.css'

const TRIGGER_LABEL: Record<string, string> = {
  requested: 'Asked for with Run a pre-mortem',
  criteria_written: 'The acceptance criteria were written',
}

const OUTCOME_LABEL: Record<string, string> = {
  written: 'Written',
  failed: 'Failed',
  empty: 'Found nothing',
}

function cost(micros: number | null | undefined): string {
  return micros == null ? 'not reported' : formatUsage({ cost_usd_micros: micros })
}

/** The Pre-mortem section of a change document's page, fed from the Hub: its firings (polled, since a
 *  firing is recorded when it ends and nothing broadcasts it) and whether the job is on. */
export function SpecPreMortem({ path, now, flash, onCopyLink }: { path: string; now: Date; flash: string | null; onCopyLink: (anchor: string) => void }) {
  const { data, error } = usePreMortems(path)
  const { data: jobList, error: jobsError } = useManagerJobs()
  const run = useRunPreMortem(path)
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const rows = data ?? []
  const newest = rows[0]?.id ?? null
  // The newest firing when a press was accepted: until the list moves on from it, one is running.
  const [askedOver, setAskedOver] = React.useState<string | null | undefined>(undefined)
  const { reset } = run
  React.useEffect(() => {
    setAskedOver((asked) => (asked === undefined || asked === newest ? asked : undefined))
    reset()
  }, [newest, reset])
  const job = jobList?.find((item) => item.key === 'pre-mortem')
  // A Hub that predates the job: a committed bundle reaches the operator's app before its restart.
  if (isNoManager(error) || isNoManager(jobsError) || (jobList && !job)) return null
  const unreadable = error ?? jobsError
  return (
    <SpecPreMortemSection
      preMortems={rows}
      jobOff={job ? !job.enabled : false}
      running={askedOver !== undefined && askedOver === newest}
      refusal={run.isError ? readableApiError(run.error, 'The Hub did not answer.') : unreadable ? readableApiError(unreadable, 'The Hub did not answer.') : null}
      pending={run.isPending}
      now={now}
      flash={flash}
      onCopyLink={onCopyLink}
      onRun={() => run.mutate(undefined, { onSuccess: () => setAskedOver(newest) })}
      onOpenManager={() => {
        if (projectId) goTo(environmentDestination(projectId, 'manager'))
      }}
    />
  )
}

/** The document's pre-mortems and the action that asks for one
 *  (`the-spec-journey-spends-the-operator-s-attention-only-on-their-decisions`, FR-11). Laid out as
 *  the Retrospective section is, so the two manager jobs on a spec page read alike. */
export function SpecPreMortemSection({
  preMortems,
  jobOff,
  running,
  refusal,
  pending,
  now,
  flash,
  onCopyLink,
  onRun,
  onOpenManager,
}: {
  /** Newest first, as the route answers. */
  preMortems: PreMortem[]
  /** The Pre-mortem job is switched off in this project: the button is withheld and the section
   *  says where to switch it on, rather than offering a press the Hub refuses. */
  jobOff: boolean
  running: boolean
  /** What the Hub said when it refused the press: one is in progress, or the job has no runner. */
  refusal: string | null
  pending: boolean
  now: Date
  flash: string | null
  onCopyLink: (anchor: string) => void
  onRun: () => void
  onOpenManager: () => void
}) {
  const latest = preMortems[0]
  const unwritten = latest && latest.outcome !== 'written' ? latest : null
  const written = preMortems.find((p) => p.outcome === 'written') ?? null
  const earlier = preMortems.filter((p) => p !== unwritten && p !== written)
  // A Hub that records answers sends `answer` on every finding, null while unanswered (spec
  // the-spec-process-uses-what-the-hub-already-knows, FR-4); an older one sends none.
  const answers = written ? answerCount(written.findings) : null
  return (
    <Section
      id="pre-mortem"
      title="Pre-mortem"
      count={written ? (answers ? `${answers.answered} of ${answers.total} answered` : String(written.findings.length)) : undefined}
      findings={[]}
      flash={flash}
      onCopyLink={onCopyLink}
      actions={
        jobOff ? null : (
          <Button variant="outline" size="xs" disabled={pending || running} onClick={onRun}>
            <Icon name="play_arrow" size={13} />
            Run a pre-mortem
          </Button>
        )
      }
    >
      <p className="aw-sp-muted aw-sp-premortem-lede">
        {answers
          ? 'A fresh reader assumes this change shipped and failed, and writes down how. The author answers each finding with a note of what it did; until every one is answered, the check lists the pre-mortem as a gap. It runs on its own once; after that, only Run a pre-mortem runs it again.'
          : 'A fresh reader assumes this change shipped and failed, and writes down how. The author reads it in its next turn here, fixes what it can and asks you about the rest.'}
      </p>
      {jobOff ? (
        <p className="aw-sp-retro-note" data-testid="premortem-off">
          <Icon name="info" size={14} />
          The Pre-mortem job is off in this project.
          <Button variant="ghost" size="xs" onClick={onOpenManager}>
            Switch it on in Manager
          </Button>
        </p>
      ) : null}
      {running ? (
        <p className="aw-sp-retro-note" role="status" data-testid="premortem-running">
          <span className="aw-sp-live" aria-hidden="true" />A pre-mortem is running. It appears here when it ends.
        </p>
      ) : null}
      {refusal ? (
        <p className="aw-sp-retro-note" role="alert" data-testid="premortem-refusal">
          <Icon name="info" size={14} />
          {refusal}
        </p>
      ) : null}
      {unwritten ? (
        <div className="aw-sp-retro-failed" data-testid="premortem-failed" data-outcome={unwritten.outcome}>
          <div className="aw-sp-retro-failed-text">
            <strong>{unwritten.outcome === 'failed' ? 'The last pre-mortem failed' : 'The last pre-mortem found no way it fails'}</strong>
            <span className="aw-sp-muted"> · {formatDateTime(unwritten.at, now)}</span>
            <p>{unwritten.detail ?? 'The Hub recorded no reason.'}</p>
          </div>
          {jobOff ? null : (
            <Button variant="outline" size="xs" disabled={pending} onClick={onRun}>
              <Icon name="refresh" size={13} />
              Run it again
            </Button>
          )}
        </div>
      ) : null}
      {written ? (
        <article data-testid="premortem-newest">
          <dl className="aw-sp-retro-facts">
            <Fact term="Made" value={formatDateTime(written.at, now)} />
            <Fact term="Trigger" value={TRIGGER_LABEL[written.trigger] ?? written.trigger} />
            <Fact term="Model" value={written.model ?? "The runner's own model"} />
            <Fact term="Cost" value={cost(written.cost_usd_micros)} />
          </dl>
          <Findings rows={written.findings} now={now} answered={Boolean(answers)} />
        </article>
      ) : !unwritten && !jobOff ? (
        <div className="aw-sp-empty">
          <Icon name="history" size={18} />
          <span>No pre-mortem yet.</span>
        </div>
      ) : null}
      {earlier.length ? <Earlier preMortems={earlier} now={now} /> : null}
    </Section>
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

/** How many of a written firing's findings are answered; null when the Hub records no answers. */
function answerCount(findings: PreMortemFinding[]): { answered: number; total: number } | null {
  if (!findings.length || findings.every((f) => f.answer === undefined)) return null
  return { answered: findings.filter((f) => f.answer).length, total: findings.length }
}

function Findings({ rows, now, answered = false }: { rows: PreMortemFinding[]; now?: Date; answered?: boolean }) {
  if (!rows.length) return null
  return (
    <div className="aw-sp-retro-report">
      <h3 className="aw-sp-retro-title">How it failed</h3>
      <ul className="aw-sp-retro-list">
        {rows.map((f, i) => (
          <li key={i} data-testid="premortem-finding" data-answered={answered ? (f.answer ? 'true' : 'false') : undefined}>
            <div className="aw-sp-premortem-finding-head">
              <span className="aw-sp-premortem-number">{i + 1}</span>
              {f.requirement ? <span className="aw-sp-retro-tag">{f.requirement}</span> : null}
              {answered && !f.answer ? (
                <span className="aw-sp-premortem-open" data-testid="premortem-unanswered">
                  Unanswered
                </span>
              ) : null}
            </div>
            <p>{f.story}</p>
            {f.cites.length ? <p className="aw-sp-retro-cites">{f.cites.join(' · ')}</p> : null}
            {answered && f.answer ? (
              <div className="aw-sp-premortem-answer" data-testid="premortem-answer">
                <Icon name="check_circle" size={14} />
                <div>
                  <p>{f.answer.note}</p>
                  <p className="aw-sp-muted">
                    Answered by {f.answer.by} · {now ? formatDateTime(f.answer.at, now) : f.answer.at}
                  </p>
                </div>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Earlier({ preMortems, now }: { preMortems: PreMortem[]; now: Date }) {
  const [open, setOpen] = React.useState<string | null>(null)
  return (
    <div className="aw-sp-retro-earlier" data-testid="premortem-earlier">
      <h3 className="aw-sp-retro-title">Earlier</h3>
      <ul>
        {preMortems.map((p) => (
          <li key={p.id}>
            <button data-slot="disclosure" type="button" className="aw-sp-disclosure" aria-expanded={open === p.id} onClick={() => setOpen((o) => (o === p.id ? null : p.id))}>
              <Icon name="chevron_right" size={13} className="aw-sp-disclosure-chevron" />
              {formatDateTime(p.at, now)} · {OUTCOME_LABEL[p.outcome] ?? p.outcome}
            </button>
            {open === p.id ? (
              <div className="aw-sp-retro-earlier-body">
                {p.findings.length ? <Findings rows={p.findings} /> : <p className="aw-sp-prose">{p.detail ?? 'The Hub recorded no reason.'}</p>}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}
