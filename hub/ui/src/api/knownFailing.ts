import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
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

/** A disturbed check run, shown beside the list and never in it (`a-disturbed-check-run-is-not-a-
 *  pile-of-flaky-tests`, FR-2): many tests failed at once and every one passed when re-run. */
export interface DisturbedRun {
  id: string
  run_id: string | null
  task_id: string | null
  check: string | null
  /** How many tests failed in the first run, and how many of them passed on the rerun. */
  failed: number | null
  passed_on_rerun: number | null
  threshold: number | null
  tests: string[]
  first_run_output: string
  at: string | null
}

interface KnownFailingBody {
  entries: KnownFailingEntry[]
  /** The last seven days of them; absent from a Hub older than the change. */
  disturbed?: DisturbedRun[]
}

function useKnownFailingBody<T>(select: (body: KnownFailingBody | null) => T) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<KnownFailingBody | null, Error, T>({
    queryKey: ['project', projectId, 'checks', 'known-failing'],
    queryFn: () =>
      getJson<KnownFailingBody>(`/api/v1/projects/${projectId}/checks/known-failing`).then(
        (body) => body,
        (error: unknown) => {
          if ((error as { status?: number })?.status === 404) return null
          throw error
        },
      ),
    select,
    enabled: isConfigured && !!projectId,
  })
}

/** The project's known-failing list. A Hub older than the route answers 404: it has no list to
 *  show, which is not a failed read. */
export function useKnownFailing() {
  return useKnownFailingBody<KnownFailingEntry[] | null>((body) => (body ? body.entries : null))
}

/** The disturbed runs of the last seven days, newest first. */
export function useDisturbedRuns() {
  return useKnownFailingBody<DisturbedRun[]>((body) => body?.disturbed ?? [])
}

/** What the clear action did: how many open flaky fix tasks it closed and how many it left. */
export interface ClearStableResult {
  closed: number
  left: number
  closed_ids: string[]
  left_ids: string[]
}

/** Close every open Hub-filed flaky fix task whose test is off the list (FR-6). */
export function useClearStableFixTasks() {
  const { selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()
  return useMutation<ClearStableResult>({
    mutationFn: () =>
      postJson<ClearStableResult>(`/api/v1/projects/${projectId}/checks/known-failing/clear-stable`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'checks', 'known-failing'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'tasks'] })
    },
  })
}
