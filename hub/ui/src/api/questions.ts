import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, patchJson } from './client'
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
  created_at: string
  answered_at?: string
}

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
