import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** One test the approval checks saw fail and then pass when re-run (`hub/hub/flaky_tests.py`). */
export interface FlakyTest {
  check: string
  /** The pytest node id; null when the whole check flaked without naming a test. */
  test: string | null
  occurrences: number
  first_seen: string | null
  last_seen: string | null
  task_ids: string[]
  run_ids: string[]
}

export interface FlakyReport {
  window_days: number
  /** Open flakes, most recently seen first. */
  flaky: FlakyTest[]
  /** What the operator last did about the list, if anything. */
  handled: { through: string; task_id: string | null; count: number; at: string | null } | null
}

/** The project's open flaky tests. SSE (`checks_flaky`) invalidates it. A Hub older than the
 *  route answers 404: it has no list to show, which is not a failed read. */
export function useFlakyTests() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<FlakyReport | null>({
    queryKey: ['project', projectId, 'checks', 'flaky'],
    queryFn: () =>
      getJson<FlakyReport>(`/api/v1/projects/${projectId}/checks/flaky`).catch((error: unknown) => {
        if ((error as { status?: number })?.status === 404) return null
        throw error
      }),
    enabled: isConfigured && !!projectId,
  })
}

/** Hand the open list to a new task (`createTask`), or dismiss it until a test flakes again. */
export function useHandleFlakyTests() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (createTask: boolean) =>
      postJson<{ task_id: string | null; count: number }>(
        `/api/v1/projects/${projectId}/checks/flaky/handled`,
        { create_task: createTask },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'checks', 'flaky'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'tasks'] })
    },
  })
}
