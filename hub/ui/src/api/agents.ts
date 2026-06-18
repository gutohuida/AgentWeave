import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
  pilot?: boolean  // Pilot mode: manual control, disables auto-execution
  registered_session_id?: string | null  // Registered --resume session ID for pilot agents
  self_registered?: boolean  // True if agent joined via self-registration
  liveness?: 'online' | 'offline' | null  // Liveness for self-registered agents
  runner_options?: Record<string, unknown>  // Runner-specific options (e.g., memory for Codex)
}

export interface ContextUsage {
  agent?: string
  model?: string
  tokens_used?: number
  tokens_limit?: number
  percent?: number
  warning?: boolean
  critical?: boolean
  threshold_warning?: number
  threshold_critical?: number
  updated_at?: string
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
}

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

  return useQuery<AgentSummary[]>({
    queryKey: ['agents'],
    queryFn: () => getJson<AgentSummary[]>('/api/v1/agents'),
    enabled: isConfigured,
    refetchInterval: 10000,
  })
}

export function useAgentTimeline(name: string | null) {
  const { isConfigured } = useConfigStore()
  return useQuery<AgentTimelineEvent[]>({
    queryKey: ['agents', name, 'timeline'],
    queryFn: () => getJson<AgentTimelineEvent[]>(`/api/v1/agents/${name}/timeline`),
    enabled: isConfigured && !!name,
    refetchInterval: 5000,
  })
}

// Global cache for agent output lines that persists across component mounts
const linesCache = new Map<string, AgentOutputLine[]>()

interface RegisterSessionVars {
  agent: string
  sessionId: string
}

export function useRegisterSession() {
  const queryClient = useQueryClient()
  const { apiKey } = useConfigStore()

  return useMutation<unknown, Error, RegisterSessionVars>({
    mutationFn: async ({ agent, sessionId }: RegisterSessionVars) => {
      const response = await fetch(`/api/v1/agents/${agent}/register-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`,
        },
        body: JSON.stringify({ session_id: sessionId }),
      })
      if (!response.ok) {
        throw new Error('Failed to register session')
      }
      return response.json()
    },
    onSuccess: (_data, variables) => {
      // Invalidate agent data to refresh the UI
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['agents', variables.agent] })
    },
  })
}

interface SetPilotModeVars {
  agent: string
  enabled: boolean
}

export function useSetPilotMode() {
  const queryClient = useQueryClient()
  const { apiKey } = useConfigStore()

  return useMutation<unknown, Error, SetPilotModeVars>({
    mutationFn: async ({ agent, enabled }: SetPilotModeVars) => {
      const response = await fetch(`/api/v1/agents/${agent}/pilot`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`,
        },
        body: JSON.stringify({ enabled }),
      })
      if (!response.ok) {
        throw new Error('Failed to set pilot mode')
      }
      return response.json()
    },
    onSuccess: (_data, variables) => {
      // Invalidate agent data to refresh the UI
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['agents', variables.agent] })
    },
  })
}

export function useAgentOutput(name: string | null) {
  const { isConfigured, apiKey } = useConfigStore()
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

    const poll = async () => {
      try {
        const currentLines = linesCache.get(cacheKey) || []
        const lastTimestamp = currentLines[currentLines.length - 1]?.timestamp
        const since = lastTimestamp
          ? `&since=${encodeURIComponent(lastTimestamp)}`
          : ''
        const url = `/api/v1/agents/${name}/output?limit=50${since}`
        const response = await fetch(url, {
          headers: { 'Authorization': `Bearer ${apiKey}` }
        })
        if (response.ok) {
          const newLines: AgentOutputLine[] = await response.json()
          if (newLines.length > 0) {
            const existingIds = new Set((linesCache.get(cacheKey) || []).map(l => l.id))
            const uniqueNew = newLines.filter(l => !existingIds.has(l.id))
            if (uniqueNew.length > 0) {
              const merged = [...(linesCache.get(cacheKey) || []), ...uniqueNew]
              linesCache.set(cacheKey, merged)
              queryClient.invalidateQueries({ queryKey: ['agents', name, 'lines'] })
            }
          }
        }
      } catch {
        // Silently fail polling - SSE is the primary source
      }
    }

    // Publish poll to the ref so the SSE handler (handleSSE.current) can
    // re-arm the gap timer around a fresh `poll()` invocation.
    pollRef.current = () => { void poll() }

    const armGapTimer = () => {
      if (gapTimerRef.current) clearTimeout(gapTimerRef.current)
      gapTimerRef.current = setTimeout(() => {
        gapTimerRef.current = null
        pollRef.current?.()
      }, 5000)
    }
    armGapTimer()

    // Initial poll on mount to seed from REST.
    poll()

    // Reconnect handler: SSE just re-established after being down.
    // Poll once to catch up on any events the stream missed.
    const unsubscribe = onSseReconnect(poll)

    return () => {
      if (gapTimerRef.current) {
        clearTimeout(gapTimerRef.current)
        gapTimerRef.current = null
      }
      pollRef.current = null
      unsubscribe()
    }
  }, [isConfigured, name, cacheKey, apiKey, queryClient])

  // Append new lines from SSE and reset the gap timer on each event so the
  // poll only fires when the stream is actually quiet.
  const handleSSE = useRef<(e: SSEEvent) => void>(() => {})
  handleSSE.current = (event: SSEEvent) => {
    if (event.type !== 'agent_output') return
    const d = event.data as { id: string; agent: string; content: string; session_id?: string; timestamp: string }
    if (d.agent !== nameRef.current) return

    const agentKey = d.agent
    const newLine: AgentOutputLine = {
      id: d.id,
      agent: d.agent,
      session_id: d.session_id,
      content: d.content,
      timestamp: d.timestamp
    }

    const current = linesCache.get(agentKey) || []
    if (current.some(l => l.id === newLine.id)) return
    linesCache.set(agentKey, [...current, newLine])
    queryClient.invalidateQueries({ queryKey: ['agents', d.agent, 'lines'] })

    // Reset the gap timer — a fresh event means the stream is alive.
    // pollRef is non-null while the polling useEffect is mounted.
    if (pollRef.current) {
      if (gapTimerRef.current) clearTimeout(gapTimerRef.current)
      gapTimerRef.current = setTimeout(() => {
        gapTimerRef.current = null
        pollRef.current?.()
      }, 5000)
    }
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
    refetchInterval: 10000,
  })
}
