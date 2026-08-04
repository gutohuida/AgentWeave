import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson, patchJson, fetchWithAuth } from './client'
import { useConfigStore } from '@/store/configStore'

export type RunnerCli = 'claude' | 'codex'

export interface Runner {
  id: string
  project_id: string
  name: string
  cli: RunnerCli
  model?: string | null
  flags?: string[] | null
  created_at: string
  updated_at: string
}

export interface RunnerCreate {
  name: string
  cli: RunnerCli
  model?: string
}

export interface RunnerUpdate {
  name?: string
  model?: string
}

export function useRunners() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<Runner[]>({
    queryKey: ['project', projectId, 'runners'],
    queryFn: () => getJson<Runner[]>(`/api/v1/projects/${projectId}/runners`),
    enabled: isConfigured && !!projectId,
  })
}

export function useCreateRunner() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (runner: RunnerCreate) =>
      postJson<Runner>(`/api/v1/projects/${projectId}/runners`, runner),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'runners'] }),
  })
}

export function useUpdateRunner() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: RunnerUpdate }) =>
      patchJson<Runner>(`/api/v1/projects/${projectId}/runners/${id}`, updates),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'runners'] }),
  })
}

export function useDeleteRunner() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await fetchWithAuth(`/api/v1/projects/${projectId}/runners/${id}`, {
        method: 'DELETE',
      })
      return res.ok
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'runners'] }),
  })
}

export function useBindAgentRunner() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ agent, runnerId }: { agent: string; runnerId: string | null }) =>
      patchJson(`/api/v1/projects/${projectId}/agents/${agent}`, { runner_id: runnerId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agents'] })
    },
  })
}
