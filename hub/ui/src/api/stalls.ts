import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { stallNotice } from '@/lib/stalls'
import { toast } from '@/lib/toast'

/** One time the project's work stopped moving (`hub/hub/stalls.py`). */
export interface Stall {
  id: string
  key: string
  cause:
    | 'loop_stalled'
    | 'delivery_refused'
    | 'integration_skipped'
    | 'integration_failed'
    | 'review_unstaffed'
    | 'dead_run'
    | 'stuck_task'
    | 'no_progress'
    | 'checks_unjudged'
  reason: string
  task_id: string | null
  loop_id: string | null
  first_seen_at: string
  last_seen_at: string
  seen_count: number
  /** The mender's thread for this stall; null while the mender is off or could not be woken. */
  conversation_id: string | null
  mender_turns: number
  outcome: 'open' | 'fixed' | 'gave_up' | 'resolved'
  outcome_detail: string
  ended_at: string | null
  /** The controls the notice offers, derived by the Hub from the cause (D5); absent from an older Hub. */
  remedies?: StallRemedy[]
}

/** `name_checker`: name a different checker for the task; `review_yourself`: the operator's own review. */
export type StallRemedy = 'name_checker' | 'review_yourself'


/** The project's open stalls, newest first. SSE (`stall_recorded`, `stall_ended`) invalidates it. */
export function useOpenStalls() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<Stall[]>({
    queryKey: ['project', projectId, 'stalls', 'open'],
    queryFn: async () =>
      (await getJson<{ stalls: Stall[] }>(`/api/v1/projects/${projectId}/stalls?open=true`)).stalls,
    enabled: isConfigured && !!projectId,
  })
}

/** End an open stall by hand (`POST /stalls/{id}/end`, outcome `resolved`). */
export function useEndStall() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (stallId: string) =>
      postJson<Stall>(`/api/v1/projects/${projectId}/stalls/${stallId}/end`, {
        outcome: 'resolved',
        detail: 'Dismissed by the operator.',
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'stalls'] }),
  })
}

/** Name a different checker for a stalled task (`POST /tasks/{id}/checker`): recorded on its build,
 *  finished work handed to them for review, and the task's review stall ended.
 *
 *  The Hub's answer is said in a toast from here, not from the control: the stall's end reaches the
 *  page by the event stream, often before this answer does, and the control leaves with the stall,
 *  so a callback of the control's own would never run (React Query drops an unmounted caller's). */
export function useNameChecker() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ taskId, agent }: { taskId: string; agent: string; taskRef?: string | null }) =>
      postJson<{ next_turn?: string | null }>(`/api/v1/projects/${projectId}/tasks/${encodeURIComponent(taskId)}/checker`, { agent }),
    onSuccess: (answer, { agent, taskRef }) => {
      const ref = taskRef || 'the task'
      toast({
        title: `${agent} checks ${ref}`,
        description: stallNotice(answer?.next_turn ?? `${agent} checks it now.`, taskRef),
        tone: 'success',
      })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'stalls'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'tasks'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'builds'] })
    },
  })
}
