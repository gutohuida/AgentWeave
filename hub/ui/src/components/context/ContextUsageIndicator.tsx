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

  return (
    <div
      data-testid="context-usage"
      data-context-status={context.usage.status}
      data-context-severity={context.severity}
      title={context.detail}
      className={compact ? 'mt-1.5' : 'flex items-center gap-3'}
    >
      {!compact && (
        <span className="text-xs font-medium whitespace-nowrap" style={{ color: context.color }}>
          {context.label}
        </span>
      )}
      {context.showBar && (
        <div
          data-testid="context-bar"
          className={`${compact ? 'w-full' : 'w-12'} rounded-full overflow-hidden`}
          style={{ height: compact ? 2 : 4, background: 'var(--surface-3)' }}
        >
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${context.percent}%`, background: context.color }}
          />
        </div>
      )}
      {compact && (!context.showBar || context.usage.status === 'estimated') && (
        <span className="block truncate text-[10px] mt-0.5" style={{ color: context.color }}>
          {context.label}
        </span>
      )}
    </div>
  )
}
