import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, patchJson, postJson } from './client'
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
  /** What happens when a run bound to this task ends without the task moving. */
  divergence_policy: DivergencePolicy
  escalation_agent?: string | null
  /** A run dropped this task and nothing has moved it since. */
  has_open_divergence: boolean
}

export type DivergencePolicy = 'surface' | 'retry' | 'escalate'

export const DIVERGENCE_POLICY_LABELS: Record<DivergencePolicy, string> = {
  surface: 'Tell me',
  retry: 'Try again once',
  escalate: 'Hand to another agent',
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

/**
 * How this task's neglect should be answered.
 *
 * Separate from `useUpdateTask` because it is a different kind of act: that one moves the task
 * through its lifecycle and can be refused by the transition machine, this one records a standing
 * instruction and cannot. Sharing a mutation would put both under one pending state, so setting a
 * policy would look like a status change in flight.
 */
export function useSetDivergenceHandling() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({
      id,
      ...fields
    }: {
      id: string
      divergence_policy?: DivergencePolicy
      escalation_agent?: string | null
    }) => patchJson<Task>(`/api/v1/projects/${projectId}/tasks/${id}`, fields),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'tasks'] }),
  })
}

export interface RunDivergence {
  id: string
  run_id: string
  agent: string
  task_id: string
  task_status_at_end: string
  run_exit_status: string
  policy_applied: DivergencePolicy
  outcome: 'surfaced' | 'retried' | 'escalated'
  response_run_id?: string | null
  previous_assignee?: string | null
  created_at: string
  resolved_at?: string | null
}

/** Runs that ended holding work nobody moved — including ones since picked up. */
export function useDivergences(openOnly = false) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<RunDivergence[]>({
    queryKey: ['project', projectId, 'divergences', openOnly],
    queryFn: () =>
      getJson<RunDivergence[]>(
        `/api/v1/projects/${projectId}/tasks/divergences/recent?open_only=${openOnly}`,
      ),
    enabled: isConfigured && !!projectId,
  })
}

/**
 * Start a run bound to a task.
 *
 * The binding is what makes the run answerable at its boundary, and it is the Hub that sets it —
 * so this is a trigger carrying `task_id`, not a task update. The task moves to in_progress by
 * itself, without the agent being asked.
 */
export function useStartWorkOnTask() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ taskId, agent, title }: { taskId: string; agent: string; title: string }) =>
      postJson<{ run_id?: string; conversation_id: string }>(
        `/api/v1/projects/${projectId}/agent/trigger`,
        {
          agent,
          message: `Work on task ${taskId}: ${title}`,
          task_id: taskId,
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'tasks'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agents'] })
    },
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
