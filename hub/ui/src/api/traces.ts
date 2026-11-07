import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, deleteJson, fetchWithAuth, getJson, putJson } from './client'
import { useConfigStore } from '@/store/configStore'

/**
 * A run's trace (a-run-is-a-trace-you-can-export): every model call, tool call, permission
 * decision, wait and delivery a run made, recorded by the Hub as OpenTelemetry-shaped spans. The
 * Hub is the only writer; this module reads them, pages them, and drives the project's export
 * settings.
 */

export type SpanStatus = 'unset' | 'ok' | 'error'

/** A root's operation: a run, a worker call, or the Hub's own request, event or background work. */
export type TraceOperation = 'invoke_agent' | 'chat' | 'aw.request' | 'aw.event' | 'aw.work'
export type TraceKind = 'run' | 'worker' | 'request' | 'event' | 'work'

export interface TraceSummary {
  trace_id: string
  root_span_id: string
  run_id: string | null
  name: string
  operation: TraceOperation
  kind: TraceKind
  agent: string | null
  conversation_id: string | null
  task_id: string | null
  /** The run's own outcome (`aw.run.status`); null for a trace that is not a run's. */
  run_status?: string | null
  /** Who started the run (`aw.run.initiator`): `operator` when you started it, `autonomous` otherwise. */
  initiator?: string | null
  status: SpanStatus
  status_message: string | null
  start_time: string
  end_time: string | null
  ended: boolean
  span_count: number
  /** A run's row (the Hub adds these to a run's summary; absent on other kinds of trace). */
  model?: string | null
  /** The task's reference and title; `task_missing` when the run named a task that is gone. */
  task_ref?: string | null
  task_title?: string | null
  task_missing?: boolean
  conversation_title?: string | null
  /** Recorded cost; null with `cost_state` `unpriced` (finished, unmeasured) or `running`. */
  cost_usd?: number | null
  cost_state?: 'measured' | 'unpriced' | 'running'
  /** Failed, stopped (cancelled or interrupted) or ended in error. */
  is_error?: boolean
}

export interface TraceList {
  traces: TraceSummary[]
  next_before: string | null
}

export interface SpanEvent {
  name: string
  time: string
  attributes: Record<string, unknown>
}

export interface Span {
  span_id: string
  trace_id: string
  parent_span_id: string | null
  name: string
  operation: string
  status: SpanStatus
  status_message: string | null
  start_time: string
  end_time: string | null
  ended: boolean
  attributes: Record<string, unknown>
  events: SpanEvent[]
}

export interface TraceDetail {
  trace_id: string
  kind: TraceKind
  run_id: string | null
  root: Span
  /** One page, ordered by start time. `total` is the whole trace's span count. */
  spans: Span[]
  total: number
  offset: number
  limit: number
}

export interface TraceSettings {
  otlp_endpoint: string | null
  /** Header values are write-only: the Hub returns the names it holds, never what they are. */
  otlp_header_names: string[]
  export_enabled: boolean
  enabled_at: string | null
  last_export_at: string | null
  last_error: string | null
  exported_spans: number
  span_count: number
  trace_count: number
  oldest_trace_at: string | null
  /** Record the operator's and runs' routine reads too (off: only what changed or failed). */
  record_reads: boolean
  spans_by_operation: Record<string, number>
  /** Spans this Hub process could not write since it started. */
  dropped_spans: number
  /** Days of spans the Hub keeps; older ones are deleted on their own. */
  retention_days: number
  /** The window a project that never chose one keeps. */
  retention_days_default: number
  /** Whether `retention_days` is this project's own choice rather than the default. */
  retention_days_chosen: boolean
}

export interface TraceSettingsInput {
  otlp_endpoint?: string | null
  otlp_headers?: Record<string, string>
  export_enabled?: boolean
  /** Null returns the project to the Hub's default window. */
  retention_days?: number | null
}

export interface TraceFilters {
  run_id?: string
  task_id?: string
  conversation_id?: string
  /** The runs that worked a task of this build. */
  build_id?: string
  agent?: string
  /** Started at or after / before: ISO datetimes. */
  since?: string
  until?: string
  /** Only traces whose root is this operation. */
  operation?: TraceOperation
  before?: string
  limit?: number
}

/** A trace whose root has not ended is still being written; this is how often it is re-read. */
const LIVE_REFETCH_MS = 3000

export const TRACE_PAGE_SIZE = 500

function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

function liveInterval(detail: TraceDetail | null | undefined): number | false {
  return detail && !detail.root.ended ? LIVE_REFETCH_MS : false
}

export function useTraces(filters: TraceFilters = {}, enabled = true) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<TraceList>({
    queryKey: ['project', projectId, 'traces', 'list', filters],
    queryFn: () =>
      getJson<TraceList>(
        `/api/v1/projects/${projectId}/traces${query({ limit: 50, ...filters })}`,
      ),
    enabled: enabled && isConfigured && !!projectId,
  })
}

/** What the traces view groups by. */
export type TraceGrouping = 'agent' | 'model' | 'task' | 'conversation' | 'kind' | 'day'

/** Statistics over every trace a filter matches (not one page), or over one group of them. */
export interface TraceTotals {
  count: number
  /** Failed, stopped (cancelled or interrupted) or ended in error; `error_kinds` says which. */
  errors: number
  error_kinds: { failed: number; stopped: number; trace_error: number }
  /** Not ended yet: no duration, and neither priced nor unpriced. */
  running: number
  /** Sum over the runs whose cost was measured; null when none was (never a stand-in zero). */
  cost_usd_micros: number | null
  priced: number
  /** Finished runs left out of `cost_usd_micros` because their cost could not be measured. */
  unpriced: number
  duration_seconds: number
  /** Over the traces that have ended; null when none has. */
  duration_avg_seconds: number | null
  tokens: { input: number; output: number; cache_read: number; cache_write: number } | null
  model_calls: number
  tool_calls: number
  /** Time spent waiting for a permission or an answer. */
  wait_seconds: number
}

export interface TraceGroup {
  key: string
  label: string
  /** A second line: a task's title under its reference. */
  detail: string | null
  /** A task group whose task no longer exists. */
  missing: boolean
  totals: TraceTotals
}

export interface TraceTotalsAnswer {
  totals: TraceTotals
  group_by: TraceGrouping | null
  /** Every group the filter matches, in the order to show them; null when ungrouped. */
  groups: TraceGroup[] | null
}

/** The statistics for the list's filters, over everything they match. A `before` cursor or page
 *  size is the list's, not the totals', and is left out. `day` groups by the operator's own day. */
export function useTraceTotals(filters: TraceFilters, groupBy: TraceGrouping | null, enabled = true) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const matching: TraceFilters = { ...filters }
  delete matching.before
  delete matching.limit
  const utcOffset = -new Date().getTimezoneOffset()
  return useQuery<TraceTotalsAnswer>({
    queryKey: ['project', projectId, 'traces', 'totals', matching, groupBy, utcOffset],
    queryFn: () =>
      getJson<TraceTotalsAnswer>(
        `/api/v1/projects/${projectId}/traces/totals${query({ ...matching, group_by: groupBy, utc_offset: utcOffset })}`,
      ),
    enabled: enabled && isConfigured && !!projectId,
  })
}

export function useTrace(traceId: string | null, offset = 0) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<TraceDetail>({
    queryKey: ['project', projectId, 'traces', 'detail', traceId, offset],
    queryFn: () =>
      getJson<TraceDetail>(
        `/api/v1/projects/${projectId}/traces/${traceId}${query({ offset, limit: TRACE_PAGE_SIZE })}`,
      ),
    enabled: isConfigured && !!projectId && !!traceId,
    refetchInterval: (q) => liveInterval(q.state.data),
  })
}

/**
 * The trace of one run, or `null` when the run has none — a run from before tracing existed, or
 * one whose trace was cleared. A 404 here is an answer, not a failure.
 */
async function fetchRunTrace(projectId: string, runId: string, offset: number): Promise<TraceDetail | null> {
  try {
    return await getJson<TraceDetail>(
      `/api/v1/projects/${projectId}/traces/by-run/${runId}${query({ offset, limit: TRACE_PAGE_SIZE })}`,
    )
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

export function useRunTrace(runId: string | null, offset = 0) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<TraceDetail | null>({
    queryKey: ['project', projectId, 'traces', 'by-run', runId, offset],
    queryFn: () => fetchRunTrace(projectId as string, runId as string, offset),
    enabled: isConfigured && !!projectId && !!runId,
    refetchInterval: (q) => liveInterval(q.state.data),
  })
}

/** The traces of several runs, one request each and only for the ids named (the first page of
 *  each). The conversation trace names a run when its turn is first unfolded. */
export function useRunTraces(runIds: string[]) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQueries({
    queries: runIds.map((runId) => ({
      queryKey: ['project', projectId, 'traces', 'by-run', runId, 0],
      queryFn: () => fetchRunTrace(projectId as string, runId, 0),
      enabled: isConfigured && !!projectId,
      refetchInterval: (q: { state: { data: TraceDetail | null | undefined } }) => liveInterval(q.state.data),
    })),
  })
}

/** The most runs a conversation's trace reads; the list route pages 200 at a time. */
export const CONVERSATION_RUNS_MAX = 2000

/** Every run of one conversation, newest first as the list route returns them, read page by page
 *  past the route's 200-row page. */
export function useConversationRuns(conversationId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<TraceSummary[]>({
    queryKey: ['project', projectId, 'traces', 'conversation-runs', conversationId],
    queryFn: async () => {
      const runs: TraceSummary[] = []
      let before: string | undefined
      while (runs.length < CONVERSATION_RUNS_MAX) {
        const page = await getJson<TraceList>(
          `/api/v1/projects/${projectId}/traces${query({ conversation_id: conversationId, operation: 'invoke_agent', limit: 200, before })}`,
        )
        runs.push(...page.traces)
        if (!page.next_before || page.traces.length === 0) break
        before = page.next_before
      }
      return runs
    },
    enabled: isConfigured && !!projectId && !!conversationId,
    refetchInterval: (q) => (q.state.data?.some((r) => !r.ended) ? LIVE_REFETCH_MS : false),
  })
}

export function useTraceSettings() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<TraceSettings>({
    queryKey: ['project', projectId, 'traces', 'settings'],
    queryFn: () => getJson<TraceSettings>(`/api/v1/projects/${projectId}/traces/settings`),
    enabled: isConfigured && !!projectId,
  })
}

export function useUpdateTraceSettings() {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: TraceSettingsInput) =>
      putJson<TraceSettings>(`/api/v1/projects/${projectId}/traces/settings`, input),
    onSuccess: (saved) => {
      queryClient.setQueryData(['project', projectId, 'traces', 'settings'], saved)
    },
  })
}

export interface TraceRange {
  /** `YYYY-MM-DD`, inclusive; empty means from the first trace. */
  since?: string
  /** `YYYY-MM-DD`, exclusive; empty means up to now. */
  until?: string
}

export function useClearTraces() {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (range: TraceRange) =>
      deleteJson<{ deleted_spans: number; deleted_traces: number }>(
        `/api/v1/projects/${projectId}/traces${query({ since: range.since, until: range.until })}`,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'traces'] })
    },
  })
}

/**
 * Download the project's traces as one OTLP JSON file. The route needs the bearer header, so a
 * plain link cannot fetch it: the body is read here and handed to the browser as an object URL.
 */
export async function downloadTraceExport(
  projectId: string,
  since?: string,
  until?: string,
): Promise<void> {
  const res = await fetchWithAuth(
    `/api/v1/projects/${projectId}/traces/export${query({ since, until })}`,
  )
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `traces-${projectId}-${since || 'start'}-${until || 'now'}.json`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  // Revoked on the next tick: revoking synchronously can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
