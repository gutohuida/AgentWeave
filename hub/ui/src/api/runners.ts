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
  flags?: unknown
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
  const { isConfigured } = useConfigStore()
  return useQuery<Runner[]>({
    queryKey: ['runners'],
    queryFn: () => getJson<Runner[]>('/api/v1/runners'),
    enabled: isConfigured,
  })
}

export function useCreateRunner() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (runner: RunnerCreate) => postJson<Runner>('/api/v1/runners', runner),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runners'] }),
  })
}

export function useUpdateRunner() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: RunnerUpdate }) =>
      patchJson<Runner>(`/api/v1/runners/${id}`, updates),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runners'] }),
  })
}

export function useDeleteRunner() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await fetchWithAuth(`/api/v1/runners/${id}`, { method: 'DELETE' })
      return res.ok
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runners'] }),
  })
}

export function useBindAgentRunner() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ agent, runnerId }: { agent: string; runnerId: string | null }) =>
      patchJson(`/api/v1/agents/${agent}`, { runner_id: runnerId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
  })
}
