import { tint } from '@/lib/colorTint'
import {
  formatDuration,
  operationLabel,
  spanHint,
  spanToken,
  type WaterfallRow,
} from '@/components/traces/traceModel'

const INDENT_PX = 14
const TICKS = [0, 0.25, 0.5, 0.75, 1]

/**
 * One row per span, indented by depth, with a bar placed by when it started and how long it took
 * relative to the whole trace. A row is a button: selecting it opens its detail below.
 */
export function TraceWaterfall({
  rows,
  totalMs,
  selectedId,
  onSelect,
}: {
  rows: WaterfallRow[]
  totalMs: number
  selectedId: string | null
  onSelect: (spanId: string) => void
}) {
  const span = totalMs > 0 ? totalMs : 1
  return (
    <div className="text-[12px]" data-testid="trace-waterfall">
      <div
        className="grid items-end gap-2 px-3 pb-1 text-[10.5px]"
        style={{ gridTemplateColumns: 'minmax(180px, 38%) 1fr 64px', color: 'var(--text-3)' }}
        aria-hidden="true"
      >
        <span>Span</span>
        <div className="relative h-4">
          {TICKS.map((tick) => (
            <span
              key={tick}
              className="absolute top-0 whitespace-nowrap"
              style={{
                left: `${tick * 100}%`,
                transform: tick === 0 ? undefined : tick === 1 ? 'translateX(-100%)' : 'translateX(-50%)',
              }}
            >
              {formatDuration(totalMs * tick)}
            </span>
          ))}
        </div>
        <span className="text-right">Duration</span>
      </div>
      {rows.map((row) => {
        const token = spanToken(row.span)
        const selected = row.span.span_id === selectedId
        const left = (row.offsetMs / span) * 100
        const width = Math.max((row.durationMs / span) * 100, 0.4)
        const hint = spanHint(row.span)
        return (
          <button
            key={row.span.span_id}
            type="button"
            data-testid={`trace-row-${row.span.span_id}`}
            data-operation={row.span.operation}
            data-status={row.span.status}
            aria-pressed={selected}
            onClick={() => onSelect(row.span.span_id)}
            className="grid w-full items-center gap-2 rounded-[var(--radius-sm)] px-3 py-[3px] text-left hover:bg-[var(--row-hover)]"
            style={{
              gridTemplateColumns: 'minmax(180px, 38%) 1fr 64px',
              background: selected ? 'var(--row-selected)' : undefined,
            }}
          >
            <span
              className="flex min-w-0 items-center gap-1.5"
              style={{ paddingLeft: row.depth * INDENT_PX }}
            >
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ background: token }}
                aria-hidden="true"
              />
              <span className="truncate" style={{ color: 'var(--text)' }} title={row.span.name}>
                {row.span.name}
              </span>
              <span className="shrink-0 text-[10.5px]" style={{ color: 'var(--text-3)' }}>
                {operationLabel(row.span.operation)}
              </span>
              {hint && (
                <span className="truncate text-[10.5px]" style={{ color: 'var(--text-2)' }} title={hint}>
                  · {hint}
                </span>
              )}
            </span>
            <span className="relative h-3.5 rounded-sm" style={{ background: 'var(--surface-2)' }}>
              <span
                className="absolute top-0 bottom-0 rounded-sm"
                data-open={row.open ? 'true' : undefined}
                style={{
                  left: `${Math.min(left, 99.6)}%`,
                  width: `${Math.min(width, 100 - Math.min(left, 99.6))}%`,
                  background: row.open ? tint(token, 45) : token,
                  border: row.open ? `1px dashed ${token}` : undefined,
                }}
              />
            </span>
            <span
              className="text-right tabular-nums"
              style={{ color: row.span.status === 'error' ? 'var(--red)' : 'var(--text-2)' }}
            >
              {formatDuration(row.durationMs)}
              {row.open ? '…' : ''}
            </span>
          </button>
        )
      })}
    </div>
  )
}
