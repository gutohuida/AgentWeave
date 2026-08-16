import { getStatusConfig } from './agentStatusConfig'

type StatusDotSize = 'sm' | 'md' | 'lg'

const DOT_SIZE_CLASS: Record<StatusDotSize, string> = {
  sm: 'h-2 w-2',
  md: 'h-2.5 w-2.5',
  lg: 'h-3 w-3',
}

/**
 * The standard status indicator: a small dot, optionally surrounded by an
 * `animate-ping` halo. Use this in any card / list / header that needs a
 * visual "is this agent running?" cue. The OverviewPage `AgentHealthCard` uses
 * a different visual (static 8x8 with glow shadow) and intentionally does not
 * use this component.
 */
export function StatusDot({ status, size = 'sm' }: { status: string; size?: StatusDotSize }) {
  const cfg = getStatusConfig(status)
  return (
    <span className={`relative flex ${DOT_SIZE_CLASS[size]} shrink-0`}>
      {cfg.pulse && (
        <span
          className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
          style={{ background: cfg.dotColor }}
        />
      )}
      <span
        className={`relative inline-flex rounded-full ${DOT_SIZE_CLASS[size]}`}
        style={{ background: cfg.dotColor }}
      />
    </span>
  )
}
