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
