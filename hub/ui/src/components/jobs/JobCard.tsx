import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { Badge } from '@/components/common/Badge'
import { Button } from '@/components/ui/button'
import { Job, JobRun } from '@/api/jobs'
import { useTasks } from '@/api/tasks'

interface JobCardProps {
  job: Job
  onRun: (id: string) => void
  onPause: (id: string) => void
  onResume: (id: string) => void
  onDelete: (id: string) => void
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

function RunHistory({ runs }: { runs?: JobRun[] }) {
  if (!runs || runs.length === 0) {
    return <p className="text-xs" style={{ color: 'var(--text-3)' }}>No runs yet</p>
  }

  return (
    <div className="space-y-2">
      {runs.slice(0, 5).map((run) => (
        <div
          key={run.id}
          className="flex items-center justify-between p-2 rounded-lg"
          style={{ background: 'var(--surface-2)' }}
        >
          <div className="flex items-center gap-2">
            <Icon
              name={
                run.status === 'completed'
                  ? 'check_circle'
                  : run.status === 'failed'
                  ? 'error'
                  : run.status === 'skipped'
                  ? 'pause'
                  : 'schedule'
              }
              size={16}
              style={{
                color:
                  run.status === 'completed'
                    ? 'var(--green)'
                    : run.status === 'failed'
                    ? 'var(--red)'
                    : run.status === 'skipped'
                    ? 'var(--amber)'
                    : 'var(--text-3)',
              }}
            />
            <span className="text-[11px]" style={{ color: 'var(--text)' }}>
              {run.trigger}
            </span>
          </div>
          <span className="text-[11px]" style={{ color: 'var(--text-3)' }}>
            {formatDistanceToNow(new Date(run.fired_at), { addSuffix: true })}
          </span>
          {(run.status === 'failed' || run.status === 'skipped') && run.error_summary && (
            <span
              className="ml-2 flex-1 min-w-0 truncate text-[11px]"
              style={{ color: run.status === 'skipped' ? 'var(--amber)' : 'var(--red)' }}
              title={run.error_summary}
            >
              {run.error_summary}
            </span>
          )}
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
          <Badge key={status} variant="secondary" className="text-[10px]">
            {status}: {count}
          </Badge>
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

export function JobCard({ job, onRun, onPause, onResume, onDelete, isPending, onOpenTasks }: JobCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
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
              {job.source === 'local' && (
                <Badge variant="secondary" className="text-[10px]">Local</Badge>
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
          </div>

          {/* Expand button */}
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => setExpanded(!expanded)}
            className="shrink-0 rounded-full"
            aria-label={expanded ? 'Collapse job details' : 'Expand job details'}
          >
            <Icon name={expanded ? 'expand_less' : 'expand_more'} size={20} />
          </Button>
        </div>

        {/* Badges row */}
        <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
          <Badge variant={getStatusVariant(job.enabled)}>{getStatusLabel(job.enabled)}</Badge>
          <Badge variant="secondary">{job.session_mode}</Badge>
          <Badge variant="default">{job.run_count} runs</Badge>
        </div>

        {/* Next/Last run */}
        <div className="mt-2 space-y-1">
          {job.next_run && job.enabled && (
            <p className="text-[11px]" style={{ color: 'var(--blue)' }}>
              Next: {formatDistanceToNow(new Date(job.next_run), { addSuffix: true })}
            </p>
          )}
          {job.last_run && (
            <p className="text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.6 }}>
              Last: {formatDistanceToNow(new Date(job.last_run), { addSuffix: true })}
            </p>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 mt-3">
          <Button variant="outline" size="xs" onClick={() => onRun(job.id)} disabled={isPending || !job.enabled} title="Run now">
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

          {showDeleteConfirm ? (
            <div className="flex items-center gap-1">
              <Button variant="destructive" size="xs" onClick={() => onDelete(job.id)} disabled={isPending}>
                Confirm
              </Button>
              <Button variant="outline" size="xs" onClick={() => setShowDeleteConfirm(false)}>
                Cancel
              </Button>
            </div>
          ) : (
            <Button variant="outline" size="xs" onClick={() => setShowDeleteConfirm(true)} disabled={isPending} title="Delete" aria-label="Delete" style={{ color: 'var(--red)' }}>
              <Icon name="delete" size={16} />
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
              <RunHistory runs={job.history} />
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
