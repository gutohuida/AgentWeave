import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
  status: SpanStatus
  status_message: string | null
  start_time: string
  end_time: string | null
  ended: boolean
  span_count: number
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
}

export interface TraceSettingsInput {
  otlp_endpoint?: string | null
  otlp_headers?: Record<string, string>
  export_enabled?: boolean
}

export interface TraceFilters {
  run_id?: string
  task_id?: string
  conversation_id?: string
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
export function useRunTrace(runId: string | null, offset = 0) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<TraceDetail | null>({
    queryKey: ['project', projectId, 'traces', 'by-run', runId, offset],
    queryFn: async () => {
      try {
        return await getJson<TraceDetail>(
          `/api/v1/projects/${projectId}/traces/by-run/${runId}${query({ offset, limit: TRACE_PAGE_SIZE })}`,
        )
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
    enabled: isConfigured && !!projectId && !!runId,
    refetchInterval: (q) => liveInterval(q.state.data),
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
