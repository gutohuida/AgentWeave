import type { AgentConversation } from '@/api/agentChat'

/** One row in a conversation list: either a conversation, or a run of firings collapsed into one. */
export type ConversationRowItem =
  | { kind: 'conversation'; conversation: AgentConversation }
  | { kind: 'loopGroup'; loopId: string; label: string; conversations: AgentConversation[] }

/** Below this, a run stays as plain rows. Collapsing a single firing hides a conversation behind a
 *  click and gains nothing — the marker already says which loop it came from. Two is where a group
 *  starts saving a row rather than costing one. */
export const MIN_FIRINGS_TO_GROUP = 2

/**
 * Collapse *consecutive* firings of one loop into a single row.
 *
 * A loop firing opens a new conversation every time, so a loop left running overnight buries the
 * threads the operator typed under its own. The marker made a firing identifiable; this makes a run
 * of them cost one row instead of eleven.
 *
 * **Consecutive, not global.** Runs are broken by any conversation that is not this loop's — another
 * loop's firing, a plain job's, or one the operator started. Grouping every firing of a loop
 * wherever it appears would reorder the list, and the order *is* the information in a list sorted by
 * recency: a firing that happened between two things the operator did belongs between them. So a
 * loop that fired, was interrupted, and fired again yields two groups, correctly.
 *
 * Input order is preserved exactly, and every conversation appears exactly once.
 */
export function groupConsecutiveFirings(
  conversations: readonly AgentConversation[],
): ConversationRowItem[] {
  const items: ConversationRowItem[] = []
  let index = 0

  while (index < conversations.length) {
    const conversation = conversations[index]
    const loop = conversation.loop
    if (!loop) {
      items.push({ kind: 'conversation', conversation })
      index += 1
      continue
    }

    let end = index + 1
    while (end < conversations.length && conversations[end].loop?.id === loop.id) end += 1
    const run = conversations.slice(index, end)

    if (run.length >= MIN_FIRINGS_TO_GROUP) {
      items.push({ kind: 'loopGroup', loopId: loop.id, label: loop.label, conversations: run })
    } else {
      for (const single of run) items.push({ kind: 'conversation', conversation: single })
    }
    index = end
  }

  return items
}

/** How many conversations a row stands for — 1, or the size of the run it collapsed.
 *
 * The display caps bound *rows*, since bounding conversations would let a cap fall inside a group
 * and split it. But "Show N more" counts conversations, because that is what the operator is being
 * told is hidden. */
export function conversationCount(item: ConversationRowItem): number {
  return item.kind === 'conversation' ? 1 : item.conversations.length
}

/** The conversations a row stands for, in order. */
export function conversationsOf(item: ConversationRowItem): AgentConversation[] {
  return item.kind === 'conversation' ? [item.conversation] : item.conversations
}

/** Cap a grouped list by rows, and report how many conversations fell off the end. */
export function capRows(
  items: ConversationRowItem[],
  cap: number,
): { visible: ConversationRowItem[]; hiddenConversations: number } {
  if (items.length <= cap) return { visible: items, hiddenConversations: 0 }
  const visible = items.slice(0, cap)
  const hiddenConversations = items.slice(cap).reduce((sum, item) => sum + conversationCount(item), 0)
  return { visible, hiddenConversations }
}
