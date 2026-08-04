import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchWithAuth, getJson, patchJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface Charter {
  id: string
  project_id: string
  name: string
  content: string
  created_at: string
  updated_at: string
}

export interface CharterCreate {
  name: string
  content: string
}

export type CharterUpdate = Partial<CharterCreate>

export function useCharters() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<Charter[]>({
    queryKey: ['project', projectId, 'charters'],
    queryFn: () => getJson<Charter[]>(`/api/v1/projects/${projectId}/charters`),
    enabled: isConfigured && !!projectId,
  })
}

export function useCreateCharter() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (charter: CharterCreate) =>
      postJson<Charter>(`/api/v1/projects/${projectId}/charters`, charter),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'charters'] }),
  })
}

export function useUpdateCharter() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: CharterUpdate }) =>
      patchJson<Charter>(`/api/v1/projects/${projectId}/charters/${id}`, updates),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'charters'] }),
  })
}

export function useDeleteCharter() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: async (id: string) => {
      await fetchWithAuth(`/api/v1/projects/${projectId}/charters/${id}`, { method: 'DELETE' })
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'charters'] }),
  })
}

export function useBindAgentCharter() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ agent, charterId }: { agent: string; charterId: string | null }) =>
      patchJson(`/api/v1/projects/${projectId}/agents/${agent}`, { charter_id: charterId }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agents'] }),
  })
}
