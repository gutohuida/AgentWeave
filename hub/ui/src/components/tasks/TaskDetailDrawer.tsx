import { useEffect, useMemo, useRef, useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { PriorityBadge, StatusBadge } from '@/components/common/Badge'
import { readableApiError } from '@/api/client'
import {
  DIVERGENCE_POLICY_LABELS,
  DivergencePolicy,
  Task,
  useAllowedTransitions,
  useSetDivergenceHandling,
  useTaskIntegrationPreview,
  useUpdateTask,
} from '@/api/tasks'
import { useAgents } from '@/api/agents'
import { useSpecDocuments } from '@/api/spec'
import { RowMenu } from '@/components/layout/RowMenu'
import { useDialogFocus } from '@/hooks/useDialogFocus'
import { hubDate } from '@/lib/hubTime'

/**
 * What approving this task is about to write, said beside the control that does it (F9).
 *
 * An inline note, deliberately not a dialog: approval is the correct, designed behaviour and a
 * confirmation step would teach the operator to dismiss it. What was missing is only the sentence —
 * approving cherry-picks the accepted evidence's commit into the project's main branch, and the
 * working tree on disk changes. That is the single most consequential act in the product and it
 * used to happen unannounced.
 *
 * Rendered only where approval is actually reachable from here, so a pending card carries no
 * warning about a merge that is several transitions away.
 */
function ApprovalWritesNote({ taskId, canApprove }: { taskId: string; canApprove: boolean }) {
  const { data } = useTaskIntegrationPreview(taskId, canApprove)
  if (!canApprove || !data) return null

  // The skipped case is not a warning — nothing will be written — but it is still the answer to
  // "where did my approved work go", and saying it *before* approval is cheaper than saying it
  // after. Neutral weight, since no repository changes.
  if (!data.will_merge) {
    return (
      <p
        data-testid={`task-approval-writes-${taskId}`}
        className="text-[11px] mt-2 px-2 py-1.5 rounded"
        style={{
          color: 'var(--text-2)',
          background: 'var(--surface-3)',
          border: '1px solid var(--border)',
        }}
      >
        <Icon name="info" size={12} /> Approving will not merge anything: {data.reason}.
      </p>
    )
  }

  return (
    <p
      data-testid={`task-approval-writes-${taskId}`}
      className="text-[11px] mt-2 px-2 py-1.5 rounded"
      style={{
        color: 'var(--amber)',
        background: 'color-mix(in srgb, var(--amber) 10%, transparent)',
        border: '1px solid color-mix(in srgb, var(--amber) 25%, transparent)',
      }}
    >
      <Icon name="alert_triangle" size={12} /> Approving writes to your repository: it cherry-picks{' '}
      {data.targets.map((target, index) => (
        <span key={target.commit_sha}>
          {index > 0 ? ' and ' : ''}
          <code className="text-[11px]">{target.commit_sha.slice(0, 12)}</code>
          {target.source_branch ? ` from ${target.source_branch}` : ''}
        </span>
      ))}{' '}
      into <strong>{data.main_branch}</strong>.
    </p>
  )
}

function statusLabel(status: string): string {
  return status.replace(/_/g, ' ')
}

/** One labelled fact in the ticket's field block. */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p
        className="text-[10px] font-semibold uppercase tracking-wide mb-1"
        style={{ color: 'var(--text-3)' }}
      >
        {label}
      </p>
      <div className="text-[12.5px] min-w-0" style={{ color: 'var(--text)' }}>
        {children}
      </div>
    </div>
  )
}

/** Absolute time for the title attribute — "2 days ago" is the right density for a field, but
 *  the exact stamp is what someone reconciling against a log actually needs. */
function exactTime(value: string): string {
  const parsed = hubDate(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function relativeTime(value: string): string {
  const parsed = hubDate(value)
  return Number.isNaN(parsed.getTime()) ? value : formatDistanceToNow(parsed, { addSuffix: true })
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
 * in behaviour, with room to read it.
 *
 * A centred panel over a dimmed backdrop — reversing this file's original right-side geometry on
 * the operator's own judgement, 2026-08-17: *"I don't want a ticket that takes the whole screen
 * like navigating to a new screen. Just that central popup that floats in the middle slightly
 * obfuscating the background to focus on the ticket."*
 *
 * The argument the drawer was built on — that a right edge keeps the board's column context
 * visible — did not survive contact: the panel read as a grey tab bolted to the side, and the
 * column it came from is not what someone reading a ticket is looking for. Dimming the board
 * instead says plainly that the ticket is the subject, and it is not a full screen, so the board
 * is still there to return to. It closes the way every other dialog here does: click outside,
 * or Escape.
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
      // The scrim. Dims rather than hides: the board stays legible behind, so the ticket reads as
      // something opened on top of the board and not as a screen navigated to.
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '3vh 24px',
        background: 'rgba(0, 0, 0, 0.32)',
        backdropFilter: 'blur(1.5px)',
        zIndex: 50,
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`task-drawer-title-${task.id}`}
        data-testid={`task-drawer-${task.id}`}
        className="task-detail-dialog"
        style={{
          // Wide enough for a description to have a line length worth reading, and capped so it
          // never becomes the full screen. Height follows content up to the viewport, so a short
          // ticket is a short panel rather than a full-height column of empty space.
          width: 'min(760px, 100%)',
          maxHeight: '94vh',
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--surface)',
          border: '1px solid var(--border-hi)',
          borderRadius: 'var(--radius-content, 10px)',
          boxShadow: '0 16px 48px rgba(0,0,0,0.28), inset 0 1px var(--lift-hi)',
          // Deliberately no `overflow: hidden` here, however tempting for the rounded corners:
          // `design.md` D8 requires the body to be the only scrolling element, and a test pins
          // it. Clipping the panel is a cosmetic want; clipping the ticket is a defect.
        }}
      >
      <div
        className="shrink-0 flex items-start justify-between gap-3 px-6 py-4"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="min-w-0">
          <h2 id={`task-drawer-title-${task.id}`} className="text-base font-semibold leading-snug" style={{ color: 'var(--text)' }}>
            {task.title}
          </h2>
          <p className="text-[11px] mt-1 font-mono" style={{ color: 'var(--text-3)' }}>
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
        // Wider gutters and more air between blocks. At 480px with `p-4 space-y-3` every section
        // ran into the next and the whole thing read as one wall; the width now allows a real
        // line length, and the sections need to be told apart to benefit from it.
        className="flex-1 px-6 py-5 space-y-5"
        style={{ overflowY: 'auto', minHeight: 0 }}
      >
        {/* The ticket's own facts, together. The card carried status, priority, assignee, agent
            state and age; this panel showed none of them and offered only a bare "…" menu, so
            opening a ticket lost information rather than gaining it — exactly backwards for the
            surface with the most room. */}
        <div
          className="task-detail-facts grid gap-x-6 gap-y-4 p-3"
          style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}
        >
          <Field label="Status">
            <div className="flex items-center gap-2 flex-wrap">
              <StatusBadge status={task.status} />
              {/* The operator's status control, beside the status it changes rather than standing
                  in for it. Offers only the moves the map declares legal from here, so an illegal
                  one is never presented and then refused. */}
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
            </div>
            <ApprovalWritesNote taskId={task.id} canApprove={moves.includes('approved')} />
          </Field>

          <Field label="Priority">
            <PriorityBadge priority={task.priority} />
          </Field>

          <Field label="Assignee">
            {task.assignee ? (
              <span className="flex items-center gap-1.5 min-w-0">
                <span className="truncate">@{task.assignee}</span>
                {/* The agent's own state, which the card showed and this did not — the difference
                    between "assigned to builder" and "builder is working on it right now". */}
                {task.assignee_status && (
                  <span className="text-[11px] shrink-0" style={{ color: 'var(--text-3)' }}>
                    · {task.assignee_status}
                  </span>
                )}
              </span>
            ) : (
              <span style={{ color: 'var(--text-3)' }}>Unassigned</span>
            )}
          </Field>

          <Field label="Updated">
            <span title={exactTime(task.updated)}>{relativeTime(task.updated)}</span>
          </Field>

          <Field label="Created">
            <span title={exactTime(task.created_at)}>{relativeTime(task.created_at)}</span>
          </Field>

          {task.assigner && (
            <Field label="Assigned by">
              <span className="truncate block">{task.assigner}</span>
            </Field>
          )}

          {task.spec_task_key && (
            <Field label="Declared as">
              <code className="text-[11.5px]">{task.spec_task_key}</code>
            </Field>
          )}
        </div>

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

        {/* F60: the record that this work went ahead without an answer. Above the description
            because it changes how everything below it should be read. */}
        {task.proceeded_without_answer_reason && (
          <div
            data-testid={`task-proceeded-detail-${task.id}`}
            className="text-[11px] p-2 rounded"
            style={{
              color: 'var(--text-2)',
              background: 'color-mix(in srgb, var(--amber) 10%, transparent)',
              border: '1px solid color-mix(in srgb, var(--amber) 25%, transparent)',
            }}
          >
            <p className="font-medium" style={{ color: 'var(--amber)' }}>Decided without you</p>
            <p className="mt-0.5">{task.proceeded_without_answer_reason}</p>
          </div>
        )}

        {/* Full description */}
        {task.description && (
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide mb-1.5" style={{ color: 'var(--text-3)' }}>Description</p>
            <p
              className="text-[12.5px] leading-relaxed p-3 rounded"
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
            <p className="text-[11px] font-semibold uppercase tracking-wide mb-1.5" style={{ color: 'var(--text-3)' }}>Serves</p>
            <ul className="text-[12.5px] leading-relaxed space-y-1.5" style={{ color: 'var(--text)' }}>
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
            <p className="text-[11px] font-semibold uppercase tracking-wide mb-1.5" style={{ color: 'var(--text-3)' }}>Unresolved</p>
            <ul className="text-[12.5px] leading-relaxed space-y-1.5" style={{ color: 'var(--text-3)' }}>
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
            <p className="text-[11px] font-semibold uppercase tracking-wide mb-1.5" style={{ color: 'var(--text-3)' }}>Requirements (as written)</p>
            <ul className="list-disc list-inside text-[12.5px] leading-relaxed space-y-1.5" style={{ color: 'var(--text)' }}>
              {task.requirements.map((req, i) => (
                <li key={i}>{req}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Acceptance Criteria */}
        {task.acceptance_criteria && task.acceptance_criteria.length > 0 && (
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide mb-1.5" style={{ color: 'var(--text-3)' }}>Acceptance Criteria</p>
            <ul className="list-disc list-inside text-[12.5px] leading-relaxed space-y-1.5" style={{ color: 'var(--text)' }}>
              {task.acceptance_criteria.map((criterion, i) => (
                <li key={i}>{criterion}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Deliverables */}
        {task.deliverables && task.deliverables.length > 0 && (
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide mb-1.5" style={{ color: 'var(--text-3)' }}>Deliverables</p>
            <ul className="list-disc list-inside text-[12.5px] leading-relaxed space-y-1.5" style={{ color: 'var(--text)' }}>
              {task.deliverables.map((deliverable, i) => (
                <li key={i}>{deliverable}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Notes */}
        {task.notes && (
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide mb-1.5" style={{ color: 'var(--text-3)' }}>Notes</p>
            <p
              className="text-[12.5px] leading-relaxed p-3 rounded"
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
          <p className="text-[11px] font-semibold uppercase tracking-wide mb-1.5" style={{ color: 'var(--text-3)' }}>
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
    </div>
  )
}
