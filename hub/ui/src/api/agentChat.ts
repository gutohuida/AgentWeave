import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { useSSE } from '@/hooks/useSSE'
import { NEW_SESSION_ID } from '@/lib/constants'

export type TimelineEntryKind = 'operator_input' | 'agent_output' | 'inbound_peer' | 'outbound_peer'

export type AgentOutputKind =
  | 'text'
  | 'thinking'
  | 'tool_use'
  | 'tool_result'
  | 'status'
  | 'diagnostic'
  | 'error'

/** One entry in the merged conversation timeline (task 8.3) — matches
 * hub/hub/api/v1/agent_chat.py's `TimelineEntry`. */
export interface TimelineEntry {
  id: string
  kind: TimelineEntryKind
  content: string
  timestamp: string
  delivery_state: 'delivered' | 'queued'
  /** The *other* agent's name — set for inbound_peer/outbound_peer only. */
  participant?: string | null
  /** agent_output only. */
  output_kind?: AgentOutputKind | null
  payload?: Record<string, unknown> | null
  run_id?: string | null
  sequence?: number | null
  /** operator_input/inbound_peer only. */
  hop_depth?: number | null
  hop_budget_exceeded?: boolean | null
}

export interface ChatHistoryResponse {
  session_id: string | null
  agent: string
  entries: TimelineEntry[]
}

const QUEUE_EVENT_TYPES = new Set([
  'queue_entry_queued',
  'queue_entry_delivered',
  'queue_entry_withdrawn',
  'queue_chain_suspended',
])

/** True if an SSE event names `agent` as its target, across the various
 * payload shapes used by message_created (`to` or `recipient`), agent_output
 * (`agent`), and the queue lifecycle events (`agent`) that move entries
 * between the undelivered and delivered states this timeline renders. */
export function eventTargetsAgent(eventType: string, data: unknown, agent: string): boolean {
  if (eventType !== 'message_created' && eventType !== 'agent_output' && !QUEUE_EVENT_TYPES.has(eventType)) {
    return false
  }
  const d = (data ?? {}) as Record<string, unknown>
  return d.to === agent || d.recipient === agent || d.agent === agent
}

export function useAgentChatHistory(agent: string | null, sessionId: string | null) {
  const { isConfigured } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    if (agent && eventTargetsAgent(event.type, event.data, agent)) {
      queryClient.invalidateQueries({ queryKey: ['agent', agent, 'chat', sessionId] })
    }
  })

  return useQuery<ChatHistoryResponse>({
    queryKey: ['agent', agent, 'chat', sessionId],
    queryFn: () => getJson<ChatHistoryResponse>(`/api/v1/agent/${agent}/chat/${sessionId}`),
    enabled: isConfigured && !!agent && !!sessionId && sessionId !== NEW_SESSION_ID,
  })
}

export function useAgentRecentChat(agent: string | null, limit: number = 50) {
  const { isConfigured } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    if (agent && eventTargetsAgent(event.type, event.data, agent)) {
      queryClient.invalidateQueries({ queryKey: ['agent', agent, 'chat', 'recent', limit] })
    }
  })

  return useQuery<ChatHistoryResponse>({
    queryKey: ['agent', agent, 'chat', 'recent', limit],
    queryFn: () => getJson<ChatHistoryResponse>(`/api/v1/agent/${agent}/chat?limit=${limit}`),
    enabled: isConfigured && !!agent,
  })
}
