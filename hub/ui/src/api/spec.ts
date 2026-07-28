import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { useSSE } from '@/hooks/useSSE'

export interface SpecEntry {
  path: string
  updated_at?: string
  // Additive — present only for documents covered by the active valid
  // manifest ("filed"); absent for "unindexed" (never reconciled),
  // "unfiled" (reconciled but no manifest entry), or "stale" documents.
  title?: string
  kind?: 'baseline' | 'system-map' | 'roadmap' | 'change-spec'
  status?: string
  parent?: string | null
  order?: number
  state?: 'filed' | 'unindexed' | 'unfiled' | 'stale'
}

export interface SpecDocument {
  path: string
  content: string
  updated_at?: string
}

export interface SpecManifestSummary {
  state: 'valid' | 'absent' | 'unreadable' | 'invalid'
  version: number | null
  source_id: string
  updated_at: string
}

export interface SpecDiagnostic {
  code: string
  path?: string | null
  field?: string | null
  expected?: string | null
  actual?: string | null
  source_ids?: string[] | null
}

export interface SpecMissingEntry {
  path: string
  title: string
  kind: string
  status: string
  parent: string | null
  order: number
}

export interface SpecListResponse {
  specs: SpecEntry[]
  home: string | null
  manifest: SpecManifestSummary | null
  missing: SpecMissingEntry[]
  diagnostics: SpecDiagnostic[]
}

export function useSpecList() {
  const { isConfigured } = useConfigStore()
  return useQuery<SpecListResponse>({
    queryKey: ['specs'],
    queryFn: () => getJson<SpecListResponse>('/api/v1/project/specs'),
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
