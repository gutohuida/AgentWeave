import { Icon } from '@/components/common/Icon'
import { formatAgo, formatDateTime } from '@/lib/format'
import type { ClearStableResult, DisturbedRun, KnownFailingEntry } from '@/api/knownFailing'

/**
 * The project's known-failing list on the Overview (`failures-already-known-are-on-a-list-not-
 * re-argued`, FR-11), in place of the flaky-tests row it replaced: every test the gates go past
 * because main fails it or it flakes, each with its check, kind, first and last seen, and its own
 * fix task. Nothing here asks the operator to act -- the fix task is theirs to start when they
 * choose -- so it is a list to read, not a row in "Needs you".
 */
export function KnownFailingList({
  entries,
  disturbed = [],
  onClear,
  clearing = false,
  cleared,
  clearError,
  onOpenTask,
  now,
}: {
  /** As the route returns them: most recently seen first. */
  entries: KnownFailingEntry[]
  /** Disturbed runs of the last seven days, newest first: beside the list, never in it. */
  disturbed?: DisturbedRun[]
  /** Closes the open flaky fix tasks whose test is off the list; without it there is no action. */
  onClear?: () => void
  clearing?: boolean
  /** What the last use of the action did. */
  cleared?: ClearStableResult | null
  clearError?: string | null
  onOpenTask: (taskId: string) => void
  now: Date
}) {
  return (
    <section className="aw-ov-section" aria-labelledby="ov-known-failing" data-testid="known-failing-list">
      <h2 id="ov-known-failing" className="aw-ov-heading">
        Known failing tests {entries.length ? <span className="aw-ov-count" data-tone="amber">{entries.length}</span> : null}
      </h2>
      {onClear ? (
        <div className="aw-ov-row-detail" data-testid="known-failing-clear">
          <button type="button" className="aw-overview-link" disabled={clearing} onClick={onClear}
            title="Close every open flaky fix task whose test is no longer on this list">
            Close fix tasks for tests that left the list
          </button>
          {cleared ? (
            <span role="status" data-slot="kf-cleared">
              {' '}Closed {cleared.closed}, left {cleared.left} open.
            </span>
          ) : null}
          {clearError ? <span role="alert"> {clearError}</span> : null}
        </div>
      ) : null}
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
      {disturbed.length > 0 ? (
        <div data-testid="disturbed-runs" className="aw-ov-kf-disturbed">
          <h3 className="aw-ov-row-detail">Disturbed runs, last 7 days (information: no test is listed and no task filed)</h3>
          <ul className="aw-ov-list">
            {disturbed.map((run) => (
              <li key={run.id} data-testid={`disturbed-${run.id}`} className="aw-ov-row">
                <span className="aw-ov-row-text">
                  <span className="aw-ov-row-title">
                    {run.check ?? 'check'} · run {run.run_id}
                  </span>
                  <span className="aw-ov-row-detail" data-slot="disturbed-count">
                    {run.failed} failed, {run.passed_on_rerun} passed when re-run
                    {run.at ? <> · <Seen label="seen" at={run.at} now={now} /></> : null}
                  </span>
                  {run.first_run_output ? (
                    <details>
                      <summary>The first run&rsquo;s output</summary>
                      <pre style={{ whiteSpace: 'pre-wrap' }}>{run.first_run_output.slice(-1500)}</pre>
                    </details>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}

function Seen({ label, at, now }: { label: string; at: string | null; now: Date }) {
  if (!at) return <span>{label} unknown</span>
  return (
    <time dateTime={at} title={formatDateTime(at, now)}>
      {label} {formatAgo(at, now)} ago
    </time>
  )
}
