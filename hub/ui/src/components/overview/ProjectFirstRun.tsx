import { useAgents } from '@/api/agents'
import { useProjectHasNoWork } from '@/api/firstRun'
import { goTo, newConversationDestination } from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'
import { FirstRunPanel } from './FirstRunPanel'

/**
 * The first-run welcome, wired: shown while the project has no agent, or has no task and no
 * specification. Nothing is shown until both are read, so a roster that is still loading never
 * flashes "Add an agent" at a project that has one.
 */
export function ProjectFirstRun({ onAddAgent }: { onAddAgent?: () => void }) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: agents, isLoading, error } = useAgents()
  const hasNoWork = useProjectHasNoWork()
  if (isLoading || error || !agents) return null
  if (agents.length > 0 && !hasNoWork) return null
  return (
    <FirstRunPanel
      agent={agents[0]?.name ?? null}
      onAddAgent={onAddAgent}
      onAskForChange={(agent) => projectId && goTo(newConversationDestination(projectId, agent))}
    />
  )
}
