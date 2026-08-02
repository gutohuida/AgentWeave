import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

/**
 * Fetched once and cached (design.md's caching mitigation for `composer-intelligence`):
 * the composer's `@path`/`$skill` triggers filter this list client-side per keystroke
 * rather than issuing a request per query.
 */
export function useWorkspacePaths() {
  const { isConfigured } = useConfigStore()
  return useQuery<string[]>({
    queryKey: ['workspace', 'paths'],
    queryFn: () => getJson<string[]>('/api/v1/workspace/paths'),
    enabled: isConfigured,
    staleTime: 60_000,
  })
}
