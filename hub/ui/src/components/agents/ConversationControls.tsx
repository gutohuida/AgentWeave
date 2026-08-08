import { Icon } from '@/components/common/Icon'
import { AgentSummary } from '@/api/agents'
import { Button } from '@/components/ui/button'
import { ContextUsageIndicator } from '@/components/context/ContextUsageIndicator'
import { StatusDot, getStatusConfig } from '@/lib/agentStatus'

export type HandoffState = 'idle' | 'preparing' | 'ready'

interface ConversationControlsProps {
  agent: AgentSummary
  isRunning: boolean
  isStopping: boolean
  onStop: () => void
  /** Undefined when no conversation is open — one of the reasons handoff is unavailable. */
  currentConversationId?: string
  handoffState: HandoffState
  handoffUnavailable: boolean
  interactionLocked: boolean
  onHandoff: () => void
  onFoldAll: () => void
}

function handoffReason(
  handoffUnavailable: boolean,
  currentConversationId: string | undefined,
  interactionLocked: boolean,
  handoffState: HandoffState,
): string | null {
  if (handoffUnavailable) return 'Requires an automatically managed runner'
  if (!currentConversationId) return 'Start a conversation first'
  if (handoffState === 'preparing') return 'Already preparing'
  if (handoffState === 'ready') return 'Already ready — send a message to resume it'
  if (interactionLocked) return 'Unavailable while the agent is busy'
  return null
}

/**
 * The conversation header's resting control set.
 *
 * There is no overflow menu here any more. It held "New conversation", every one of the agent's
 * conversations, "Handoff" and "Agent details" — three of which belong in navigation and one of
 * which is too important to hide. Conversation switching moved to the rail, agent settings to the
 * agent's row menu, and handoff onto this header as a labelled control, visible at rest:
 * *"handoff needs an explicit place to sit. Where we know it's there. Users might not know or
 * forget about the handoff."*
 */
export function ConversationControls({
  agent,
  isRunning,
  isStopping,
  onStop,
  currentConversationId,
  handoffState,
  handoffUnavailable,
  interactionLocked,
  onHandoff,
  onFoldAll,
}: ConversationControlsProps) {
  const statusCfg = getStatusConfig(agent.status)

  const reason = handoffReason(handoffUnavailable, currentConversationId, interactionLocked, handoffState)
  const handoffDisabled = reason !== null

  const handoffLabel =
    handoffState === 'preparing' ? 'Preparing…' : handoffState === 'ready' ? 'Handoff ready' : 'Handoff'

  return (
    <div className="flex items-center gap-3">
      {/* Active-agent indicator */}
      <span className="flex items-center gap-1.5 min-w-0">
        <StatusDot status={agent.status} size="sm" />
        <span className="text-xs font-medium truncate" style={{ color: 'var(--text)' }}>
          {agent.name}
        </span>
        <span className="text-[11px]" style={{ color: statusCfg.labelColor }}>
          {statusCfg.label}
        </span>
      </span>

      <ContextUsageIndicator value={agent.context_usage} compact />

      <div className="flex-1" />

      {isRunning && (
        <Button variant="destructive" size="xs" onClick={onStop} disabled={isStopping} title="Terminate the in-progress run">
          <Icon name="stop" size={12} />
          {isStopping ? 'Stopping…' : 'Stop turn'}
        </Button>
      )}

      {/* Present and labelled whether or not it can be used: an unavailable handoff states its
          reason rather than being omitted, so the control set does not shift between agents. */}
      <Button
        variant="ghost"
        size="xs"
        data-testid="conversation-handoff"
        disabled={handoffDisabled}
        aria-disabled={handoffDisabled ? 'true' : undefined}
        aria-label={reason ? `${handoffLabel} — ${reason}` : handoffLabel}
        title={reason ?? 'Prepare a durable handoff before ending this session'}
        onClick={onHandoff}
      >
        <Icon name="move_up" size={12} />
        {handoffLabel}
      </Button>

      <Button variant="ghost" size="xs" onClick={onFoldAll}>Fold all turns</Button>
    </div>
  )
}
