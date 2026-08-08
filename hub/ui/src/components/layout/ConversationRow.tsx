import { conversationLabel, type AgentConversation } from '@/api/agentChat'

/** What each attention state looks like at rest.
 *
 * `waiting` is the one that matters: a run that stopped for the operator is invisible today
 * unless you open the conversation it stopped in, while the agent's answer timeout counts down.
 * Colour here is information, not decoration — an idle conversation carries none. */
const ATTENTION: Record<AgentConversation['attention'], { color: string; label: string } | null> = {
  running: { color: 'var(--green)', label: 'Running' },
  waiting: { color: 'var(--amber)', label: 'Waiting for you' },
  idle: null,
}

interface ConversationRowProps {
  conversation: AgentConversation
  active: boolean
  onOpen: () => void
  /** The owning agent's identity colour, drawn as a persistent leading edge. Set in the recency
   *  view, where rows from different agents are interleaved; unset in the tree, where the parent
   *  agent row already carries the colour. Never a hover tint — that defeats scanning, which is
   *  the only reason the recency view exists. */
  agentColor?: string
  /** Shown in the recency view, where the agent is not implied by the row's position. */
  agentName?: string
  testId: string
}

export function ConversationRow({
  conversation,
  active,
  onOpen,
  agentColor,
  agentName,
  testId,
}: ConversationRowProps) {
  const attention = ATTENTION[conversation.attention]
  const label = conversationLabel(conversation)

  return (
    <button
      type="button"
      className="row-item"
      data-testid={testId}
      data-active={active ? 'true' : 'false'}
      data-attention={conversation.attention}
      data-origin={conversation.origin}
      aria-current={active ? 'page' : undefined}
      onClick={onOpen}
      title={agentName ? `${label} — ${agentName}` : label}
    >
      {agentColor && (
        <span
          data-testid={`${testId}-edge`}
          aria-hidden="true"
          className="h-4 w-[2px] shrink-0 rounded-full"
          style={{ background: agentColor }}
        />
      )}
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {conversation.origin === 'peer' && (
        <span
          data-testid={`${testId}-origin`}
          className="shrink-0 text-[10px]"
          style={{ color: 'var(--text-3)' }}
          title="Started by another agent"
        >
          peer
        </span>
      )}
      {attention && (
        <span
          data-testid={`${testId}-attention`}
          className="h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ background: attention.color }}
          title={attention.label}
          aria-label={attention.label}
          role="img"
        />
      )}
    </button>
  )
}
