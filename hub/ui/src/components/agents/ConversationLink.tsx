import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'
import { agentDestination, goTo } from '@/lib/navigation'

/** Opens an agent's conversation from anywhere (slice remaining-hidden-data): a transition a run
 *  made, or the run itself, links to where that run happened. */
export function ConversationLink({
  agent,
  conversationId,
  children,
  testId,
}: {
  agent: string
  conversationId: string
  children: ReactNode
  testId?: string
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  if (!projectId) return null
  return (
    <button
      type="button"
      className="aw-link aw-link-inline"
      data-testid={testId}
      onClick={(event) => {
        event.stopPropagation()
        goTo(agentDestination(projectId, agent, conversationId))
      }}
    >
      {children}
    </button>
  )
}
