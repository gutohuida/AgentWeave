import { Icon } from '@/components/common/Icon'
import type { SpecBlockingFinding, SpecDeliveryStatus } from '@/api/spec'
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
