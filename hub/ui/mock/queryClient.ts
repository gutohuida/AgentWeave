import { QueryClient } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { PROJECT_ID, projectConversations, projectSummaries } from './fixtures'

/** The real rail fetches through React Query; the mock answers from the cache instead, under the
 *  very keys the hooks use, so the component on screen is the one the app ships. Nothing is ever
 *  stale and nothing refetches — there is no Hub behind the mock. */
export function mockQueryClient(): QueryClient {
  const client = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, gcTime: Infinity, retry: false, refetchOnMount: false } },
  })
  client.setQueryData(['projects'], projectSummaries())
  client.setQueryData(['project', PROJECT_ID, 'conversations', 'open'], projectConversations)
  for (const p of projectSummaries()) {
    if (p.id !== PROJECT_ID) client.setQueryData(['project', p.id, 'conversations', 'open'], { conversations: [], archived_count: 0 })
  }
  useConfigStore.setState({ selectedProjectId: PROJECT_ID })
  return client
}
