import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, putJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface Instructions {
  content: string
}

export function useInstructions() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<Instructions>({
    queryKey: ['project', projectId, 'instructions'],
    queryFn: () => getJson<Instructions>(`/api/v1/projects/${projectId}/project/instructions`),
    enabled: isConfigured && !!projectId,
  })
}

export function useSaveInstructions() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (content: string) =>
      putJson<Instructions>(`/api/v1/projects/${projectId}/project/instructions`, { content }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'instructions'] })
    },
  })
}
