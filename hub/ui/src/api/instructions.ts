import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, putJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface Instructions {
  content: string
}

export function useInstructions() {
  const { isConfigured } = useConfigStore()
  return useQuery<Instructions>({
    queryKey: ['instructions'],
    queryFn: () => getJson<Instructions>('/api/v1/project/instructions'),
    enabled: isConfigured,
  })
}

export function useSaveInstructions() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (content: string) =>
      putJson<Instructions>('/api/v1/project/instructions', { content }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['instructions'] })
    },
  })
}
