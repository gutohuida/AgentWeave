import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

/**
 * Fetched once and cached (design.md's caching mitigation for `composer-intelligence`):
 * the composer's `@path`/`$skill` triggers filter this list client-side per keystroke
 * rather than issuing a request per query.
 */
export function useWorkspacePaths() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<string[]>({
    queryKey: ['project', projectId, 'workspace', 'paths'],
    queryFn: () => getJson<string[]>(`/api/v1/projects/${projectId}/workspace/paths`),
    enabled: isConfigured && !!projectId,
    staleTime: 60_000,
  })
}
