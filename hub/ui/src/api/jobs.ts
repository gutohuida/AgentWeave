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
  error_summary?: string
}

/** A job's loop state, present only when the job opted into being a loop (design D6). */
export interface LoopSummary {
  /** The `Loop` row's own id — what `GET /tasks?loop_id=` actually scopes by, distinct from the
   *  job's id. */
  id: string
  /** The loop's job's name (design D20/B4.2) — what a picker shows; `LoopSummary` carried no name
   *  of its own before B4. */
  label: string
  purpose: string
  stop_at?: string
  stop_when_queue_empties: boolean
  stop_reason?: string
  stopped_at?: string
  /** What happened ("completed"/"stopped"), null while still running (design D17). */
  ending_state?: 'completed' | 'stopped' | null
  /** When an operator archived this loop; null while it is listed by default (design D16). */
  archived_at?: string | null
  /** status -> count of this loop's non-fetched-yet-terminal tasks, keyed by `Task.status`. */
  queue: Record<string, number>
  current_task?: { id: string; title: string; status: string } | null
  open_questions: number
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
  /** Design D16: null means live and listed by default; set only by `POST /jobs/{id}/archive`. */
  archived_at?: string | null
  history?: JobRun[]
  loop?: LoopSummary | null
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
  // Loop opt-in (design D6): the Hub creates a `Loop` row iff at least one of these is present in
  // the request body. Omit all three entirely — never send `purpose: ''` or
  // `stop_when_queue_empties: false` — unless the caller actually means to opt this job into a loop.
  purpose?: string
  stop_at?: string
  stop_when_queue_empties?: boolean
}

export interface JobUpdate {
  name?: string
  agent?: string
  message?: string
  cron?: string
  session_mode?: 'new' | 'resume'
  enabled?: boolean
  // Same opt-in rule as `JobCreate` — omit unless the loop section was touched. Supplying any of
  // these for a job with no existing loop is a 400 unless this is the update that creates one.
  purpose?: string
  stop_at?: string
  stop_when_queue_empties?: boolean
  stop_reason?: string
}

export function useJobs() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<Job[]>({
    queryKey: ['project', projectId, 'jobs'],
    queryFn: () => getJson<Job[]>(`/api/v1/projects/${projectId}/jobs`),
    enabled: isConfigured && !!projectId,
  })
}

export function useJob(jobId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<Job>({
    queryKey: ['project', projectId, 'jobs', jobId],
    queryFn: () => getJson<Job>(`/api/v1/projects/${projectId}/jobs/${jobId}`),
    enabled: isConfigured && !!projectId && !!jobId,
  })
}

export function useCreateJob() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (job: JobCreate) => postJson<Job>(`/api/v1/projects/${projectId}/jobs`, job),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'jobs'] }),
  })
}

export function useUpdateJob() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: JobUpdate }) =>
      patchJson<Job>(`/api/v1/projects/${projectId}/jobs/${id}`, updates),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'jobs'] }),
  })
}

export function usePauseJob() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (id: string) =>
      patchJson<Job>(`/api/v1/projects/${projectId}/jobs/${id}`, { enabled: false }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'jobs'] }),
  })
}

export function useResumeJob() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (id: string) =>
      patchJson<Job>(`/api/v1/projects/${projectId}/jobs/${id}`, { enabled: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'jobs'] }),
  })
}

export function useDeleteJob() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await fetchWithAuth(`/api/v1/projects/${projectId}/jobs/${id}`, {
        method: 'DELETE',
      })
      return res.ok
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'jobs'] }),
  })
}

export function useRunJob() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (id: string) =>
      postJson<{ success: boolean; job_id: string; run_id: string }>(
        `/api/v1/projects/${projectId}/jobs/${id}/run`,
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'jobs'] }),
  })
}
