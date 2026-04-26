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
              name={run.status === 'completed' ? 'check_circle' : run.status === 'failed' ? 'error' : 'schedule'}
              size={16}
              style={{
                color: run.status === 'completed' ? 'var(--green)' : run.status === 'failed' ? 'var(--red)' : 'var(--text-3)'
              }}
            />
            <span className="text-[11px]" style={{ color: 'var(--text)' }}>
              {run.trigger}
            </span>
          </div>
          <span className="text-[11px]" style={{ color: 'var(--text-3)' }}>
            {formatDistanceToNow(new Date(run.fired_at), { addSuffix: true })}
          </span>
        </div>
      ))}
    </div>
  )
}

const btnSmall = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: '4px',
  height: 28,
  borderRadius: 'var(--radius-sm)',
  padding: '0 10px',
  fontSize: 12,
  fontWeight: 500,
  cursor: 'pointer',
  border: '1px solid var(--border)',
  background: 'var(--surface-2)',
  color: 'var(--text-2)',
  transition: 'opacity 0.15s',
} as React.CSSProperties

export function JobCard({ job, onRun, onPause, onResume, onDelete, isPending }: JobCardProps) {
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
          <button
            onClick={() => setExpanded(!expanded)}
            className="shrink-0 p-1 rounded-full transition-colors"
            style={{ color: 'var(--text-3)' }}
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
          <button
            onClick={() => onRun(job.id)}
            disabled={isPending || !job.enabled}
            style={{ ...btnSmall, opacity: (isPending || !job.enabled) ? 0.5 : 1 }}
            title="Run now"
          >
            <Icon name="play_arrow" size={16} />
            Run
          </button>

          {job.enabled ? (
            <button
              onClick={() => onPause(job.id)}
              disabled={isPending}
              style={{ ...btnSmall, opacity: isPending ? 0.5 : 1 }}
              title="Pause"
            >
              <Icon name="pause" size={16} />
              Pause
            </button>
          ) : (
            <button
              onClick={() => onResume(job.id)}
              disabled={isPending}
              style={{ ...btnSmall, opacity: isPending ? 0.5 : 1 }}
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
                style={{ ...btnSmall, background: 'var(--red)', color: '#fff', borderColor: 'transparent', opacity: isPending ? 0.5 : 1 }}
              >
                Confirm
              </button>
              <button
                onClick={() => setShowDeleteConfirm(false)}
                style={btnSmall}
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowDeleteConfirm(true)}
              disabled={isPending}
              style={{ ...btnSmall, color: 'var(--red)' }}
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
