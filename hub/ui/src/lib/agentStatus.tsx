/**
 * Single source of truth for agent status presentation. Previously duplicated
 * in 2 components (AgentCard, AgentInfoTab) — Q6.
 */

export interface StatusConfig {
  dotColor: string
  label: string
  pulse: boolean
  labelColor: string
}

export const STATUS_CONFIG: Record<string, StatusConfig> = {
  running: { dotColor: 'var(--green)', label: 'Running', pulse: true,  labelColor: 'var(--green)' },
  stalled: { dotColor: 'var(--amber)', label: 'Stalled', pulse: false, labelColor: 'var(--amber)' },
  active:  { dotColor: 'var(--green)', label: 'Active',  pulse: false, labelColor: 'var(--green)' },
  idle:    { dotColor: 'var(--text-3)', label: 'Idle',    pulse: false, labelColor: 'var(--text-3)' },
  waiting: { dotColor: 'var(--amber)',  label: 'Waiting', pulse: false, labelColor: 'var(--amber)' },
}

const FALLBACK_STATUS: StatusConfig = {
  dotColor: 'var(--text-3)',
  label: '',
  pulse: false,
  labelColor: 'var(--text-3)',
}

/** Returns the status config for a raw status string, falling back to a neutral
 * "unknown" config when the status is not recognized. Use this everywhere a
 * component needs the dot color / pulse / label — never `STATUS_CONFIG[x] ??`
 * inline. The label falls back to the raw status string for unknown values. */
export function getStatusConfig(status: string): StatusConfig {
  const cfg = STATUS_CONFIG[status]
  if (cfg) return cfg
  return { ...FALLBACK_STATUS, label: status }
}

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
