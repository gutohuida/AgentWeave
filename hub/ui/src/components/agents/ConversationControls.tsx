import { Icon } from '@/components/common/Icon'
import type { AgentConversation } from '@/api/agentChat'
import { Button } from '@/components/ui/button'
import { ContextUsageIndicator } from '@/components/context/ContextUsageIndicator'

/** `ready` is gone. It used to mean "the run that was asked to write a handoff has ended",
 *  which is the inference this capability removed — readiness is now a property of a checkpoint
 *  record that exists and passed its probes, decided by the Hub and never inferred from output. */
export type HandoffState = 'idle' | 'preparing'

interface ConversationControlsProps {
  /**
   * The open conversation's own context reading, passed in rather than taken from `agent`.
   *
   * `agent.context_usage` is one reading per agent — the newest across every thread it owns — so
   * this header showed whichever conversation last reported, whichever one you were actually in.
   * Explicit prop rather than reaching into the conversation here, so the scope of the number is
   * decided at the call site where the current conversation is known.
   */
  contextUsage: AgentConversation['context_usage']
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
  if (handoffState === 'preparing') return 'Already writing one'
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
  contextUsage,
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
  const reason = handoffReason(handoffUnavailable, currentConversationId, interactionLocked, handoffState)
  const handoffDisabled = reason !== null

  // "Checkpoint" is the vocabulary the product uses now: the record is the thing, and this
  // button is one way to produce one.
  const handoffLabel = handoffState === 'preparing' ? 'Checkpointing…' : 'Checkpoint'

  return (
    // Wraps rather than overflows: this row is now shown in a 420px-wide conversation column as
    // well as a full-width one, and nothing may leave it at either.
    <div className="flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1">
      {/* The agent's name and status used to be repeated here, beside the header's own. One
          header, one identity — the duplication was invisible at full width and became three
          copies of the same word once the surface was narrowed. */}

      {/* Not `compact`: the compact form is a 2px bar with no number, which answers "is it
          filling up" and nothing else. The conversation header is where an operator decides
          whether to checkpoint, so it shows the count, the window and the percentage. */}
      <ContextUsageIndicator value={contextUsage} />

      {isRunning && (
        <Button variant="destructive" size="xs" className="shrink-0" onClick={onStop} disabled={isStopping} title="Terminate the in-progress run">
          <Icon name="stop" size={12} />
          {isStopping ? 'Stopping…' : 'Stop turn'}
        </Button>
      )}

      {/* Present and labelled whether or not it can be used: an unavailable handoff states its
          reason rather than being omitted, so the control set does not shift between agents. */}
      <Button
        variant="ghost"
        size="xs"
        className="shrink-0"
        data-testid="conversation-handoff"
        disabled={handoffDisabled}
        aria-disabled={handoffDisabled ? 'true' : undefined}
        aria-label={reason ? `${handoffLabel} — ${reason}` : handoffLabel}
        title={reason ?? 'Write a checkpoint and continue in a new conversation'}
        onClick={onHandoff}
      >
        <Icon name="move_up" size={12} />
        {handoffLabel}
      </Button>

      <Button variant="ghost" size="xs" className="shrink-0" onClick={onFoldAll}>Fold all turns</Button>
    </div>
  )
}
