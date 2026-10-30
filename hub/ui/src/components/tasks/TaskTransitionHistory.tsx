import { Icon } from '@/components/common/Icon'
import { useTaskTransitions } from '@/api/tasks'
import { hubDate } from '@/lib/hubTime'

/**
 * Who moved this task, when, and from what (F203).
 *
 * `task_transitions` records every accepted move — from, to, whether a run or the operator asked,
 * which agent's run it was, whether the runtime moved it rather than the actor, and a digest of
 * the policy that governed it. All of it was unreadable: no route, no tool, and this repository's
 * own drives opened the sqlite file to say anything about attribution.
 *
 * Oldest first, which is the order `sequence` records and the order the history reads in. Several
 * moves staged in one flush share a timestamp to the microsecond, so the time is a label here and
 * never the sort key.
 */
export function TaskTransitionHistory({ taskId, open }: { taskId: string; open: boolean }) {
  const { data, isLoading, isError } = useTaskTransitions(taskId, open)
  const rows = data?.transitions ?? []

  if (isLoading || isError || rows.length === 0) {
    // A task that predates the table legitimately has no history, and nothing is lost by a
    // section that is not there. An error says nothing false either — the status the drawer
    // already shows is the task's own, and is not read from here.
    return null
  }

  return (
    <div data-testid={`task-transitions-${taskId}`}>
      <p
        className="text-[11px] font-semibold uppercase tracking-wide mb-1.5"
        style={{ color: 'var(--text-3)' }}
      >
        History
      </p>
      <ul className="space-y-1.5">
        {rows.map((row) => {
          // "the operator" and "a run" are different claims, and `actor_kind` is recorded rather
          // than inferred from `run_id` being null, so it is what is shown.
          //
          // A scheduled job's move keeps the operator's authority (`actor_kind`) and records its own
          // cause: read from `origin`, never from position (F190). `job_kind` says whether the
          // job's loop draws from a specification, which is what makes it a flow.
          //
          // `checks` is the project's checks returning work their run failed: the operator's
          // authority (they configured the checks), not the operator's act, so not "You".
          const who =
            row.origin === 'job'
              ? row.job_name
                ? `${row.job_kind === 'flow' ? 'Flow' : 'Loop'} ${row.job_name}`
                : 'A scheduled job'
              : row.origin === 'checks'
                ? 'The project’s checks'
                : row.actor_kind === 'operator'
                ? 'You'
                : row.actor_agent
                  ? row.actor_agent
                  : 'A run'
          // `runtime` means the Hub made the move on the run's behalf at a moment the run did not
          // choose. Saying "moved" for that would credit a decision nobody made.
          const verb = row.origin === 'runtime' ? 'was moved for' : 'moved'
          const when = row.created_at ? hubDate(row.created_at) : null
          return (
            <li
              key={row.id}
              className="text-[11.5px] leading-relaxed flex items-start gap-1.5"
              style={{ color: 'var(--text-2)' }}
            >
              <Icon name="arrow_forward" size={12} className="mt-1 shrink-0" aria-hidden="true" />
              <span>
                <strong style={{ color: 'var(--text)' }}>{who}</strong> {verb}{' '}
                <code>{row.from_status}</code> → <code>{row.to_status}</code>
                {when ? <> · {when.toLocaleString()}</> : null}
                {row.policy_digest ? (
                  <>
                    {' '}
                    ·{' '}
                    <span title={`Policy digest ${row.policy_digest}`}>
                      under policy <code>{row.policy_digest.slice(0, 8)}</code>
                    </span>
                  </>
                ) : null}
                {row.to_status === 'revision_needed' ? (
                  // Why it went back (FR-8): the class and its sentence, or a plain statement that
                  // this send-back carries none (recorded before the Hub kept them, or the
                  // operator's status menu, which sends a status alone).
                  <span className="block" data-testid={`task-transition-reason-${row.id}`}>
                    {row.reason_class ? (
                      <>
                        <code>{row.reason_class}</code>
                        {row.reason ? <>: {row.reason}</> : null}
                      </>
                    ) : (
                      <span style={{ color: 'var(--text-3)' }}>no reason recorded</span>
                    )}
                  </span>
                ) : null}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
