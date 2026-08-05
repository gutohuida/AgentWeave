import type { AgentConversation } from '@/api/agentChat'
import { ControlOption, ControlPill } from './ComposerModelControls'

interface ComposerConversationRoutingProps {
  conversations: AgentConversation[]
  /** undefined/null means "new conversation" — matches AgentOutputPanel's own
   * NEW_CONVERSATION_VALUE convention at the call site. */
  currentConversationId?: string | null
  onSelectConversation: (id: string) => void
  onNewConversation: () => void
}

function shortId(id: string): string {
  return id.length > 16 ? `${id.slice(0, 16)}…` : id
}

/**
 * States, before sending, whether the next message continues the current conversation or
 * starts a new one — visible in the composer itself, not only behind the conversation
 * header's menu (2026-08-04-hub-model-control-and-provisioning: "A message is routed to a
 * stated conversation").
 */
export function ComposerConversationRouting({
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewConversation,
}: ComposerConversationRoutingProps) {
  const isNew = !currentConversationId
  const valueLabel = isNew ? 'New' : shortId(currentConversationId)

  return (
    <ControlPill label="To" valueLabel={valueLabel}>
      {(close) => (
        <>
          <ControlOption
            active={isNew}
            label="New conversation"
            onSelect={() => {
              onNewConversation()
              close()
            }}
          />
          {conversations.map((conversation) => (
            <ControlOption
              key={conversation.id}
              active={conversation.id === currentConversationId}
              label={shortId(conversation.id)}
              onSelect={() => {
                onSelectConversation(conversation.id)
                close()
              }}
            />
          ))}
        </>
      )}
    </ControlPill>
  )
}
