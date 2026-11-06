import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** One entry of the project's known-failing list (`hub/hub/known_failing.py`, `entry_view`). */
export interface KnownFailingEntry {
  id: string
  check: string
  /** The test's id from the check's report; null when the whole check is listed. */
  test: string | null
  whole_check: boolean
  kind: 'fails on main' | 'flaky'
  first_seen: string | null
  last_seen: string | null
  added_by_run: string | null
  passes: number
  /** The entry's owner fix task; only `id` is known when the task row is gone. */
  fix_task: {
    id: string
    display_id?: string | null
    title?: string
    status?: string
    assignee?: string | null
  } | null
}

/** The project's known-failing list. A Hub older than the route answers 404: it has no list to
 *  show, which is not a failed read. */
export function useKnownFailing() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<KnownFailingEntry[] | null>({
    queryKey: ['project', projectId, 'checks', 'known-failing'],
    queryFn: () =>
      getJson<{ entries: KnownFailingEntry[] }>(
        `/api/v1/projects/${projectId}/checks/known-failing`,
      ).then(
        (body) => body.entries,
        (error: unknown) => {
          if ((error as { status?: number })?.status === 404) return null
          throw error
        },
      ),
    enabled: isConfigured && !!projectId,
  })
}
