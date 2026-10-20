import { Icon } from '@/components/common/Icon'

/** One part of a screen and the error its query failed with (`null` when it did not fail). */
export type QueryFailure = readonly [label: string, error: unknown]

/**
 * Says, in one line, which parts of a screen the Hub did not answer for.
 *
 * A screen built from several queries otherwise renders a failed one as its default — an empty
 * list, a zero, "nobody is working" — and the operator cannot tell that from the truth (F197's
 * shape). This names the parts that failed, so what is shown beside it reads as incomplete rather
 * than as fact. Renders nothing while every query has answered.
 */
export function QueryErrorNotice({ failures, className }: { failures: readonly QueryFailure[]; className?: string }) {
  const failed = failures.filter(([, error]) => Boolean(error))
  if (failed.length === 0) return null
  const labels = failed.map(([label]) => label)
  const list = labels.length === 1 ? labels[0] : `${labels.slice(0, -1).join(', ')} and ${labels[labels.length - 1]}`
  const first = failed[0][1]
  return (
    <div
      role="alert"
      data-testid="query-error-notice"
      className={['aw-query-error', className].filter(Boolean).join(' ')}
      title={first instanceof Error ? first.message : undefined}
    >
      <Icon name="warning" size={14} />
      <span>
        Couldn’t read {list} from the Hub. What is shown here may be incomplete.
      </span>
    </div>
  )
}
