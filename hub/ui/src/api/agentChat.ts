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
  conversation_id: string | null
  session_id: string | null
  agent: string
  entries: TimelineEntry[]
}

export interface AgentConversation {
  id: string
  agent: string
  provider_session_id: string | null
  lifecycle: 'open' | 'archived'
  created_at: string
  updated_at: string
}

export function useAgentConversations(agent: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    const data = (event.data ?? {}) as Record<string, unknown>
    if (data.project_id !== projectId) return
    if (agent && data.agent === agent && data.conversation_id) {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agent', agent, 'conversations'] })
    }
  })

  return useQuery<AgentConversation[]>({
    queryKey: ['project', projectId, 'agent', agent, 'conversations'],
    queryFn: () =>
      getJson<AgentConversation[]>(`/api/v1/projects/${projectId}/agent/${agent}/conversations`),
    enabled: isConfigured && !!projectId && !!agent,
  })
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

export function useAgentChatHistory(agent: string | null, conversationId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    const d = (event.data ?? {}) as { project_id?: string }
    if (agent && d.project_id === projectId && eventTargetsAgent(event.type, event.data, agent)) {
      queryClient.invalidateQueries({
        queryKey: ['project', projectId, 'agent', agent, 'chat', conversationId],
      })
    }
  })

  return useQuery<ChatHistoryResponse>({
    queryKey: ['project', projectId, 'agent', agent, 'chat', conversationId],
    queryFn: () =>
      getJson<ChatHistoryResponse>(
        `/api/v1/projects/${projectId}/agent/${agent}/chat/${conversationId}`,
      ),
    enabled:
      isConfigured && !!projectId && !!agent && !!conversationId && conversationId !== NEW_SESSION_ID,
  })
}

export function useAgentRecentChat(agent: string | null, limit: number = 50) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    const d = (event.data ?? {}) as { project_id?: string }
    if (agent && d.project_id === projectId && eventTargetsAgent(event.type, event.data, agent)) {
      queryClient.invalidateQueries({
        queryKey: ['project', projectId, 'agent', agent, 'chat', 'recent', limit],
      })
    }
  })

  return useQuery<ChatHistoryResponse>({
    queryKey: ['project', projectId, 'agent', agent, 'chat', 'recent', limit],
    queryFn: () =>
      getJson<ChatHistoryResponse>(`/api/v1/projects/${projectId}/agent/${agent}/chat?limit=${limit}`),
    enabled: isConfigured && !!projectId && !!agent,
  })
}
