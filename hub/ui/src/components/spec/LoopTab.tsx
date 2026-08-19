import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { Badge } from '@/components/common/Badge'
import { Button } from '@/components/ui/button'
import { useLoop } from '@/api/loops'

interface LoopTabProps {
  loopId: string
  onClose: () => void
}

function EndingSummary({ endingState, stopReason }: { endingState?: string | null; stopReason?: string | null }) {
  if (endingState === 'completed') return <Badge variant="success">Complete</Badge>
  if (endingState === 'stopped') return <Badge variant="warning">Stopped early{stopReason ? `: ${stopReason}` : ''}</Badge>
  return <Badge variant="info">Running</Badge>
}

/**
 * The panel shell's `loop:<loop_id>` drill-down tab (`2026-08-18-a-loop-writes-its-own-queue`,
 * task B6.1) — purpose, stop condition, ending state and reason, queue counts by status, the
 * claimed item, open questions, and firing history, from `GET /projects/{id}/loops/{loop_id}`
 * (design D16: readable regardless of `archived_at`, so an ended loop still renders completely —
 * task B6.5, the record is most valuable *after* the loop finished).
 *
 * **Deliberately not built here** (open queue items LA4/B6.2-B6.4 in
 * `openspec/changes/2026-08-18-a-loop-writes-its-own-queue/tasks.md`): an active-now indicator,
 * its motion, and SSE-driven live updates. All three depend on design D13's helper
 * (`JobRun.status` gaining a "running" value) which does not exist yet — B4.3's own module
 * docstring in `hub/hub/api/v1/loops.py` already records the same gap for this exact data. A
 * substitute join here would repeat the mistake design D19 already named and rejected once. This
 * tab renders everything the API can state today and nothing it cannot.
 */
export function LoopTab({ loopId, onClose }: LoopTabProps) {
  const { data: loop, isLoading, isError } = useLoop(loopId)

  if (isLoading) {
    return (
      <div className="p-4" data-testid="loop-tab" style={{ fontSize: 12, color: 'var(--text-3)' }}>
        Loading…
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
        <EndingSummary endingState={loop.ending_state} stopReason={loop.stop_reason} />
        {loop.archived_at && <Badge variant="secondary">Archived</Badge>}
      </div>

      {loop.purpose && (
        <p className="mt-3" style={{ fontSize: 12, color: 'var(--text)' }}>
          {loop.purpose}
        </p>
      )}

      <div className="mt-3 space-y-1" style={{ fontSize: 11, color: 'var(--text-3)' }}>
        <p data-testid="loop-tab-stop-condition">
          Stop condition:{' '}
          {loop.stop_at
            ? `at ${new Date(loop.stop_at).toLocaleString()}`
            : loop.stop_when_queue_empties
              ? 'when the queue empties'
              : 'runs until stopped by the operator'}
        </p>
        {loop.stopped_at && <p>Stopped {formatDistanceToNow(new Date(loop.stopped_at), { addSuffix: true })}</p>}
      </div>

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
          Current item
        </p>
        {loop.current_task ? (
          <p style={{ fontSize: 11, color: 'var(--text)' }} data-testid="loop-tab-current-task">
            {loop.current_task.title} ({loop.current_task.status})
          </p>
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
                  {formatDistanceToNow(new Date(run.fired_at), { addSuffix: true })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
