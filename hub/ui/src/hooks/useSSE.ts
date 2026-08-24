import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'

export interface SSEEvent {
  type: string
  data: unknown
  timestamp: string
  severity?: string
}

type SSEListener = (event: SSEEvent) => void

/** 'closed' — not configured, or the last subscriber unmounted.
 * 'connecting' — first-ever connection attempt in flight.
 * 'open' — actively streaming.
 * 'reconnecting' — a previously open (or attempted) connection was lost and
 * a retry is scheduled or in flight. */
export type SSEConnectionState = 'closed' | 'connecting' | 'open' | 'reconnecting'

const SSE_EVENT_TYPES = [
  'message_created',
  'message_read',
  'task_created',
  'task_updated',
  'task_integration_retried',
  'queue_entry_abandoned',
  'question_asked',
  'question_answered',
  'agent_heartbeat',
  'agent_created',
  'agent_output',
  'agent_session_changed',
  'session_synced',
  'log_event',
  'context_warning',
  'spec_updated',
  'job_created',
  'job_updated',
  'job_deleted',
  'job_fired',
  'loop_stopped',
  'loop_queue_exhausted',
  'loop_archived',
  'loop_control_changed',
  'loop_edit_staged',
  'loop_edit_applied',
  'run_started',
  'run_completed',
  'run_failed',
  'run_stopped',
  'run_interrupted',
  'queue_entry_queued',
  'queue_entry_delivered',
  'queue_entry_withdrawn',
  'queue_entry_released',
  'accounting_budget_updated',
  'queue_chain_suspended',
  'permission_denied',
  'permission_requested',
  'permission_decided',
  'project_created',
  'project_opened',
  'project_relocated',
  'project_settings_updated',
]

const MAX_BUFFERED = 200

// The backend pings every 15s (events.py's EventSourceResponse(ping=15)).
// More than 2x that plus margin before declaring a silently-dead connection.
let IDLE_TIMEOUT_MS = 40_000
const IDLE_CHECK_INTERVAL_MS = 5_000

/** Test-only: override the idle-dead-connection threshold so reconnect
 * tests don't need to wait out the real 40s default. */
export function __setIdleTimeoutForTest(ms: number): void {
  IDLE_TIMEOUT_MS = ms
}

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

let connectionState: SSEConnectionState = 'closed'
const stateListeners = new Set<(state: SSEConnectionState) => void>()

function setConnectionState(next: SSEConnectionState): void {
  if (next === connectionState) return
  connectionState = next
  stateListeners.forEach((cb) => {
    try {
      cb(next)
    } catch {
      // Swallow listener errors so one bad subscriber doesn't break the chain.
    }
  })
}

export function getSSEConnectionState(): SSEConnectionState {
  return connectionState
}

/** Subscribe to connection-state transitions (closed/connecting/open/
 * reconnecting). Returns an unsubscribe function. */
export function onSseStateChange(cb: (state: SSEConnectionState) => void): () => void {
  stateListeners.add(cb)
  return () => {
    stateListeners.delete(cb)
  }
}

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
  setConnectionState('closed')
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
  IDLE_TIMEOUT_MS = 40_000
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
  setConnectionState(hasEverConnected ? 'reconnecting' : 'connecting')

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
  let lastActivityAt = Date.now()

  const cancel = () => {
    cancelled = true
    if (idleTimer) clearInterval(idleTimer)
    reader.cancel().catch(() => {})
  }
  activeStream = { cancel }
  setConnectionState('open')

  // The backend sends a `: ping` comment every 15s (EventSourceResponse's
  // `ping=15`) precisely so a client can tell a truly dead connection from
  // a quiet one. If the underlying TCP peer dies without closing the socket
  // (e.g. the process is killed rather than shut down), reader.read() never
  // rejects and never resolves `done: true` — it just hangs forever, since
  // no FIN/RST reaches the client. Comment frames don't parse into a named
  // event (feedSSEChunk only emits frames with a `data:` line), so activity
  // has to be tracked at the raw-chunk level, not the event level. Cancel
  // the reader (without setting `cancelled`) once nothing has arrived —
  // not even a ping — for more than twice the ping interval; that failure
  // still flows through the catch/finally below and schedules a reconnect.
  const idleTimer = setInterval(() => {
    if (Date.now() - lastActivityAt > IDLE_TIMEOUT_MS) {
      reader.cancel().catch(() => {})
    }
  }, IDLE_CHECK_INTERVAL_MS)

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
        lastActivityAt = Date.now()
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
      // stream errored (includes the idle watchdog above cancelling the reader)
    } finally {
      clearInterval(idleTimer)
      if (!cancelled) {
        // Stream ended unexpectedly → schedule reconnect
        if (activeStream && activeStream.cancel === cancel) {
          activeStream = null
        }
        setConnectionState('reconnecting')
        scheduleReconnect(hubUrl, apiKey)
      }
    }
  })()
}

/** Live connection state for rendering a stream-health indicator. */
export function useSSEConnectionState(): SSEConnectionState {
  const [state, setState] = useState<SSEConnectionState>(getSSEConnectionState())
  useEffect(() => {
    setState(getSSEConnectionState())
    return onSseStateChange(setState)
  }, [])
  return state
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

  // On every reconnect (not the initial connect), invalidate everything so
  // views that only update via SSE catch up on whatever happened while the
  // stream was down — rather than staying stale until their next poll, or
  // forever for entities with no poll left after 2.3 removes the backstop.
  useEffect(() => {
    return onSseReconnect(() => {
      queryClient.invalidateQueries()
    })
  }, [queryClient])

  useEffect(() => {
    const invalidateHandler: SSEListener = (event) => {
      // The one stream is instance-wide — every project's events, each
      // stamped server-side with its own project_id (hub/hub/sse.py). Every
      // invalidation below targets THAT event's project, not necessarily the
      // one currently selected, so an inactive project's cache is already
      // fresh by the time the operator switches to it (design.md: "the rail
      // summary updates without switching to it").
      const pid = (event.data as { project_id?: string } | null)?.project_id
      switch (event.type) {
        case 'message_created':
        case 'message_read':
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'messages'] })
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'status'] })
          break
        case 'task_created':
        case 'task_updated':
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'tasks'] })
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'status'] })
          // Neither payload carries `loop_id` (`tasks.py` broadcasts only `id`/`title`/`status`),
          // and `Task.loop_id` is write-once (design D14) so there is no reassignment to track —
          // but a claimed/completed/queued task changes its loop's queue counts and current item,
          // so the loops list/detail refetch here rather than staying stale until something else
          // invalidates them.
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'loops'] })
          break
        case 'queue_entry_abandoned': {
          // The Hub stopped trying to deliver something. The queue card is where that shows, and
          // the prefix covers both that agent's entries and its status without naming either.
          const agent = (event.data as { agent?: string } | null)?.agent
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'queue', agent] })
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'status'] })
          break
        }
        case 'task_integration_retried':
          // The note reads a per-task key, and a retry appends a row to exactly one of them.
          queryClient.invalidateQueries({
            queryKey: ['project', pid, 'task', (event.data as { task_id?: string } | null)?.task_id, 'integrations'],
          })
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'tasks'] })
          break
        case 'question_asked':
        case 'question_answered':
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'questions'] })
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'status'] })
          break
        case 'agent_created':
        case 'agent_heartbeat':
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'tasks'] })
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'agents'] })
          queryClient.invalidateQueries({ queryKey: ['projects'] })
          break
        case 'run_started':
        case 'run_completed':
        case 'run_failed':
        case 'run_stopped':
        case 'run_interrupted':
          if (event.type !== 'run_started') {
            // A terminal run status is the moment a loop firing's own JobRun leaves
            // "in_progress" (design D13, task A4.3: `finalize_job_run_for_conversation` runs
            // before this broadcasts) — the loops list/detail's `firing_active` would otherwise
            // stay stuck true until something else happened to refetch it.
            queryClient.invalidateQueries({ queryKey: ['project', pid, 'loops'] })
          }
          // Run status is folded into the agents list response (agents.py's
          // agents_with_active_run), and a Hub-triggered run never posts a
          // heartbeat — without this, the running/idle badge would never
          // update for a direct-spawn run.
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'agents'] })
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'accounting'] })
          queryClient.invalidateQueries({ queryKey: ['projects'] })
          break
        case 'accounting_budget_updated':
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'accounting'] })
          break
        case 'queue_entry_queued':
        case 'queue_entry_delivered':
        case 'queue_entry_withdrawn':
        case 'queue_entry_released':
        case 'queue_chain_suspended': {
          const d = event.data as { agent?: string }
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'agents'] })
          if (d?.agent) {
            queryClient.invalidateQueries({ queryKey: ['project', pid, 'queue', d.agent] })
          }
          break
        }
        case 'context_warning':
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'agents'] })
          break
        case 'agent_session_changed': {
          const d = event.data as { agent?: string }
          if (d?.agent) {
            queryClient.invalidateQueries({ queryKey: ['project', pid, 'agent', d.agent, 'sessions'] })
          }
          break
        }
        case 'job_created':
        case 'job_updated':
        case 'job_deleted':
        case 'job_fired': {
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'jobs'] })
          const d = event.data as { id?: string }
          if (d?.id) {
            queryClient.invalidateQueries({ queryKey: ['project', pid, 'jobs', d.id] })
          }
          if (event.type === 'job_fired') {
            // A firing becoming "in_progress" (design D13, task A4.3) is committed before this
            // broadcasts (`scheduler.py`), so the loops list/detail's `firing_active` is already
            // true by the time a listener refetches.
            queryClient.invalidateQueries({ queryKey: ['project', pid, 'loops'] })
          }
          break
        }
        // Task B6.4 (`2026-08-18-a-loop-writes-its-own-queue`): `loop_queue_exhausted` (design D6)
        // is a loop event's first consumer here — none of the six were reaching a listener before
        // this task, because they were absent from `SSE_EVENT_TYPES` above and silently dropped.
        // `loop_stopped`/`loop_queue_exhausted` key their loop id as `loop_id`; the other four
        // (staged/applied edits, control changes, archival) key it as `id` — both are read below
        // rather than assumed to be one or the other.
        case 'loop_stopped':
        case 'loop_queue_exhausted':
        case 'loop_archived':
        case 'loop_control_changed':
        case 'loop_edit_staged':
        case 'loop_edit_applied': {
          queryClient.invalidateQueries({ queryKey: ['project', pid, 'loops'] })
          const d = event.data as { loop_id?: string; id?: string }
          const loopId = d?.loop_id ?? d?.id
          if (loopId) {
            queryClient.invalidateQueries({ queryKey: ['project', pid, 'loops', loopId] })
          }
          break
        }
        case 'project_created':
        case 'project_opened':
        case 'project_relocated':
        case 'project_settings_updated':
          queryClient.invalidateQueries({ queryKey: ['projects'] })
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
