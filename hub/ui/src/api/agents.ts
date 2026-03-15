import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
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

export function useAgents() {
  const { isConfigured } = useConfigStore()
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

export function useAgentOutput(name: string | null) {
  const { isConfigured } = useConfigStore()
  const [lines, setLines] = useState<AgentOutputLine[]>([])
  const nameRef = useRef(name)
  const seededRef = useRef(false)
  nameRef.current = name

  // Reset when agent changes
  useEffect(() => {
    setLines([])
    seededRef.current = false
  }, [name])

  // Seed from REST on mount / name change (once — staleTime:Infinity prevents
  // automatic refetches from clobbering live SSE-appended lines)
  const { data: initial } = useQuery<AgentOutputLine[]>({
    queryKey: ['agents', name, 'output'],
    queryFn: () => getJson<AgentOutputLine[]>(`/api/v1/agents/${name}/output?limit=200`),
    enabled: isConfigured && !!name,
    staleTime: Infinity,
  })

  useEffect(() => {
    if (!initial || seededRef.current) return
    seededRef.current = true
    setLines(initial)
  }, [initial])

  // Append new lines from SSE — stable ref avoids listener churn
  const handleSSE = useRef<(e: SSEEvent) => void>(() => {})
  handleSSE.current = (event: SSEEvent) => {
    if (event.type !== 'agent_output') return
    const d = event.data as { agent: string; content: string; session_id?: string; timestamp: string }
    if (d.agent !== nameRef.current) return
    setLines((prev) => [
      ...prev,
      { id: `live-${Date.now()}`, agent: d.agent, session_id: d.session_id, content: d.content, timestamp: d.timestamp },
    ])
  }

  useSSE((event) => handleSSE.current(event))

  return { lines }
}
