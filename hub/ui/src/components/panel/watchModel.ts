// What the Watch tab derives from the roster, the conversations and the open questions
// (`the-side-panel-s-watch-tab-...`): who is doing what, and which conversation is on show.

import type { AgentConversation } from '@/api/agentChat'
import type { AgentSummary } from '@/api/agents'
import type { Question } from '@/api/questions'
import { hubDate } from '@/lib/hubTime'
import type { WatchChoice } from '@/store/watchChoiceStore'

export type WatchState = 'working' | 'waiting for your answer' | 'idle'

/** Waiting outranks working: an agent blocked on a question is still running, but the question is
 *  the part the operator has to see (FR-6). */
export function watchState(agent: AgentSummary, questions: readonly Question[]): WatchState {
  const asking = questions.some(
    (q) => q.from_agent === agent.name && !q.answered && !q.declined && q.asker_waiting !== false,
  )
  if (asking) return 'waiting for your answer'
  return agent.running_conversation_id || agent.status === 'running' ? 'working' : 'idle'
}

/** One agent's open conversations, newest activity first (FR-2). Sorted here, not trusted to the
 *  route's order. */
export function conversationsOf(agent: string, all: readonly AgentConversation[]): AgentConversation[] {
  return all
    .filter((c) => c.agent === agent && c.lifecycle !== 'archived')
    .sort((a, b) => hubDate(b.updated_at).getTime() - hubDate(a.updated_at).getTime())
}

/** The conversation the agent is running now, else its most recently active one (FR-3). `ordered`
 *  is newest first. Null when it has none. */
export function defaultConversation(agent: AgentSummary, ordered: readonly AgentConversation[]): AgentConversation | null {
  const running = agent.running_conversation_id
  return ordered.find((c) => c.id === running) ?? ordered[0] ?? null
}

export interface WatchResolution {
  /** The agent being watched; null when none is chosen or the remembered one no longer exists. */
  agent: AgentSummary | null
  conversations: AgentConversation[]
  /** The conversation on show; null when the agent has none yet. */
  conversation: AgentConversation | null
}

/** A hand pick that is still open wins; a closed one, or none, follows the agent (FR-4, FR-7). */
export function resolveWatch(
  choice: WatchChoice,
  agents: readonly AgentSummary[],
  all: readonly AgentConversation[],
): WatchResolution {
  const agent = choice.agent ? (agents.find((a) => a.name === choice.agent) ?? null) : null
  if (!agent) return { agent: null, conversations: [], conversation: null }
  const conversations = conversationsOf(agent.name, all)
  const picked = choice.conversationId ? conversations.find((c) => c.id === choice.conversationId) : undefined
  return { agent, conversations, conversation: picked ?? defaultConversation(agent, conversations) }
}
