import type { AgentSummary } from '@/api/agents'
import type { ProjectSettings } from '@/api/projects'
import type { TraceSettings } from '@/api/traces'
import { PROJECT_DEFAULTS } from '@/components/settings/settingsOptions'
import type { AgentSettingsSection, AppSettingsSection, EnvironmentSection } from '@/lib/navigation'
import type { NotifyKind } from '@/lib/notify/classify'
import { DEFAULT_NOTIFY_PREFS, type NotifyPrefs } from '@/lib/notify/prefs'

/** Which sections of each scope hold a setting that is not its default: what 'Changed only' keeps.
 *  The predicates are the ones the rows use for their own reset, so a row and its section agree;
 *  a section none of whose rows has a default (Instructions, Charters, Worktrees...) is never kept. */

export const WINDOWS_NOTIFY_DEFAULTS: Record<NotifyKind, boolean> = { ask: true, fail: true, done: false, reply: false }

export function appChangedSections(prefs: NotifyPrefs, windows: Partial<Record<NotifyKind, boolean>> | undefined): Set<AppSettingsSection> {
  const kinds = Object.keys(DEFAULT_NOTIFY_PREFS.kinds) as NotifyKind[]
  const changed =
    prefs.sound !== DEFAULT_NOTIFY_PREFS.sound ||
    prefs.volume !== DEFAULT_NOTIFY_PREFS.volume ||
    kinds.some((kind) => prefs.kinds[kind] !== DEFAULT_NOTIFY_PREFS.kinds[kind]) ||
    kinds.some((kind) => windows?.[kind] !== undefined && windows[kind] !== WINDOWS_NOTIFY_DEFAULTS[kind])
  return new Set<AppSettingsSection>(changed ? ['notifications'] : [])
}

export function projectChangedSections(settings: ProjectSettings | undefined, traces: TraceSettings | undefined): Set<EnvironmentSection> {
  const out = new Set<EnvironmentSection>()
  if (settings) {
    const d = PROJECT_DEFAULTS
    const reach = settings.reach_grants
    if (settings.allow_agent_jobs !== d.allow_agent_jobs || settings.hop_budget !== d.hop_budget || settings.turn_delivery_cap !== d.turn_delivery_cap) out.add('collaboration')
    if (settings.agent_budget !== d.agent_budget) out.add('budgets')
    if (Boolean(settings.default_permission_mode) || Boolean(reach && (reach.roots.length || reach.hosts.length))) out.add('permissions')
    if ((settings.checks_give_way ?? false) !== d.checks_give_way || Boolean(settings.generated_files)) out.add('checks')
    if (
      (settings.pr_landing ?? false) !== d.pr_landing ||
      (settings.pr_single_commit ?? false) !== d.pr_single_commit ||
      (settings.pr_ci_full_check ?? false) !== d.pr_ci_full_check ||
      (settings.pr_ci_check_names ?? []).length > 0 ||
      (settings.pr_ci_interval_minutes ?? 2) !== d.pr_ci_interval_minutes ||
      (settings.pr_ci_cutoff_minutes ?? 60) !== d.pr_ci_cutoff_minutes
    )
      out.add('landing')
    if (settings.checkpoint_mode !== d.checkpoint_mode || settings.checkpoint_threshold_value != null) out.add('checkpoints')
  }
  if (traces?.retention_days_chosen) out.add('traces')
  return out
}

/** For an agent, only its own values count. */
export function agentChangedSections(agent: AgentSummary | null | undefined): Set<AgentSettingsSection> {
  const out = new Set<AgentSettingsSection>()
  if (!agent) return out
  if (agent.permission_timeout_seconds != null || agent.question_timeout_seconds != null) out.add('running')
  if (agent.default_permission_mode || agent.reach_grants != null) out.add('permissions')
  if (agent.checkpoint_mode != null || agent.checkpoint_threshold_value != null) out.add('checkpoints')
  return out
}
