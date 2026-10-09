import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import { hubDate } from '@/lib/hubTime'
import {
  useReviewSpecAmendments,
  useSpecAmendments,
  useSpecDocuments,
  type SpecAmendment,
} from '@/api/spec'

const OP_LABEL: Record<SpecAmendment['op'], string> = {
  add_task: 'Added task',
  add_criterion: 'Added criterion',
  change_criterion: 'Changed criterion',
  remove_criterion: 'Removed criterion',
  cannot_satisfy: 'Cannot satisfy',
}

/**
 * What a tester changed in an approved document, and whether the operator has looked
 * (`a-tester-drives-the-built-product-and-keeps-the-spec-true`, FR-9).
 *
 * Every amendment took effect when it was made; reviewing it records that the operator has read
 * it. A relaxing one (a criterion changed or removed, or a cannot-satisfy report) is what holds its
 * requirement back from verified until then, so that consequence is said on its row.
 */
export function SpecAmendmentsPanel({ path }: { path: string }) {
  const { data: documentsData, isError: documentsError } = useSpecDocuments()
  const record = documentsData?.documents.find((entry) => entry.path === path)
  // The documents view says whether there is anything to list. When that read failed it cannot say
  // "none", so the list itself is asked rather than the panel claiming there are no amendments.
  const mayHave = documentsError || (record?.amendments?.total ?? 0) > 0
  const { data, error } = useSpecAmendments(path, mayHave)
  const review = useReviewSpecAmendments()

  const amendments = data?.amendments ?? []
  if (!mayHave || (!error && amendments.length === 0 && !record?.amendments)) return null
  const unreviewed = amendments.filter((amendment) => !amendment.reviewed).length

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
        {amendments.map((amendment) => (
          <AmendmentRow
            key={amendment.id}
            amendment={amendment}
            busy={review.isPending}
            onReview={() => review.mutate({ path, ids: [amendment.id] })}
          />
        ))}
      </ul>
    </section>
  )
}

function AmendmentRow({
  amendment,
  busy,
  onReview,
}: {
  amendment: SpecAmendment
  busy: boolean
  onReview: () => void
}) {
  const at = hubDate(amendment.created_at)
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
        {amendment.reviewed ? (
          <span style={{ color: 'var(--text-3)' }}>
            Reviewed{amendment.reviewed_by ? ` by ${amendment.reviewed_by}` : ''}
          </span>
        ) : (
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
      {amendment.relaxing && !amendment.reviewed && (
        <span style={{ color: 'var(--amber)' }}>
          {amendment.identifier ?? 'Its requirement'} cannot be verified until you review this.
        </span>
      )}
    </li>
  )
}
