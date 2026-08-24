import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson, patchJson } from './client'
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
  /** How many firings this one record stands for (`loop-notices-and-reacts` design D6).
   *  1 on a firing that happened; higher only on a stall record, where each further refusal for
   *  the same stall counts here instead of appending a row. Optional because a Hub older than
   *  migration `0087` does not send it. */
  tick_count?: number
}

/**
 * An edit staged against a loop and waiting for the next firing to apply it (design D11).
 *
 * Reported separately from the loop's live fields rather than merged into them, because a reader
 * of the live fields must not be shown a value that is not yet in force. Only the keys actually
 * staged appear — an absent `purpose` means "this edit did not touch the purpose", never "the
 * purpose is being cleared".
 */
export interface LoopPendingEdit {
  staged_by?: string | null
  staged_at: string
  purpose?: string
  stop_at?: string
  stop_when_queue_empties?: boolean
}

/** A job's loop state, present only when the job opted into being a loop (design D6). */
export interface LoopSummary {
  /** The `Loop` row's own id — what `GET /tasks?loop_id=` actually scopes by, distinct from the
   *  job's id. */
  id: string
  /** The loop's job's name (design D20/B4.2) — what a picker shows; `LoopSummary` carried no name
   *  of its own before B4. */
  label: string
  /** Which agent runs each firing — the loop's job's `agent`. Distinct from `control`, which says
   *  who may extend the queue rather than who works it. Optional because the server schema
   *  defaults it to an empty string, so "present but empty" is a real state the UI must render
   *  past rather than trust. */
  agent?: string
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
  // `loop-becomes-a-flow` task 1.5: a list, because a flow may staff several tasks at once.
  // Group 1 changes no behaviour, so it holds zero or one and renders as the scalar did.
  current_tasks?: { id: string; title: string; status: string }[]
  // Why the next firing would be refused, or absent if it would proceed
  // (`loop-notices-and-reacts` 5.5). From the Hub's own firing decision, never inferred from
  // the queue counts, so the board cannot say one thing while the firing does another.
  stall_reason?: string | null
  open_questions: number
  /** Who may extend this queue (design D10). Null means the current default, the operator —
   *  returned unresolved by the Hub, so it is left unresolved here too. */
  control?: string | null
  /** Set only while an edit is staged and waiting for the next firing. Null the rest of the
   *  time, which is most of the time. */
  pending_edit?: LoopPendingEdit | null
  /** Is a firing of this loop's job in progress right now (design D13, task A4.4) — the one
   *  shared fact both the edit-staging response and the loop panel read, computed once
   *  server-side from `JobRun.status == "in_progress"`. */
  firing_active: boolean
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

/**
 * A job's recent firings, fetched on demand.
 *
 * The jobs collection deliberately does not carry `history` — only `GET /jobs/{id}` does, and the
 * list view renders from the collection, so an expanded card had no runs to show and reported
 * "No runs yet" for a job whose firings had failed (broken-loop check 9.6). This fetches the
 * dedicated history route instead of widening the collection response, so a project with many
 * jobs pays for history only on the card the operator actually opened.
 */
export function useJobHistory(jobId: string | null, enabled = true) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<JobRun[]>({
    queryKey: ['project', projectId, 'jobs', jobId, 'history'],
    queryFn: () =>
      getJson<JobRun[]>(`/api/v1/projects/${projectId}/jobs/${jobId}/history?limit=10`),
    enabled: enabled && isConfigured && !!projectId && !!jobId,
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

export function useArchiveJob() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (id: string) =>
      postJson<Job>(`/api/v1/projects/${projectId}/jobs/${id}/archive`),
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
