import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface DirectoryEntry {
  name: string
  path: string
}

export interface DirectoryListing {
  path: string
  parent: string | null
  entries: DirectoryEntry[]
  reason?: string | null
}

/** Directory listing — instance-scoped, not project-scoped: it backs choosing a project
 * directory before a project exists (2026-08-04-hub-model-control-and-provisioning). */
export function useDirectoryListing(path: string | null) {
  const { isConfigured } = useConfigStore()
  return useQuery<DirectoryListing>({
    queryKey: ['fs-list', path],
    queryFn: () => getJson<DirectoryListing>(`/api/v1/fs/list?path=${encodeURIComponent(path!)}`),
    enabled: isConfigured && !!path,
  })
}

/** The available browsing starting points (drive letters, or the configured workspace
 * root) — composer/chrome refinement §9.1. Rarely changes within a session; a longer
 * staleTime avoids refetching it every time the picker reopens. */
export function useFilesystemRoots() {
  const { isConfigured } = useConfigStore()
  return useQuery<{ roots: DirectoryEntry[] }>({
    queryKey: ['fs-roots'],
    queryFn: () => getJson<{ roots: DirectoryEntry[] }>('/api/v1/fs/roots'),
    enabled: isConfigured,
    staleTime: 60_000,
  })
}
