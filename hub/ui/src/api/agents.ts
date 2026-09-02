import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteJson, getJson, patchJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { onSseReconnect, useSSE, SSEEvent } from '@/hooks/useSSE'
import { hubDate } from '@/lib/hubTime'

export interface AgentSummary {
  name: string
  /** What this agent is for, in the operator's words. Absent when unset — never "". */
  description?: string | null
  status: string
  latest_status_msg?: string
  last_seen?: string
  message_count: number
  active_task_count: number
  /** "open" or "archived". Only ever "archived" for a caller that asked for archived agents. */
  lifecycle?: 'open' | 'archived'
  runner?: string  // The bound Runner's CLI; "native" when there is no binding
  display_model?: string  // e.g. "Claude", "Kimi", "Minimax" — derived from runner
  context_usage?: ContextUsage
  session_started_at?: string  // ISO timestamp when current session started
  self_registered?: boolean  // True if agent joined via self-registration
  liveness?: 'online' | 'offline' | null  // Liveness for self-registered agents
  runner_options?: Record<string, unknown>  // Runner-specific options (e.g., memory for Codex)
  color_index?: number | null  // Stable palette index, assigned once at registration
  runner_id?: string | null  // Bound Runner record, if any (runner-agent-charter-separation)
  charter_id?: string | null  // Bound Charter record, if any (runner-agent-charter-separation)
  /** How long this agent waits on the operator. `null` means the built-in default. */
  permission_timeout_seconds?: number | null
  question_timeout_seconds?: number | null
  /** What this agent may do when the conversation has not said. `null` is the built-in default. */
  default_permission_mode?: string | null
  /** Per-agent checkpoint overrides. All null means "inherit the project's". */
  checkpoint_mode?: 'off' | 'offered' | 'automatic' | null
  checkpoint_threshold_mode?: 'percent' | 'tokens' | null
  checkpoint_threshold_value?: number | null
  checkpoint_notes_value?: number | null
  /** Two independent grants, both closed by default. Summary access is not transcript access. */
  can_read_checkpoints?: boolean
  can_recall?: boolean
  /** Authority over what ships: accepted evidence is what lets approval merge an agent's work. */
  can_accept_evidence?: boolean
}

export interface AgentLaunchability {
  runner?: string
  present: boolean
  authorized: boolean
  runnable: boolean
  reason?: string | null
  /** Only meaningful for an agent the Hub can trigger directly (a bound Runner) and
   * only once `runnable` already holds — `null` means "not applicable", not "unready".
   * See openspec/changes/2026-08-06-agent-messaging-delivery/tasks.md §6. */
  collaboration_ready?: boolean | null
  collaboration_reason?: string | null
}

export interface AgentLaunchabilityResponse {
  agents: Record<string, AgentLaunchability>
}

/** Either `runner_id` or both `provider` and `model` — not both, not neither. See
 * `OperatorAgentCreate` in hub/hub/api/v1/agents.py for the same contract. */
export type AgentCreate =
  | { name: string; runner_id: string; charter_id?: string }
  | { name: string; provider: string; model: string; charter_id?: string }

export interface CreatedAgent {
  id: string
  name: string
  runner_id: string
  charter_id?: string | null
  color_index: number
  contact_mode: string
  self_registered: boolean
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

/** Every lifecycle status a run can be in; `started` is the only one that is not terminal.
 *
 *  It lives here, beside the response that carries it, rather than in `lib/agentTimelineModel`
 *  where it used to: the timeline route now *states* a run's status (renaming `Run.status`'s
 *  `running` to `started` at the boundary, design D5), so this is a wire value rather than
 *  something the client reduces its way to. */
export type RunLifecycleStatus =
  | 'started'
  | 'completed'
  | 'failed'
  | 'stopped'
  | 'interrupted'

/** What a run's own row records about how it went — the server's `RunFacts`.
 *
 *  Read from `Run`, never from which lifecycle events happen to have landed in the window, so
 *  a run whose terminal event is outside the window still reports its outcome. */
export interface AgentRunFacts {
  status: RunLifecycleStatus
  exit_code?: number | null
  started_at: string
  ended_at?: string | null
}

/** The timeline response: the events, and the facts of the runs those events name.
 *
 *  `runs` is keyed by `run_id` and holds a row for exactly the runs the returned events name.
 *  A lookup miss therefore means "no run row for this id", never "this run has not ended". */
export interface AgentTimelineResponse {
  events: AgentTimelineEvent[]
  runs: Record<string, AgentRunFacts>
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

/** Which agents a caller wants. `open` is the default everywhere an agent is *offered*.
 *
 *  `all` exists for the one surface that must still resolve an archived agent — its own
 *  configuration page, which is where unarchiving happens. */
export type AgentLifecycleFilter = 'open' | 'archived' | 'all'

export function useAgents(lifecycle: AgentLifecycleFilter = 'open') {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()

  // Invalidate immediately when the CLI pushes a session_synced SSE event
  useSSE((event) => {
    const d = (event.data ?? {}) as { project_id?: string }
    if (event.type === 'session_synced' && d.project_id === projectId) {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agents'] })
    }
  })

  // Invalidated by session_synced above and by agent_heartbeat/context_warning
  // in useSSE.ts's central switch; a lost connection is now visible (the
  // StatusBar "Reconnecting…" indicator) and self-heals via the
  // invalidateQueries() reconciliation on reconnect, so the poll fallback
  // this used to need is no longer necessary.
  return useQuery<AgentSummary[]>({
    // The filter is part of the key: an "all" fetch must not overwrite the open roster every
    // other surface reads, or opening one settings page would put archived agents in the rail.
    queryKey: ['project', projectId, 'agents', ...(lifecycle === 'open' ? [] : [lifecycle])],
    queryFn: () =>
      getJson<AgentSummary[]>(
        `/api/v1/projects/${projectId}/agents${lifecycle === 'open' ? '' : `?lifecycle=${lifecycle}`}`,
      ),
    enabled: isConfigured && !!projectId,
  })
}

export function useArchiveAgent() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: async ({
      agent,
      archived,
      discardQueueEntryIds = [],
    }: {
      agent: string
      archived: boolean
      discardQueueEntryIds?: string[]
    }) => {
      for (const entryId of discardQueueEntryIds) {
        await deleteJson(`/api/v1/projects/${projectId}/queue/entries/${entryId}`)
      }
      return postJson<{ name: string; lifecycle: string }>(
        `/api/v1/projects/${projectId}/agents/${agent}/${archived ? 'archive' : 'unarchive'}`,
        {},
      )
    },
    onSuccess: () => {
      // Every roster variant, not just the open one — the settings page is reading `all`, and it
      // is the surface the operator is looking at when this resolves.
      queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey[0] === 'project' &&
          query.queryKey[1] === projectId &&
          query.queryKey[2] === 'agents',
      })
    },
  })
}

/** The description bound to `MAX_DESCRIPTION_CHARS` in hub/hub/api/v1/agents.py. The API is the
 *  real guard; the input's maxLength stops the operator typing past it rather than being the only
 *  thing that catches it. */
export const MAX_AGENT_DESCRIPTION_CHARS = 256

/** Set or clear what this agent is for. `null` and a blank string are the same thing to the API,
 *  which normalizes both to no description. */
export function useUpdateAgentDescription() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ agent, description }: { agent: string; description: string | null }) =>
      patchJson(`/api/v1/projects/${projectId}/agents/${agent}`, { description }),
    onSuccess: () => {
      // Every roster variant: the settings page reads `all`, and it is the surface being looked at.
      queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey[0] === 'project' &&
          query.queryKey[1] === projectId &&
          query.queryKey[2] === 'agents',
      })
    },
  })
}

/** The agent's default posture. `null` clears it back to the built-in default.
 *
 * Writing this also rewrites the legacy `config.yolo` flag server-side — they are the same
 * choice at two ages, not two settings, and the Hub keeps them saying one thing. */
export function useUpdateAgentPermissionDefault() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ agent, mode }: { agent: string; mode: string | null }) =>
      patchJson(`/api/v1/projects/${projectId}/agents/${agent}`, {
        default_permission_mode: mode,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey[0] === 'project' &&
          query.queryKey[1] === projectId &&
          query.queryKey[2] === 'agents',
      })
    },
  })
}

/**
 * An agent's checkpoint override, applied as a whole threshold or not at all.
 *
 * Mode and value travel together. Sending one without the other is refused by the Hub, because an
 * agent inheriting `percent` and supplying `150` would read as 150% and never fire — configured
 * to look at, inert in practice.
 */
export function useUpdateAgentCheckpointOverride() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ agent, mode, value, notes }: {
      agent: string
      mode: 'percent' | 'tokens' | null
      value: number | null
      notes: number | null
    }) =>
      patchJson(`/api/v1/projects/${projectId}/agents/${agent}`, {
        checkpoint_threshold_mode: value === null ? null : mode,
        checkpoint_threshold_value: value,
        checkpoint_notes_value: value === null ? null : notes,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey[0] === 'project' &&
          query.queryKey[1] === projectId &&
          query.queryKey[2] === 'agents',
      })
    },
  })
}

/** Whether this agent checkpoints at all, independently of the threshold it uses. Null inherits. */
export function useUpdateAgentCheckpointMode() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ agent, mode }: { agent: string; mode: string | null }) =>
      patchJson(`/api/v1/projects/${projectId}/agents/${agent}`, { checkpoint_mode: mode }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey[0] === 'project' &&
          query.queryKey[1] === projectId &&
          query.queryKey[2] === 'agents',
      })
    },
  })
}

/** One of the two access grants. Separate calls, because they are separate permissions. */
export function useUpdateAgentGrant() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ agent, grant, enabled }: {
      agent: string
      grant: 'can_read_checkpoints' | 'can_recall' | 'can_accept_evidence'
      enabled: boolean
    }) => patchJson(`/api/v1/projects/${projectId}/agents/${agent}`, { [grant]: enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey[0] === 'project' &&
          query.queryKey[1] === projectId &&
          query.queryKey[2] === 'agents',
      })
    },
  })
}

export function useCreateAgent() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (agent: AgentCreate) =>
      postJson<CreatedAgent>(`/api/v1/projects/${projectId}/agents`, agent),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agents'] })
      queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] === 'projects' })
    },
  })
}

export function useAgentLaunchability() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<AgentLaunchabilityResponse>({
    queryKey: ['project', projectId, 'agents', 'launchability'],
    queryFn: () =>
      getJson<AgentLaunchabilityResponse>(`/api/v1/projects/${projectId}/agents/launchability`),
    enabled: isConfigured && !!projectId,
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
    case 'permission_denied':
    case 'question_not_asked': // retired backstop; kept so old event_logs rows still route
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
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    const d = (event.data ?? {}) as { project_id?: string }
    if (name && d.project_id === projectId && eventBelongsToTimeline(event, name)) {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agents', name, 'timeline'] })
    }
  })

  return useQuery<AgentTimelineResponse>({
    queryKey: ['project', projectId, 'agents', name, 'timeline'],
    queryFn: () =>
      getJson<AgentTimelineResponse>(`/api/v1/projects/${projectId}/agents/${name}/timeline`),
    enabled: isConfigured && !!projectId && !!name,
  })
}

// Global cache for agent output lines that persists across component mounts.
// Keyed by "<projectId>:<agentName>" — an agent name is only unique within
// its own project, so two projects' same-named agents must not share a slot.
const linesCache = new Map<string, AgentOutputLine[]>()

export function useAgentOutput(name: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
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

  const cacheKey = `${projectId ?? 'null'}:${name ?? 'null'}`

  // Seed from REST on mount / agent change - using React Query for caching
  const { data: initialData, isLoading: isLoadingInitial } = useQuery<AgentOutputLine[]>({
    queryKey: ['project', projectId, 'agents', name, 'output', 'seed'],
    queryFn: () =>
      getJson<AgentOutputLine[]>(`/api/v1/projects/${projectId}/agents/${name}/output?limit=200`),
    enabled: isConfigured && !!projectId && !!name,
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
        merged.sort((a, b) => hubDate(a.timestamp).getTime() - hubDate(b.timestamp).getTime())
        linesCache.set(cacheKey, merged)
        // Trigger re-render by invalidating the custom query key
        queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agents', name, 'lines'] })
      }
      isInitialMount.current = false
    }
  }, [name, projectId, cacheKey, initialData, queryClient])

  // Reset isInitialMount when agent changes
  useEffect(() => {
    isInitialMount.current = true
  }, [name, projectId])

  // Get current lines from cache (using a dummy query to trigger re-renders)
  const { data: lines = [] } = useQuery<AgentOutputLine[]>({
    queryKey: ['project', projectId, 'agents', name, 'lines'],
    queryFn: () => linesCache.get(cacheKey) || [],
    enabled: !!projectId && !!name,
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
    if (!isConfigured || !projectId || !name) return

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
          `/api/v1/projects/${projectId}/agents/${name}/output?limit=50${since}`,
        )
        if (!disposed && newLines.length > 0) {
          const existingIds = new Set((linesCache.get(cacheKey) || []).map(l => l.id))
          const uniqueNew = newLines.filter(l => !existingIds.has(l.id))
          if (uniqueNew.length > 0) {
            const merged = [...(linesCache.get(cacheKey) || []), ...uniqueNew]
            merged.sort((a, b) => hubDate(a.timestamp).getTime() - hubDate(b.timestamp).getTime())
            linesCache.set(cacheKey, merged)
            queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agents', name, 'lines'] })
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
  }, [isConfigured, projectId, name, cacheKey, queryClient])

  // Append new lines from SSE and reset the gap timer on each event so the
  // poll only fires when the stream is actually quiet.
  const handleSSE = useRef<(e: SSEEvent) => void>(() => {})
  handleSSE.current = (event: SSEEvent) => {
    if (event.type !== 'agent_output') return
    const d = event.data as AgentOutputLine & { project_id?: string }
    if (d.agent !== nameRef.current || d.project_id !== projectId) return

    const agentKey = cacheKey
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
    queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agents', d.agent, 'lines'] })
  }

  useSSE((event) => handleSSE.current(event))

  return { lines, isLoading }
}

export function useAgentSessions(agentName: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ sessions: AgentSession[] }>({
    queryKey: ['project', projectId, 'agent', agentName, 'sessions'],
    queryFn: () =>
      getJson<{ sessions: AgentSession[] }>(
        `/api/v1/projects/${projectId}/agent/sessions/${agentName}`,
      ),
    enabled: isConfigured && !!projectId && !!agentName,
  })
}
