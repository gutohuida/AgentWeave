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
  /** The mender only: the model its turns run on while `model` is null -- the catalog's default for
   *  its runner's CLI -- or null with no runner. Absent on a Hub that predates it. */
  default_model?: { id: string; label: string } | null
  /** Fire on the job's triggers, or only on its button. The route lists it for every job; only a job
   *  with a `firing_choice` can change it. */
  mode?: 'automatic' | 'button'
  /** A job with a button: the choice between it and automatic firing, in words. Null on the others;
   *  absent on a Hub that predates it, which shows no choice until it restarts. */
  firing_choice?: { button: string; where: string; automatic: string } | null
  /** A job with a button: what all its firings in this project recorded, summed. */
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

/** One firing of the build retrospective, written or not, as its document lists it. `report` is
 *  absent from a failed firing. */
export interface BuildRetrospective {
  id: string
  at: string
  trigger: string
  model: string | null
  outcome: ManagerFiring['outcome']
  detail: string | null
  duration_ms: number | null
  usage: Record<string, number> | null
  cost_usd_micros: number | null
  parts: number
  vault_source: string | null
  report: RetrospectiveReport | null
}

export interface RetrospectiveFinding {
  text: string
  cites: string[]
}

export interface RetrospectiveSendBack {
  transition_id: string
  task_id: string
  readable_id: string | null
  at: string
  by: string
  run_id: string | null
  reason_class: string | null
  reason: string | null
  /** `defect`, `process` or `spec`. */
  cause: string
  cause_from: 'model' | 'reviewer'
  explanation: string
  cites: string[]
}

interface RetrospectiveEvent {
  id: string
  kind: string
  detail: Record<string, unknown> | null
}

interface RetrospectiveCost {
  runs: number
  cost_usd_micros: number
}

/** The stored report (`build_retrospective.py`). `nothing` names each empty section with what it
 *  says instead. */
export interface RetrospectiveReport {
  parts: number
  dropped: number
  where_time_went: {
    findings: RetrospectiveFinding[]
    per_task: Array<{
      task_id: string
      readable_id: string | null
      title: string
      status: string
      building_seconds: number
      waiting_for_review_seconds: number
      in_check_gate_seconds: number
      waiting_to_start_seconds: number
    }>
  }
  send_backs: RetrospectiveSendBack[]
  spec_missed: {
    findings: RetrospectiveFinding[]
    amendments: RetrospectiveEvent[]
    tasks_added_mid_build: Array<{ task_id: string; readable_id: string | null; title: string }>
    unsatisfiable_criteria: RetrospectiveEvent[]
    requirements_without_accepted_evidence: string[]
    reconcile_gaps: Array<{ class?: string; requirement?: string; where?: string; summary?: string }>
  }
  staffing: {
    findings: RetrospectiveFinding[]
    builds: Array<{ id: string; driver: string; level: string }>
    per_agent: Array<RetrospectiveCost & { agent: string }>
  }
  cost: {
    findings: RetrospectiveFinding[]
    per_agent: Array<RetrospectiveCost & { agent: string }>
    per_task: Array<RetrospectiveCost & { task_id: string }>
    totals: RetrospectiveCost
  }
  friction: {
    findings: RetrospectiveFinding[]
    stalls: Array<{ id: string; cause: string | null; reason: string | null; outcome: string | null }>
    flaky_send_backs: RetrospectiveSendBack[]
    operator_waits: Array<{ question_id: string; task_id: string | null; waited_seconds: number }>
  }
  what_worked: RetrospectiveFinding[]
  /** `label` is `code_and_checks`, `specs`, `staffing_and_running` or `tooling`. */
  improvements: Array<RetrospectiveFinding & { label: string }>
  lessons: RetrospectiveFinding[]
  transcripts_read: Array<{ run_id: string; task_id: string | null; agent: string; flags: string[] }>
  nothing: Partial<
    Record<
      | 'where_time_went'
      | 'send_backs'
      | 'spec_missed'
      | 'staffing'
      | 'cost'
      | 'friction'
      | 'what_worked'
      | 'improvements'
      | 'lessons'
      | 'transcripts_read',
      string
    >
  >
}

/** A document's retrospectives, newest first. Polled: a firing is recorded when it ends, not broadcast. */
export function useBuildRetrospectives(path: string) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<BuildRetrospective[]>({
    queryKey: ['project', projectId, 'manager', 'retrospectives', path],
    queryFn: async () =>
      (
        await getJson<{ retrospectives: BuildRetrospective[] }>(
          `/api/v1/projects/${projectId}/manager/jobs/build-retrospective/retrospectives?path=${encodeURIComponent(path)}`,
        )
      ).retrospectives,
    enabled: isConfigured && !!projectId && !!path,
    retry: (count, error) => !isNoManager(error) && count < 2,
    refetchInterval: (query) => (isNoManager(query.state.error) ? false : 10_000),
  })
}

/** "Review this build": refused with 409 and a sentence while one is in progress or with no runner. */
export function useReviewThisBuild(path: string) {
  const queryClient = useQueryClient()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  return useMutation({
    mutationFn: () =>
      postJson<unknown>(
        `/api/v1/projects/${projectId}/manager/jobs/build-retrospective/run?path=${encodeURIComponent(path)}`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'manager'] })
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
