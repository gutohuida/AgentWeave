import * as React from 'react'
import type { PreMortem, PreMortemFinding } from '@/api/manager'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { formatDateTime, formatUsage } from '@/lib/format'
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
  return (
    <Section
      id="pre-mortem"
      title="Pre-mortem"
      count={written ? String(written.findings.length) : undefined}
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
        A fresh reader assumes this change shipped and failed, and writes down how. The author reads it in its next turn here, fixes what it can and asks you about the rest.
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
          <Findings rows={written.findings} />
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

function Findings({ rows }: { rows: PreMortemFinding[] }) {
  if (!rows.length) return null
  return (
    <div className="aw-sp-retro-report">
      <h3 className="aw-sp-retro-title">How it failed</h3>
      <ul className="aw-sp-retro-list">
        {rows.map((f, i) => (
          <li key={i} data-testid="premortem-finding">
            {f.requirement ? <span className="aw-sp-retro-tag">{f.requirement}</span> : null}
            <p>{f.story}</p>
            {f.cites.length ? <p className="aw-sp-retro-cites">{f.cites.join(' · ')}</p> : null}
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
