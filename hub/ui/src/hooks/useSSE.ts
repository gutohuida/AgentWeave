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
  'agent_session_changed',
  'log_event',
  'context_warning',
  'spec_updated',
]

const MAX_BUFFERED = 200

const listeners = new Set<SSEListener>()
/** Subscribers notified when the SSE stream reconnects after a previous
 * connection ended. The first connect (initial mount) does NOT fire this —
 * only subsequent reconnects do. Used by useAgentOutput to schedule a
 * one-shot reconciliation poll after the stream was down (M21). */
const reconnectListeners = new Set<() => void>()
let activeStream: { cancel: () => void } | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let connectedUrl = ''
let connectedKey = ''
let hasEverConnected = false
let subscriberCount = 0
let connectingUrl = ''
let connectingKey = ''
const eventBuffer: SSEEvent[] = []

export function getBufferedEvents(): SSEEvent[] {
  return eventBuffer.slice()
}

/** Subscribe to SSE stream reconnect events. The callback fires every time
 * the underlying stream reconnects (NOT on the initial connect). Returns
 * an unsubscribe function. */
export function onSseReconnect(cb: () => void): () => void {
  reconnectListeners.add(cb)
  return () => {
    reconnectListeners.delete(cb)
  }
}

function fireReconnect(): void {
  reconnectListeners.forEach((cb) => {
    try {
      cb()
    } catch {
      // Swallow listener errors so one bad subscriber doesn't break the chain.
    }
  })
}

export function cancelReconnect(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (activeStream) {
    activeStream.cancel()
    activeStream = null
  }
  connectedUrl = ''
  connectedKey = ''
  connectingUrl = ''
  connectingKey = ''
}

/**
 * Test-only helper. Resets the module-level SSE state so unit tests are
 * deterministic. Not intended for production use.
 */
export function __resetSSEStateForTest(): void {
  cancelReconnect()
  listeners.clear()
  reconnectListeners.clear()
  hasEverConnected = false
  subscriberCount = 0
  eventBuffer.length = 0
}

function dispatchEvent(type: string, data: unknown): void {
  try {
    const obj = (data ?? {}) as Record<string, unknown>
    const severity = typeof obj?.severity === 'string' ? obj.severity : undefined
    const sseEvent: SSEEvent = { type, data, timestamp: new Date().toISOString(), severity }
    eventBuffer.push(sseEvent)
    if (eventBuffer.length > MAX_BUFFERED) eventBuffer.shift()
    listeners.forEach((fn) => fn(sseEvent))
  } catch {
    // ignore malformed events
  }
}

/**
 * Parse a chunk of SSE bytes into events. SSE format:
 *   event: <type>\n
 *   data: <json>\n
 *   \n
 * We accumulate a partial line buffer for the rare case a chunk splits a frame.
 */
function feedSSEChunk(buffer: string, chunk: string): { remaining: string; events: Array<{ type: string; data: string }> } {
  const combined = buffer + chunk
  const events: Array<{ type: string; data: string }> = []
  const frames = combined.split(/\r?\n\r?\n/)
  // All but the last entry are complete frames
  const remaining = frames.pop() ?? ''
  for (const frame of frames) {
    let eventType = 'message'
    const dataLines: string[] = []
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith('event:')) {
        eventType = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim())
      }
    }
    if (dataLines.length > 0) {
      events.push({ type: eventType, data: dataLines.join('\n') })
    }
  }
  return { remaining, events }
}

function scheduleReconnect(hubUrl: string, apiKey: string): void {
  if (subscriberCount === 0) return
  if (reconnectTimer) clearTimeout(reconnectTimer)
  reconnectTimer = setTimeout(() => connect(hubUrl, apiKey), 3000)
}

async function connect(hubUrl: string, apiKey: string): Promise<void> {
  if (subscriberCount === 0) return
  // No-op if already connected with the same config
  if (connectedUrl === hubUrl && connectedKey === apiKey && activeStream !== null) {
    return
  }
  // Multiple mounted hooks may ask for the stream in the same render pass.
  // Share the in-flight connection attempt as well as the resulting stream.
  if (connectingUrl === hubUrl && connectingKey === apiKey) return
  connectingUrl = hubUrl
  connectingKey = apiKey
  connectedUrl = hubUrl
  connectedKey = apiKey
  if (activeStream) {
    activeStream.cancel()
    activeStream = null
  }

  const url = `${hubUrl}/api/v1/events`
  let response: Response
  try {
    response = await fetch(url, {
      headers: { Authorization: `Bearer ${apiKey}` },
    })
  } catch {
    if (connectingUrl === hubUrl && connectingKey === apiKey) {
      connectingUrl = ''
      connectingKey = ''
    }
    scheduleReconnect(hubUrl, apiKey)
    return
  }
  if (!response.ok || !response.body) {
    if (connectingUrl === hubUrl && connectingKey === apiKey) {
      connectingUrl = ''
      connectingKey = ''
    }
    scheduleReconnect(hubUrl, apiKey)
    return
  }

  if (subscriberCount === 0) {
    await response.body.cancel()
    return
  }

  if (connectingUrl === hubUrl && connectingKey === apiKey) {
    connectingUrl = ''
    connectingKey = ''
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let cancelled = false

  const cancel = () => {
    cancelled = true
    reader.cancel().catch(() => {})
  }
  activeStream = { cancel }

  // Fire the reconnect hook for any connect after the first one. The first
  // connect is NOT a reconnect — it's the initial subscription. Subscribers
  // (e.g. useAgentOutput) use this to schedule a one-shot reconciliation
  // poll to catch up on events that arrived while the stream was down.
  if (hasEverConnected) {
    fireReconnect()
  }
  hasEverConnected = true

  ;(async () => {
    try {
      while (!cancelled) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const { remaining, events } = feedSSEChunk(buffer, '')
        buffer = remaining
        for (const evt of events) {
          // Only dispatch known event types and the unnamed "message" / "connected" keepalive
          if (evt.type === 'message') {
            // keepalive / connected — ignore
            continue
          }
          if (SSE_EVENT_TYPES.includes(evt.type)) {
            let parsed: unknown = evt.data
            try {
              parsed = JSON.parse(evt.data)
            } catch {
              // keep raw string
            }
            dispatchEvent(evt.type, parsed)
          }
        }
      }
    } catch {
      // stream errored
    } finally {
      if (!cancelled) {
        // Stream ended unexpectedly → schedule reconnect
        if (activeStream && activeStream.cancel === cancel) {
          activeStream = null
        }
        scheduleReconnect(hubUrl, apiKey)
      }
    }
  })()
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
    subscriberCount += 1
    connect(hubUrl, apiKey)
    return () => {
      subscriberCount = Math.max(0, subscriberCount - 1)
      // The stream is shared by every useSSE consumer. Only the final
      // subscriber may tear it down; unmounting a page must not interrupt
      // another page's live updates.
      if (subscriberCount === 0) {
        cancelReconnect()
      }
    }
  }, [hubUrl, apiKey, isConfigured])

  // When the user clears their config (e.g. logout), tear down any pending
  // reconnect timer so we don't keep retrying in the background.
  useEffect(() => {
    if (!isConfigured) {
      cancelReconnect()
    }
  }, [isConfigured])

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
          queryClient.invalidateQueries({ queryKey: ['tasks'] })
          queryClient.invalidateQueries({ queryKey: ['agents'] })
          break
        case 'context_warning':
          queryClient.invalidateQueries({ queryKey: ['agents'] })
          break
        case 'agent_session_changed': {
          const d = event.data as { agent?: string }
          if (d?.agent) {
            queryClient.invalidateQueries({ queryKey: ['agent', d.agent, 'sessions'] })
          }
          break
        }
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
