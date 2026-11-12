import { useAgents, type AgentSummary } from '@/api/agents'
import { agentSettingsDestination, goTo, type AgentSettingsSection } from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'

/** The four project settings an agent can hold its own value for. An agent's value replaces the
 *  project's (reach grants too: `hub/hub/reach.py` `effective_grants`), so a change here does not
 *  reach the agents named under it. */
const HOLDS: Record<string, (agent: AgentSummary) => boolean> = {
  default_permission_mode: (agent) => Boolean(agent.default_permission_mode),
  reach_grants: (agent) => agent.reach_grants != null,
  checkpoint_mode: (agent) => agent.checkpoint_mode != null,
  checkpoint_point: (agent) => agent.checkpoint_threshold_value != null,
}

export type OverriddenSetting = keyof typeof HOLDS

/** The non-archived agents holding their own value for *setting*, each opening that agent's row.
 *  Nothing is drawn when none does. */
export function AgentOverrides({ setting, section, agentLabel }: { setting: OverriddenSetting; section: AgentSettingsSection; agentLabel: string }) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: agents = [], isError } = useAgents()
  const holders = agents.filter((agent) => agent.lifecycle !== 'archived' && HOLDS[setting](agent))
  if (isError) return <p className="aw-settings-row-overrides" data-testid="setting-overrides-unavailable">Agents with their own could not be read.</p>
  if (!projectId || holders.length === 0) return null
  return (
    <p className="aw-settings-row-overrides" data-testid="setting-overrides">
      <span>Agents with their own:</span>
      {holders.map((agent) => (
        <button
          key={agent.name}
          type="button"
          className="aw-settings-row-override"
          onClick={() => goTo(agentSettingsDestination(projectId, agent.name, section, agentLabel))}
        >
          {agent.name}
        </button>
      ))}
    </p>
  )
}
