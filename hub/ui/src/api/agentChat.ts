import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

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

export function useAgentChatHistory(agent: string | null, sessionId: string | null) {
  const { isConfigured } = useConfigStore()
  return useQuery<ChatHistoryResponse>({
    queryKey: ['agent', agent, 'chat', sessionId],
    queryFn: () => getJson<ChatHistoryResponse>(`/api/v1/agent/${agent}/chat/${sessionId}`),
    enabled: isConfigured && !!agent && !!sessionId && sessionId !== 'new',
    refetchInterval: 3000, // Refetch every 3 seconds for new messages
  })
}

export function useAgentRecentChat(agent: string | null, limit: number = 50) {
  const { isConfigured } = useConfigStore()
  return useQuery<ChatMessage[]>({
    queryKey: ['agent', agent, 'chat', 'recent', limit],
    queryFn: () => getJson<ChatMessage[]>(`/api/v1/agent/${agent}/chat?limit=${limit}`),
    enabled: isConfigured && !!agent,
    refetchInterval: 3000,
  })
}
