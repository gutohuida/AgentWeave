import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchWithAuth, getJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface Message {
  id: string
  project_id: string
  from: string
  to: string
  subject?: string
  content: string
  type: string
  timestamp: string
  read: boolean
  read_at?: string
  task_id?: string
}

export function useMessages(agent?: string) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const params = agent ? `?agent=${encodeURIComponent(agent)}` : ''
  return useQuery<Message[]>({
    queryKey: ['project', projectId, 'messages', agent],
    queryFn: () => getJson<Message[]>(`/api/v1/projects/${projectId}/messages${params}`),
    enabled: isConfigured && !!projectId,
  })
}

export interface MessageHistoryOpts {
  sort?: 'asc' | 'desc'
  conversation?: string
}

export function useMessageHistory(opts: MessageHistoryOpts = {}) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const params = new URLSearchParams({ history: 'true' })
  if (opts.sort) params.set('sort', opts.sort)
  if (opts.conversation) params.set('conversation', opts.conversation)
  return useQuery<Message[]>({
    queryKey: ['project', projectId, 'messages', 'history', opts],
    queryFn: () => getJson<Message[]>(`/api/v1/projects/${projectId}/messages?${params}`),
    enabled: isConfigured && !!projectId,
  })
}

export function useMarkRead() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (messageId: string) =>
      fetchWithAuth(`/api/v1/projects/${projectId}/messages/${messageId}/read`, {
        method: 'PATCH',
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'messages'] }),
  })
}
