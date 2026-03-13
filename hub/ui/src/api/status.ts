import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'

export interface StatusData {
  project_id: string
  project_name: string
  agents_active: string[]
  message_counts: { pending: number; total: number }
  task_counts: Record<string, number>
  question_counts: { unanswered: number; total: number }
}

export function useStatus() {
  return useQuery<StatusData>({
    queryKey: ['status'],
    queryFn: () => getJson<StatusData>('/api/v1/status'),
    refetchInterval: 30_000,
  })
}
