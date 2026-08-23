import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { Badge, StatusBadge } from '@/components/common/Badge'
import { Button } from '@/components/ui/button'
import { Job, JobRun, useJobHistory } from '@/api/jobs'
import { useTasks } from '@/api/tasks'
import { hubDate } from '@/lib/hubTime'
import { describeCron } from '@/lib/cron'

interface JobCardProps {
  job: Job
  onRun: (id: string) => void
  onPause: (id: string) => void
  onResume: (id: string) => void
  onArchive: (id: string) => void
  isPending: boolean
  /** A loop's queue count or current item, clicked: switch to the Tasks tab filtered to this
   *  loop's tasks. Same mechanism `SpecDocumentTasksLink` already proved live (design D5). */
  onOpenTasks?: (taskIds: string[]) => void
}

function getStatusVariant(enabled: boolean): 'default' | 'secondary' | 'success' {
  return enabled ? 'success' : 'secondary'
}

function getStatusLabel(enabled: boolean): string {
  return enabled ? 'Active' : 'Paused'
}

/**
 * One status→colour map for a job run, read by both the expanded history rows and the collapsed
 * card's trend dots. Kept as a single function rather than restated at each site: a second copy of
 * a status mapping is precisely the drift `IDENTITY.md` guards against, three copies of the task
 * mapping having already diverged before that clause was written.
 */
function runStatusColor(status: string): string {
  switch (status) {
    case 'completed':
      return 'var(--green)'
    case 'failed':
      return 'var(--red)'
    case 'skipped':
      return 'var(--amber)'
    default:
      return 'var(--text-3)'
  }
}

/**
 * "Is this job healthy?" answered at list-scan speed — the last five firings as status dots,
 * reusing `runStatusColor` so the strip can never come to mean something the expanded list below it
 * does not.
 *
 * Rendered only when the runs are already in hand, never fetched for it. `GET /jobs` carries no
 * `history` at all — `JobResponse.history` is documented "Included in get_job only" — and this
 * card's own history request is deliberately gated on `expanded` so a project with many jobs does
 * not pay one request per card just to draw five dots. For a *collapsed* card to show this, the
 * collection response would have to carry each job's last five runs inline; `status` alone is
 * enough, nothing else here is read.
 */
function TrendDots({ runs }: { runs: JobRun[] }) {
  // Oldest on the left: this strip is read as a trend, while `RunHistory` below it is a
  // newest-first log. Each order is the right one for its own shape.
  const recent = runs.slice(0, 5).reverse()
  const counts = recent.reduce<Record<string, number>>((acc, run) => {
    acc[run.status] = (acc[run.status] ?? 0) + 1
    return acc
  }, {})
  const summary = Object.entries(counts)
    .map(([status, n]) => `${n} ${status}`)
    .join(', ')

  return (
    <div className="trend-row" data-testid="job-trend">
      <span className="trend-label">Last {recent.length}</span>
      {/* Colour alone carries the outcome here, so the strip states it in words too. */}
      <div className="trend-dots" role="img" aria-label={`Recent runs: ${summary}`} title={summary}>
        {recent.map((run) => (
          <span
            key={run.id}
            className="trend-dot"
            style={{ background: runStatusColor(run.status) }}
          />
        ))}
      </div>
    </div>
  )
}

function RunHistory({ runs, isLoading }: { runs?: JobRun[]; isLoading?: boolean }) {
  // "No runs yet" is a claim about the job, so it must not be said while the answer is still in
  // flight — that is how a job with failed firings came to read as one that had never fired.
  if (isLoading && (!runs || runs.length === 0)) {
    return <p className="text-xs" style={{ color: 'var(--text-3)' }}>Loading runs…</p>
  }

  if (!runs || runs.length === 0) {
    return <p className="text-xs" style={{ color: 'var(--text-3)' }}>No runs yet</p>
  }

  return (
    <div className="space-y-2">
      {runs.slice(0, 5).map((run) => (
        <div
          key={run.id}
          className="flex items-center justify-between gap-3 p-2 rounded-lg"
          style={{ background: 'var(--surface-2)' }}
        >
          <div className="flex items-center gap-2 shrink-0">
            <Icon
              name={
                run.status === 'completed'
                  ? 'check_circle'
                  : run.status === 'failed'
                  ? 'error'
                  : run.status === 'skipped'
                  ? 'pause'
                  : run.status === 'stopped'
                  ? 'stop'
                  : 'schedule'
              }
              size={16}
              style={{ color: runStatusColor(run.status) }}
            />
            <span className="text-[11px]" style={{ color: 'var(--text)' }}>
              {run.trigger}
            </span>
          </div>
          {/* Before the timestamp, not after: the reason is the flex-1 child, so ordering it last
              let it consume the row's free space and shunted the timestamp back against the
              trigger ("scheduled1 minute ago"). Invisible until this card started loading its own
              history, since the list response never carried a run to render. */}
          {(run.status === 'failed' || run.status === 'skipped') && run.error_summary && (
            <span
              className="flex-1 min-w-0 truncate text-[11px]"
              style={{ color: run.status === 'skipped' ? 'var(--amber)' : 'var(--red)' }}
              title={run.error_summary}
            >
              {run.error_summary}
            </span>
          )}
          <span className="text-[11px] shrink-0" style={{ color: 'var(--text-3)' }}>
            {formatDistanceToNow(hubDate(run.fired_at), { addSuffix: true })}
          </span>
        </div>
      ))}
    </div>
  )
}

/**
 * A job's loop state, rendered only when `job.loop` is present — a plain job's card must not
 * change shape at all (human-only check 8.1). Its own component rather than inline in `JobCard`
 * so the `useTasks({ loopId })` fetch — needed only to build the task-id list `onOpenTasks`
 * expects — only ever runs for a job that actually has a loop.
 */
function LoopBlock({ job, onOpenTasks }: { job: Job; onOpenTasks?: (taskIds: string[]) => void }) {
  const loop = job.loop
  const { data: loopTasks } = useTasks(loop ? { loopId: loop.id } : undefined)

  if (!loop) return null

  const totalQueued = Object.values(loop.queue).reduce((sum, n) => sum + n, 0)
  const canOpenQueue = Boolean(onOpenTasks && loopTasks && loopTasks.length > 0)
  const openQueue = () => {
    if (onOpenTasks && loopTasks) onOpenTasks(loopTasks.map((t) => t.id))
  }
  const linkStyle: React.CSSProperties = {
    background: 'none',
    border: 'none',
    color: 'var(--blue)',
    cursor: 'pointer',
    padding: 0,
    font: 'inherit',
    textAlign: 'left',
  }

  return (
    <div
      className="pt-3 space-y-2"
      style={{ borderTop: '1px dashed var(--border)' }}
      data-testid="job-loop-block"
    >
      <div className="flex items-center gap-1.5">
        <Icon name="all_inclusive" size={14} style={{ color: 'var(--blue)' }} />
        <span className="text-[11px] font-medium" style={{ color: 'var(--text-2)' }}>
          Loop
        </span>
        <Badge variant={loop.stop_reason ? 'secondary' : 'success'} className="text-[10px]">
          {loop.stop_reason ? 'Stopped' : 'Active'}
        </Badge>
      </div>

      {loop.purpose && (
        <p className="text-xs" style={{ color: 'var(--text)' }}>
          {loop.purpose}
        </p>
      )}

      {loop.stop_reason && (
        <p className="text-[11px]" style={{ color: 'var(--amber)' }}>
          Stopped: {loop.stop_reason}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px]" style={{ color: 'var(--text-3)' }}>
          Queue: {totalQueued}
        </span>
        {Object.entries(loop.queue).map(([status, count]) => (
          <span key={status} className="inline-flex items-center gap-1">
            <span className="sr-only">{status}: {count}</span>
            <span aria-hidden="true" className="inline-flex items-center gap-1">
              <StatusBadge status={status} />
              <span className="text-[10px] tabular-nums" style={{ color: 'var(--text-3)' }}>{count}</span>
            </span>
          </span>
        ))}
      </div>

      {loop.current_task ? (
        canOpenQueue ? (
          <button type="button" onClick={openQueue} style={linkStyle} className="text-[11px]">
            {loop.current_task.title} ({loop.current_task.status})
          </button>
        ) : (
          <p className="text-[11px]" style={{ color: 'var(--text-3)' }}>
            {loop.current_task.title} ({loop.current_task.status})
          </p>
        )
      ) : (
        <p className="text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.6 }}>
          No current item
        </p>
      )}

      {loop.open_questions > 0 && (
        <p className="text-[11px]" style={{ color: 'var(--amber)' }}>
          {loop.open_questions} open question{loop.open_questions === 1 ? '' : 's'}
        </p>
      )}
    </div>
  )
}

export function JobCard({ job, onRun, onPause, onResume, onArchive, isPending, onOpenTasks }: JobCardProps) {
  const [expanded, setExpanded] = useState(false)
  // Fetched only once the card is open: the collection this card renders from carries no history,
  // and a project can list many jobs the operator never expands.
  const { data: fetchedHistory, isLoading: historyLoading } = useJobHistory(job.id, expanded)
  const history = job.history ?? fetchedHistory
  const [showArchiveConfirm, setShowArchiveConfirm] = useState(false)
  // Null for any schedule that cannot be stated exactly — the line is then simply absent rather
  // than repeating the raw expression the chip above already shows.
  const cronPlain = describeCron(job.cron)

  return (
    <div
      className="interactive-card elevation-resting"
      style={{
        borderRadius: 'var(--radius)',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>
                {job.name}
              </p>
              {/* Where the job is defined is a category, not a state — `info` is amber, the
                  product's attention colour, and spent it on a fact that needs none. Neutral plus
                  the glyph carries the distinction without competing with the status badges below. */}
              {job.source === 'local' && (
                <Badge variant="secondary" className="text-[10px]"><Icon name="home" size={11} />Local</Badge>
              )}
            </div>

            <p className="text-xs mt-1" style={{ color: 'var(--text-3)' }}>
              @{job.agent}
            </p>

            {/* Cron expression */}
            <div className="flex items-center gap-2 mt-2">
              <Icon name="schedule" size={14} style={{ color: 'var(--text-3)' }} />
              <code className="text-xs px-2 py-0.5 rounded" style={{ background: 'var(--surface-3)', color: 'var(--text)', fontFamily: "'JetBrains Mono', monospace" }}>
                {job.cron}
              </code>
            </div>
            {cronPlain && <p className="job-cron-plain"><Icon name="chat" size={11} />{cronPlain}</p>}
          </div>

          {/* Expand button */}
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => setExpanded(!expanded)}
            className="shrink-0 rounded-full"
            aria-label={expanded ? 'Collapse job details' : 'Expand job details'}
          >
            <span style={{ display: 'flex', transform: expanded ? 'rotate(180deg)' : undefined, transition: 'transform var(--dur-fast) var(--ease)' }}>
              <Icon name="expand_more" size={20} />
            </span>
          </Button>
        </div>

        {/* Badges row */}
        <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
          <Badge variant={getStatusVariant(job.enabled)}>{getStatusLabel(job.enabled)}</Badge>
          <Badge variant="secondary">{job.session_mode}</Badge>
          <Badge variant="default">{job.run_count} runs</Badge>
        </div>

        {history && history.length > 0 && <TrendDots runs={history} />}

        {/* Next/Last run */}
        <div className="mt-2 space-y-1">
          {job.next_run && job.enabled && (
            <p className="text-[11px]" style={{ color: 'var(--blue)' }}>
              Next: {formatDistanceToNow(hubDate(job.next_run), { addSuffix: true })}
            </p>
          )}
          {job.last_run && (
            <p className="text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.6 }}>
              Last: {formatDistanceToNow(hubDate(job.last_run), { addSuffix: true })}
            </p>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 mt-3">
          <Button variant="primary" size="xs" onClick={() => onRun(job.id)} disabled={isPending || !job.enabled} title="Run now">
            <Icon name="play_arrow" size={16} />
            Run
          </Button>

          {job.enabled ? (
            <Button variant="outline" size="xs" onClick={() => onPause(job.id)} disabled={isPending} title="Pause">
              <Icon name="pause" size={16} />
              Pause
            </Button>
          ) : (
            <Button variant="outline" size="xs" onClick={() => onResume(job.id)} disabled={isPending} title="Resume">
              <Icon name="play_arrow" size={16} />
              Resume
            </Button>
          )}

          {showArchiveConfirm ? (
            <div className="flex items-center gap-1">
              <Button variant="destructive" size="xs" onClick={() => onArchive(job.id)} disabled={isPending}>
                Archive
              </Button>
              <Button variant="outline" size="xs" onClick={() => setShowArchiveConfirm(false)}>
                Cancel
              </Button>
            </div>
          ) : (
            /* `destructive`, not `outline` tinted red: the outline variant forces its own SVG to
               `--text-2`, so the inline `color: var(--red)` this used to carry rendered nothing at
               all and Archive was pixel-identical to Pause. It also made one action wear two
               vocabularies — the confirm step beside it is already `destructive`. */
            <Button variant="destructive" size="icon-xs" onClick={() => setShowArchiveConfirm(true)} disabled={isPending} title="Archive" aria-label="Archive">
              <Icon name="archive" size={16} />
            </Button>
          )}
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div
          className="px-4 pb-4 space-y-4"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          <div className="pt-4 space-y-4">
            {/* Message */}
            <div>
              <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>Message</p>
              <p
                className="text-xs p-3 rounded-lg"
                style={{
                  color: 'var(--text)',
                  background: 'var(--surface-3)',
                  whiteSpace: 'pre-wrap'
                }}
              >
                {job.message}
              </p>
            </div>

            {/* Run History */}
            <div>
              <p className="text-[11px] font-medium mb-2" style={{ color: 'var(--text-3)' }}>Recent Runs</p>
              <RunHistory runs={history} isLoading={historyLoading} />
            </div>

            {/* Loop — absent entirely for a plain job */}
            {job.loop && <LoopBlock job={job} onOpenTasks={onOpenTasks} />}

            {/* IDs footer */}
            <div className="pt-3 flex items-center gap-2" style={{ borderTop: '1px solid var(--border)' }}>
              <Icon name="tag" size={14} style={{ color: 'var(--text-3)' }} />
              <span className="text-[11px]" style={{ color: 'var(--text-3)' }}>
                {job.id}
              </span>
              {job.last_session_id && (
                <>
                  <span style={{ color: 'var(--border)' }}>|</span>
                  <Icon name="chat" size={14} style={{ color: 'var(--text-3)' }} />
                  <span className="text-[11px]" style={{ color: 'var(--text-3)' }}>
                    {job.last_session_id}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
