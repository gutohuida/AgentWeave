import { useState } from 'react'
import type { AgentSummary } from '@/api/agents'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'

interface ControlledConversationProps {
  agent: AgentSummary
  /** Where the destination starts. `null` is "the agent has no conversation yet". */
  conversationId?: string | null
  onSelectConversation?: (conversationId: string | null) => void
}

/**
 * `AgentOutputPanel` is controlled: the destination owns which conversation is open and the panel
 * renders it. This is the smallest thing that plays App's half of that contract, so a test can
 * exercise a flow that moves the destination — sending the first message, handing over to a
 * handoff — without mounting the whole shell.
 *
 * Rendering the panel bare is still correct for anything that only reads one fixed conversation.
 */
export function ControlledConversation({
  agent,
  conversationId: initial = null,
  onSelectConversation,
}: ControlledConversationProps) {
  const [current, setCurrent] = useState<string | null>(initial)
  return (
    <AgentOutputPanel
      agent={agent}
      conversationId={current}
      onSelectConversation={(next) => {
        setCurrent(next)
        onSelectConversation?.(next)
      }}
    />
  )
}
