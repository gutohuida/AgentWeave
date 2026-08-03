import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { onSseReconnect, useSSE, SSEEvent } from '@/hooks/useSSE'

export interface AgentSummary {
  name: string
  status: string
  latest_status_msg?: string
  last_seen?: string
  message_count: number
  active_task_count: number
  role?: string  // "principal" | "delegate" | "collaborator"
  yolo?: boolean
  runner?: string  // "native" | "claude_proxy" | "kimi" | "manual"
  display_model?: string  // e.g. "Claude", "Kimi", "Minimax" — derived from runner
  dev_role?: string        // Primary dev role (backward compatibility)
  dev_role_label?: string  // Primary dev role label
  dev_roles?: string[]        // All role IDs (new multi-role support)
  dev_role_labels?: string[]  // Labels for all roles
  context_usage?: ContextUsage
  session_started_at?: string  // ISO timestamp when current session started
  self_registered?: boolean  // True if agent joined via self-registration
  liveness?: 'online' | 'offline' | null  // Liveness for self-registered agents
  runner_options?: Record<string, unknown>  // Runner-specific options (e.g., memory for Codex)
  color_index?: number | null  // Stable palette index, assigned once at registration
}

export interface AgentLaunchability {
  runner?: string
  present: boolean
  authorized: boolean
  runnable: boolean
  reason?: string | null
}

export interface AgentLaunchabilityResponse {
  agents: Record<string, AgentLaunchability>
}

export interface ContextUsage {
  status: ContextUsageStatus
  source: string
  basis?: ContextUsageBasis | null
  context_tokens?: number | null
  limit_tokens?: number | null
  percent?: number | null
  model?: string | null
  session_id?: string | null
  observed_at: number
  breakdown?: ContextUsageBreakdown | null
}

export type ContextUsageStatus = 'measured' | 'estimated' | 'unsupported' | 'unavailable'

export type ContextUsageBasis =
  | 'provider_context'
  | 'latest_request_input'
  | 'provider_reported_ratio'
  | 'cumulative_delta'

export interface ContextUsageBreakdown {
  input_tokens?: number
  output_tokens?: number
  cache_read_tokens?: number
  cache_creation_tokens?: number
  reasoning_tokens?: number
  cached_input_tokens?: number
}

export interface AgentTimelineEvent {
  id: string
  event_type: string
  timestamp: string
  summary: string
  data: Record<string, unknown>
}

export interface AgentOutputLine {
  id: string
  agent: string
  session_id?: string
  content: string
  timestamp: string
  kind?: StreamEventKind | null
  payload?: Record<string, unknown> | null
  run_id?: string | null
  sequence?: number | null
}

export type StreamEventKind =
  | 'text' | 'thinking' | 'tool_use' | 'tool_result'
  | 'status' | 'diagnostic' | 'error'

export interface AgentSession {
  id: string
  type: string
  path: string
  last_active?: string
  started_at?: string
}

export function useAgents() {
  const { isConfigured } = useConfigStore()
  const queryClient = useQueryClient()

  // Invalidate immediately when the CLI pushes a session_synced SSE event
  useSSE((event) => {
    if (event.type === 'session_synced') {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    }
  })

  // Invalidated by session_synced above and by agent_heartbeat/context_warning
  // in useSSE.ts's central switch; a lost connection is now visible (the
  // StatusBar "Reconnecting…" indicator) and self-heals via the
  // invalidateQueries() reconciliation on reconnect, so the poll fallback
  // this used to need is no longer necessary.
  return useQuery<AgentSummary[]>({
    queryKey: ['agents'],
    queryFn: () => getJson<AgentSummary[]>('/api/v1/agents'),
    enabled: isConfigured,
  })
}

export function useAgentLaunchability() {
  const { isConfigured } = useConfigStore()
  return useQuery<AgentLaunchabilityResponse>({
    queryKey: ['agents', 'launchability'],
    queryFn: () => getJson<AgentLaunchabilityResponse>('/api/v1/agents/launchability'),
    enabled: isConfigured,
    staleTime: 30_000,
  })
}

/** True if an SSE event carries one of the three source rows the timeline
 * endpoint merges (Message, EventLog, AgentHeartbeat) for the given agent. */
export function eventBelongsToTimeline(event: SSEEvent, name: string): boolean {
  const d = (event.data ?? {}) as Record<string, unknown>
  switch (event.type) {
    case 'message_created':
      return d.from === name || d.to === name || d.recipient === name
    case 'log_event':
    case 'agent_heartbeat':
    case 'run_started':
    case 'run_completed':
    case 'run_failed':
    case 'run_stopped':
    case 'run_interrupted':
      return d.agent === name
    default:
      return false
  }
}

export function useAgentTimeline(name: string | null) {
  const { isConfigured } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    if (name && eventBelongsToTimeline(event, name)) {
      queryClient.invalidateQueries({ queryKey: ['agents', name, 'timeline'] })
    }
  })

  return useQuery<AgentTimelineEvent[]>({
    queryKey: ['agents', name, 'timeline'],
    queryFn: () => getJson<AgentTimelineEvent[]>(`/api/v1/agents/${name}/timeline`),
    enabled: isConfigured && !!name,
  })
}

// Global cache for agent output lines that persists across component mounts
const linesCache = new Map<string, AgentOutputLine[]>()

export function useAgentOutput(name: string | null) {
  const { isConfigured } = useConfigStore()
  const queryClient = useQueryClient()
  const nameRef = useRef(name)
  const isInitialMount = useRef(true)
  // M21 gap-timer + poll refs. The polling effect arms the timer and
  // publishes the current `poll` function into `pollRef.current`. The SSE
  // handler (registered at module/listener level, no closure over the
  // effect) reads `pollRef.current` and re-arms the gap timer so a
  // continuous stream of events keeps the timer from firing, while a
  // quiet stream lets the timer fire a single reconciliation poll.
  const gapTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pollRef = useRef<(() => void) | null>(null)
  nameRef.current = name

  const cacheKey = name || 'null'

  // Seed from REST on mount / agent change - using React Query for caching
  const { data: initialData, isLoading: isLoadingInitial } = useQuery<AgentOutputLine[]>({
    queryKey: ['agents', name, 'output', 'seed'],
    queryFn: () => getJson<AgentOutputLine[]>(`/api/v1/agents/${name}/output?limit=200`),
    enabled: isConfigured && !!name,
    staleTime: 1000 * 60 * 5, // 5 minutes
  })

  // Sync initial data to cache on first mount or agent change
  useEffect(() => {
    if (!name || !initialData) return

    // On initial mount or agent change, merge server data with cache
    // Server data takes precedence for deduplication
    if (isInitialMount.current) {
      const existingIds = new Set((linesCache.get(cacheKey) || []).map(l => l.id))
      const newFromServer = initialData.filter(l => !existingIds.has(l.id))

      if (newFromServer.length > 0 || !linesCache.has(cacheKey)) {
        const merged = [...(linesCache.get(cacheKey) || []), ...newFromServer]
        // Sort by timestamp to ensure correct order
        merged.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
        linesCache.set(cacheKey, merged)
        // Trigger re-render by invalidating the custom query key
        queryClient.invalidateQueries({ queryKey: ['agents', name, 'lines'] })
      }
      isInitialMount.current = false
    }
  }, [name, cacheKey, initialData, queryClient])

  // Reset isInitialMount when agent changes
  useEffect(() => {
    isInitialMount.current = true
  }, [name])

  // Get current lines from cache (using a dummy query to trigger re-renders)
  const { data: lines = [] } = useQuery<AgentOutputLine[]>({
    queryKey: ['agents', name, 'lines'],
    queryFn: () => linesCache.get(cacheKey) || [],
    enabled: !!name,
    staleTime: Infinity,
    initialData: () => linesCache.get(cacheKey) || [],
  })

  const isLoading = isLoadingInitial && lines.length === 0

  // Reconcile on SSE gap or reconnect (M21). Replaces the previous
  // unconditional `setInterval(poll, 2000)` with a one-shot gap timer
  // that's reset every time an SSE event arrives for this agent. If the
  // stream goes quiet for >5 s the timer fires a single reconciliation
  // poll; any subsequent SSE event resets it again. SSE reconnects also
  // fire a poll since events may have arrived while the stream was down.
  useEffect(() => {
    if (!isConfigured || !name) return

    let disposed = false

    const armGapTimer = () => {
      if (disposed) return
      if (gapTimerRef.current) clearTimeout(gapTimerRef.current)
      gapTimerRef.current = setTimeout(() => {
        gapTimerRef.current = null
        pollRef.current?.()
      }, 5000)
    }

    const poll = async () => {
      if (disposed) return
      try {
        const currentLines = linesCache.get(cacheKey) || []
        const lastTimestamp = currentLines[currentLines.length - 1]?.timestamp
        const since = lastTimestamp
          ? `&since=${encodeURIComponent(lastTimestamp)}`
          : ''
        const newLines = await getJson<AgentOutputLine[]>(
          `/api/v1/agents/${name}/output?limit=50${since}`,
        )
        if (!disposed && newLines.length > 0) {
          const existingIds = new Set((linesCache.get(cacheKey) || []).map(l => l.id))
          const uniqueNew = newLines.filter(l => !existingIds.has(l.id))
          if (uniqueNew.length > 0) {
            const merged = [...(linesCache.get(cacheKey) || []), ...uniqueNew]
            merged.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
            linesCache.set(cacheKey, merged)
            queryClient.invalidateQueries({ queryKey: ['agents', name, 'lines'] })
          }
        }
      } catch {
        // Silently fail polling - SSE is the primary source
      } finally {
        // A fallback poll is a reconciliation cycle, not a one-shot recovery.
        // Re-arm even when the Hub request fails so a stalled SSE stream heals.
        armGapTimer()
      }
    }

    // Publish poll to the ref so the SSE handler (handleSSE.current) can
    // re-arm the gap timer around a fresh `poll()` invocation.
    pollRef.current = () => { void poll() }
    armGapTimer()

    // Initial poll on mount to seed from REST.
    void poll()

    // Reconnect handler: SSE just re-established after being down.
    // Poll once to catch up on any events the stream missed.
    const unsubscribe = onSseReconnect(poll)

    return () => {
      disposed = true
      if (gapTimerRef.current) {
        clearTimeout(gapTimerRef.current)
        gapTimerRef.current = null
      }
      pollRef.current = null
      unsubscribe()
    }
  }, [isConfigured, name, cacheKey, queryClient])

  // Append new lines from SSE and reset the gap timer on each event so the
  // poll only fires when the stream is actually quiet.
  const handleSSE = useRef<(e: SSEEvent) => void>(() => {})
  handleSSE.current = (event: SSEEvent) => {
    if (event.type !== 'agent_output') return
    const d = event.data as AgentOutputLine
    if (d.agent !== nameRef.current) return

    const agentKey = d.agent
    const newLine: AgentOutputLine = {
      id: d.id,
      agent: d.agent,
      session_id: d.session_id,
      content: d.content,
      timestamp: d.timestamp,
      kind: d.kind,
      payload: d.payload,
      run_id: d.run_id,
      sequence: d.sequence,
    }

    // Reset the gap timer — a fresh event means the stream is alive.
    // pollRef is non-null while the polling useEffect is mounted.
    if (pollRef.current) {
      if (gapTimerRef.current) clearTimeout(gapTimerRef.current)
      gapTimerRef.current = setTimeout(() => {
        gapTimerRef.current = null
        pollRef.current?.()
      }, 5000)
    }

    const current = linesCache.get(agentKey) || []
    if (current.some(l => l.id === newLine.id)) return
    linesCache.set(agentKey, [...current, newLine])
    queryClient.invalidateQueries({ queryKey: ['agents', d.agent, 'lines'] })
  }

  useSSE((event) => handleSSE.current(event))

  return { lines, isLoading }
}

export function useAgentSessions(agentName: string | null) {
  const { isConfigured } = useConfigStore()
  return useQuery<{ sessions: AgentSession[] }>({
    queryKey: ['agent', agentName, 'sessions'],
    queryFn: () => getJson<{ sessions: AgentSession[] }>(`/api/v1/agent/sessions/${agentName}`),
    enabled: isConfigured && !!agentName,
  })
}
