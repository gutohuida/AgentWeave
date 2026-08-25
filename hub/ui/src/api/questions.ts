import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, patchJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface QuestionOption {
  label: string
  /** What choosing this actually means — the reason options beat a bare text box. */
  description: string
}

export interface Question {
  id: string
  project_id: string
  from_agent: string
  question: string
  blocking: boolean
  /** Answers the agent offered. Empty means open-ended; the operator may always type instead. */
  options?: QuestionOption[]
  /** Short chip naming the decision, e.g. "Database". */
  header?: string | null
  multi_select?: boolean
  answer_labels?: string[]
  answered: boolean
  answer?: string
  /** Batch identity. One `ask_user` call can carry several questions; a question asked on its
   *  own reports `batch_size: 1`, so nothing has to special-case the unbatched form. */
  batch_id?: string | null
  batch_index?: number
  batch_size?: number
  created_at: string
  answered_at?: string
  /** The operator closed this without answering. Distinct from `answered`: an empty answer says
   *  they responded with nothing, this says they chose not to respond. */
  declined?: boolean
  declined_at?: string | null
  /** Whether anyone is still waiting on this. False once the asking run has ended — its `ask_user`
   *  call is gone, so nothing receives an answer as a result any more. Absent means "assume yes",
   *  which matches the Hub's own presumption for a question with no recorded asker. */
  asker_waiting?: boolean
}

/** How long a run waits for an answer when its agent sets no `question_timeout_seconds`.
 *
 * Mirrors `QUESTION_ANSWER_TIMEOUT` in `hub/hub/mcp_server.py` — 240s, what an ordinary MCP tool
 * call was measured tolerating. Restated here because nothing on the wire carries it: the
 * questions payload has no timeout field at all, and the roster reports `null` to mean "the
 * built-in default" without ever saying what that default is. `AgentSettingsPage` already states
 * the same 240 as its placeholder, so this is the second copy, not the first.
 */
export const DEFAULT_QUESTION_TIMEOUT_SECONDS = 240

export function useQuestions(answered?: boolean) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const params = answered !== undefined ? `?answered=${answered}` : ''
  return useQuery<Question[]>({
    queryKey: ['project', projectId, 'questions', answered],
    queryFn: () => getJson<Question[]>(`/api/v1/projects/${projectId}/questions${params}`),
    enabled: isConfigured && !!projectId,
    // An agent blocks on a question it asked, so arriving late is close to not arriving. SSE
    // already invalidates this key; the interval is the backstop for a dropped event.
    refetchInterval: 3000,
  })
}

export function useAnswerQuestion() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ id, answer, labels }: { id: string; answer: string; labels?: string[] }) =>
      patchJson<Question>(`/api/v1/projects/${projectId}/questions/${id}`, {
        answer,
        labels: labels ?? [],
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'questions'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'status'] })
    },
  })
}

/**
 * Close a question without answering it.
 *
 * Also invalidates tasks: a question that had parked a task as blocked releases it, so the board is
 * stale the moment this succeeds.
 */
export function useDeclineQuestion() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ id }: { id: string }) =>
      postJson<Question>(`/api/v1/projects/${projectId}/questions/${id}/decline`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'questions'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'status'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'tasks'] })
    },
  })
}
