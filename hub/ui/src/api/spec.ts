import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { useSSE } from '@/hooks/useSSE'

export interface SpecEntry {
  path: string
  updated_at?: string
}

export interface SpecDocument {
  path: string
  content: string
  updated_at?: string
}

export function useSpecList() {
  const { isConfigured } = useConfigStore()
  return useQuery<{ specs: SpecEntry[] }>({
    queryKey: ['specs'],
    queryFn: () => getJson<{ specs: SpecEntry[] }>('/api/v1/project/specs'),
    enabled: isConfigured,
  })
}

export function useSpec(path: string | null) {
  const { isConfigured } = useConfigStore()
  return useQuery<SpecDocument>({
    queryKey: ['spec', path],
    queryFn: () =>
      getJson<SpecDocument>(`/api/v1/project/spec?path=${encodeURIComponent(path ?? '')}`),
    enabled: isConfigured && !!path,
  })
}

export function useSpecEvents() {
  const queryClient = useQueryClient()

  // Invalidate spec queries when the Hub broadcasts a spec_updated SSE event
  useSSE((event) => {
    if (event.type === 'spec_updated') {
      queryClient.invalidateQueries({ queryKey: ['specs'] })
      const d = event.data as { path?: string }
      if (d?.path) {
        queryClient.invalidateQueries({ queryKey: ['spec', d.path] })
      }
    }
  })
}
