/** The conversation bar's Checkpoint control: its state, its label and why it is unavailable.
 *
 *  `ready` is gone. It used to mean "the run that was asked to write a handoff has ended", which is
 *  the inference this capability removed — readiness is now a property of a checkpoint record that
 *  exists and passed its probes, decided by the Hub and never inferred from output. */
export type HandoffState = 'idle' | 'preparing'

/** Present and labelled whether or not it can be used: an unavailable checkpoint states its reason
 *  rather than being omitted, so the control set does not shift between agents. */
export function handoffReason(
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

/** "Checkpoint" is the vocabulary the product uses now: the record is the thing, and this button
 *  is one way to produce one. */
export function handoffLabel(handoffState: HandoffState): string {
  return handoffState === 'preparing' ? 'Checkpointing…' : 'Checkpoint'
}
