import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { useSSE } from '@/hooks/useSSE'
import { NEW_SESSION_ID } from '@/lib/constants'

export interface ChatMessage {
  id: string
  role: 'user' | 'agent'
  content: string
  timestamp: string
}

export interface ChatHistoryResponse {
  session_id: string
  agent: string
  messages: ChatMessage[]
}

/** True if an SSE event names `agent` as its target, across the various
 * payload shapes used by message_created (`to` or `recipient`) and
 * agent_output (`agent`) broadcast sites. */
export function eventTargetsAgent(eventType: string, data: unknown, agent: string): boolean {
  if (eventType !== 'message_created' && eventType !== 'agent_output') return false
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

  return useQuery<ChatMessage[]>({
    queryKey: ['agent', agent, 'chat', 'recent', limit],
    queryFn: () => getJson<ChatMessage[]>(`/api/v1/agent/${agent}/chat?limit=${limit}`),
    enabled: isConfigured && !!agent,
  })
}
