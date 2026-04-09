import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson, patchJson, fetchWithAuth } from './client'
import { useConfigStore } from '@/store/configStore'

export interface JobRun {
  id: string
  job_id: string
  fired_at: string
  status: string
  trigger: string
  session_id?: string
  message_id?: string
}

export interface Job {
  id: string
  project_id: string
  name: string
  agent: string
  message: string
  cron: string
  session_mode: 'new' | 'resume'
  enabled: boolean
  source: 'local' | 'hub'
  created_at: string
  last_run?: string
  next_run?: string
  run_count: number
  last_session_id?: string
  history?: JobRun[]
}

export interface JobCreate {
  name: string
  agent: string
  message: string
  cron: string
  session_mode?: 'new' | 'resume'
  enabled?: boolean
  id?: string
  source?: 'local' | 'hub'
}

export interface JobUpdate {
  name?: string
  agent?: string
  message?: string
  cron?: string
  session_mode?: 'new' | 'resume'
  enabled?: boolean
}

export function useJobs() {
  const { isConfigured } = useConfigStore()
  return useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: () => getJson<Job[]>('/api/v1/jobs'),
    enabled: isConfigured,
    refetchInterval: 10000,
  })
}

export function useJob(jobId: string | null) {
  const { isConfigured } = useConfigStore()
  return useQuery<Job>({
    queryKey: ['jobs', jobId],
    queryFn: () => getJson<Job>(`/api/v1/jobs/${jobId}`),
    enabled: isConfigured && !!jobId,
  })
}

export function useCreateJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (job: JobCreate) => postJson<Job>('/api/v1/jobs', job),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  })
}

export function useUpdateJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: JobUpdate }) =>
      patchJson<Job>(`/api/v1/jobs/${id}`, updates),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  })
}

export function usePauseJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => patchJson<Job>(`/api/v1/jobs/${id}`, { enabled: false }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  })
}

export function useResumeJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => patchJson<Job>(`/api/v1/jobs/${id}`, { enabled: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  })
}

export function useDeleteJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await fetchWithAuth(`/api/v1/jobs/${id}`, { method: 'DELETE' })
      return res.ok
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  })
}

export function useRunJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => postJson<{ success: boolean; job_id: string; run_id: string }>(`/api/v1/jobs/${id}/run`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  })
}
