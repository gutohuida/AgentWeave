import * as React from 'react'
import type { VaultContradiction, VaultReport } from '@/api/vault'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field } from '@/components/ui/settings'
import { formatDay } from '@/lib/format'
import '@/styles/vault.css'

/** What the operator decides about the vault: facts that disagree, and entries an agent reported
 *  wrong. The same cards appear in the library's review views and, for one source's facts, in the
 *  reader. A form's refusal is shown on the form, where the input still is. */

/** An action the container runs; it answers `{ error }` with the Hub's reason when refused. */
export type VaultActionResult = Promise<{ error: string } | void>

export function ContradictionCard({
  contradiction,
  onResolve,
  now,
}: {
  contradiction: VaultContradiction
  /** `stands` null: neither fact holds. `note` is required by the Hub. */
  onResolve: (contradictionId: string, stands: string | null, note: string) => VaultActionResult
  now?: Date
}) {
  const { id, sides, status } = contradiction
  const open = status === 'open'
  // The presumed side is the default, as agents are told until the operator decides.
  const [stands, setStands] = React.useState<string | null>(contradiction.presumed ?? sides[0]?.id ?? null)
  const [note, setNote] = React.useState('')
  const [pending, setPending] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  return (
    <section
      className="vault-contradiction"
      data-testid={`vault-contradiction-${id}`}
      data-status={status ?? 'elsewhere'}
      aria-label="Two facts disagree"
    >
      <header className="vault-contradiction-head" data-tone={status === 'resolved' ? 'settled' : undefined}>
        <Icon name={status === 'resolved' ? 'check_circle' : 'alert_triangle'} size={14} />
        <span>{status === 'resolved' ? 'Settled' : 'Two facts disagree'}</span>
      </header>
      {contradiction.explanation ? <p className="vault-contradiction-why">{contradiction.explanation}</p> : null}
      <div className="vault-contradiction-sides" role={open ? 'radiogroup' : undefined} aria-label={open ? 'What holds' : undefined}>
        {sides.map((side) => (
          <div
            key={side.id}
            className="vault-contradiction-side"
            data-testid={`vault-contradiction-side-${side.id}`}
            data-presumed={side.presumed ? 'true' : 'false'}
            data-chosen={open && stands === side.id ? 'true' : 'false'}
          >
            <p className="vault-contradiction-claim">
              {side.claim ??
                (side.missing
                  ? 'A fact no longer in the vault (it was deleted, or replaced when its source was read again)'
                  : `A private fact, held on ${contradiction.holder ?? 'another machine'}`)}
            </p>
            <p className="vault-contradiction-source">
              {side.source}
              {side.date ? `${side.source ? ' · ' : ''}${formatDay(side.date, now)}` : ''}
              {side.presumed ? ' · newer, presumed to hold' : ''}
            </p>
            {open ? (
              <Button
                type="button"
                variant={stands === side.id ? 'primary' : 'outline'}
                size="xs"
                role="radio"
                aria-checked={stands === side.id}
                data-testid={`vault-resolve-${id}-stand-${side.id}`}
                onClick={() => setStands(side.id)}
              >
                This one holds
              </Button>
            ) : null}
          </div>
        ))}
      </div>
      {status === 'resolved' ? (
        <p className="vault-contradiction-why">
          Resolved:{' '}
          {contradiction.resolution?.stands
            ? `${sides.find((side) => side.id === contradiction.resolution?.stands)?.claim ?? 'one fact'} stands`
            : 'neither fact stands'}
          . {contradiction.resolution?.note}
        </p>
      ) : open ? (
        <form
          className="vault-resolve"
          aria-label="Resolve this contradiction"
          onSubmit={async (event) => {
            event.preventDefault()
            setPending(true)
            setError(null)
            const result = await onResolve(id, stands, note.trim())
            setPending(false)
            if (result?.error) setError(result.error)
          }}
        >
          <Button
            type="button"
            variant={stands === null ? 'primary' : 'ghost'}
            size="xs"
            className="self-start"
            role="radio"
            aria-checked={stands === null}
            data-testid={`vault-resolve-${id}-neither`}
            onClick={() => setStands(null)}
          >
            Neither holds
          </Button>
          <Field htmlFor={`vault-resolve-${id}-note`} error={error ?? undefined} hint="Saved in the vault as a decision.">
            <div className="flex items-center gap-2">
              <Input
                id={`vault-resolve-${id}-note`}
                data-testid={`vault-resolve-${id}-note`}
                value={note}
                placeholder="Why"
                aria-label="Why"
                onChange={(e) => setNote(e.target.value)}
              />
              <Button type="submit" variant="primary" size="sm" data-testid={`vault-resolve-${id}-submit`} disabled={pending || !note.trim()}>
                {pending ? 'Recording…' : 'Record decision'}
              </Button>
            </div>
          </Field>
        </form>
      ) : (
        <p className="vault-contradiction-why">
          Held on {contradiction.holder ?? 'another machine'}; it can be resolved there.
        </p>
      )}
    </section>
  )
}

const REPORT_STATUS: Record<VaultReport['status'], { label: string; tone?: 'amber' }> = {
  pending: { label: 'Waiting for the manager' },
  corrected: { label: 'Corrected' },
  answered: { label: 'Answered' },
  referred: { label: 'Referred to you', tone: 'amber' },
  closed: { label: 'Closed' },
}

export function ReportCard({
  report,
  onOpenEntry,
  onClose,
  onReview,
}: {
  report: VaultReport
  onOpenEntry: (id: string) => void
  onClose: (reportId: string, note: string) => VaultActionResult
  /** Asks the manager to look into a pending report now (F801); absent, a pending report waits. */
  onReview?: (reportId: string) => VaultActionResult
}) {
  const status = REPORT_STATUS[report.status] ?? { label: report.status }
  return (
    <article className="vault-report" data-testid={`vault-report-${report.id}`} data-status={report.status}>
      <header className="vault-report-head">
        <span className="min-w-0 flex-1">
          <span className="vault-report-who">{report.reporter.agent} on </span>
          {report.entry_name}
        </span>
        <span className="vault-chip" data-tone={status.tone}>
          {status.label}
        </span>
      </header>
      <p className="vault-report-message">{report.message}</p>
      {report.answer ? <p className="vault-report-answer">{report.answer}</p> : null}
      {report.replaced_by ? (
        <p className="vault-report-answer">
          {report.replaced_by_claim ?? 'A corrected fact was written.'}{' '}
          <Button
            variant="ghost"
            size="xs"
            data-testid={`vault-report-link-${report.id}`}
            onClick={() => onOpenEntry(report.replaced_by as string)}
          >
            Open the corrected fact
          </Button>
        </p>
      ) : null}
      {report.close ? <p className="vault-report-answer">Closed: {report.close.note}</p> : null}
      {report.status === 'referred' ? <CloseReportForm report={report} onClose={onClose} /> : null}
      {report.status === 'pending' && onReview ? <ReviewReportButton report={report} onReview={onReview} /> : null}
    </article>
  )
}

/** A pending report the manager has not reached, looked into on request (F801): the job that
 *  answers reports runs on its own schedule, and a report that missed it otherwise just waits. */
function ReviewReportButton({
  report,
  onReview,
}: {
  report: VaultReport
  onReview: (reportId: string) => VaultActionResult
}) {
  const [state, setState] = React.useState<'idle' | 'pending' | 'queued'>('idle')
  const [error, setError] = React.useState<string | null>(null)
  return (
    <div className="vault-report-review">
      <Button
        variant="ghost"
        size="xs"
        data-testid={`vault-report-${report.id}-review`}
        disabled={state !== 'idle'}
        title="Ask the manager to look into this report now"
        onClick={async () => {
          setState('pending')
          setError(null)
          const result = await onReview(report.id)
          if (result?.error) {
            setError(result.error)
            setState('idle')
          } else setState('queued')
        }}
      >
        Look into it
      </Button>
      {error ? (
        <p className="vault-report-review-error" role="alert">
          {error}
        </p>
      ) : state === 'queued' ? (
        <p className="vault-report-answer">Looking into it in the background. The answer appears here when it finishes.</p>
      ) : null}
    </div>
  )
}

function CloseReportForm({
  report,
  onClose,
}: {
  report: VaultReport
  onClose: (reportId: string, note: string) => VaultActionResult
}) {
  const { id } = report
  const [note, setNote] = React.useState('')
  const [pending, setPending] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  return (
    <form
      className="vault-resolve"
      aria-label="Close this report"
      onSubmit={async (event) => {
        event.preventDefault()
        setPending(true)
        setError(null)
        const result = await onClose(id, note.trim())
        setPending(false)
        if (result?.error) setError(result.error)
      }}
    >
      <Field htmlFor={`vault-report-${id}-note`} error={error ?? undefined} hint="Recorded with the report.">
        <div className="flex items-center gap-2">
          <Input
            id={`vault-report-${id}-note`}
            data-testid={`vault-report-${id}-note`}
            value={note}
            placeholder="What you decided"
            aria-label="What you decided"
            onChange={(e) => setNote(e.target.value)}
          />
          <Button type="submit" variant="primary" size="sm" data-testid={`vault-report-${id}-close`} disabled={pending || !note.trim()}>
            {pending ? 'Closing…' : 'Close report'}
          </Button>
        </div>
      </Field>
    </form>
  )
}
