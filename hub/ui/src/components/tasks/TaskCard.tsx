import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { readableApiError } from '@/api/client'
import {
  DIVERGENCE_POLICY_LABELS,
  DivergencePolicy,
  Task,
  useAllowedTransitions,
  useSetDivergenceHandling,
  useStartWorkOnTask,
  useUpdateTask,
} from '@/api/tasks'
import { useAgents } from '@/api/agents'
import { StatusBadge } from '@/components/common/Badge'
import { RowMenu } from '@/components/layout/RowMenu'
import { agentColorVars } from '@/lib/agentColors'

interface TaskCardProps {
  task: Task
  assigneeColorIndex?: number | null
}

function statusLabel(status: string): string {
  return status.replace(/_/g, ' ')
}

const AGENT_STATUS_STYLES: Record<string, { color: string; bg: string; border: string }> = {
  running: {
    color: 'var(--green)',
    bg: 'color-mix(in srgb, var(--green) 10%, transparent)',
    border: 'color-mix(in srgb, var(--green) 25%, transparent)',
  },
  active: {
    color: 'var(--blue)',
    bg: 'color-mix(in srgb, var(--blue) 10%, transparent)',
    border: 'color-mix(in srgb, var(--blue) 25%, transparent)',
  },
  waiting: {
    color: 'var(--amber)',
    bg: 'color-mix(in srgb, var(--amber) 10%, transparent)',
    border: 'color-mix(in srgb, var(--amber) 25%, transparent)',
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

export function TaskCard({ task, assigneeColorIndex }: TaskCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [refusal, setRefusal] = useState<string | null>(null)
  const { data: allowed } = useAllowedTransitions()
  const updateTask = useUpdateTask()
  const setHandling = useSetDivergenceHandling()
  const startWork = useStartWorkOnTask()
  const { data: agents } = useAgents()

  const agentNames = (agents ?? []).map((a) => a.name)
  const policy = task.divergence_policy ?? 'surface'

  // Only what the operator may do from *this* status, read from the Hub's own declaration. The
  // board can still be stale — a move legal when the card rendered may not be by the time it is
  // clicked — which is why the refusal below is shown rather than swallowed.
  const moves = allowed?.transitions?.[task.status] ?? []

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
        transition: 'border-color var(--dur-fast) var(--ease), background-color var(--dur-fast) var(--ease)',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--border-hi)' }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}
    >
      {/* Header - always visible */}
      <div
        className="p-3 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
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

          <div className="flex shrink-0 items-center gap-1" onClick={(e) => e.stopPropagation()}>
            {/* The operator's status control. Offers only the moves the map declares legal for an
                operator from this status, so an illegal one is never presented and then refused. */}
            {moves.length > 0 && (
              <RowMenu
                label={`Change status of ${task.title}`}
                testId={`task-status-menu-${task.id}`}
                persistent
                items={moves.map((next) => ({
                  id: next,
                  label: `Move to ${statusLabel(next)}`,
                  onSelect: () => {
                    setRefusal(null)
                    updateTask.mutate(
                      { id: task.id, status: next },
                      {
                        // `ApiError.message` is the raw response body, so a 409 would render as
                        // JSON. `readableApiError` pulls out the sentence the Hub wrote for a
                        // human — which is the whole reason the refusal names the reachable set.
                        onError: (error: unknown) =>
                          setRefusal(readableApiError(error, 'The Hub refused this change.')),
                      },
                    )
                  },
                }))}
              />
            )}

            {/* Start work on this task. The Hub binds the run and moves the task itself, so this
                is the one path where beginning work and the board agreeing about it are the same
                act rather than two things an agent has to remember to do. */}
            {agentNames.length > 0 && (
              <RowMenu
                label={`Start work on ${task.title}`}
                testId={`task-start-work-${task.id}`}
                icon="play_arrow"
                persistent
                items={agentNames.map((name) => ({
                  id: name,
                  label: `Start ${name} on this`,
                  onSelect: () => {
                    setRefusal(null)
                    startWork.mutate(
                      { taskId: task.id, agent: name, title: task.title },
                      {
                        onError: (error: unknown) =>
                          setRefusal(readableApiError(error, 'The Hub could not start that run.')),
                      },
                    )
                  },
                }))}
              />
            )}

            {/* Expand/collapse button */}
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
          </div>
        </div>

        {/* Badges row */}
        <div className="flex flex-wrap items-center gap-1.5 mt-2">
          <StatusBadge status={task.status} />
          {/* A run ended holding this and nothing has moved it since. Amber rather than red: the
              work is not lost and nothing is broken — it is the operator's attention this needs.
              Clears by itself the moment anyone moves the task. */}
          {task.has_open_divergence && (
            <span
              data-testid={`task-divergence-${task.id}`}
              title="A run ended without moving this task."
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                background: 'color-mix(in srgb, var(--amber) 12%, transparent)',
                border: '1px solid color-mix(in srgb, var(--amber) 30%, transparent)',
                borderRadius: 9999,
                padding: '1px 6px',
                fontSize: 10,
                fontWeight: 500,
                color: 'var(--amber)',
              }}
            >
              <Icon name="alert_triangle" size={10} />
              Dropped
            </span>
          )}
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
              <span
                data-testid={`task-assignee-color-${task.assignee}`}
                className="mr-1 h-1.5 w-1.5 rounded-full"
                style={{ background: agentColorVars(assigneeColorIndex).accent }}
              />
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

        {/* A refused move. The Hub's detail names the current status and what is reachable from
            it, so it is shown as written rather than replaced with a generic failure — a board
            that offered a move which has since become illegal should say which, not just "error". */}
        {refusal && (
          <p
            data-testid={`task-status-refusal-${task.id}`}
            className="text-[11px] mt-2 p-2 rounded"
            style={{
              color: 'var(--amber)',
              background: 'color-mix(in srgb, var(--amber) 10%, transparent)',
              border: '1px solid color-mix(in srgb, var(--amber) 25%, transparent)',
            }}
          >
            {refusal}
          </p>
        )}

        {/* Expand hint */}
        {!expanded && (
          <p className="text-[11px] mt-1.5" style={{ color: 'var(--blue)' }}>
            {hasDetails ? 'Click to see details…' : 'Click for options…'}
          </p>
        )}
      </div>

      {/* Expanded details */}
      {expanded && (
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

            {/* How this task's neglect is answered. Here, on the task, rather than in a settings
                screen, because it is a routing decision about this work — the cheap agent does it,
                the expensive one picks up what the cheap one dropped — and a policy that can only
                be set through an API is a policy nobody sets. */}
            <div className="mb-3">
              <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>
                If a run ends without moving this
              </p>
              <div className="flex flex-wrap items-center gap-1.5">
                {(Object.keys(DIVERGENCE_POLICY_LABELS) as DivergencePolicy[]).map((option) => {
                  const active = policy === option
                  return (
                    <button
                      key={option}
                      data-testid={`task-policy-${option}-${task.id}`}
                      aria-pressed={active}
                      onClick={(e) => {
                        e.stopPropagation()
                        if (active) return
                        setRefusal(null)
                        setHandling.mutate(
                          { id: task.id, divergence_policy: option },
                          {
                            onError: (error: unknown) =>
                              setRefusal(readableApiError(error, 'The Hub refused that setting.')),
                          },
                        )
                      }}
                      className="text-[11px] px-2 py-1 rounded transition-colors"
                      style={{
                        background: active
                          ? 'color-mix(in srgb, var(--blue) 14%, transparent)'
                          : 'var(--surface-3)',
                        border: `1px solid ${
                          active
                            ? 'color-mix(in srgb, var(--blue) 35%, transparent)'
                            : 'var(--border)'
                        }`,
                        color: active ? 'var(--blue)' : 'var(--text-2)',
                        fontWeight: active ? 600 : 500,
                      }}
                    >
                      {DIVERGENCE_POLICY_LABELS[option]}
                    </button>
                  )
                })}
              </div>

              {/* Only where it means something. Offering an escalation target under "Tell me"
                  would suggest it does something, and it does not. */}
              {policy === 'escalate' && (
                <div className="mt-2">
                  <label
                    className="text-[11px] block mb-1"
                    style={{ color: 'var(--text-3)' }}
                    htmlFor={`escalation-agent-${task.id}`}
                  >
                    Hand it to
                  </label>
                  <select
                    id={`escalation-agent-${task.id}`}
                    data-testid={`task-escalation-agent-${task.id}`}
                    value={task.escalation_agent ?? ''}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => {
                      setRefusal(null)
                      setHandling.mutate(
                        { id: task.id, escalation_agent: e.target.value || null },
                        {
                          onError: (error: unknown) =>
                            setRefusal(readableApiError(error, 'The Hub refused that setting.')),
                        },
                      )
                    }}
                    className="text-xs w-full p-1.5 rounded"
                    style={{
                      background: 'var(--surface-3)',
                      border: '1px solid var(--border)',
                      color: 'var(--text)',
                    }}
                  >
                    <option value="">Nobody — just tell me</option>
                    {agentNames.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                  {!task.escalation_agent && (
                    <p className="text-[11px] mt-1" style={{ color: 'var(--text-3)' }}>
                      With nobody named, this behaves the same as “Tell me”.
                    </p>
                  )}
                </div>
              )}
            </div>

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
