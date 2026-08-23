import { presentContextUsage } from './contextPresentation'

interface ContextUsageIndicatorProps {
  value: unknown
  compact?: boolean
}

export function ContextUsageIndicator({
  value,
  compact = false,
}: ContextUsageIndicatorProps) {
  const context = presentContextUsage(value)
  if (!context) return null

  if (!compact) {
    const used = context.usage.context_tokens?.toLocaleString() ?? 'Unknown'
    const limit = context.usage.limit_tokens?.toLocaleString() ?? 'Unknown'
    const ring = context.percent === null
      ? 'var(--surface-3)'
      : `conic-gradient(${context.color} ${context.percent}%, var(--surface-3) ${context.percent}% 100%)`

    return (
      <div
        data-testid="context-usage"
        data-context-status={context.usage.status}
        data-context-severity={context.severity}
        className="context-usage-control"
        tabIndex={0}
        aria-label={`Context window: ${context.detail}`}
      >
        <span className="context-usage-ring" style={{ background: ring }} aria-hidden="true">
          <span />
        </span>
        <span className="context-usage-label" style={{ color: context.color }}>
          {context.label}
        </span>
        <span className="context-usage-popover" role="tooltip">
          <span className="context-usage-popover-title">Context window</span>
          <span className="context-usage-popover-row"><span>Used</span><b>{used} tok</b></span>
          <span className="context-usage-popover-row"><span>Budget</span><b>{limit} tok</b></span>
          {context.showBar && (
            <span className="context-usage-popover-bar" data-testid="context-bar">
              <span style={{ width: `${context.percent}%`, background: context.color }} />
            </span>
          )}
          <span className="context-usage-popover-note">{context.detail}</span>
        </span>
      </div>
    )
  }

  return (
    <div
      data-testid="context-usage"
      data-context-status={context.usage.status}
      data-context-severity={context.severity}
      title={context.detail}
      className="mt-1.5"
      // A bar and a text label are different heights, so a row of agent cards rendered ragged
      // wherever one agent had a measured context and its neighbour only an estimate. Reserving
      // the taller of the two keeps the grid on one baseline whichever way each card resolves.
      style={{ minHeight: 14 }}
    >
      {context.showBar && (
        <div
          data-testid="context-bar"
          className="w-full rounded-full overflow-hidden"
          style={{ height: 2, background: 'var(--surface-3)' }}
        >
          <div
            className="h-full rounded-full"
            style={{
              width: `${context.percent}%`,
              background: context.color,
              // The motion scale, not Tailwind's default easing — this was the last ad-hoc
              // `transition-all duration-500` on the surfaces this pass covered.
              transition: 'width var(--dur-slow) var(--ease), background var(--dur-base) var(--ease)',
            }}
          />
        </div>
      )}
      {(!context.showBar || context.usage.status === 'estimated') && (
        <span className="block truncate text-[10px] mt-0.5" style={{ color: context.color }}>
          {context.label}
        </span>
      )}
    </div>
  )
}
