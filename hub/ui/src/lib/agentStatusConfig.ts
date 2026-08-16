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
