import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, getJson, patchJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** One of the Hub's background jobs (`hub/hub/manager.py`'s registry) and what the operator chose
 *  for it in this project. A job never configured is listed disabled with nothing chosen. */
export interface ManagerJob {
  key: string
  title: string
  description: string
  trigger: string
  /** True: with no runner the job does nothing. Absent on a Hub that predates it, read as false. */
  needs_runner?: boolean
  enabled: boolean
  /** Null: the job's own default runner (for titles, the conversation's agent's). */
  runner_id: string | null
  /** Null: the runner's own model. */
  model: string | null
  /** The chapters job only: fire on its triggers, or only when 'Weave the thread' is pressed. */
  mode?: 'automatic' | 'button'
  /** The chapters job only: what all its firings in this project recorded, summed. */
  usage_total?: JobUsageTotal
}

/** `firings` counts the job's firings; each other dimension is summed over those that reported it. */
export interface JobUsageTotal {
  firings: number
  input_tokens?: number
  output_tokens?: number
  cache_read_tokens?: number
  cache_write_tokens?: number
  reasoning_tokens?: number
  cost_usd_micros?: number
}

export type ManagerJobInput = Partial<Pick<ManagerJob, 'enabled' | 'runner_id' | 'model' | 'mode'>>

/** One model spawn a job made — a `manager_job_fired` event's payload plus its id and time. */
export interface ManagerFiring {
  id: string
  at: string
  job: string
  trigger: string
  subject: Record<string, string>
  runner_id: string
  cli: string
  model: string | null
  outcome: 'written' | 'answered' | 'empty' | 'failed'
  detail: string | null
  duration_ms: number
  usage: Record<string, number> | null
  /** What the model answered, cut at 8,000 characters (F581); absent on an older Hub. */
  answer?: string | null
}

/** True when the Hub predates the manager. A committed bundle reaches the operator's app before
 *  its server restarts, so this is a state the section has to read, not an error. */
export function isNoManager(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

export function useManagerJobs() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ManagerJob[]>({
    queryKey: ['project', projectId, 'manager', 'jobs'],
    queryFn: async () =>
      (await getJson<{ jobs: ManagerJob[] }>(`/api/v1/projects/${projectId}/manager/jobs`)).jobs,
    enabled: isConfigured && !!projectId,
    retry: (count, error) => !isNoManager(error) && count < 2,
  })
}

/** Polled while the section is open: a firing is recorded as an event, not broadcast. */
export function useManagerActivity(limit = 50) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ManagerFiring[]>({
    queryKey: ['project', projectId, 'manager', 'activity', limit],
    queryFn: async () =>
      (
        await getJson<{ firings: ManagerFiring[] }>(
          `/api/v1/projects/${projectId}/manager/activity?limit=${limit}`,
        )
      ).firings,
    enabled: isConfigured && !!projectId,
    retry: (count, error) => !isNoManager(error) && count < 2,
    refetchInterval: (query) => (isNoManager(query.state.error) ? false : 10_000),
  })
}

/** "Weave the thread": ask the chapters job to fire now, whatever its automatic/button choice. */
export function useWeaveThread() {
  const queryClient = useQueryClient()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  return useMutation({
    mutationFn: () => postJson<unknown>(`/api/v1/projects/${projectId}/manager/jobs/chapters/run`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'manager', 'activity'] })
    },
  })
}

export function useUpdateManagerJob() {
  const queryClient = useQueryClient()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  return useMutation({
    mutationFn: ({ key, input }: { key: string; input: ManagerJobInput }) =>
      patchJson<ManagerJob>(`/api/v1/projects/${projectId}/manager/jobs/${key}`, input),
    onSuccess: (job) => {
      queryClient.setQueryData<ManagerJob[]>(['project', projectId, 'manager', 'jobs'], (current) =>
        current?.map((item) => (item.key === job.key ? job : item)),
      )
      // The settings route reports the title job's state (its compatibility fields).
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'settings'] })
    },
  })
}
