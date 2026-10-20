import { Icon } from '@/components/common/Icon'
import { StatusBadge } from '@/components/common/Badge'
import { EvidenceLink } from '@/components/evidence/EvidenceLink'
import type { Job, JobRun } from '@/api/jobs'
import { formatAgo, formatDateTime } from '@/lib/format'
import { loopStateLabel, runStatusColor } from '@/lib/jobState'

/** What a job row opens to: its message, its recent firings and, for a loop, where the loop
 *  stands. Presentational — the row's container fetches the history and the loop's task ids.
 *
 *  Carried over from the old JobCard with its findings intact: a refused firing leads with its own
 *  status (F24), a stall says how often it was re-checked, "No runs yet" is never said while the
 *  answer is in flight, a flow lists every current item with what the agent's name means there
 *  (F26, F63), and an ended or stopping loop says so (F655, F714). */

/** The last five firings as dots, oldest on the left, with the outcomes in words for a reader. */
export function TrendDots({ runs }: { runs: JobRun[] }) {
  const recent = runs.slice(0, 5).reverse()
  const counts = recent.reduce<Record<string, number>>((acc, run) => {
    acc[run.status] = (acc[run.status] ?? 0) + 1
    return acc
  }, {})
  const summary = Object.entries(counts)
    .map(([status, n]) => `${n} ${status}`)
    .join(', ')
  return (
    <span className="trend-row aw-job-trend" data-testid="job-trend">
      <span className="trend-label">Last {recent.length}</span>
      <span className="trend-dots" role="img" aria-label={`Recent runs: ${summary}`} title={summary}>
        {recent.map((run) => (
          <span key={run.id} className="trend-dot" style={{ background: runStatusColor(run.status) }} />
        ))}
      </span>
    </span>
  )
}

const RUN_ICON: Record<string, string> = {
  completed: 'check_circle',
  failed: 'error',
  skipped: 'pause',
  stopped: 'stop',
}

export function RunHistory({
  runs,
  isLoading,
  error,
  now,
}: {
  runs?: JobRun[]
  isLoading?: boolean
  /** Why the history could not be read. Never "No runs yet" for a failed read. */
  error?: string | null
  now: Date
}) {
  if (error && (!runs || runs.length === 0)) {
    return (
      <p className="aw-job-detail-muted" role="alert" data-testid="job-runs-error">
        Its run history could not be read: {error}
      </p>
    )
  }
  if (isLoading && (!runs || runs.length === 0)) {
    return <p className="aw-job-detail-muted aw-delayed">Loading runs…</p>
  }
  if (!runs || runs.length === 0) {
    return <p className="aw-job-detail-muted">No runs yet</p>
  }
  return (
    <ul className="aw-job-runs">
      {runs.slice(0, 5).map((run) => {
        const refused = run.status === 'failed' || run.status === 'skipped'
        return (
          <li key={run.id} className="aw-job-run">
            <span className="aw-job-run-status" style={{ color: runStatusColor(run.status) }}>
              <Icon name={RUN_ICON[run.status] ?? 'schedule'} size={13} />
              <span data-testid={`job-run-status-${run.id}`}>{run.status}</span>
            </span>
            <span className="aw-job-detail-muted">{run.trigger}</span>
            {refused && run.error_summary ? (
              <span
                className="aw-job-run-reason"
                style={{ color: run.status === 'skipped' ? 'var(--amber)' : 'var(--red)' }}
                title={run.error_summary}
              >
                {run.error_summary}
              </span>
            ) : (
              <span className="aw-job-run-reason" />
            )}
            {refused && /\bevidence\b/i.test(run.error_summary ?? '') ? (
              <EvidenceLink focus={null} testId={`job-run-evidence-${run.id}`}>
                Evidence
              </EvidenceLink>
            ) : null}
            {(run.tick_count ?? 1) > 1 ? (
              <span className="aw-job-detail-muted" data-testid={`job-run-ticks-${run.id}`}>
                re-checked {run.tick_count} times
              </span>
            ) : null}
            <time className="aw-job-detail-muted" dateTime={run.fired_at} title={formatDateTime(run.fired_at, now)}>
              {formatAgo(run.fired_at, now)} ago
            </time>
          </li>
        )
      })}
    </ul>
  )
}

/** What the agent's name beside a current task means (F26); `held` reads "waiting on" (F63). */
function CurrentTaskAgent({ name, capacity }: { name: string; capacity?: 'working' | 'held' | 'next' | 'assigned' }) {
  const qualifier = capacity === 'next' ? 'next: ' : capacity === 'assigned' ? 'assigned: ' : capacity === 'held' ? 'waiting on ' : ''
  return (
    <span className="aw-job-current-agent">
      {qualifier}
      {name}
    </span>
  )
}

/** A loop's state. Absent entirely for a plain job. `loopTaskIds` is every task the loop owns,
 *  handed to `onOpenTasks` when a current item is clicked. */
export function LoopBlock({ job, loopTaskIds, onOpenTasks }: { job: Job; loopTaskIds?: string[]; onOpenTasks?: (taskIds: string[]) => void }) {
  const loop = job.loop
  if (!loop) return null
  const totalQueued = Object.values(loop.queue).reduce((sum, n) => sum + n, 0)
  const canOpen = Boolean(onOpenTasks && loopTaskIds && loopTaskIds.length > 0)
  const currentTasks = loop.current_tasks ?? []
  const state = loopStateLabel(job)
  return (
    <div className="aw-job-loop" data-testid="job-loop-block">
      <div className="aw-job-loop-head">
        <Icon name="all_inclusive" size={14} />
        <span className="aw-job-detail-label">Loop</span>
        <span className="aw-job-loop-state" data-state={state === 'Active' ? 'active' : 'ended'}>
          {state}
        </span>
      </div>
      {loop.purpose ? <p className="aw-job-detail-text">{loop.purpose}</p> : null}
      {loop.stop_reason ? <p className="aw-job-detail-warn">Stopped: {loop.stop_reason}</p> : null}
      <div className="aw-job-loop-queue">
        <span className="aw-job-detail-muted">Queue: {totalQueued}</span>
        {Object.entries(loop.queue).map(([status, count]) => (
          <span key={status} className="inline-flex items-center gap-1">
            <span className="sr-only">
              {status}: {count}
            </span>
            <span aria-hidden="true" className="inline-flex items-center gap-1">
              <StatusBadge status={status} />
              <span className="aw-job-detail-muted tabular">{count}</span>
            </span>
          </span>
        ))}
      </div>
      {currentTasks.length > 0 ? (
        <div className="aw-job-loop-current" data-testid="job-loop-current-tasks">
          {currentTasks.map((task) =>
            canOpen ? (
              <button
                key={task.id}
                data-slot="job-current-task"
                type="button"
                className="aw-job-current-link"
                onClick={() => onOpenTasks?.(loopTaskIds ?? [])}
              >
                {task.title} ({task.status})
                {task.agent ? <CurrentTaskAgent name={task.agent} capacity={task.agent_capacity} /> : null}
              </button>
            ) : (
              <p key={task.id} className="aw-job-detail-muted">
                {task.title} ({task.status})
                {task.agent ? <CurrentTaskAgent name={task.agent} capacity={task.agent_capacity} /> : null}
              </p>
            ),
          )}
        </div>
      ) : (
        <p className="aw-job-detail-muted">No current item</p>
      )}
      {loop.open_questions > 0 ? (
        <p className="aw-job-detail-warn">
          {loop.open_questions} open question{loop.open_questions === 1 ? '' : 's'}
        </p>
      ) : null}
    </div>
  )
}

export function JobDetails({
  job,
  runs,
  runsLoading,
  runsError,
  loopTaskIds,
  onOpenTasks,
  now,
}: {
  job: Job
  runs?: JobRun[]
  runsLoading?: boolean
  runsError?: string | null
  loopTaskIds?: string[]
  onOpenTasks?: (taskIds: string[]) => void
  now: Date
}) {
  return (
    <div className="aw-job-details">
      <section>
        <p className="aw-job-detail-label">Message</p>
        <p className="aw-job-message">{job.message}</p>
      </section>
      <section>
        <p className="aw-job-detail-label">Recent runs</p>
        <RunHistory runs={runs} isLoading={runsLoading} error={runsError} now={now} />
      </section>
      {job.loop ? <LoopBlock job={job} loopTaskIds={loopTaskIds} onOpenTasks={onOpenTasks} /> : null}
      <p className="aw-job-ids">
        <button data-slot="job-copy-id" type="button" className="aw-job-id" title="Copy the job's id" onClick={() => void navigator.clipboard?.writeText(job.id)}>
          <Icon name="content_copy" size={11} /> Copy job id
        </button>
        {job.last_session_id ? (
          <button
            data-slot="job-copy-id"
            type="button"
            className="aw-job-id"
            title={job.last_session_id}
            onClick={() => void navigator.clipboard?.writeText(job.last_session_id ?? '')}
          >
            <Icon name="content_copy" size={11} /> Copy last session id
          </button>
        ) : null}
      </p>
    </div>
  )
}
