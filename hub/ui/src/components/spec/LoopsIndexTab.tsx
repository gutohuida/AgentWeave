import { useMemo } from 'react'
import { Icon } from '@/components/common/Icon'
import { Badge } from '@/components/common/Badge'
import type { LoopSummary } from '@/api/loops'
import { endingBucket } from './loopCounts'

interface LoopsIndexTabProps {
  loops: LoopSummary[]
  isLoading: boolean
  includeArchived: boolean
  onToggleIncludeArchived: (next: boolean) => void
  currentLoopId: string | null
  onSelect: (loopId: string) => void
}

function summarizeCounts(loops: LoopSummary[]): string {
  const counts = { running: 0, stalled: 0, idle: 0, completed: 0, stopped: 0 }
  for (const loop of loops) counts[endingBucket(loop)] += 1
  const parts: string[] = []
  if (counts.completed > 0) parts.push(`${counts.completed} complete`)
  if (counts.stopped > 0) parts.push(`${counts.stopped} stopped early`)
  if (counts.running > 0) parts.push(`${counts.running} running`)
  if (counts.stalled > 0) parts.push(`${counts.stalled} stalled`)
  if (counts.idle > 0) parts.push(`${counts.idle} idle`)
  return parts.length > 0 ? parts.join(' · ') : 'No loops'
}

/**
 * The 5px dot the S3 `considered` mock puts inside every loop status badge. `currentColor` is the
 * whole point: the dot takes the badge's own tone, so a status can never end up with a dot in a
 * colour its text does not share — the same rule `Badge`'s own comment states for bg and border.
 */
function StatusDot() {
  return (
    <span
      aria-hidden="true"
      style={{ width: 5, height: 5, borderRadius: 9999, background: 'currentColor', flexShrink: 0 }}
    />
  )
}

/**
 * The row's single status badge.
 *
 * **Open questions are folded in here rather than carried separately.** The mock gives a row one
 * badge, and shows `1 open question` occupying that slot on the loop that has one — an unanswered
 * question is the more urgent fact about a loop than whether it is between firings, so it wins the
 * slot. The previous build showed the ending state *and* a second badge further down, which read
 * as two independent statuses for one loop.
 */
function StatusBadge({ loop }: { loop: LoopSummary }) {
  if (loop.open_questions > 0) {
    return (
      <Badge variant="warning">
        <StatusDot />
        {loop.open_questions} open question{loop.open_questions === 1 ? '' : 's'}
      </Badge>
    )
  }
  const bucket = endingBucket(loop)
  if (bucket === 'stalled')
    return (
      <Badge variant="warning">
        <StatusDot />
        stalled
      </Badge>
    )
  if (bucket === 'completed')
    return (
      <Badge variant="success">
        <StatusDot />
        complete
      </Badge>
    )
  if (bucket === 'stopped')
    return (
      <Badge variant="warning">
        <StatusDot />
        stopped early
      </Badge>
    )
  // "Running" is claimed only while a firing is actually in progress. A loop between firings —
  // or one whose job is paused and has never fired at all — is idle, and saying otherwise made
  // the panel report work that was not happening.
  if (bucket === 'running')
    return (
      <Badge variant="info">
        <StatusDot />
        running
      </Badge>
    )
  return (
    <Badge variant="secondary">
      <StatusDot />
      idle
    </Badge>
  )
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
 *
 * **Brought to `design/mocks/S3/considered.html` on 2026-08-24**, the variant the operator
 * approved. What changed and why each was a divergence rather than a preference:
 *
 * - The loading state was three 64px solid blocks. Finding 7's whole point is that a skeleton
 *   "previews the shape of what's coming" — so it is now four rows of a 14px icon square and a
 *   10px line, the shape of a real row, plus the toolbar's own skeleton.
 * - The switch sat before its label; the mock reads "Show archived" then the control. The
 *   `.panel-switch` CSS needs the input as its immediate previous sibling, so the input moves
 *   with the switch and the text leads.
 * - Status badges were capitalised and dotless, and open questions were a *second* badge on a
 *   lower row — two statuses for one loop. One badge, one dot, lowercase, questions winning the
 *   slot when there are any.
 * - The row carried a leading `sync` icon and a purpose line the mock does not have, and split
 *   its metadata across two shapes. The mock's meta is one line: agent glyph, `@name`, `·`,
 *   `queue N`.
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
      <div className="flex shrink-0 items-center justify-between gap-2 px-2.5 pb-2 pt-1">
        <span style={{ fontSize: 12, color: 'var(--text-3)' }} data-testid="loops-index-summary">
          {summary}
        </span>
        {/* Label first, then the control — the mock's reading order. The input stays immediately
            before `.panel-switch` because the switch's checked and focus styling is written as an
            adjacent-sibling rule in `index.css`. */}
        <label
          className="flex items-center gap-[7px]"
          style={{ fontSize: 12, color: 'var(--text-2)', cursor: 'pointer' }}
        >
          Show archived
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => onToggleIncludeArchived(e.target.checked)}
            data-testid="loops-index-include-archived"
            className="sr-only"
          />
          <span className="panel-switch" aria-hidden="true" />
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-1 pb-1.5" data-testid="loops-index-results">
        {isLoading ? (
          // Finding 7: shaped like the rows that will arrive, not like a block. Four, matching the
          // mock — enough to read as a list rather than as one thing still loading.
          <div aria-label="Loading loops">
            <div className="flex items-center gap-2 px-2.5 py-1.5">
              <span className="skeleton" style={{ height: 12, width: '60%' }} />
            </div>
            {['60%', '45%', '70%', '60%'].map((width, i) => (
              <div key={i} className="flex items-center gap-2 px-2.5 py-1.5">
                <span className="skeleton" style={{ width: 14, height: 14, flex: 'none' }} />
                <span className="skeleton" style={{ height: 10, flex: 1, maxWidth: width }} />
              </div>
            ))}
          </div>
        ) : loops.length === 0 ? (
          <p style={{ padding: 10, fontSize: 12, color: 'var(--text-3)' }}>
            {includeArchived
              ? 'No loops yet.'
              : 'No loops yet. Archived loops are hidden — check "Show archived".'}
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
                data-active={selected ? 'true' : 'false'}
                className="row-item !items-stretch flex-col gap-1 px-2.5 py-2"
                style={{ border: 'none', cursor: 'pointer' }}
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    className="min-w-0 flex-1 truncate text-left"
                    style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)' }}
                  >
                    {loop.label}
                  </span>
                  {loop.archived_at && (
                    <Badge variant="secondary" className="shrink-0">
                      Archived
                    </Badge>
                  )}
                  <span className="shrink-0">
                    <StatusBadge loop={loop} />
                  </span>
                </div>
                {/* One line, in the mock's order and punctuation. Who is actually running this
                    loop: the index listed a label and a purpose but never said whose loop it was,
                    so "what is running right now" could not be answered by agent (operator,
                    2026-08-19). */}
                <div
                  className="flex min-w-0 items-center gap-1.5 pl-0.5"
                  style={{ fontSize: 11, color: 'var(--text-3)' }}
                >
                  {loop.agent && (
                    <>
                      <Icon
                        name="smart_toy"
                        size={12}
                        style={{ color: 'var(--text-3)', flexShrink: 0 }}
                      />
                      <span className="truncate" data-testid={`loops-index-agent-${loop.id}`}>
                        @{loop.agent}
                      </span>
                      <span aria-hidden="true">·</span>
                    </>
                  )}
                  <span className="shrink-0">queue {totalQueued}</span>
                </div>
                {/* 5.4: the label says what is being waited on, not merely that something is. The
                    text is the Hub's own refusal reason, so the board and the firing cannot say
                    different things about why nothing is happening. */}
                {loop.stall_reason && (
                  <p
                    className="truncate pl-0.5 text-left"
                    style={{ fontSize: 11, color: 'var(--amber)' }}
                    data-testid={`loops-index-stall-${loop.id}`}
                  >
                    {loop.stall_reason.replace(/^loop queue is /, '')}
                  </p>
                )}
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}
