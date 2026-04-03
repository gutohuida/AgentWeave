import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { useSSE, SSEEvent } from '@/hooks/useSSE'

export interface AgentSummary {
  name: string
  status: string
  latest_status_msg?: string
  last_seen?: string
  message_count: number
  active_task_count: number
  role?: string  // "principal" | "delegate" | "collaborator"
  yolo?: boolean
  runner?: string  // "native" | "claude_proxy" | "manual"
  dev_role?: string        // Primary dev role (backward compatibility)
  dev_role_label?: string  // Primary dev role label
  dev_roles?: string[]        // All role IDs (new multi-role support)
  dev_role_labels?: string[]  // Labels for all roles
  context_usage?: ContextUsage
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

export function useAgentOutput(name: string | null) {
  const { isConfigured, apiKey } = useConfigStore()
  const queryClient = useQueryClient()
  const nameRef = useRef(name)
  const isInitialMount = useRef(true)
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

  // Poll for new lines every 2 seconds (fallback when SSE misses events)
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

    // Poll immediately on mount
    poll()
    const interval = setInterval(poll, 2000)
    return () => clearInterval(interval)
  }, [isConfigured, name, cacheKey, apiKey, queryClient])

  // Append new lines from SSE
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
