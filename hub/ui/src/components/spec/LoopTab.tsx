import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { Badge } from '@/components/common/Badge'
import { Button } from '@/components/ui/button'
import { useLoop, useStopLoop, useArchiveLoop, useSetLoopControl, type LoopSummary } from '@/api/loops'
import { useAgents } from '@/api/agents'
import { readableApiError } from '@/api/client'
import { hubDate } from '@/lib/hubTime'
import { endingBucket } from './loopCounts'
import { LoopSettings } from './LoopSettings'

interface LoopTabProps {
  loopId: string
  onClose: () => void
}

/** How a stop condition reads on its own, so the staged and the live one are described the same
 *  way and a difference between them is a difference in the loop, not in the wording. */
function stopWhenQueueEmptiesText(value: boolean): string {
  return value ? 'when the queue empties' : 'not when the queue empties'
}

function stopAtText(value?: string | null): string {
  return value ? `at ${hubDate(value).toLocaleString()}` : 'no scheduled stop'
}

/** The staged fields, each as the pair the operator has to compare: what governs the loop now,
 *  and what will govern it from the next firing. Only staged keys produce a row — an absent key
 *  means this edit did not touch that field, so showing it would invent a change. */
function stagedFields(loop: LoopSummary): Array<{ key: string; label: string; now: string; next: string }> {
  const pending = loop.pending_edit
  if (!pending) return []
  const rows: Array<{ key: string; label: string; now: string; next: string }> = []
  if (pending.agent !== undefined) {
    rows.push({
      key: 'agent',
      label: 'Default agent',
      now: loop.agent || 'none',
      next: pending.agent || 'none',
    })
  }
  if (pending.purpose !== undefined) {
    rows.push({
      key: 'purpose',
      label: 'Purpose',
      now: loop.purpose || 'not stated',
      next: pending.purpose || 'not stated',
    })
  }
  if (pending.stop_at !== undefined) {
    rows.push({ key: 'stop_at', label: 'Stop at', now: stopAtText(loop.stop_at), next: stopAtText(pending.stop_at) })
  }
  if (pending.stop_when_queue_empties !== undefined) {
    rows.push({
      key: 'stop_when_queue_empties',
      label: 'Stop when the queue empties',
      now: stopWhenQueueEmptiesText(loop.stop_when_queue_empties),
      next: stopWhenQueueEmptiesText(pending.stop_when_queue_empties),
    })
  }
  return rows
}

/**
 * A staged edit, and which definition is in force while it waits (design D11, task A2.4 —
 * "a requirement, not polish").
 *
 * The Hub has reported `pending_edit` since A2.4 and nothing rendered it, so an operator who
 * staged an edit saw the loop's *old* values with no sign anything was waiting — the worst
 * possible reading, because it is indistinguishable from the edit having been lost. That gap is
 * what blocked human-only check A6.1 ("does 'pending versus live' read clearly enough to
 * trust?").
 *
 * Every value is labelled with when it applies rather than by position or colour alone: "In force
 * now" against "From the next firing". A firing already running keeps the live definition to its
 * end — stated explicitly here, because that is exactly the case where "next firing" is ambiguous
 * and an operator watching a run could otherwise believe their edit is already governing it.
 *
 * This panel is the *only* place the distinction is drawn. A first cut also annotated the live
 * purpose and stop condition in place, guarding against an operator who reads one of them and
 * stops there — but the panel renders directly above both, so the annotation restated what was
 * already on screen twice over, and the operator judged it noise (2026-08-19). If either live
 * field ever moves out of this panel's sightline, the guard becomes real again.
 */
function PendingEdit({ loop }: { loop: LoopSummary }) {
  const pending = loop.pending_edit
  if (!pending) return null
  const rows = stagedFields(loop)

  return (
    <div
      className="mt-3 rounded-[var(--radius-sm)] p-2.5"
      data-testid="loop-tab-pending-edit"
      style={{ background: 'var(--surface-2)', border: '1px solid var(--amber)' }}
    >
      <div className="flex items-center gap-1.5">
        <Icon name="schedule" size={13} style={{ color: 'var(--amber)', flexShrink: 0 }} />
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)' }}>
          Edit staged — it applies at the next firing
        </span>
      </div>
      <p className="mt-1" style={{ fontSize: 11, color: 'var(--text-3)' }} data-testid="loop-tab-pending-edit-who">
        Staged by {pending.staged_by || 'the operator'}{' '}
        {formatDistanceToNow(hubDate(pending.staged_at), { addSuffix: true })}.
        {loop.firing_active
          ? ' The firing running now keeps the definition below marked “In force now”; the edit reaches the firing after it.'
          : ' Until then the loop runs on the definition below marked “In force now”.'}
      </p>

      {rows.length === 0 ? (
        /* `pending_edit_at` is set while every per-field column stayed NULL. Legitimate — the
         * columns are "not touched by this edit", not "no edit" — so say the edit exists rather
         * than rendering an empty box that reads as a bug. */
        <p className="mt-2" style={{ fontSize: 11, color: 'var(--text-3)' }} data-testid="loop-tab-pending-edit-empty">
          It changes no field this panel shows.
        </p>
      ) : (
        <div className="mt-2 space-y-2">
          {rows.map((row) => (
            <div key={row.key} data-testid={`loop-tab-pending-${row.key}`}>
              <p style={{ fontSize: 10, fontWeight: 500, color: 'var(--text-3)' }}>{row.label}</p>
              <p style={{ fontSize: 11, color: 'var(--text)' }}>
                <span style={{ color: 'var(--text-3)' }}>In force now: </span>
                {row.now}
              </p>
              <p style={{ fontSize: 11, color: 'var(--text)' }}>
                <span style={{ color: 'var(--amber)' }}>From the next firing: </span>
                {row.next}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** The loop's state, from the one shared helper rather than a second reading of `ending_state`.
 *
 *  This used to fall through to "Running" whenever `ending_state` was null, which is true of a loop
 *  that has never fired as well as one firing right now — so a paused loop reported itself as
 *  running. It was also redundant in the one case it got right: the animated "Running now" pill
 *  rendered immediately beside it already says that, with motion. So `running` renders nothing
 *  here and lets that pill carry it. */
function EndingSummary({ loop }: { loop: LoopSummary }) {
  const bucket = endingBucket(loop)
  if (bucket === 'completed') return <Badge variant="success">Complete</Badge>
  if (bucket === 'stopped') {
    return (
      <Badge variant="warning">
        Stopped early{loop.stop_reason ? `: ${loop.stop_reason}` : ''}
      </Badge>
    )
  }
  if (bucket === 'running') return null
  return <Badge variant="secondary">Idle</Badge>
}

const DEFAULT_STOP_REASON = 'Stopped by the operator'

/**
 * Stop, Archive and who decides the queue, from the loop's own tab
 * (`a-loop-is-stopped-archived-and-delegated-from-its-own-tab`, design D4). Visibility comes from
 * the same `endingBucket` as the badge, so the two cannot disagree: a running loop offers Stop and
 * the controller toggle, an ended one offers Archive, an archived one nothing. Confirmation is
 * inline and two-step, as `JobCard`'s Archive is.
 */
function LoopActions({ loop }: { loop: LoopSummary & { job_id: string } }) {
  const stop = useStopLoop()
  const archive = useArchiveLoop()
  const setControl = useSetLoopControl()
  const { data: archivedAgents, isError: archivedListFailed } = useAgents('archived')
  const [confirming, setConfirming] = useState<'stop' | 'archive' | null>(null)
  const [reason, setReason] = useState('')

  if (loop.archived_at) return null
  const bucket = endingBucket(loop)
  const ended = bucket === 'completed' || bucket === 'stopped'
  const delegated = loop.control === 'creator'
  const agent = loop.agent ?? ''
  const agentArchived = !!archivedAgents?.some((a) => a.name === agent)

  const failure = stop.isError
    ? readableApiError(stop.error, 'Could not stop this loop.')
    : archive.isError
      ? readableApiError(archive.error, 'Could not archive this loop.')
      : setControl.isError
        ? readableApiError(setControl.error, 'Could not change who decides this loop’s queue.')
        : null
  const pending = stop.isPending || archive.isPending || setControl.isPending

  return (
    <div className="mt-3 space-y-2" data-testid="loop-tab-actions">
      {!ended && (
        <p data-testid="loop-tab-controller" style={{ fontSize: 11, color: 'var(--text-3)' }}>
          Additions to this queue are decided by {delegated ? agent || 'the loop’s agent' : 'you'}.
          {agent && !agentArchived && (
            <>
              {' '}
              <Button
                variant="outline"
                size="xs"
                disabled={pending}
                onClick={() => setControl.mutate({ loopId: loop.id, control: delegated ? 'operator' : 'creator' })}
              >
                {delegated ? 'Decide them yourself' : `Let ${agent} decide`}
              </Button>
            </>
          )}
        </p>
      )}

      {!ended && confirming !== 'stop' && (
        <Button variant="destructive" size="xs" disabled={pending} onClick={() => setConfirming('stop')}>
          Stop
        </Button>
      )}
      {!ended && confirming === 'stop' && (
        <div data-testid="loop-tab-stop-confirm" className="space-y-1.5">
          <p style={{ fontSize: 11, color: 'var(--text-3)' }}>
            {loop.firing_active
              ? 'The firing running now finishes; no firing starts after it.'
              : 'No firing starts after this.'}
          </p>
          <label className="block" style={{ fontSize: 11, color: 'var(--text-3)' }}>
            Reason
            <input
              className="mt-0.5 block w-full rounded-[var(--radius-sm)] px-2 py-1"
              style={{ fontSize: 11, background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}
              value={reason}
              placeholder={DEFAULT_STOP_REASON}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <div className="flex items-center gap-1">
            <Button
              variant="destructive"
              size="xs"
              disabled={pending}
              onClick={() => {
                stop.mutate({ jobId: loop.job_id, reason: reason.trim() || DEFAULT_STOP_REASON })
                setConfirming(null)
              }}
            >
              Stop loop
            </Button>
            <Button variant="outline" size="xs" onClick={() => setConfirming(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {ended && confirming !== 'archive' && (
        <Button variant="outline" size="xs" disabled={pending} onClick={() => setConfirming('archive')}>
          Archive
        </Button>
      )}
      {ended && confirming === 'archive' && (
        <div className="flex items-center gap-1" data-testid="loop-tab-archive-confirm">
          <Button
            variant="destructive"
            size="xs"
            disabled={pending}
            onClick={() => {
              archive.mutate({ loopId: loop.id })
              setConfirming(null)
            }}
          >
            Archive loop
          </Button>
          <Button variant="outline" size="xs" onClick={() => setConfirming(null)}>
            Cancel
          </Button>
        </div>
      )}

      {!ended && archivedListFailed && (
        <p style={{ fontSize: 11, color: 'var(--text-3)' }}>
          Could not check whether {agent || 'the loop’s agent'} is archived; delegating to an archived agent has no effect.
        </p>
      )}

      {failure && (
        <p role="alert" style={{ fontSize: 11, color: 'var(--red)' }}>
          {failure}
        </p>
      )}
    </div>
  )
}

/**
 * The panel shell's `loop:<loop_id>` drill-down tab (`2026-08-18-a-loop-writes-its-own-queue`,
 * task B6.1) — purpose, stop condition, ending state and reason, queue counts by status, the
 * claimed item, open questions, and firing history, from `GET /projects/{id}/loops/{loop_id}`
 * (design D16: readable regardless of `archived_at`, so an ended loop still renders completely —
 * task B6.5, the record is most valuable *after* the loop finished).
 *
 * **B6.2 the active-now indicator** reads `loop.firing_active` (design D13/D19's shared helper,
 * `_batch_loop_summaries` in `hub/hub/api/v1/jobs.py`) — no second join is added here, matching
 * D19's rejection of exactly that. **B6.3** its motion is Tailwind's `animate-pulse` (a CSS
 * animation), the same class `LogsView`/`AgentTimeline`/`AgentOutputPanel` already use for a live
 * dot — it inherits `index.css`'s blanket `prefers-reduced-motion: reduce` rule for free, so no
 * component-level `matchMedia` check is needed. **B6.4** live updates are SSE-driven: `useSSE.ts`'s
 * central switch invalidates this tab's `useLoop` query on the loop's own six event types (staged/
 * applied edits, control changes, stop, exhaustion, archival — `loop_queue_exhausted`'s first
 * consumer) plus `job_fired` and the terminal `run_*` events that flip `firing_active`, so this
 * component itself stays a plain read of React Query state and does not subscribe directly.
 */
export function LoopTab({ loopId, onClose }: LoopTabProps) {
  const { data: loop, isLoading, isError } = useLoop(loopId)

  if (isLoading) {
    // Shape-matched, like the index tabs already are: a heading line, then the step rows this
    // panel is about to fill in. The two detail tabs were the last places still saying "Loading…".
    return (
      <div className="space-y-2 p-4" data-testid="loop-tab" aria-label="Loading loop">
        <div className="skeleton h-3 w-1/2" />
        <div className="skeleton h-9 w-full" />
        <div className="skeleton h-9 w-full" />
        <div className="skeleton h-9 w-5/6" />
      </div>
    )
  }

  if (isError || !loop) {
    return (
      <div className="p-4" data-testid="loop-tab" style={{ fontSize: 12, color: 'var(--text-3)' }}>
        This loop could not be loaded.
      </div>
    )
  }

  const queueEntries = Object.entries(loop.queue)
  const totalQueued = queueEntries.reduce((sum, [, n]) => sum + n, 0)

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-y-auto p-3" data-testid="loop-tab">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <Icon name="sync" size={16} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
          <h2 className="truncate" style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>
            {loop.label}
          </h2>
        </div>
        <Button variant="ghost" size="icon-xs" onClick={onClose} aria-label="Close" title="Close">
          <Icon name="close" size={14} />
        </Button>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <EndingSummary loop={loop} />
        {loop.archived_at && <Badge variant="secondary">Archived</Badge>}
        {loop.firing_active && (
          <span data-testid="loop-tab-firing-active">
            <Badge variant="success" pill>
              <span className="inline-flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
                Running now
              </span>
            </Badge>
          </span>
        )}
        {loop.pending_edit && (
          <span data-testid="loop-tab-pending-badge">
            <Badge variant="warning">Edit staged</Badge>
          </span>
        )}
      </div>

      <LoopSettings loop={loop} />

      <PendingEdit loop={loop} />

      {loop.purpose && (
        <p className="mt-3" style={{ fontSize: 12, color: 'var(--text)' }}>
          {loop.purpose}
        </p>
      )}

      <div className="mt-3 space-y-1" style={{ fontSize: 11, color: 'var(--text-3)' }}>
        <p data-testid="loop-tab-stop-condition">
          Stop condition:{' '}
          {loop.stop_at
            ? `at ${hubDate(loop.stop_at).toLocaleString()}`
            : loop.stop_when_queue_empties
              ? 'when the queue empties'
              : 'runs until stopped by the operator'}
        </p>
        {loop.stopped_at && <p>Stopped {formatDistanceToNow(hubDate(loop.stopped_at), { addSuffix: true })}</p>}
      </div>

      <LoopActions loop={loop} />

      <div className="mt-4">
        <p className="mb-1.5" style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-3)' }}>
          Queue ({totalQueued})
        </p>
        {queueEntries.length === 0 ? (
          <p style={{ fontSize: 11, color: 'var(--text-3)', opacity: 0.6 }}>Empty</p>
        ) : (
          <div className="flex flex-wrap items-center gap-1.5">
            {queueEntries.map(([status, count]) => (
              <Badge key={status} variant="secondary">
                {status}: {count}
              </Badge>
            ))}
          </div>
        )}
      </div>

      <div className="mt-4">
        <p className="mb-1.5" style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-3)' }}>
          {(loop.current_tasks?.length ?? 0) > 1 ? 'Current items' : 'Current item'}
        </p>
        {loop.current_tasks?.length ? (
          loop.current_tasks.map((task) => (
            <p
              key={task.id}
              style={{ fontSize: 11, color: 'var(--text)' }}
              data-testid="loop-tab-current-task"
            >
              {task.title} ({task.status})
              {task.agent ? (
                <span style={{ color: 'var(--text-3)', opacity: 0.75 }}> — {task.agent}</span>
              ) : null}
            </p>
          ))
        ) : (
          <p style={{ fontSize: 11, color: 'var(--text-3)', opacity: 0.6 }}>No current item</p>
        )}
      </div>

      {loop.open_questions > 0 && (
        <div className="mt-4">
          <Badge variant="warning">
            {loop.open_questions} open question{loop.open_questions === 1 ? '' : 's'}
          </Badge>
        </div>
      )}

      <div className="mt-4">
        <p className="mb-1.5" style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-3)' }}>
          Firing history
        </p>
        {loop.history.length === 0 ? (
          <p style={{ fontSize: 11, color: 'var(--text-3)', opacity: 0.6 }}>No firings yet</p>
        ) : (
          <div className="space-y-1.5" data-testid="loop-tab-history">
            {loop.history.map((run) => (
              <div
                key={run.id}
                className="flex items-center justify-between rounded-[var(--radius-sm)] px-2 py-1.5"
                style={{ background: 'var(--surface-2)' }}
              >
                <div className="flex items-center gap-1.5">
                  <Icon
                    name={run.status === 'completed' ? 'check_circle' : run.status === 'failed' ? 'error' : 'schedule'}
                    size={13}
                    style={{
                      color:
                        run.status === 'completed'
                          ? 'var(--green)'
                          : run.status === 'failed'
                            ? 'var(--red)'
                            : 'var(--text-3)',
                    }}
                  />
                  <span style={{ fontSize: 11, color: 'var(--text)' }}>{run.trigger}</span>
                </div>
                <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
                  {formatDistanceToNow(hubDate(run.fired_at), { addSuffix: true })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
