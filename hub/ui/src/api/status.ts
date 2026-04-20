import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface StatusData {
  project_id: string
  project_name: string
  agents_active: string[]
  message_counts: { pending: number; total: number }
  task_counts: Record<string, number>
  question_counts: { unanswered: number; total: number }
}

export interface QualityConfig {
  review_required?: boolean
  docs_path?: string
  docs_threshold?: string
  echo_chamber_guard?: string
  attribution_tag?: boolean
  dependency_check?: boolean
}

export interface SessionSyncData {
  synced: boolean
  synced_at?: string
  data?: {
    quality?: QualityConfig
    [key: string]: unknown
  }
}

export function useStatus() {
  const { isConfigured } = useConfigStore()
  return useQuery<StatusData>({
    queryKey: ['status'],
    queryFn: () => getJson<StatusData>('/api/v1/status'),
    refetchInterval: 30_000,
    enabled: isConfigured,
  })
}

export function useSessionSync() {
  const { isConfigured } = useConfigStore()
  return useQuery<SessionSyncData>({
    queryKey: ['session-sync'],
    queryFn: () => getJson<SessionSyncData>('/api/v1/session/sync'),
    refetchInterval: 60_000,
    enabled: isConfigured,
  })
}
