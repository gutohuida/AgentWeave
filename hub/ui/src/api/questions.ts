import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, patchJson } from './client'

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
  const params = answered !== undefined ? `?answered=${answered}` : ''
  return useQuery<Question[]>({
    queryKey: ['questions', answered],
    queryFn: () => getJson<Question[]>(`/api/v1/questions${params}`),
  })
}

export function useAnswerQuestion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, answer }: { id: string; answer: string }) =>
      patchJson<Question>(`/api/v1/questions/${id}`, { answer }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['questions'] })
      queryClient.invalidateQueries({ queryKey: ['status'] })
    },
  })
}
