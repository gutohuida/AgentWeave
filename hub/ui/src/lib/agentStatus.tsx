import type { AgentSummary } from '@/api/agents'

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

/**
 * Single source of truth for the context-bar color thresholds. Previously
 * duplicated verbatim in 3 components (AgentDetailPanel, OverviewPage,
 * AgentsPage) — Q6.
 */
export function contextBarColor(percent: number, warning: boolean): string {
  if (warning || percent >= 70) return 'var(--red)'
  if (percent >= 40) return 'var(--amber)'
  return 'var(--green)'
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

const DEV_ROLE_PILL_STYLE_SM: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 500,
  padding: '1px 5px',
  borderRadius: 9999,
  background: 'rgba(168,85,247,0.1)',
  color: 'var(--purple)',
}

const DEV_ROLE_PILL_STYLE_MD: React.CSSProperties = {
  fontSize: 11,
  padding: '4px 8px',
  borderRadius: 9999,
  background: 'rgba(168,85,247,0.1)',
  color: 'var(--purple)',
}

type DevRolePillSize = 'sm' | 'md'

/**
 * The standard "purple pill" dev-role badge. Handles both the modern
 * `dev_roles[]` array and the legacy single `dev_role` field. Pass
 * `maxItems` to cap the visible pills (used by compact card views like
 * OverviewPage and AgentsPage). Renders nothing when the agent has no
 * dev-role info. Use `size="md"` for the more spacious variant rendered
 * in detail sections (AgentInfoTab) and `size="sm"` (the default) for
 * compact list/card headers.
 */
export function DevRoleTagList({ agent, maxItems, size = 'sm' }: { agent: AgentSummary; maxItems?: number; size?: DevRolePillSize }) {
  const roles = agent.dev_roles
  const legacyRole = agent.dev_role
  if (!roles?.length && !legacyRole) return null
  const visible = maxItems != null ? (roles ?? []).slice(0, maxItems) : (roles ?? [])
  const style = size === 'md' ? DEV_ROLE_PILL_STYLE_MD : DEV_ROLE_PILL_STYLE_SM
  return (
    <>
      {visible.map((role, idx) => (
        <span key={role} style={style}>
          {agent.dev_role_labels?.[idx] ?? role}
        </span>
      ))}
      {!visible.length && legacyRole && (
        <span style={style}>
          {agent.dev_role_label ?? legacyRole}
        </span>
      )}
    </>
  )
}
