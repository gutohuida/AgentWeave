import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { useSSE } from '@/hooks/useSSE'

export interface SpecEntry {
  path: string
  updated_at?: string
  // Additive — present only for documents the index covers ("filed"); absent
  // for "unindexed" (no usable index to be filed against) and "unfiled" (the
  // index is valid and does not list this document). There is no "stale":
  // that state meant a cached row no active sync source claimed, and neither
  // the cache nor the sources exist.
  title?: string
  kind?: 'baseline' | 'system-map' | 'roadmap' | 'change-spec'
  status?: string
  parent?: string | null
  order?: number
  state?: 'filed' | 'unindexed' | 'unfiled'
}

export interface SpecDocument {
  path: string
  content: string
  updated_at?: string
}

// `source_id` and `updated_at` are gone with the push model: a source was a
// machine syncing this project's documents, and there are no longer any. The
// index is a file the Hub reads, so its state is the only thing to report.
export interface SpecManifestSummary {
  state: 'valid' | 'absent' | 'unreadable' | 'invalid'
  version: number | null
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
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<SpecListResponse>({
    queryKey: ['project', projectId, 'specs'],
    queryFn: () => getJson<SpecListResponse>(`/api/v1/projects/${projectId}/project/specs`),
    enabled: isConfigured && !!projectId,
  })
}

export function useSpec(path: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<SpecDocument>({
    queryKey: ['project', projectId, 'spec', path],
    queryFn: () =>
      getJson<SpecDocument>(
        `/api/v1/projects/${projectId}/project/spec?path=${encodeURIComponent(path ?? '')}`,
      ),
    enabled: isConfigured && !!projectId && !!path,
  })
}

export function useSpecEvents() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()

  // Invalidate spec queries when the Hub broadcasts a spec_updated SSE event
  useSSE((event) => {
    const d = event.data as { path?: string; project_id?: string }
    if (event.type === 'spec_updated' && d.project_id === projectId) {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specs'] })
      if (d?.path) {
        queryClient.invalidateQueries({ queryKey: ['project', projectId, 'spec', d.path] })
      }
    }
  })
}
