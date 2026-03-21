import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { Task } from '@/api/tasks'
import { Badge, statusVariant, priorityVariant } from '@/components/common/Badge'

interface TaskCardProps {
  task: Task
}

export function TaskCard({ task }: TaskCardProps) {
  const [expanded, setExpanded] = useState(false)

  const hasDetails = task.description || 
    (task.requirements && task.requirements.length > 0) ||
    (task.acceptance_criteria && task.acceptance_criteria.length > 0) ||
    (task.deliverables && task.deliverables.length > 0) ||
    task.notes

  return (
    <div className="m3-card-elevated overflow-hidden">
      {/* Header - always visible */}
      <div 
        className="p-4 cursor-pointer"
        onClick={() => hasDetails && setExpanded(!expanded)}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="m3-title-small" style={{ color: 'var(--foreground)' }}>
              {task.title}
            </p>
            
            {/* Compact description */}
            {task.description && (
              <p 
                className={`m3-body-small mt-1 ${expanded ? '' : 'line-clamp-2'}`} 
                style={{ color: 'var(--on-sv)' }}
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
              className="shrink-0 p-1 rounded-full transition-colors hover:bg-black/5"
              style={{ color: 'var(--on-sv)' }}
            >
              <Icon name={expanded ? 'expand_less' : 'expand_more'} size={20} />
            </button>
          )}
        </div>

        {/* Badges row */}
        <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
          <Badge variant={statusVariant(task.status)}>{task.status}</Badge>
          <Badge variant={priorityVariant(task.priority)}>{task.priority}</Badge>
          {task.assignee && (
            <Badge variant="secondary">@{task.assignee}</Badge>
          )}
          {task.assigner && task.assigner !== task.assignee && (
            <Badge variant="secondary">from: {task.assigner}</Badge>
          )}
        </div>

        {/* Timestamp */}
        <p className="m3-label-small mt-2" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
          {formatDistanceToNow(new Date(task.updated), { addSuffix: true })}
        </p>

        {/* Expand hint */}
        {hasDetails && !expanded && (
          <p className="m3-label-small mt-2" style={{ color: 'var(--primary)' }}>
            Click to see details…
          </p>
        )}
      </div>

      {/* Expanded details */}
      {expanded && hasDetails && (
        <div 
          className="px-4 pb-4 space-y-4"
          style={{ borderTop: '1px solid var(--outline-variant)' }}
        >
          <div className="pt-4">
            {/* Full description */}
            {task.description && (
              <div className="mb-4">
                <p className="m3-label-small mb-1" style={{ color: 'var(--on-sv)' }}>Description</p>
                <p 
                  className="m3-body-small p-3 rounded-lg" 
                  style={{ 
                    color: 'var(--foreground)', 
                    background: 'var(--surface-high)',
                    whiteSpace: 'pre-wrap'
                  }}
                >
                  {task.description}
                </p>
              </div>
            )}

            {/* Requirements */}
            {task.requirements && task.requirements.length > 0 && (
              <div className="mb-4">
                <p className="m3-label-small mb-1" style={{ color: 'var(--on-sv)' }}>Requirements</p>
                <ul className="list-disc list-inside m3-body-small space-y-1" style={{ color: 'var(--foreground)' }}>
                  {task.requirements.map((req, i) => (
                    <li key={i}>{req}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Acceptance Criteria */}
            {task.acceptance_criteria && task.acceptance_criteria.length > 0 && (
              <div className="mb-4">
                <p className="m3-label-small mb-1" style={{ color: 'var(--on-sv)' }}>Acceptance Criteria</p>
                <ul className="list-disc list-inside m3-body-small space-y-1" style={{ color: 'var(--foreground)' }}>
                  {task.acceptance_criteria.map((criterion, i) => (
                    <li key={i}>{criterion}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Deliverables */}
            {task.deliverables && task.deliverables.length > 0 && (
              <div className="mb-4">
                <p className="m3-label-small mb-1" style={{ color: 'var(--on-sv)' }}>Deliverables</p>
                <ul className="list-disc list-inside m3-body-small space-y-1" style={{ color: 'var(--foreground)' }}>
                  {task.deliverables.map((deliverable, i) => (
                    <li key={i}>{deliverable}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Notes */}
            {task.notes && (
              <div>
                <p className="m3-label-small mb-1" style={{ color: 'var(--on-sv)' }}>Notes</p>
                <p 
                  className="m3-body-small p-3 rounded-lg" 
                  style={{ 
                    color: 'var(--foreground)', 
                    background: 'var(--surface-high)',
                    whiteSpace: 'pre-wrap'
                  }}
                >
                  {task.notes}
                </p>
              </div>
            )}

            {/* Task ID footer */}
            <div className="mt-4 pt-3 flex items-center gap-2" style={{ borderTop: '1px solid var(--outline-variant)' }}>
              <Icon name="tag" size={14} style={{ color: 'var(--on-sv)' }} />
              <span className="m3-label-small" style={{ color: 'var(--on-sv)' }}>
                {task.id}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
