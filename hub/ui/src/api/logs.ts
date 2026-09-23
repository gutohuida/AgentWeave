import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
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

/**
 * The project's log, newest page first (F252), returned in time order for the screen.
 *
 * The route answers newest first and `offset` counts back from the newest, so the first page is
 * the latest `limit` entries and `loadOlder` asks for the page before it. It used to fetch the
 * route's *oldest* 500 and could never show a later entry. Pages are joined and de-duplicated by
 * id: an entry that arrives between two requests shifts the offsets by one, so the next page can
 * repeat a row, never skip one.
 */
export function useLogs(opts: LogsOpts = {}) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()
  const pageSize = opts.limit ?? 500

  const params = new URLSearchParams()
  if (opts.agent) params.set('agent', opts.agent)
  if (opts.event_type) params.set('event_type', opts.event_type)
  if (opts.severity && opts.severity !== 'all') params.set('severity', opts.severity)
  if (opts.since) params.set('since', opts.since)
  params.set('limit', String(pageSize))

  const query = useInfiniteQuery<EventLogEntry[]>({
    queryKey: ['project', projectId, 'logs', opts.agent, opts.event_type, opts.severity],
    queryFn: ({ pageParam }) =>
      getJson<EventLogEntry[]>(
        `/api/v1/projects/${projectId}/logs?${params}&offset=${pageParam as number}`,
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) =>
      lastPage.length < pageSize ? undefined : allPages.length * pageSize,
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

  const seen = new Set<string>()
  const entries: EventLogEntry[] = []
  // Pages are newest first and so is each page; walking them backwards gives time order.
  for (const page of [...(query.data?.pages ?? [])].reverse()) {
    for (const entry of [...page].reverse()) {
      if (seen.has(entry.id)) continue
      seen.add(entry.id)
      entries.push(entry)
    }
  }

  return {
    data: query.data ? entries : undefined,
    isLoading: query.isLoading,
    error: query.error,
    dataUpdatedAt: query.dataUpdatedAt,
    hasOlder: query.hasNextPage,
    loadOlder: () => query.fetchNextPage(),
    isLoadingOlder: query.isFetchingNextPage,
  }
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
