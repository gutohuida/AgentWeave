import { useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { readableApiError } from '@/api/client'
import {
  DIVERGENCE_POLICY_LABELS,
  DivergencePolicy,
  Task,
  useAllowedTransitions,
  useSetDivergenceHandling,
  useUpdateTask,
} from '@/api/tasks'
import { useAgents } from '@/api/agents'
import { useSpecDocuments } from '@/api/spec'
import { RowMenu } from '@/components/layout/RowMenu'
import { useDialogFocus } from '@/hooks/useDialogFocus'

function statusLabel(status: string): string {
  return status.replace(/_/g, ' ')
}

interface TaskDetailDrawerProps {
  task: Task | null
  onClose: () => void
  /** Threaded straight to the requirement chips (F4) — clicking one from inside the drawer
   *  navigates exactly the way clicking one on the collapsed card does. */
  onOpenRequirement?: (documentPath: string, anchor: string) => void
}

/**
 * The task, opened — everything the card's old inline expansion held (`design.md` D8), unchanged
 * in behaviour, relocated to a right-side panel with room to read it.
 *
 * A right-side drawer, not a centred modal: a modal covering the board loses the column context
 * ("which status is this in") a Jira-style ticket keeps visible at the edge. It closes the same
 * way `AgentCreateDialog.tsx`'s modal backdrop already does in this codebase — a click outside the
 * panel — so no new interaction convention is introduced, only a different geometry: there is no
 * dimming backdrop element here, because the board behind stays the thing being clicked, not a
 * scrim standing in for it.
 */
export function TaskDetailDrawer({ task, onClose, onOpenRequirement }: TaskDetailDrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const open = task !== null
  const [refusal, setRefusal] = useState<string | null>(null)
  // Open while the operator is saying what a hand-set block is waiting for. The Hub requires the
  // reason, so a menu that sent the status on its own would offer a move that then fails — the one
  // thing the allowed-transitions endpoint exists to prevent.
  const [blockingReason, setBlockingReason] = useState<string | null>(null)

  const { data: allowed } = useAllowedTransitions()
  const updateTask = useUpdateTask()
  const setHandling = useSetDivergenceHandling()
  const { data: agents } = useAgents()
  const { data: specDocuments } = useSpecDocuments()

  const agentNames = (agents ?? []).map((a) => a.name)
  // Resolves every link in `requirement_links` — not just the ones `requirement_ids` names — so
  // "Serves" below can navigate the same way the card's F4 chips do, without narrowing to the
  // card's subset (see the note on the "Serves" block: this list has always shown every link).
  const documentPathById = useMemo(
    () => new Map((specDocuments?.documents ?? []).map((doc) => [doc.id, doc.path])),
    [specDocuments],
  )

  useEffect(() => {
    setRefusal(null)
    setBlockingReason(null)
  }, [task?.id])

  useDialogFocus(open, panelRef, onClose)

  // Click-outside-closes, on the board itself rather than a modal backdrop (`design.md` D8) — no
  // full-screen scrim element exists to attach this to, so it is a document-level listener that
  // ignores clicks landing inside the panel. It also has to ignore clicks inside the status menu's
  // own dropdown (`RowMenu`, Radix `DropdownMenu`): Radix portals that content to a sibling of
  // `document.body`, outside `panelRef`, so without this a click on "Move to blocked" would read
  // as a click on the board and close the drawer out from under the menu it just opened.
  useEffect(() => {
    if (!open) return
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node
      const inPanel = panelRef.current?.contains(target) ?? false
      const inPortaledPopper = target instanceof Element && target.closest('[data-radix-popper-content-wrapper]') !== null
      if (!inPanel && !inPortaledPopper) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handlePointerDown)
    return () => document.removeEventListener('mousedown', handlePointerDown)
  }, [open, onClose])

  if (!task) return null

  const moves = allowed?.transitions?.[task.status] ?? []
  const policy = task.divergence_policy ?? 'surface'
  const blockedAccent = 'var(--purple)'

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={`task-drawer-title-${task.id}`}
      data-testid={`task-drawer-${task.id}`}
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        // Full height (`design.md` D8) — the drawer never itself has a shorter fixed height that
        // would compete with the body's own scroll below.
        bottom: 0,
        width: 'min(480px, 100vw)',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--surface)',
        borderLeft: '1px solid var(--border)',
        boxShadow: '-8px 0 24px rgba(0,0,0,0.18)',
        zIndex: 50,
      }}
    >
      <div
        className="shrink-0 flex items-start justify-between gap-3 p-4"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="min-w-0">
          <h2 id={`task-drawer-title-${task.id}`} className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
            {task.title}
          </h2>
          <p className="text-[11px] mt-1" style={{ color: 'var(--text-3)' }}>
            {task.id}
          </p>
        </div>
        <button
          data-testid={`task-drawer-close-${task.id}`}
          aria-label="Close"
          onClick={onClose}
          className="shrink-0 p-1 rounded"
          style={{ color: 'var(--text-3)' }}
        >
          <Icon name="close" size={18} />
        </button>
      </div>

      {/* The scrolling region. Deliberately the only element in this panel with `overflow: auto` —
          everything above and below it is `shrink-0`, so a long description or many chips scrolls
          the content rather than being cut off by a fixed-height ancestor (`design.md` D8's
          no-clipping requirement; `tasks.md` 6.5). */}
      <div
        data-testid={`task-drawer-body-${task.id}`}
        className="flex-1 p-4 space-y-3"
        style={{ overflowY: 'auto', minHeight: 0 }}
      >
        {/* The operator's status control. Offers only the moves the map declares legal for an
            operator from this status, so an illegal one is never presented and then refused. */}
        {moves.length > 0 && (
          <div>
            <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>Status</p>
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
          </div>
        )}

        {/* Naming what a hand-set block waits for. Required by the Hub, so the control collects it
            rather than sending a status that would be refused. */}
        {blockingReason !== null && (
          <div
            data-testid={`task-block-reason-${task.id}`}
            className="rounded px-2 py-1.5"
            style={{ background: 'var(--surface-3)', border: '1px solid var(--border)' }}
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

        {/* A refused move. The Hub's detail names the current status and what is reachable from
            it, so it is shown as written rather than replaced with a generic failure — a board
            that offered a move which has since become illegal should say which, not just "error". */}
        {refusal && (
          <p
            data-testid={`task-status-refusal-${task.id}`}
            className="text-[11px] p-2 rounded"
            style={{
              color: 'var(--amber)',
              background: 'color-mix(in srgb, var(--amber) 10%, transparent)',
              border: '1px solid color-mix(in srgb, var(--amber) 25%, transparent)',
            }}
          >
            {refusal}
          </p>
        )}

        {/* Full description */}
        {task.description && (
          <div>
            <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>Description</p>
            <p
              className="text-xs p-2.5 rounded"
              style={{ color: 'var(--text)', background: 'var(--surface-3)', whiteSpace: 'pre-wrap' }}
            >
              {task.description}
            </p>
          </div>
        )}

        {/* What this task is checked against. `requirements` below is the caller's prose and
            can say things no identifier can; these are the links the approval gate enforces —
            unchanged in behaviour from the old inline expansion, per `design.md` D8, except for
            one addition (6.3): where a link's evidence was rejected, the reason
            (`latest_rejection_reason`) is shown too — the one place it has ever reached a screen.
            Driven by `requirement_links` directly, not the card's `requirement_ids`-scoped chips
            (`useRequirementChips`) — a link can exist here without being in `requirement_ids`, and
            this list has always shown every one, same as before this change. */}
        {task.requirement_links && task.requirement_links.length > 0 && (
          <div data-testid={`task-serves-${task.id}`}>
            <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>Serves</p>
            <ul className="text-xs space-y-1" style={{ color: 'var(--text)' }}>
              {task.requirement_links.map((link) => {
                const documentPath = documentPathById.get(link.document_id)
                const anchor = link.anchor ? link.anchor.replace(/^#/, '') : link.identifier
                const clickable = Boolean(onOpenRequirement && documentPath)
                return (
                  <li key={link.requirement_id}>
                    <button
                      type="button"
                      disabled={!clickable}
                      onClick={() => {
                        if (clickable) onOpenRequirement!(documentPath!, anchor)
                      }}
                      style={{
                        color: 'inherit',
                        cursor: clickable ? 'pointer' : 'default',
                        textAlign: 'left',
                      }}
                    >
                      <code className="text-[11px]">{link.identifier}</code>
                      {link.statement ? ` — ${link.statement}` : null}
                      {link.state !== 'active' && (
                        <span className="ml-1 text-[10px]" style={{ color: 'var(--text-3)' }}>
                          ({link.state})
                        </span>
                      )}
                    </button>
                    {link.has_rejected_evidence && link.latest_rejection_reason && (
                      <p className="text-[11px] mt-0.5" style={{ color: 'var(--red)' }}>
                        Rejected: {link.latest_rejection_reason}
                      </p>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        )}

        {/* References that named no requirement this project has. Shown rather than dropped:
            a task that quietly lost a reference is the failure the links exist to prevent. */}
        {task.unresolved_requirements && task.unresolved_requirements.length > 0 && (
          <div>
            <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--text-3)' }}>Unresolved</p>
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
          <div>
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
          <div>
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
          <div>
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
              style={{ color: 'var(--text)', background: 'var(--surface-3)', whiteSpace: 'pre-wrap' }}
            >
              {task.notes}
            </p>
          </div>
        )}

        {/* How this task's neglect is answered. Here, on the task, rather than in a settings
            screen, because it is a routing decision about this work — the cheap agent does it,
            the expensive one picks up what the cheap one dropped — and a policy that can only
            be set through an API is a policy nobody sets. */}
        <div>
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
                  onClick={() => {
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
                      active ? 'color-mix(in srgb, var(--blue) 35%, transparent)' : 'var(--border)'
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
                style={{ background: 'var(--surface-3)', border: '1px solid var(--border)', color: 'var(--text)' }}
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
      </div>
    </div>
  )
}
