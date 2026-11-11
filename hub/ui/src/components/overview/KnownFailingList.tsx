import { Icon } from '@/components/common/Icon'
import { formatAgoLong, formatDateTime } from '@/lib/format'
import type { KnownFailingEntry } from '@/api/knownFailing'

/**
 * The project's known-failing list on the Overview (`failures-already-known-are-on-a-list-not-
 * re-argued`, FR-11), in place of the flaky-tests row it replaced: every test the gates go past
 * because main fails it or it flakes, each with its check, kind, first and last seen, and its own
 * fix task. Nothing here asks the operator to act -- the fix task is theirs to start when they
 * choose -- so it is a list to read, not a row in "Needs you".
 */
export function KnownFailingList({
  entries,
  onOpenTask,
  now,
}: {
  /** As the route returns them: most recently seen first. */
  entries: KnownFailingEntry[]
  onOpenTask: (taskId: string) => void
  now: Date
}) {
  return (
    <section className="aw-ov-section" aria-labelledby="ov-known-failing" data-testid="known-failing-list">
      <h2 id="ov-known-failing" className="aw-ov-heading">
        Known failing tests {entries.length ? <span className="aw-ov-count" data-tone="amber">{entries.length}</span> : null}
      </h2>
      {entries.length === 0 ? (
        <div className="aw-ov-calm">
          <Icon name="check_circle" size={15} /> No test is known to fail on main or to flake.
        </div>
      ) : (
        <ul className="aw-ov-list">
          {entries.map((entry) => (
            <li key={entry.id} data-testid={`known-failing-${entry.id}`} className="aw-ov-row aw-ov-kf-row" data-kind={entry.kind}>
              <span className="aw-ov-row-icon" data-kind={entry.kind === 'flaky' ? 'flaky' : 'main'} aria-hidden="true">
                <Icon name={entry.kind === 'flaky' ? 'bug_report' : 'call_split'} size={13} />
              </span>
              <span className="aw-ov-row-text">
                <span className="aw-ov-row-title" title={entry.test ?? undefined}>
                  {entry.test ?? `The whole ${entry.check} check`}
                </span>
                <span className="aw-ov-row-detail">
                  <span data-slot="kf-check">{entry.check}</span> · <span data-slot="kf-kind">{entry.kind}</span> ·{' '}
                  <Seen label="first seen" at={entry.first_seen} now={now} /> ·{' '}
                  <Seen label="last seen" at={entry.last_seen} now={now} />
                </span>
              </span>
              <span className="aw-ov-row-end">
                {entry.fix_task ? (
                  <button
                    data-slot="kf-fix-task"
                    type="button"
                    className="aw-overview-link"
                    title={entry.fix_task.title}
                    onClick={() => onOpenTask(entry.fix_task!.id)}
                  >
                    {entry.fix_task.display_id ?? entry.fix_task.id}
                    {entry.fix_task.status ? ` · ${entry.fix_task.status.replace(/_/g, ' ')}` : ''}
                  </button>
                ) : (
                  <span>No fix task</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Seen({ label, at, now }: { label: string; at: string | null; now: Date }) {
  if (!at) return <span>{label} unknown</span>
  return (
    <time dateTime={at} title={formatDateTime(at, now)}>
      {label} {formatAgoLong(at, now)}
    </time>
  )
}
