import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'

export interface SSEEvent {
  type: string
  data: unknown
  timestamp: string
  severity?: string
}

type SSEListener = (event: SSEEvent) => void

const SSE_EVENT_TYPES = [
  'message_created',
  'message_read',
  'task_created',
  'task_updated',
  'question_asked',
  'question_answered',
  'agent_heartbeat',
  'agent_output',
  'agent_config_updated',
  'agent_removed',
  'log_event',
]

const MAX_BUFFERED = 200

const listeners = new Set<SSEListener>()
let eventSource: EventSource | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let connectedUrl = ''
let connectedKey = ''
const eventBuffer: SSEEvent[] = []

export function getBufferedEvents(): SSEEvent[] {
  return eventBuffer.slice()
}

function handleNamedEvent(type: string, e: MessageEvent) {
  try {
    const data = JSON.parse(e.data) as Record<string, unknown>
    const severity = typeof data?.severity === 'string' ? data.severity : undefined
    const sseEvent: SSEEvent = { type, data, timestamp: new Date().toISOString(), severity }
    eventBuffer.push(sseEvent)
    if (eventBuffer.length > MAX_BUFFERED) eventBuffer.shift()
    listeners.forEach((fn) => fn(sseEvent))
  } catch {
    // ignore malformed events
  }
}

function connect(hubUrl: string, apiKey: string) {
  // No-op if already connected with the same config
  if (
    connectedUrl === hubUrl &&
    connectedKey === apiKey &&
    eventSource !== null &&
    eventSource.readyState !== EventSource.CLOSED
  ) {
    return
  }
  connectedUrl = hubUrl
  connectedKey = apiKey
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  const url = `${hubUrl}/api/v1/events?token=${encodeURIComponent(apiKey)}`
  eventSource = new EventSource(url)

  // Handle the initial "connected" confirmation (unnamed event)
  eventSource.onmessage = () => {
    // keepalive / connected — no-op
  }

  // Subscribe to each named event type the server emits
  for (const type of SSE_EVENT_TYPES) {
    eventSource.addEventListener(type, (e) => handleNamedEvent(type, e as MessageEvent))
  }

  eventSource.onerror = () => {
    eventSource?.close()
    eventSource = null
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(() => connect(hubUrl, apiKey), 3000)
  }
}

export function useSSE(onEvent?: SSEListener) {
  const { hubUrl, apiKey, isConfigured } = useConfigStore()
  const queryClient = useQueryClient()
  const listenerRef = useRef<SSEListener | null>(null)
  // Keep onEvent in a ref so the effect below doesn't need it as a dep.
  // This prevents constant listener teardown/re-add on every render.
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!isConfigured) return
    connect(hubUrl, apiKey)
  }, [hubUrl, apiKey, isConfigured])

  useEffect(() => {
    const invalidateHandler: SSEListener = (event) => {
      switch (event.type) {
        case 'message_created':
        case 'message_read':
          queryClient.invalidateQueries({ queryKey: ['messages'] })
          queryClient.invalidateQueries({ queryKey: ['status'] })
          break
        case 'task_created':
        case 'task_updated':
          queryClient.invalidateQueries({ queryKey: ['tasks'] })
          queryClient.invalidateQueries({ queryKey: ['status'] })
          break
        case 'question_asked':
        case 'question_answered':
          queryClient.invalidateQueries({ queryKey: ['questions'] })
          queryClient.invalidateQueries({ queryKey: ['status'] })
          break
        case 'agent_heartbeat':
          queryClient.invalidateQueries({ queryKey: ['agents'] })
          break
        case 'agent_config_updated':
        case 'agent_removed':
          queryClient.invalidateQueries({ queryKey: ['agentConfigs'] })
          queryClient.invalidateQueries({ queryKey: ['agents'] })
          break
      }
      onEventRef.current?.(event)
    }

    if (listenerRef.current) {
      listeners.delete(listenerRef.current)
    }
    listenerRef.current = invalidateHandler
    listeners.add(invalidateHandler)

    return () => {
      if (listenerRef.current) {
        listeners.delete(listenerRef.current)
        listenerRef.current = null
      }
    }
  }, [queryClient]) // onEvent intentionally omitted — use onEventRef instead
}
