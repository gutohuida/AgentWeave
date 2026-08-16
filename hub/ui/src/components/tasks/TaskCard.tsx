import { useMemo, useState } from 'react'
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
import { useSpecDocuments } from '@/api/spec'
import { StatusBadge } from '@/components/common/Badge'
import { RowMenu } from '@/components/layout/RowMenu'
import { TaskIntegrationNote } from '@/components/tasks/TaskIntegrationNote'
import { agentColorVars } from '@/lib/agentColors'

interface TaskCardProps {
  task: Task
  assigneeColorIndex?: number | null
  /** A requirement chip, clicked: which document it lives in (resolved from `document_id`) and
   *  which fragment to scroll to. Omitted where there is nowhere to route to. */
  onOpenRequirement?: (documentPath: string, anchor: string) => void
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

export function TaskCard({ task, assigneeColorIndex, onOpenRequirement }: TaskCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [refusal, setRefusal] = useState<string | null>(null)
  // Open while the operator is saying what a hand-set block is waiting for. The Hub requires the
  // reason, so a menu that sent the status on its own would offer a move that then fails — the one
  // thing the allowed-transitions endpoint exists to prevent.
  const [blockingReason, setBlockingReason] = useState<string | null>(null)
  const { data: allowed } = useAllowedTransitions()
  const updateTask = useUpdateTask()
  const setHandling = useSetDivergenceHandling()
  const startWork = useStartWorkOnTask()
  const { data: agents } = useAgents()
  const { data: specDocuments } = useSpecDocuments()

  const agentNames = (agents ?? []).map((a) => a.name)
  const policy = task.divergence_policy ?? 'surface'

  // Which requirement this task serves, without expanding the card (F4). One chip per
  // `requirement_ids` entry — looked up in `requirement_links` for the statement, the rejected
  // tone, and where to navigate; a bare identifier with no matching link still renders, just
  // without a title or a click target, rather than being silently dropped.
  const linkByIdentifier = useMemo(
    () => new Map((task.requirement_links ?? []).map((link) => [link.identifier, link])),
    [task.requirement_links],
  )
  const documentPathById = useMemo(
    () => new Map((specDocuments?.documents ?? []).map((doc) => [doc.id, doc.path])),
    [specDocuments],
  )

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

  // Waiting work sits in the In Progress column rather than a column of its own (R3), so the card
  // itself has to carry the difference. Purple rather than amber: amber already means "stalled",
  // and these are opposites — one is an agent that dropped the work, the other is an agent that
  // correctly refused to guess. Colouring them alike would teach the operator to read the signal
  // that means "someone did the right thing" as a problem.
  const isBlocked = task.status === 'blocked'
  const blockedAccent = 'var(--purple)'

  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: `1px solid ${isBlocked ? `color-mix(in srgb, ${blockedAccent} 45%, transparent)` : 'var(--border)'}`,
        borderRadius: 'var(--radius)',
        overflow: 'hidden',
        transition: 'border-color var(--dur-fast) var(--ease), background-color var(--dur-fast) var(--ease)',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = isBlocked ? blockedAccent : 'var(--border-hi)' }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = isBlocked
          ? `color-mix(in srgb, ${blockedAccent} 45%, transparent)`
          : 'var(--border)'
      }}
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
                    if (next === 'blocked') {
                      // Ask what it is waiting for first. An unexplained block leaves the operator
                      // working out what they are holding up — which is the position they were in
                      // when the card said in progress and nothing was happening.
                      setBlockingReason('')
                      return
                    }
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

        {/* Which requirement(s) this task serves — visible without expanding, which is the whole
            complaint F4 answers: the connection to the specification used to be invisible until
            the card was opened. Empty when `requirement_ids` is empty or absent, no placeholder,
            matching the card's existing pattern for other optional fields. */}
        {(task.requirement_ids?.length ?? 0) > 0 && (
          <div
            className="flex flex-wrap items-center gap-1 mt-1.5"
            data-testid={`task-requirement-chips-${task.id}`}
            onClick={(e) => e.stopPropagation()}
          >
            {task.requirement_ids!.map((identifier) => {
              const link = linkByIdentifier.get(identifier)
              const rejected = link?.has_rejected_evidence === true
              const documentPath = link ? documentPathById.get(link.document_id) : undefined
              const anchor = link?.anchor ? link.anchor.replace(/^#/, '') : identifier
              const clickable = Boolean(onOpenRequirement && documentPath)
              return (
                <button
                  key={identifier}
                  type="button"
                  data-testid={`task-requirement-chip-${task.id}-${identifier}`}
                  title={link?.statement ?? identifier}
                  disabled={!clickable}
                  onClick={() => {
                    if (clickable) onOpenRequirement!(documentPath!, anchor)
                  }}
                  className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                  style={{
                    background: rejected
                      ? 'color-mix(in srgb, var(--red) 12%, transparent)'
                      : 'var(--surface-3)',
                    border: `1px solid ${
                      rejected ? 'color-mix(in srgb, var(--red) 30%, transparent)' : 'var(--border)'
                    }`,
                    color: rejected ? 'var(--red)' : 'var(--text-2)',
                    cursor: clickable ? 'pointer' : 'default',
                  }}
                >
                  {identifier}
                </button>
              )
            })}
          </div>
        )}

        {/* What this task is waiting for, and who it is waiting on. Said in words rather than left
            to a badge: "blocked" alone puts the operator back where they were when the card said in
            progress and nothing was happening. */}
        {isBlocked && (
          <div
            data-testid={`task-blocked-${task.id}`}
            className="mt-2 flex items-start gap-2 rounded px-2 py-1.5"
            style={{
              background: `color-mix(in srgb, ${blockedAccent} 10%, transparent)`,
              border: `1px solid color-mix(in srgb, ${blockedAccent} 25%, transparent)`,
            }}
          >
            <Icon name="help_circle" size={12} style={{ color: blockedAccent, marginTop: 2 }} />
            <div className="min-w-0">
              <p className="text-[11px] font-medium" style={{ color: blockedAccent }}>
                Waiting on you
              </p>
              {task.blocked_reason && (
                <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-2)' }}>
                  {task.blocked_reason}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Naming what a hand-set block waits for. Required by the Hub, so the control collects it
            rather than sending a status that would be refused. */}
        {blockingReason !== null && (
          <div
            data-testid={`task-block-reason-${task.id}`}
            className="mt-2 rounded px-2 py-1.5"
            style={{ background: 'var(--surface-3)', border: '1px solid var(--border)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <label className="text-[11px]" style={{ color: 'var(--text-2)' }}>
              What is this waiting for?
            </label>
            <input
              autoFocus
              value={blockingReason}
              onChange={(e) => setBlockingReason(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') setBlockingReason(null)
              }}
              placeholder="e.g. the staging API key"
              className="mt-1 w-full rounded px-2 py-1 text-xs"
              style={{
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                color: 'var(--text)',
              }}
            />
            <div className="mt-1.5 flex items-center gap-2">
              <button
                data-testid={`task-block-confirm-${task.id}`}
                disabled={!blockingReason.trim()}
                onClick={() => {
                  const reason = blockingReason.trim()
                  if (!reason) return
                  setRefusal(null)
                  updateTask.mutate(
                    { id: task.id, status: 'blocked', blocked_reason: reason },
                    {
                      onSuccess: () => setBlockingReason(null),
                      onError: (error: unknown) =>
                        setRefusal(readableApiError(error, 'The Hub refused this change.')),
                    },
                  )
                }}
                className="rounded px-2 py-0.5 text-[11px]"
                style={{
                  background: blockingReason.trim() ? blockedAccent : 'var(--surface-3)',
                  color: blockingReason.trim() ? 'var(--bg)' : 'var(--text-3)',
                  border: '1px solid var(--border)',
                }}
              >
                Mark waiting
              </button>
              <button
                onClick={() => setBlockingReason(null)}
                className="text-[11px]"
                style={{ color: 'var(--text-3)' }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Badges row */}
        <div className="flex flex-wrap items-center gap-1.5 mt-2">
          <StatusBadge status={task.status} />
          {/* A run ended holding this and nothing has moved it since. Amber rather than red: the
              work is not lost and nothing is broken — it is the operator's attention this needs.
              Clears by itself the moment anyone moves the task.

              "Stalled", not "Dropped": the operator was shown the first label on 2026-08-10 and
              asked *"what is a dropped task?"*. A word only its author understands is not a
              signal. The title says the whole thing, because the badge cannot — what the board
              claims, and that nothing is actually running. */}
          {task.has_open_divergence && (
            <span
              data-testid={`task-divergence-${task.id}`}
              title="A run worked on this and ended without changing its status. Nothing is running now."
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
              Stalled
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

        {/* Approval merges, so an approved card owes an answer about where the work went. */}
        <TaskIntegrationNote taskId={task.id} status={task.status} />

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

            {/* What this task is checked against. `requirements` below is the caller's prose and
                can say things no identifier can; these are the links the approval gate enforces,
                and the board used to show only the prose — so a card could not tell you whether it
                was tied to the specification at all. */}
            {task.requirement_links && task.requirement_links.length > 0 && (
              <div className="mb-3" data-testid={`task-serves-${task.id}`}>
                <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>Serves</p>
                <ul className="text-xs space-y-1" style={{ color: 'var(--text)' }}>
                  {task.requirement_links.map((link) => (
                    <li key={link.requirement_id}>
                      <code className="text-[11px]">{link.identifier}</code>
                      {link.statement ? ` — ${link.statement}` : null}
                      {link.state !== 'active' && (
                        <span className="ml-1 text-[10px]" style={{ color: 'var(--text-3)' }}>
                          ({link.state})
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* References that named no requirement this project has. Shown rather than dropped:
                a task that quietly lost a reference is the failure the links exist to prevent. */}
            {task.unresolved_requirements && task.unresolved_requirements.length > 0 && (
              <div className="mb-3">
                <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>
                  Unresolved
                </p>
                <ul className="text-xs space-y-1" style={{ color: 'var(--text-3)' }}>
                  {task.unresolved_requirements.map((item) => (
                    <li key={item.reference}>
                      {item.reference} — {item.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Requirements, as the caller wrote them */}
            {task.requirements && task.requirements.length > 0 && (
              <div className="mb-3">
                <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>Requirements (as written)</p>
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
