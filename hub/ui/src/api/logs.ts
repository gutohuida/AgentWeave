import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { useSSE } from '@/hooks/useSSE'

export interface EventLogEntry {
  id: string
  project_id: string
  event_type: string
  agent?: string
  data?: Record<string, unknown>
  severity: string
  timestamp: string
}

export interface LogsOpts {
  agent?: string
  event_type?: string
  severity?: string
  since?: string
  limit?: number
  live?: boolean
}

export function useLogs(opts: LogsOpts = {}) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()

  const params = new URLSearchParams()
  if (opts.agent) params.set('agent', opts.agent)
  if (opts.event_type) params.set('event_type', opts.event_type)
  if (opts.severity && opts.severity !== 'all') params.set('severity', opts.severity)
  if (opts.since) params.set('since', opts.since)
  params.set('limit', String(opts.limit ?? 500))

  const query = useQuery<EventLogEntry[]>({
    queryKey: ['project', projectId, 'logs', opts.agent, opts.event_type, opts.severity],
    queryFn: () => getJson<EventLogEntry[]>(`/api/v1/projects/${projectId}/logs?${params}`),
    enabled: isConfigured && !!projectId,
    staleTime: 0,
  })

  // Invalidate immediately when any SSE event arrives (live mode)
  useSSE(
    opts.live
      ? (event) => {
          const d = (event.data ?? {}) as { project_id?: string }
          if (d.project_id === projectId) {
            queryClient.invalidateQueries({ queryKey: ['project', projectId, 'logs'] })
          }
        }
      : undefined
  )

  return query
}

export function useLogAgents() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<string[]>({
    queryKey: ['project', projectId, 'logs', 'agents'],
    queryFn: () => getJson<string[]>(`/api/v1/projects/${projectId}/logs/agents`),
    enabled: isConfigured && !!projectId,
    staleTime: 10_000,
  })
}
