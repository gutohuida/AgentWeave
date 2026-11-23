import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query'
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
  /** The run this firing belongs to (`mrun-…`), its initiator and its start; absent on a firing
   *  recorded before runs had ids. */
  run_id?: string
  initiator?: ManagerInitiator
  started_at?: string
}

// --- runs (`background-manager-work-you-can-see`) -------------------------------------------------

/** `operator`: a button or a request; `autonomous`: the Hub on its own (`worker.Initiator`). */
export type ManagerInitiator = 'operator' | 'autonomous'

/** A manager run in progress, as `GET /manager/runs/running` lists it (oldest first) and
 *  `manager_run_started` announces it. A mender run's id is its `run-…` and it carries its
 *  conversation; a job's run is `mrun-…` with `conversation_id` null. */
export interface ManagerRunningRun {
  run_id: string
  job: string
  subject: Record<string, unknown>
  trigger: string
  initiator: ManagerInitiator | string
  started_at: string
  conversation_id?: string | null
}

/** A run that ended, as `manager_run_ended` announces it, or as drawn from its firings. */
export interface ManagerEndedRun extends ManagerRunningRun {
  ended_at: string
  duration_ms?: number | null
  outcome: ManagerFiring['outcome'] | string
  detail: string | null
  usage?: Record<string, number> | null
}

/** An item's newest run when it failed and nobody has seen it (`GET /manager/runs/unseen-failures`). */
export interface ManagerUnseenFailure {
  run_id: string
  job: string
  subject: Record<string, unknown>
  ended_at: string
  detail: string | null
}

export function managerRunsKey(projectId: string | null | undefined, which: 'running' | 'unseen' | 'ended-live') {
  return ['project', projectId, 'manager', 'runs', which] as const
}

/** The runs in progress. Kept current by the stream (`useSSE`: started adds, ended removes) and
 *  re-read on every run signal, so a run that started before the page opened is still shown. */
export function useRunningManagerRuns() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ManagerRunningRun[]>({
    queryKey: managerRunsKey(projectId, 'running'),
    queryFn: async () =>
      (await getJson<{ runs: ManagerRunningRun[] }>(`/api/v1/projects/${projectId}/manager/runs/running`, { background: true }))
        .runs ?? [],
    enabled: isConfigured && !!projectId,
    retry: (count, error) => !isNoManager(error) && count < 2,
  })
}

/** Each item's unseen failure; re-read on every run signal and on `manager_run_seen`. */
export function useUnseenManagerFailures() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ManagerUnseenFailure[]>({
    queryKey: managerRunsKey(projectId, 'unseen'),
    queryFn: async () =>
      (
        await getJson<{ failures: ManagerUnseenFailure[] }>(`/api/v1/projects/${projectId}/manager/runs/unseen-failures`, {
          background: true,
        })
      ).failures ?? [],
    enabled: isConfigured && !!projectId,
    retry: (count, error) => !isNoManager(error) && count < 2,
  })
}

/** Mark failures seen: the operator opened the item's list, or hovered the top bar while they were
 *  listed. Ids already seen or unknown are ignored by the Hub. */
export function useMarkManagerRunsSeen() {
  const queryClient = useQueryClient()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  return useMutation({
    mutationFn: (runIds: string[]) => postJson<unknown>(`/api/v1/projects/${projectId}/manager/runs/seen`, { run_ids: runIds }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: managerRunsKey(projectId, 'unseen') })
    },
  })
}

/** Runs from `/activity`'s firings (newest first), one per run id: the run's newest firing ends it,
 *  and its outcome is the first failure's, else the newest firing's. Firings with no run id are
 *  from before runs had ids and are left out. */
export function endedRunsFromFirings(firings: ManagerFiring[]): ManagerEndedRun[] {
  const runs = new Map<string, ManagerEndedRun>()
  for (const firing of firings) {
    if (!firing.run_id) continue
    const known = runs.get(firing.run_id)
    if (!known) {
      runs.set(firing.run_id, {
        run_id: firing.run_id,
        job: firing.job,
        subject: firing.subject ?? {},
        trigger: firing.trigger,
        initiator: firing.initiator ?? 'autonomous',
        started_at: firing.started_at ?? firing.at,
        ended_at: firing.at,
        outcome: firing.outcome,
        detail: firing.detail,
        usage: firing.usage,
        conversation_id: null,
      })
    } else if (firing.outcome === 'failed') {
      known.outcome = 'failed'
      known.detail = firing.detail
    }
  }
  return [...runs.values()]
}

/** The runs that ended most recently, newest first: those this window heard end (mender runs
 *  included), merged with those recorded before it opened; and why the recorded ones could not be
 *  read, if they could not. */
export function useRecentManagerRuns(limit = 8) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const recorded = useQuery<ManagerEndedRun[]>({
    queryKey: ['project', projectId, 'manager', 'activity', 'runs'],
    queryFn: async () =>
      endedRunsFromFirings(
        (await getJson<{ firings: ManagerFiring[] }>(`/api/v1/projects/${projectId}/manager/activity?limit=50`, { background: true }))
          .firings ?? [],
      ),
    enabled: isConfigured && !!projectId,
    retry: (count, error) => !isNoManager(error) && count < 2,
  })
  const live = useQuery<ManagerEndedRun[]>({
    queryKey: managerRunsKey(projectId, 'ended-live'),
    queryFn: () => [],
    enabled: false,
    initialData: [],
    staleTime: Infinity,
  })
  const merged = new Map<string, ManagerEndedRun>()
  for (const run of [...(live.data ?? []), ...(recorded.data ?? [])]) {
    if (!merged.has(run.run_id)) merged.set(run.run_id, run)
  }
  const runs = [...merged.values()].sort((a, b) => (a.ended_at < b.ended_at ? 1 : a.ended_at > b.ended_at ? -1 : 0)).slice(0, limit)
  return { runs, error: recorded.error }
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

/** One run of the log, as `GET /manager/runs` lists it: a job's run (`mrun-…`) or the mender's
 *  (`run-…`, with its conversation). `no_cost_reason` says why `usage` has no cost. */
export interface ManagerLoggedRun {
  run_id: string
  job: string
  subject: Record<string, unknown>
  trigger: string
  initiator: ManagerInitiator | string | null
  started_at: string
  ended_at: string
  duration_ms: number | null
  outcome: ManagerFiring['outcome'] | string
  detail: string | null
  usage: Record<string, number> | null
  no_cost_reason: string | null
  conversation_id: string | null
}

/** A run with what its model answered (`GET /manager/runs/{run_id}`). */
export interface ManagerRunDetail extends ManagerLoggedRun {
  answer?: string | null
}

/** One job's totals over every run it has, whatever the log is narrowed to. */
export interface ManagerJobRunTotals {
  runs: number
  failed: number
  cost_usd_micros: number | null
}

export interface ManagerRunLogPage {
  runs: ManagerLoggedRun[]
  totals: Record<string, ManagerJobRunTotals>
  has_more: boolean
}

/** The run log, newest first, narrowed to *job* when given; each page continues after the last run
 *  of the one before. Polled while the section is open: a run's end is an event the log reads. */
export function useManagerRunLog(job: string | null, pageSize = 50) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useInfiniteQuery<ManagerRunLogPage, Error, InfiniteData<ManagerRunLogPage, string | null>, readonly unknown[], string | null>({
    queryKey: ['project', projectId, 'manager', 'runs', 'log', job ?? 'all', pageSize],
    initialPageParam: null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: String(pageSize) })
      if (job) params.set('job', job)
      if (pageParam) params.set('before', pageParam)
      return getJson<ManagerRunLogPage>(`/api/v1/projects/${projectId}/manager/runs?${params}`)
    },
    getNextPageParam: (last) => (last.has_more && last.runs.length ? last.runs[last.runs.length - 1].run_id : undefined),
    enabled: isConfigured && !!projectId,
    retry: (count, error) => !isNoManager(error) && count < 2,
    refetchInterval: (query) => (isNoManager(query.state.error) ? false : 10_000),
  })
}

/** One run with its answer, for the detail a `run=<run_id>` link opens. */
export function useManagerRun(runId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ManagerRunDetail>({
    queryKey: ['project', projectId, 'manager', 'runs', 'one', runId],
    queryFn: () => getJson<ManagerRunDetail>(`/api/v1/projects/${projectId}/manager/runs/${encodeURIComponent(runId ?? '')}`),
    enabled: isConfigured && !!projectId && !!runId,
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
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

/** One firing of the pre-mortem (`the-spec-journey-spends-the-operator-s-attention-only-on-their-decisions`,
 *  FR-11): a fresh reader assumed the change shipped and failed, and wrote down how. `findings` is
 *  empty on a firing that wrote nothing. */
export interface PreMortem {
  id: string
  at: string
  /** `requested`: the Run a pre-mortem button; `criteria_written`: the document left the step that
   *  writes its acceptance criteria while the job fires automatically. */
  trigger: string
  model: string | null
  outcome: ManagerFiring['outcome']
  detail: string | null
  cost_usd_micros: number | null
  findings: PreMortemFinding[]
}

/** One way the change failed: the story, the requirement it breaks when it names one, and what the
 *  reader cites for it (a file:line, a criterion, an earlier decision). */
export interface PreMortemFinding {
  story: string
  requirement: string | null
  cites: string[]
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
          { background: true },
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

/** A document's pre-mortems, newest first. Polled: a firing is recorded when it ends, not broadcast. */
export function usePreMortems(path: string) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<PreMortem[]>({
    queryKey: ['project', projectId, 'manager', 'pre-mortems', path],
    queryFn: async () =>
      (
        await getJson<{ pre_mortems: PreMortem[] }>(
          `/api/v1/projects/${projectId}/manager/jobs/pre-mortem/pre-mortems?path=${encodeURIComponent(path)}`,
          { background: true },
        )
      ).pre_mortems,
    enabled: isConfigured && !!projectId && !!path,
    retry: (count, error) => !isNoManager(error) && count < 2,
    refetchInterval: (query) => (isNoManager(query.state.error) ? false : 10_000),
  })
}

/** "Run a pre-mortem": refused with 409 and a sentence while the job is off, has no runner, or one
 *  of this document is in progress. */
export function useRunPreMortem(path: string) {
  const queryClient = useQueryClient()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  return useMutation({
    mutationFn: () => postJson<unknown>(`/api/v1/projects/${projectId}/manager/jobs/pre-mortem/run`, { path }),
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
