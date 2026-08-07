import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { useSSE } from '@/hooks/useSSE'

export interface UnaskedQuestion {
  id: string
  agent: string
  run_id: string | null
  conversation_id: string | null
  question: string
  status: 'pending' | 'asked' | 'dismissed'
  created_at: string
  resolved_at: string | null
}

/** Questions an agent ended a turn on without ever routing through `ask_user`.
 *
 * Unlike a permission request, nothing is blocked on these — the turn has already ended. They
 * still refetch on an interval as well as on SSE, because a dropped event would leave the
 * operator looking at a finished conversation with no sign that the agent is waiting on them.
 */
export function usePendingUnaskedQuestions() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    const d = (event.data ?? {}) as { project_id?: string }
    if (
      (event.type === 'question_not_asked' || event.type === 'unasked_question_resolved') &&
      d.project_id === projectId
    ) {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'unasked-questions'] })
    }
  })

  return useQuery<UnaskedQuestion[]>({
    queryKey: ['project', projectId, 'unasked-questions'],
    queryFn: () =>
      getJson<UnaskedQuestion[]>(`/api/v1/projects/${projectId}/unasked-questions`),
    enabled: isConfigured && !!projectId,
    refetchInterval: 5000,
  })
}

/** Re-prompt the agent to ask its question through the tool, or decide it was not one.
 *
 * Both actions resolve the record, so they share an invalidation. The re-prompt's wording lives
 * on the server: it is what turns prose into a tool call, and that is not a click handler's job.
 */
export function useResolveUnaskedQuestion() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'ask' | 'dismiss' }) =>
      postJson(`/api/v1/projects/${projectId}/unasked-questions/${id}/${action}`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'unasked-questions'] })
    },
  })
}
