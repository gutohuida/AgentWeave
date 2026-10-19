import { useEffect, useMemo, useState } from 'react'
import { format } from 'date-fns'
import { readableApiError } from '@/api/client'
import type { TraceDetail } from '@/api/traces'
import { Badge } from '@/components/common/Badge'
import { EmptyState } from '@/components/common/EmptyState'
import { Button } from '@/components/ui/button'
import { SpanDetail } from '@/components/traces/SpanDetail'
import { TraceWaterfall } from '@/components/traces/TraceWaterfall'
import { buildWaterfall, formatDuration, traceExtent } from '@/components/traces/traceModel'
import { hubDate } from '@/lib/hubTime'

/** "Now", re-read every second while the trace is still being written, so open spans grow. */
function useNow(live: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!live) return
    setNow(Date.now())
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [live])
  return now
}

/**
 * A trace, drawn: a waterfall of its spans above the selected span's detail. The caller owns the
 * query (by run or by trace id) and the page offset; this owns selection.
 */
export function TraceView({
  detail,
  isLoading,
  error,
  offset,
  onOffsetChange,
  emptyDescription = 'This run has no trace. Runs before tracing was added have none, and a cleared trace is gone.',
}: {
  /** `null` means the Hub answered and there is no trace. */
  detail: TraceDetail | null | undefined
  isLoading: boolean
  error: unknown
  offset: number
  onOffsetChange: (offset: number) => void
  emptyDescription?: string
}) {
  const live = !!detail && !detail.root.ended
  const now = useNow(live)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const rows = useMemo(
    () => (detail ? buildWaterfall(detail.root, detail.spans, now) : []),
    [detail, now],
  )
  const extent = useMemo(
    () => (detail ? traceExtent(detail.root, detail.spans, now) : { startMs: 0, totalMs: 0 }),
    [detail, now],
  )

  if (isLoading) {
    return (
      <div aria-label="Loading trace" className="space-y-2 p-4">
        {[0, 1, 2, 3, 4, 5].map((row) => <div key={row} className="skeleton h-5 w-full" />)}
      </div>
    )
  }
  if (error) {
    return (
      <div role="alert" className="p-4 text-xs" style={{ color: 'var(--red)' }}>
        <strong>The trace could not be loaded.</strong>
        <p className="mt-1">{readableApiError(error, 'The Hub did not return a reason.')}</p>
      </div>
    )
  }
  if (!detail) {
    return <EmptyState icon="monitoring" title="No trace" description={emptyDescription} />
  }

  const selected =
    rows.find((row) => row.span.span_id === selectedId)?.span ?? rows[0]?.span ?? detail.root
  const pageEnd = Math.min(detail.offset + detail.spans.length, detail.total)
  const paged = detail.total > detail.limit
  const agent = detail.root.attributes?.['gen_ai.agent.name']

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="trace-view">
      <div
        className="flex flex-wrap items-center gap-2 px-3 py-2 text-[11.5px]"
        style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-3)' }}
      >
        <Badge variant={detail.root.status === 'error' ? 'danger' : live ? 'info' : detail.root.status === 'ok' ? 'success' : 'default'}>
          {live ? 'running' : detail.root.status === 'unset' ? 'ended' : detail.root.status}
        </Badge>
        {typeof agent === 'string' && <span style={{ color: 'var(--text-2)' }}>{agent}</span>}
        <span>{format(hubDate(detail.root.start_time), 'MMM d, HH:mm:ss')}</span>
        <span>· {formatDuration(extent.totalMs)}{live ? ' so far' : ''}</span>
        <span>· {detail.total.toLocaleString()} span{detail.total === 1 ? '' : 's'}</span>
        {detail.kind === 'worker' && <span>· worker</span>}
        {paged && (
          <span className="ml-auto flex items-center gap-1.5" data-testid="trace-paging">
            <span>
              {(detail.offset + 1).toLocaleString()}–{pageEnd.toLocaleString()} of {detail.total.toLocaleString()}
            </span>
            <Button
              variant="outline"
              size="xs"
              disabled={offset <= 0}
              onClick={() => onOffsetChange(Math.max(0, offset - detail.limit))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="xs"
              disabled={pageEnd >= detail.total}
              onClick={() => onOffsetChange(offset + detail.limit)}
            >
              Next
            </Button>
          </span>
        )}
      </div>
      {detail.root.status === 'error' && detail.root.status_message && (
        <div className="px-3 py-1.5 text-[11.5px]" style={{ color: 'var(--red)', borderBottom: '1px solid var(--border)' }}>
          {detail.root.status_message}
        </div>
      )}
      <div className="min-h-[120px] flex-[3] overflow-auto py-2">
        <TraceWaterfall
          rows={rows}
          totalMs={extent.totalMs}
          selectedId={selected.span_id}
          onSelect={setSelectedId}
        />
      </div>
      <div className="min-h-[160px] flex-[2] overflow-auto px-3 py-3" style={{ borderTop: '1px solid var(--border)' }}>
        <SpanDetail span={selected} nowMs={now} />
      </div>
    </div>
  )
}
