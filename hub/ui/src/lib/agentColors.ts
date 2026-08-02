/**
 * Stable per-agent colour lookup (task 8.2). The palette itself lives in
 * index.css as raw hue tokens (--agent-1..8) plus derived --agent-N-tint /
 * --agent-N-border via color-mix — this just maps a persisted `color_index`
 * (from `AgentSummary.color_index`, assigned once at registration on the Hub,
 * see hub/hub/agent_colors.py) onto those CSS variables.
 *
 * PALETTE_SIZE must match hub/hub/agent_colors.py's PALETTE_SIZE exactly —
 * both sides need to agree on when the palette wraps.
 */

export const AGENT_COLOR_PALETTE_SIZE = 8

export interface AgentColorVars {
  /** Accent: border colour and the name-label text. */
  accent: string
  /** Low-saturation background tint for a bubble/surface. */
  tint: string
  /** Discernible boundary colour, tinted with the hue. */
  border: string
}

// No colour has been assigned (e.g. an agent seen only via activity, never
// registered — see agents.py's `list_agents` fallback path) or the index is
// otherwise absent. Never derived from the agent's name; falls back to a
// neutral, always-legible treatment instead.
const NEUTRAL: AgentColorVars = {
  accent: 'var(--text-3)',
  tint: 'var(--surface-2)',
  border: 'var(--border)',
}

export function agentColorVars(colorIndex: number | null | undefined): AgentColorVars {
  if (colorIndex == null || colorIndex < 0) return NEUTRAL
  const hue = (colorIndex % AGENT_COLOR_PALETTE_SIZE) + 1
  return {
    accent: `var(--agent-${hue})`,
    tint: `var(--agent-${hue}-tint)`,
    border: `var(--agent-${hue}-border)`,
  }
}
