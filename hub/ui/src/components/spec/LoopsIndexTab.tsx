import { useMemo } from 'react'
import { Icon } from '@/components/common/Icon'
import { Badge } from '@/components/common/Badge'
import type { LoopSummary } from '@/api/loops'

interface LoopsIndexTabProps {
  loops: LoopSummary[]
  isLoading: boolean
  includeArchived: boolean
  onToggleIncludeArchived: (next: boolean) => void
  currentLoopId: string | null
  onSelect: (loopId: string) => void
}

type EndingBucket = 'running' | 'completed' | 'stopped'

/** B5.3: counts by *ending state*, never by matching `stop_reason` text — `ending_state` is the
 *  one value design D17 says is authoritative for what happened to a loop. `null` means still
 *  running; nothing here re-derives that from the presence/absence of a `stop_reason` string. */
function endingBucket(loop: LoopSummary): EndingBucket {
  if (loop.ending_state === 'completed') return 'completed'
  if (loop.ending_state === 'stopped') return 'stopped'
  return 'running'
}

function summarizeCounts(loops: LoopSummary[]): string {
  const counts = { running: 0, completed: 0, stopped: 0 }
  for (const loop of loops) counts[endingBucket(loop)] += 1
  const parts: string[] = []
  if (counts.completed > 0) parts.push(`${counts.completed} complete`)
  if (counts.stopped > 0) parts.push(`${counts.stopped} stopped early`)
  if (counts.running > 0) parts.push(`${counts.running} running`)
  return parts.length > 0 ? parts.join(' · ') : 'No loops'
}

function EndingBadge({ loop }: { loop: LoopSummary }) {
  const bucket = endingBucket(loop)
  if (bucket === 'completed') return <Badge variant="success">Complete</Badge>
  if (bucket === 'stopped') return <Badge variant="warning">Stopped early</Badge>
  return <Badge variant="info">Running</Badge>
}

/**
 * The panel shell's `loops` index tab (`2026-08-18-a-loop-writes-its-own-queue`, task B5.1) — a
 * project-wide governance glance at every loop, sourced from `GET /projects/{id}/loops` (design
 * D20; no conversation id, because a loop firing always starts a fresh one).
 *
 * B5.2's distinction from the files tree: this index **stays open** when a drill-down opens
 * (`panelTabsStore.openTab` has no `loops`-closing rule the way it closes `files` for a `file:`
 * tab) — a governance glance, not a launcher. Selecting a loop here is therefore never wired
 * through anything that would close this tab.
 */
export function LoopsIndexTab({
  loops,
  isLoading,
  includeArchived,
  onToggleIncludeArchived,
  currentLoopId,
  onSelect,
}: LoopsIndexTabProps) {
  const summary = useMemo(() => summarizeCounts(loops), [loops])

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col" data-testid="loops-index-tab">
      <div
        className="flex shrink-0 items-center justify-between gap-2 px-3 py-2"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <span style={{ fontSize: 11, color: 'var(--text-3)' }} data-testid="loops-index-summary">
          {summary}
        </span>
        <label
          className="flex items-center gap-1.5"
          style={{ fontSize: 11, color: 'var(--text-2)', cursor: 'pointer' }}
        >
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => onToggleIncludeArchived(e.target.checked)}
            data-testid="loops-index-include-archived"
          />
          Show archived
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-1.5" data-testid="loops-index-results">
        {isLoading ? (
          <p style={{ padding: 10, fontSize: 12, color: 'var(--text-3)' }}>Loading…</p>
        ) : loops.length === 0 ? (
          <p style={{ padding: 10, fontSize: 12, color: 'var(--text-3)' }}>
            {includeArchived ? 'No loops yet.' : 'No loops yet. Archived loops are hidden — check "Show archived".'}
          </p>
        ) : (
          loops.map((loop) => {
            const totalQueued = Object.values(loop.queue).reduce((sum, n) => sum + n, 0)
            const selected = loop.id === currentLoopId
            return (
              <button
                key={loop.id}
                type="button"
                data-testid={`loops-index-row-${loop.id}`}
                onClick={() => onSelect(loop.id)}
                className="flex w-full flex-col gap-1 rounded-[var(--radius-sm)] px-2.5 py-2 text-left"
                style={{
                  border: 'none',
                  background: selected ? 'var(--surface-2)' : 'transparent',
                  cursor: 'pointer',
                }}
              >
                <div className="flex min-w-0 items-center gap-1.5">
                  <Icon name="sync" size={14} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
                  <span
                    className="min-w-0 flex-1 truncate"
                    style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)' }}
                  >
                    {loop.label}
                  </span>
                  {loop.archived_at && (
                    <Badge variant="secondary" className="shrink-0">
                      Archived
                    </Badge>
                  )}
                  <span className="shrink-0">
                    <EndingBadge loop={loop} />
                  </span>
                </div>
                {loop.purpose && (
                  <p className="truncate" style={{ fontSize: 11, color: 'var(--text-2)' }}>
                    {loop.purpose}
                  </p>
                )}
                <div className="flex flex-wrap items-center gap-1.5">
                  <span style={{ fontSize: 11, color: 'var(--text-3)' }}>Queue: {totalQueued}</span>
                  {loop.open_questions > 0 && (
                    <Badge variant="warning">
                      {loop.open_questions} open question{loop.open_questions === 1 ? '' : 's'}
                    </Badge>
                  )}
                </div>
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}
