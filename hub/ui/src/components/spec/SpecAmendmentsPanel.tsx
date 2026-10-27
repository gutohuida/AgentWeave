import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import { hubDate } from '@/lib/hubTime'
import {
  useAcceptSpecAmendment,
  useDeclineSpecAmendment,
  useRespondToReport,
  useReviewSpecAmendments,
  useSpecAmendments,
  useSpecDocuments,
  type SpecAmendment,
} from '@/api/spec'

const OP_LABEL: Record<SpecAmendment['op'], string> = {
  add_task: 'Added task',
  add_requirement: 'Added requirement',
  add_criterion: 'Added criterion',
  change_criterion: 'Changed criterion',
  remove_criterion: 'Removed criterion',
  cannot_satisfy: 'Cannot satisfy',
}

const PROPOSED_LABEL: Record<SpecAmendment['op'], string> = {
  add_task: 'Proposes a task',
  add_requirement: 'Proposes a requirement',
  add_criterion: 'Proposes a criterion',
  change_criterion: 'Proposes changing criterion',
  remove_criterion: 'Proposes removing criterion',
  cannot_satisfy: 'Cannot satisfy',
}

/** A row whose change is in the document: applied at once, or accepted. */
function recorded(amendment: SpecAmendment): boolean {
  return !amendment.state || amendment.state === 'applied' || amendment.state === 'accepted'
}

/**
 * What changed, or is proposed to change, in an approved document, and whether the operator has
 * looked (`a-tester-drives-the-built-product-and-keeps-the-spec-true`, FR-9;
 * `amendments-main-watch-and-the-next-slice`, D1).
 *
 * A tester's amendment took effect when it was made; reviewing it records that the operator has
 * read it. A relaxing one (a criterion changed or removed, or a cannot-satisfy report) is what holds
 * its requirement back from verified until then, so that consequence is said on its row. An
 * author's or the lead's proposal changes nothing until the operator accepts it; Decline asks for a
 * reason, which the proposer reads.
 */
export function SpecAmendmentsPanel({ path }: { path: string }) {
  const { data: documentsData, isError: documentsError } = useSpecDocuments()
  const record = documentsData?.documents.find((entry) => entry.path === path)
  // The documents view says whether there is anything to list. When that read failed it cannot say
  // "none", so the list itself is asked rather than the panel claiming there are no amendments.
  const mayHave =
    documentsError ||
    (record?.amendments?.total ?? 0) > 0 ||
    (record?.amendments?.proposed ?? 0) > 0
  const { data, error } = useSpecAmendments(path, mayHave)
  const review = useReviewSpecAmendments()

  const amendments = data?.amendments ?? []
  if (!mayHave || (!error && amendments.length === 0 && !record?.amendments)) return null
  const unreviewed = amendments.filter((amendment) => recorded(amendment) && !amendment.reviewed).length
  const proposed = amendments.filter((amendment) => amendment.state === 'proposed').length

  return (
    <section
      data-testid="spec-amendments"
      className="flex shrink-0 flex-col gap-1.5 px-3 py-2 text-xs"
      style={{ borderTop: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-2">
        <span style={{ color: 'var(--text-2)', fontWeight: 600 }}>Amendments</span>
        <span style={{ color: unreviewed ? 'var(--amber)' : 'var(--text-3)' }}>
          {unreviewed ? `${unreviewed} not reviewed` : 'all reviewed'}
        </span>
        {proposed > 0 && (
          <span style={{ color: 'var(--amber)' }}>
            · {proposed} proposed, waiting for you
          </span>
        )}
        <div className="flex-1" />
        {unreviewed > 0 && (
          <Button
            variant="ghost"
            size="xs"
            disabled={review.isPending}
            onClick={() => review.mutate({ path })}
          >
            Mark all reviewed
          </Button>
        )}
      </div>
      {error && (
        <p style={{ color: 'var(--amber)' }}>
          Could not load the amendments: {readableApiError(error, 'the Hub did not answer.')}
        </p>
      )}
      <ul className="flex flex-col gap-1">
        {amendments.map((amendment) =>
          recorded(amendment) ? (
            <AmendmentRow
              key={amendment.id}
              path={path}
              amendment={amendment}
              busy={review.isPending}
              onReview={() => review.mutate({ path, ids: [amendment.id] })}
            />
          ) : (
            <ProposalRow key={amendment.id} path={path} amendment={amendment} />
          ),
        )}
      </ul>
    </section>
  )
}

const RESPONSE_LABEL: Record<string, string> = {
  amended: 'Answered: criterion amended',
  accepted: 'Answered: report accepted',
  rejected: 'Answered: report rejected',
}

function AmendmentRow({
  path,
  amendment,
  busy,
  onReview,
}: {
  path: string
  amendment: SpecAmendment
  busy: boolean
  onReview: () => void
}) {
  const at = hubDate(amendment.created_at)
  // F700: a cannot-satisfy report is answered, not marked reviewed.
  const report = amendment.op === 'cannot_satisfy'
  return (
    <li
      data-testid={`spec-amendment-${amendment.id}`}
      className="flex flex-col gap-0.5 rounded-[var(--radius-sm)] px-2 py-1.5"
      style={{
        background: amendment.reviewed
          ? 'var(--surface-2)'
          : 'color-mix(in srgb, var(--amber) 10%, transparent)',
        color: 'var(--text-2)',
      }}
    >
      <div className="flex flex-wrap items-center gap-x-1.5">
        {!amendment.reviewed && <Icon name="warning" size={13} />}
        <span style={{ fontWeight: 600 }}>{OP_LABEL[amendment.op] ?? amendment.op}</span>
        <code>{amendment.target}</code>
        {amendment.identifier && <span>({amendment.identifier})</span>}
        <span style={{ color: 'var(--text-3)' }}>
          · @{amendment.author}
          {amendment.run_id ? ` in run ${amendment.run_id}` : ''} ·{' '}
          <span title={at.toLocaleString()}>{formatDistanceToNow(at, { addSuffix: true })}</span>
        </span>
        <div className="flex-1" />
        {amendment.state === 'accepted' ? (
          <span style={{ color: 'var(--text-3)' }}>
            Accepted{amendment.decided_by ? ` by ${amendment.decided_by}` : ''}
          </span>
        ) : amendment.reviewed ? (
          <span style={{ color: 'var(--text-3)' }}>
            {(amendment.response && RESPONSE_LABEL[amendment.response]) || 'Reviewed'}
            {amendment.reviewed_by ? ` by ${amendment.reviewed_by}` : ''}
          </span>
        ) : report ? null : (
          <Button variant="primary" size="xs" disabled={busy} onClick={onReview}>
            Mark reviewed
          </Button>
        )}
      </div>
      <span>{amendment.reason}</span>
      {amendment.how_to_check && (
        <span style={{ color: 'var(--text-3)' }}>
          How to check: <code>{amendment.how_to_check}</code>
        </span>
      )}
      {amendment.response_reason && (
        <span style={{ color: 'var(--text-3)' }}>Answer: {amendment.response_reason}</span>
      )}
      {report && !amendment.reviewed && <ReportAnswer path={path} amendment={amendment} />}
      {amendment.relaxing && !amendment.reviewed && (
        <span style={{ color: 'var(--amber)' }}>
          {amendment.identifier ?? 'Its requirement'} cannot be verified until you review this.
        </span>
      )}
    </li>
  )
}

/** The change a proposal makes, field by field, as the route returns it (`change`). */
function ChangeSummary({ change }: { change: Record<string, unknown> | null }) {
  if (!change) return null
  const fields = Object.entries(change).filter(
    ([key, value]) => key !== 'from' && value !== null && value !== '' && !(Array.isArray(value) && !value.length),
  )
  if (!fields.length) return null
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-2" data-testid="amendment-change">
      {fields.map(([key, value]) => (
        <div key={key} className="contents">
          <dt style={{ color: 'var(--text-3)' }}>{key}</dt>
          <dd>{Array.isArray(value) ? value.join(', ') : String(value)}</dd>
        </div>
      ))}
    </dl>
  )
}

const DECIDED_LABEL: Record<string, string> = {
  declined: 'Declined',
  stale: 'No longer applied when accepted',
}

/** An author's or the lead's proposal (D1): nothing changed until the operator accepts it. */
function ProposalRow({ path, amendment }: { path: string; amendment: SpecAmendment }) {
  const accept = useAcceptSpecAmendment()
  const decline = useDeclineSpecAmendment()
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState('')
  const at = hubDate(amendment.created_at)
  const open = amendment.state === 'proposed'
  const busy = accept.isPending || decline.isPending
  const failure = accept.error ?? decline.error
  return (
    <li
      data-testid={`spec-amendment-${amendment.id}`}
      className="flex flex-col gap-0.5 rounded-[var(--radius-sm)] px-2 py-1.5"
      style={{
        background: open ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'var(--surface-2)',
        color: 'var(--text-2)',
      }}
    >
      <div className="flex flex-wrap items-center gap-x-1.5">
        <span style={{ fontWeight: 600 }}>{PROPOSED_LABEL[amendment.op] ?? amendment.op}</span>
        <code>{amendment.target}</code>
        <span style={{ color: 'var(--text-3)' }}>
          · @{amendment.author} ·{' '}
          <span title={at.toLocaleString()}>{formatDistanceToNow(at, { addSuffix: true })}</span>
        </span>
        <div className="flex-1" />
        {open ? (
          <>
            <Button
              variant="primary"
              size="xs"
              disabled={busy}
              onClick={() => accept.mutate({ path, id: amendment.id })}
            >
              Accept
            </Button>
            <Button variant="ghost" size="xs" disabled={busy} onClick={() => setDeclining(true)}>
              Decline…
            </Button>
          </>
        ) : (
          <span style={{ color: 'var(--text-3)' }}>
            {DECIDED_LABEL[amendment.state ?? ''] ?? amendment.state}
            {amendment.decided_by ? ` by ${amendment.decided_by}` : ''}
          </span>
        )}
      </div>
      <span>{amendment.reason}</span>
      {amendment.how_to_check && (
        <span style={{ color: 'var(--text-3)' }}>
          How to check: <code>{amendment.how_to_check}</code>
        </span>
      )}
      <ChangeSummary change={amendment.change} />
      {amendment.decided_reason && (
        <span style={{ color: 'var(--text-3)' }}>Why: {amendment.decided_reason}</span>
      )}
      {open && declining && (
        <div className="flex flex-wrap items-center gap-1.5">
          <input
            aria-label="Reason for declining the amendment"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="what the proposer should know"
          />
          <Button
            variant="primary"
            size="xs"
            disabled={busy || reason.trim() === ''}
            onClick={() =>
              decline.mutate(
                { path, id: amendment.id, reason: reason.trim() },
                { onSuccess: () => setDeclining(false) },
              )
            }
          >
            Decline and tell the proposer
          </Button>
        </div>
      )}
      {failure && (
        <span role="alert" style={{ color: 'var(--red)' }}>
          {readableApiError(failure, 'The Hub refused this decision.')}
        </span>
      )}
    </li>
  )
}

/** The three answers to a cannot-satisfy report (F700), each of which does something. */
function ReportAnswer({ path, amendment }: { path: string; amendment: SpecAmendment }) {
  const respond = useRespondToReport()
  const before = (amendment.before ?? {}) as Record<string, string>
  const [mode, setMode] = useState<'amend' | 'reject' | null>(null)
  const [then, setThen] = useState(before.then ?? '')
  const [howToCheck, setHowToCheck] = useState(before.how_to_check ?? '')
  const [reason, setReason] = useState('')

  function send(response: 'amend' | 'accept' | 'reject') {
    const change: Record<string, string> = {}
    if (response === 'amend') {
      if (then.trim() && then.trim() !== (before.then ?? '')) change.then = then.trim()
      if (howToCheck.trim() && howToCheck.trim() !== (before.how_to_check ?? ''))
        change.how_to_check = howToCheck.trim()
    }
    respond.mutate(
      {
        path,
        id: amendment.id,
        response,
        reason: reason.trim(),
        ...(response === 'amend' ? { change } : {}),
      },
      { onSuccess: () => setMode(null) },
    )
  }

  const amendReady = then.trim() !== (before.then ?? '') || howToCheck.trim() !== (before.how_to_check ?? '')
  return (
    <div className="flex flex-col gap-1" data-testid={`report-answer-${amendment.id}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Button variant="ghost" size="xs" disabled={respond.isPending} onClick={() => setMode('amend')}>
          Amend criterion…
        </Button>
        <Button variant="primary" size="xs" disabled={respond.isPending} onClick={() => send('accept')}>
          Accept and unblock
        </Button>
        <Button variant="ghost" size="xs" disabled={respond.isPending} onClick={() => setMode('reject')}>
          Reject…
        </Button>
      </div>
      {mode === 'amend' && (
        <div className="flex flex-col gap-1">
          <label className="flex flex-col gap-0.5">
            <span>Then</span>
            <input aria-label="Criterion then" value={then} onChange={(e) => setThen(e.target.value)} />
          </label>
          <label className="flex flex-col gap-0.5">
            <span>How to check</span>
            <input
              aria-label="Criterion how to check"
              value={howToCheck}
              onChange={(e) => setHowToCheck(e.target.value)}
            />
          </label>
          <input
            aria-label="Reason for the amendment"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="why (optional)"
          />
          <div>
            <Button
              variant="primary"
              size="xs"
              disabled={respond.isPending || !amendReady}
              onClick={() => send('amend')}
            >
              Amend and unblock
            </Button>
          </div>
        </div>
      )}
      {mode === 'reject' && (
        <div className="flex flex-wrap items-center gap-1.5">
          <input
            aria-label="Reason for rejecting the report"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="what the reporter should try"
          />
          <Button
            variant="primary"
            size="xs"
            disabled={respond.isPending || reason.trim() === ''}
            onClick={() => send('reject')}
          >
            Reject and tell the reporter
          </Button>
        </div>
      )}
      {respond.isError && (
        <span role="alert" style={{ color: 'var(--red)' }}>
          {readableApiError(respond.error, 'The Hub refused this answer.')}
        </span>
      )}
    </div>
  )
}
