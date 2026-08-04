import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, patchJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface Question {
  id: string
  project_id: string
  from_agent: string
  question: string
  blocking: boolean
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
  })
}

export function useAnswerQuestion() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ id, answer }: { id: string; answer: string }) =>
      patchJson<Question>(`/api/v1/projects/${projectId}/questions/${id}`, { answer }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'questions'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'status'] })
    },
  })
}
