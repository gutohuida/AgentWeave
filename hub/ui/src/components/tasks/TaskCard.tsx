import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { Task } from '@/api/tasks'
import { StatusBadge } from '@/components/common/Badge'

interface TaskCardProps {
  task: Task
}

const AGENT_STATUS_STYLES: Record<string, { color: string; bg: string; border: string }> = {
  running: {
    color: 'var(--green)',
    bg: 'rgba(34,197,94,0.1)',
    border: 'rgba(34,197,94,0.25)',
  },
  active: {
    color: 'var(--blue)',
    bg: 'rgba(59,130,246,0.1)',
    border: 'rgba(59,130,246,0.25)',
  },
  waiting: {
    color: 'var(--amber)',
    bg: 'rgba(245,158,11,0.1)',
    border: 'rgba(245,158,11,0.25)',
  },
  idle: {
    color: 'var(--text-3)',
    bg: 'var(--surface-3)',
    border: 'var(--border)',
  },
}

function agentStatusTitle(task: Task): string {
  const status = task.assignee_status ?? 'idle'
  const details = [`worker: ${status}`]
  if (task.assignee_status_msg) details.push(task.assignee_status_msg)
  if (task.assignee_last_seen) {
    details.push(
      `last seen ${formatDistanceToNow(new Date(task.assignee_last_seen), { addSuffix: true })}`,
    )
  }
  return details.join(' · ')
}

export function TaskCard({ task }: TaskCardProps) {
  const [expanded, setExpanded] = useState(false)
  const assigneeStatus = task.assignee_status ?? (task.assignee ? 'idle' : null)
  const assigneeStatusStyle = assigneeStatus
    ? AGENT_STATUS_STYLES[assigneeStatus] ?? AGENT_STATUS_STYLES.idle
    : null

  const hasDetails = task.description ||
    (task.requirements && task.requirements.length > 0) ||
    (task.acceptance_criteria && task.acceptance_criteria.length > 0) ||
    (task.deliverables && task.deliverables.length > 0) ||
    task.notes

  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        overflow: 'hidden',
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--border-hi)' }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}
    >
      {/* Header - always visible */}
      <div
        className="p-3 cursor-pointer"
        onClick={() => hasDetails && setExpanded(!expanded)}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium" style={{ color: 'var(--text)' }}>
              {task.title}
            </p>

            {/* Compact description */}
            {task.description && (
              <p
                className={`text-xs mt-1 ${expanded ? '' : 'line-clamp-2'}`}
                style={{ color: 'var(--text-3)' }}
              >
                {task.description}
              </p>
            )}
          </div>

          {/* Expand/collapse button */}
          {hasDetails && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                setExpanded(!expanded)
              }}
              className="shrink-0 p-1 rounded transition-colors"
              style={{ color: 'var(--text-3)' }}
            >
              <Icon name={expanded ? 'expand_less' : 'expand_more'} size={18} />
            </button>
          )}
        </div>

        {/* Badges row */}
        <div className="flex flex-wrap items-center gap-1.5 mt-2">
          <StatusBadge status={task.status} />
          <StatusBadge status={task.priority} />
          {task.assignee && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                background: 'var(--surface-3)',
                border: '1px solid var(--border)',
                borderRadius: 9999,
                padding: '1px 6px',
                fontSize: 10,
                fontWeight: 500,
                color: 'var(--text-2)',
              }}
            >
              @{task.assignee}
            </span>
          )}
          {assigneeStatus && assigneeStatusStyle && (
            <span
              title={agentStatusTitle(task)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                background: assigneeStatusStyle.bg,
                border: `1px solid ${assigneeStatusStyle.border}`,
                borderRadius: 9999,
                padding: '1px 6px',
                fontSize: 10,
                fontWeight: 500,
                color: assigneeStatusStyle.color,
                textTransform: 'capitalize',
              }}
            >
              <span
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: 9999,
                  background: assigneeStatusStyle.color,
                }}
              />
              {assigneeStatus.replace(/_/g, ' ')}
            </span>
          )}
          {task.assigner && task.assigner !== task.assignee && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                background: 'var(--surface-3)',
                border: '1px solid var(--border)',
                borderRadius: 9999,
                padding: '1px 6px',
                fontSize: 10,
                fontWeight: 500,
                color: 'var(--text-2)',
              }}
            >
              from: {task.assigner}
            </span>
          )}
        </div>

        {/* Timestamp */}
        <p className="text-[11px] mt-2" style={{ color: 'var(--text-3)' }}>
          {formatDistanceToNow(new Date(task.updated), { addSuffix: true })}
        </p>

        {/* Expand hint */}
        {hasDetails && !expanded && (
          <p className="text-[11px] mt-1.5" style={{ color: 'var(--blue)' }}>
            Click to see details…
          </p>
        )}
      </div>

      {/* Expanded details */}
      {expanded && hasDetails && (
        <div
          className="px-3 pb-3 space-y-3"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          <div className="pt-3">
            {/* Full description */}
            {task.description && (
              <div className="mb-3">
                <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>Description</p>
                <p
                  className="text-xs p-2.5 rounded"
                  style={{
                    color: 'var(--text)',
                    background: 'var(--surface-3)',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {task.description}
                </p>
              </div>
            )}

            {/* Requirements */}
            {task.requirements && task.requirements.length > 0 && (
              <div className="mb-3">
                <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>Requirements</p>
                <ul className="list-disc list-inside text-xs space-y-1" style={{ color: 'var(--text)' }}>
                  {task.requirements.map((req, i) => (
                    <li key={i}>{req}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Acceptance Criteria */}
            {task.acceptance_criteria && task.acceptance_criteria.length > 0 && (
              <div className="mb-3">
                <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>Acceptance Criteria</p>
                <ul className="list-disc list-inside text-xs space-y-1" style={{ color: 'var(--text)' }}>
                  {task.acceptance_criteria.map((criterion, i) => (
                    <li key={i}>{criterion}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Deliverables */}
            {task.deliverables && task.deliverables.length > 0 && (
              <div className="mb-3">
                <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>Deliverables</p>
                <ul className="list-disc list-inside text-xs space-y-1" style={{ color: 'var(--text)' }}>
                  {task.deliverables.map((deliverable, i) => (
                    <li key={i}>{deliverable}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Notes */}
            {task.notes && (
              <div>
                <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>Notes</p>
                <p
                  className="text-xs p-2.5 rounded"
                  style={{
                    color: 'var(--text)',
                    background: 'var(--surface-3)',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {task.notes}
                </p>
              </div>
            )}

            {/* Task ID footer */}
            <div className="mt-3 pt-2 flex items-center gap-2" style={{ borderTop: '1px solid var(--border)' }}>
              <Icon name="tag" size={12} style={{ color: 'var(--text-3)' }} />
              <span className="text-[11px]" style={{ color: 'var(--text-3)' }}>
                {task.id}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
