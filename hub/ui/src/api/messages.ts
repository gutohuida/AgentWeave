import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchWithAuth, getJson } from './client'

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
  const params = agent ? `?agent=${encodeURIComponent(agent)}` : ''
  return useQuery<Message[]>({
    queryKey: ['messages', agent],
    queryFn: () => getJson<Message[]>(`/api/v1/messages${params}`),
  })
}

export function useMarkRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (messageId: string) =>
      fetchWithAuth(`/api/v1/messages/${messageId}/read`, { method: 'PATCH' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['messages'] }),
  })
}
