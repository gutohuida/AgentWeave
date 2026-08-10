import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, patchJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface Task {
  id: string
  project_id: string
  title: string
  description?: string
  status: string
  priority: string
  assignee?: string
  assigner?: string
  assignee_status?: string | null
  assignee_status_msg?: string | null
  assignee_last_seen?: string | null
  requirements?: string[]
  acceptance_criteria?: string[]
  deliverables?: string[]
  notes?: string
  created_at: string
  updated: string
}

export function useTasks() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<Task[]>({
    queryKey: ['project', projectId, 'tasks'],
    queryFn: () => getJson<Task[]>(`/api/v1/projects/${projectId}/tasks`),
    enabled: isConfigured && !!projectId,
  })
}

export function useUpdateTask() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      patchJson<Task>(`/api/v1/projects/${projectId}/tasks/${id}`, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'tasks'] }),
  })
}

/** `{ from_status: [reachable...] }` for the operator, as the Hub declares it. */
export type AllowedTransitions = Record<string, string[]>

/**
 * The transition map, fetched once for the operator rather than per task.
 *
 * The legal set depends on who is asking, so it deliberately does not ride on the task response —
 * a resource that varies by asker breaks what every cache assumes about it, this query key
 * included. And it is not per-task: forty cards in the same status have one answer, not forty.
 * See design D13 of `openspec/changes/2026-08-10-task-transition-machine`.
 *
 * Serving it from the same declaration the Hub enforces is the point. A copy of the map here would
 * drift, and the first symptom would be the card offering a move that is then refused.
 */
export function useAllowedTransitions() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ actor_kind: string; transitions: AllowedTransitions }>({
    queryKey: ['project', projectId, 'task-transitions'],
    queryFn: () =>
      getJson<{ actor_kind: string; transitions: AllowedTransitions }>(
        `/api/v1/projects/${projectId}/tasks/transitions/allowed`,
      ),
    enabled: isConfigured && !!projectId,
    // The map changes only when the Hub is redeployed, so refetching it per window focus is noise.
    staleTime: Infinity,
  })
}
