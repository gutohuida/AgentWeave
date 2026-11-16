import { Icon } from '@/components/common/Icon'
import { useState } from 'react'
import { readableApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { formatAgoLong } from '@/lib/format'
import type { SpecAcknowledgedGap, SpecBlockingFinding, SpecDeliveryStatus } from '@/api/spec'
import { plainGap } from './gapWords'

/* Small pieces of the document header's messages (`useSpecPhaseControls`). */

/** Gaps grouped by code, in the order the Hub listed them. */
function groupGaps(gaps: SpecBlockingFinding[]): Array<[string, SpecBlockingFinding[]]> {
  const groups = new Map<string, SpecBlockingFinding[]>()
  for (const gap of gaps) {
    const group = groups.get(gap.code)
    if (group) group.push(gap)
    else groups.set(gap.code, [gap])
  }
  return [...groups.entries()]
}

/** One plain-words line per kind of gap (`plainGap`): the Hub's code stays in its answers, not here. */
export function GapLines({ gaps }: { gaps: SpecBlockingFinding[] }) {
  return (
    <ul className="flex min-w-0 max-w-full flex-col gap-0.5">
      {groupGaps(gaps).map(([code, group]) => (
        <li key={code} data-testid={`approval-warning-${code}`} className="flex min-w-0 items-start gap-1.5">
          <Icon name="warning" size={13} className="shrink-0" />
          <span className="min-w-0 [overflow-wrap:anywhere]">{plainGap(code, group)}</span>
        </li>
      ))}
    </ul>
  )
}

/** Gaps somebody chose to leave open, apart from the open ones: each says why, who and when. */
export function AcknowledgedGapLines({ gaps }: { gaps: SpecAcknowledgedGap[] }) {
  return (
    <ul className="flex min-w-0 max-w-full flex-col gap-1" data-testid="acknowledged-gaps">
      {gaps.map((gap) => (
        <li
          key={`${gap.code}:${gap.where}`}
          data-testid={`acknowledged-gap-${gap.code}`}
          className="flex min-w-0 items-start gap-1.5"
        >
          <Icon name="check" size={13} className="shrink-0" />
          <span className="min-w-0 [overflow-wrap:anywhere]">
            <span>{plainGap(gap.code, [gap])}</span>{' '}
            <span data-testid="acknowledged-gap-meta" style={{ color: 'var(--text-3)' }}>
              Acknowledged by {gap.by}
              {gap.at ? ` ${formatAgoLong(gap.at)}` : ''}: {gap.reason}
            </span>
          </span>
        </li>
      ))}
    </ul>
  )
}

/** One Acknowledge control per open gap: the operator leaves it open with a reason (FR-11). */
export function AcknowledgeGapControls({
  gaps,
  onAcknowledge,
}: {
  gaps: SpecBlockingFinding[]
  onAcknowledge: (gap: SpecBlockingFinding, reason: string) => Promise<void>
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [refusal, setRefusal] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const keyOf = (gap: SpecBlockingFinding) => `${gap.code}:${gap.where}`
  async function submit(gap: SpecBlockingFinding) {
    setPending(true)
    setRefusal(null)
    try {
      await onAcknowledge(gap, reason.trim())
      setEditing(null)
      setReason('')
    } catch (error) {
      setRefusal(readableApiError(error, 'The Hub did not accept that acknowledgement.'))
    } finally {
      setPending(false)
    }
  }
  return (
    <ul className="flex min-w-0 max-w-full flex-col gap-1" data-testid="acknowledge-controls">
      {gaps.map((gap) => (
        <li key={keyOf(gap)} className="flex min-w-0 flex-col gap-1">
          {editing === keyOf(gap) ? (
            <span className="flex flex-wrap items-center gap-1.5">
              <input
                data-testid="acknowledge-reason"
                aria-label="Why this gap may stay"
                placeholder="Why this gap may stay"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <Button
                variant="primary"
                size="xs"
                data-testid="acknowledge-submit"
                disabled={pending || reason.trim() === ''}
                onClick={() => void submit(gap)}
              >
                Acknowledge
              </Button>
              <Button variant="ghost" size="xs" onClick={() => setEditing(null)}>
                Cancel
              </Button>
            </span>
          ) : (
            <Button
              variant="ghost"
              size="xs"
              data-testid="acknowledge-open"
              className="!h-auto min-w-0 max-w-full !justify-start !whitespace-normal py-1 text-left"
              onClick={() => {
                setRefusal(null)
                setReason('')
                setEditing(keyOf(gap))
              }}
            >
              Acknowledge: {gap.where ? `${gap.where} — ` : ''}{plainGap(gap.code, [gap])}
            </Button>
          )}
        </li>
      ))}
      {refusal && (
        <li role="alert" data-testid="acknowledge-refusal">
          {refusal}
        </li>
      )}
    </ul>
  )
}

export function ReviewerLine({ status }: { status: SpecDeliveryStatus }) {
  const stale = Boolean(status.reviewer) && status.reviewer_state !== 'ok'
  return (
    <p
      data-testid="delivery-reviewer"
      data-stale={stale ? 'true' : 'false'}
      className="aw-spec-message"
      data-tone={stale ? 'warn' : undefined}
      style={{ color: stale ? 'var(--amber)' : 'var(--text-3)' }}
    >
      {stale && <Icon name="warning" size={13} />}
      {!status.reviewer
        ? 'Reviewed by any free agent: the document names no reviewer.'
        : stale
          ? `Reviewed by @${status.reviewer}, ${
              status.reviewer_state === 'archived'
                ? 'which is archived'
                : 'which is not an agent on this project'
            }: its reviews will come to you.`
          : `Reviewed by @${status.reviewer}.`}
    </p>
  )
}
