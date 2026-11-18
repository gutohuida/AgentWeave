import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteJson, getJson, putJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** One quarantined test (`hub/hub/quarantine.py`, `view`): its failures count against no gate. */
export interface QuarantinedTest {
  id: string
  check: string
  test: string
  /** The flake rate when it entered. */
  flake_rate: number | null
  flips: number | null
  entered_at: string | null
  /** Consecutive passes toward leaving. */
  passes: number
  /** How many it needs to leave. */
  passes_to_exit: number
  fix_task_id: string | null
  /** The fix task; only `id` is known when the task row is gone. */
  fix_task: {
    id: string
    display_id?: string | null
    title?: string
    status?: string
    assignee?: string | null
  } | null
}

/** A test the operator marked never to be quarantined. */
export interface NeverQuarantineMark {
  id: string
  check: string
  test: string
  marked_at: string | null
}

export interface QuarantineBody {
  threshold: number
  exit_passes: number
  /** Newest entry first. */
  quarantined: QuarantinedTest[]
  /** Newest mark first. */
  marks: NeverQuarantineMark[]
}

/** A quarantined test as a check result or a landing records it when it excused the failure
 *  (`quarantine.snapshot`): kept after the test leaves. */
export interface QuarantineExcuse {
  id?: string
  check?: string
  test: string
  flake_rate?: number | null
  entered_at?: string | null
  passes?: number
  fix_task_id?: string | null
}

const key = (projectId: string | null) => ['project', projectId, 'checks', 'quarantine']

/** The project's quarantine. A Hub older than the route answers 404: nothing to show. */
export function useQuarantine() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<QuarantineBody | null, Error>({
    queryKey: key(projectId),
    queryFn: () =>
      getJson<QuarantineBody>(`/api/v1/projects/${projectId}/checks/quarantine`).then(
        (body) => body,
        (error: unknown) => {
          if ((error as { status?: number })?.status === 404) return null
          throw error
        },
      ),
    enabled: isConfigured && !!projectId,
  })
}

export function useSetNeverQuarantine() {
  const { selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, { check: string; test: string }>({
    mutationFn: (body) => putJson(`/api/v1/projects/${projectId}/checks/quarantine/marks`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key(projectId) }),
  })
}

export function useRemoveNeverQuarantine() {
  const { selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, { check: string; test: string }>({
    mutationFn: ({ check, test }) =>
      deleteJson(
        `/api/v1/projects/${projectId}/checks/quarantine/marks?check=${encodeURIComponent(check)}&test=${encodeURIComponent(test)}`,
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key(projectId) }),
  })
}
