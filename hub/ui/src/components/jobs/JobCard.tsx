import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { Badge } from '@/components/common/Badge'
import { Job, JobRun } from '@/api/jobs'

interface JobCardProps {
  job: Job
  onRun: (id: string) => void
  onPause: (id: string) => void
  onResume: (id: string) => void
  onDelete: (id: string) => void
  isPending: boolean
}

function getStatusVariant(enabled: boolean): 'default' | 'secondary' | 'success' {
  return enabled ? 'success' : 'secondary'
}

function getStatusLabel(enabled: boolean): string {
  return enabled ? 'Active' : 'Paused'
}

function RunHistory({ runs }: { runs?: JobRun[] }) {
  if (!runs || runs.length === 0) {
    return <p className="m3-body-small" style={{ color: 'var(--on-sv)' }}>No runs yet</p>
  }

  return (
    <div className="space-y-2">
      {runs.slice(0, 5).map((run) => (
        <div
          key={run.id}
          className="flex items-center justify-between p-2 rounded-lg"
          style={{ background: 'var(--surface-high)' }}
        >
          <div className="flex items-center gap-2">
            <Icon
              name={run.status === 'completed' ? 'check_circle' : run.status === 'failed' ? 'error' : 'schedule'}
              size={16}
              style={{
                color: run.status === 'completed' ? 'var(--success)' : run.status === 'failed' ? 'var(--destructive)' : 'var(--on-sv)'
              }}
            />
            <span className="m3-label-small" style={{ color: 'var(--foreground)' }}>
              {run.trigger}
            </span>
          </div>
          <span className="m3-label-small" style={{ color: 'var(--on-sv)' }}>
            {formatDistanceToNow(new Date(run.fired_at), { addSuffix: true })}
          </span>
        </div>
      ))}
    </div>
  )
}

export function JobCard({ job, onRun, onPause, onResume, onDelete, isPending }: JobCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  return (
    <div className="m3-card-elevated overflow-hidden">
      {/* Header */}
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="m3-title-small" style={{ color: 'var(--foreground)' }}>
                {job.name}
              </p>
              {job.source === 'local' && (
                <Badge variant="secondary" className="text-[10px]">Local</Badge>
              )}
            </div>
            
            <p className="m3-body-small mt-1" style={{ color: 'var(--on-sv)' }}>
              @{job.agent}
            </p>

            {/* Cron expression */}
            <div className="flex items-center gap-2 mt-2">
              <Icon name="schedule" size={14} style={{ color: 'var(--on-sv)' }} />
              <code className="m3-body-small px-2 py-0.5 rounded" style={{ background: 'var(--surface-high)', color: 'var(--foreground)' }}>
                {job.cron}
              </code>
            </div>
          </div>

          {/* Expand button */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="shrink-0 p-1 rounded-full transition-colors hover:bg-black/5"
            style={{ color: 'var(--on-sv)' }}
          >
            <Icon name={expanded ? 'expand_less' : 'expand_more'} size={20} />
          </button>
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
            <p className="m3-label-small" style={{ color: 'var(--primary)' }}>
              Next: {formatDistanceToNow(new Date(job.next_run), { addSuffix: true })}
            </p>
          )}
          {job.last_run && (
            <p className="m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
              Last: {formatDistanceToNow(new Date(job.last_run), { addSuffix: true })}
            </p>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 mt-3">
          <button
            onClick={() => onRun(job.id)}
            disabled={isPending || !job.enabled}
            className="m3-btn-small m3-btn-primary flex items-center gap-1"
            title="Run now"
          >
            <Icon name="play_arrow" size={16} />
            Run
          </button>
          
          {job.enabled ? (
            <button
              onClick={() => onPause(job.id)}
              disabled={isPending}
              className="m3-btn-small m3-btn-secondary flex items-center gap-1"
              title="Pause"
            >
              <Icon name="pause" size={16} />
              Pause
            </button>
          ) : (
            <button
              onClick={() => onResume(job.id)}
              disabled={isPending}
              className="m3-btn-small m3-btn-secondary flex items-center gap-1"
              title="Resume"
            >
              <Icon name="play_arrow" size={16} />
              Resume
            </button>
          )}

          {showDeleteConfirm ? (
            <div className="flex items-center gap-1">
              <button
                onClick={() => onDelete(job.id)}
                disabled={isPending}
                className="m3-btn-small m3-btn-destructive"
              >
                Confirm
              </button>
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="m3-btn-small m3-btn-secondary"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowDeleteConfirm(true)}
              disabled={isPending}
              className="m3-btn-small m3-btn-secondary flex items-center gap-1"
              style={{ color: 'var(--destructive)' }}
              title="Delete"
            >
              <Icon name="delete" size={16} />
            </button>
          )}
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div
          className="px-4 pb-4 space-y-4"
          style={{ borderTop: '1px solid var(--outline-variant)' }}
        >
          <div className="pt-4 space-y-4">
            {/* Message */}
            <div>
              <p className="m3-label-small mb-1" style={{ color: 'var(--on-sv)' }}>Message</p>
              <p
                className="m3-body-small p-3 rounded-lg"
                style={{
                  color: 'var(--foreground)',
                  background: 'var(--surface-high)',
                  whiteSpace: 'pre-wrap'
                }}
              >
                {job.message}
              </p>
            </div>

            {/* Run History */}
            <div>
              <p className="m3-label-small mb-2" style={{ color: 'var(--on-sv)' }}>Recent Runs</p>
              <RunHistory runs={job.history} />
            </div>

            {/* IDs footer */}
            <div className="pt-3 flex items-center gap-2" style={{ borderTop: '1px solid var(--outline-variant)' }}>
              <Icon name="tag" size={14} style={{ color: 'var(--on-sv)' }} />
              <span className="m3-label-small" style={{ color: 'var(--on-sv)' }}>
                {job.id}
              </span>
              {job.last_session_id && (
                <>
                  <span style={{ color: 'var(--outline-variant)' }}>|</span>
                  <Icon name="chat" size={14} style={{ color: 'var(--on-sv)' }} />
                  <span className="m3-label-small" style={{ color: 'var(--on-sv)' }}>
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
