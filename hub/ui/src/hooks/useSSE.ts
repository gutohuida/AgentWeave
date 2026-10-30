import { useEffect, useRef, useState } from 'react'
import { useQueryClient, type Query, type QueryClient } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import type { AgentSummary, ContextUsage } from '@/api/agents'
import type { AgentConversation, ProjectConversations } from '@/api/agentChat'

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
  'build_stopped',
  // The operator's stop and resume (`_after_build_change`, spec.py); the scheduler's own stop sends `build_stopped`.
  'build_updated',
  'task_integration_retried',
  'queue_entry_abandoned',
  'question_asked',
  'question_answered',
  'stall_recorded',
  'stall_ended',
  // Main moved outside the Hub (`main_watch`), and the operator marking it seen.
  'main_moved',
  'main_notice_seen',
  // A built slice's next slice offered, taken or declined (`slice_drafting`).
  'next_slice_offered',
  'next_slice_answered',
  'checks_flaky',
  'agent_heartbeat',
  'agent_created',
  'agent_output',
  'agent_session_changed',
  'session_synced',
  'log_event',
  'context_warning',
  'spec_updated',
  'journey_updated',
  'job_created',
  'job_updated',
  'job_deleted',
  'job_fired',
  // A chapters version was committed (`hub/hub/chapters.py` save): the Thread page refreshes.
  'chapters_updated',
  'loop_stopped',
  'loop_queue_exhausted',
  'loop_archived',
  'loop_control_changed',
  'loop_edit_staged',
  'loop_edit_applied',
  'task_checks_finished',
  'task_landing_changed',
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
  'agent_archived',
  'agent_unarchived',
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
/** Bumped by every connect attempt and by cancelReconnect: an attempt whose fetch resolves after a
 *  newer attempt or a cancel closes its own stream instead of opening a second one (F1039). */
let connectGeneration = 0
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

/** Refetch every open task story (`['project', pid, 'tasks', id, 'story']`) of project *pid*. */
function invalidateTaskStories(queryClient: QueryClient, pid: string | undefined): void {
  invalidateCoalesced(queryClient, {
    predicate: (query) => {
      const key = query.queryKey
      return key[0] === 'project' && key[1] === pid && key[2] === 'tasks' && key[4] === 'story'
    },
  })
}

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

/** Subscribe to "the client may have missed events". The callback fires after
 * every reconnect (NOT the initial connect) and whenever the Hub reports a
 * `stream_gap`, i.e. that it dropped events this client's queue had no room
 * for. Returns an unsubscribe function. */
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
  connectGeneration += 1
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
  invalidators.forEach((i) => i.unsubReconnect())
  invalidators.clear()
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
  const generation = ++connectGeneration

  const url = `${hubUrl}/api/v1/events`
  let response: Response
  try {
    response = await fetch(url, {
      headers: { Authorization: `Bearer ${apiKey}` },
    })
  } catch {
    if (generation !== connectGeneration) return
    if (connectingUrl === hubUrl && connectingKey === apiKey) {
      connectingUrl = ''
      connectingKey = ''
    }
    scheduleReconnect(hubUrl, apiKey)
    return
  }
  // F1039: the subscriber unmounted (StrictMode's mount, unmount, mount) or a newer attempt began
  // while this fetch was in flight; that attempt owns the stream now.
  if (generation !== connectGeneration) {
    await response.body?.cancel().catch(() => {})
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
          if (evt.type === 'stream_gap') {
            // Stream metadata, not a project's event: the Hub dropped events for this
            // client. Tell listeners, then run every catch-up (F253).
            let gap: unknown = evt.data
            try {
              gap = JSON.parse(evt.data)
            } catch {
              // keep raw string
            }
            dispatchEvent('stream_gap', gap)
            fireReconnect()
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

/** Refresh the agent roster without its per-agent sub-resources (output seed, lines, timeline):
 *  those keys sit under the same prefix but are fed by their own events. */
function agentListFilter(pid: string | undefined) {
  return {
    queryKey: ['project', pid, 'agents'],
    predicate: (q: { queryKey: readonly unknown[] }) => q.queryKey.length <= 4,
  }
}

type ReadingHolder = { context_usage?: ContextUsage | null }

/** The reading to keep when *incoming* arrives for a row holding *current*: the newer one, except
 *  that one without a percentage does not displace a complete reading of the same provider session
 *  (the Hub's rule, `usable_context_reading`). */
function nextReading(current: ContextUsage | null | undefined, incoming: ContextUsage): ContextUsage | null | undefined {
  if (!current) return incoming
  if (typeof current.observed_at === 'number' && incoming.observed_at < current.observed_at) return current
  if (
    (incoming.percent === null || incoming.percent === undefined) &&
    current.percent !== null &&
    current.percent !== undefined &&
    current.session_id === incoming.session_id
  ) {
    return current
  }
  return incoming
}

/** Put a `context_warning` reading into the cached roster and conversation lists. Returns false
 *  when the payload names no agent, so the caller refetches instead. */
function applyContextReading(queryClient: QueryClient, pid: string | undefined, data: unknown): boolean {
  const reading = data as (ContextUsage & { agent?: string; conversation_id?: string | null }) | null
  if (!pid || !reading || typeof reading.agent !== 'string' || typeof reading.observed_at !== 'number') {
    return false
  }
  const { agent, conversation_id: conversationId, ...usage } = reading
  const incoming = usage as ContextUsage
  const patch = <T extends ReadingHolder>(row: T): T => {
    const next = nextReading(row.context_usage, incoming)
    return next === row.context_usage ? row : { ...row, context_usage: next }
  }
  queryClient.setQueriesData<AgentSummary[]>(agentListFilter(pid), (rows) =>
    Array.isArray(rows) ? rows.map((r) => (r.name === agent ? patch(r) : r)) : rows,
  )
  if (conversationId) {
    const patchConversation = <T extends { id: string } & ReadingHolder>(rows: T[]) =>
      rows.map((c) => (c.id === conversationId ? patch(c) : c))
    queryClient.setQueriesData<ProjectConversations>(
      { queryKey: ['project', pid, 'conversations'] },
      (current) => (current?.conversations ? { ...current, conversations: patchConversation(current.conversations) } : current),
    )
    queryClient.setQueriesData<AgentConversation[]>(
      { queryKey: ['project', pid, 'agent', agent, 'conversations'] },
      (rows) => (Array.isArray(rows) ? patchConversation(rows) : rows),
    )
  }
  return true
}

function invalidateSpecShownPhase(inv: (f?: InvalidateFilters) => void, pid: string | undefined): void {
  inv({ queryKey: ['project', pid, 'spec'] })
  inv({ queryKey: ['project', pid, 'specs'] })
  inv({ queryKey: ['project', pid, 'specDocuments'] })
}

/** Apply one stream event to *queryClient*'s cache. Called once per event per tab (see
 *  `acquireInvalidator`), however many components subscribe. */
function applyInvalidation(queryClient: QueryClient, event: SSEEvent): void {
  const inv = (filters?: InvalidateFilters) => invalidateOncePerEvent(queryClient, event, filters)
  const pid = (event.data as { project_id?: string } | null)?.project_id
  switch (event.type) {
        case 'message_created':
        case 'message_read':
          inv({ queryKey: ['project', pid, 'messages'] })
          inv({ queryKey: ['project', pid, 'status'] })
          break
        case 'task_created':
        case 'spec_updated':
          // Evidence recorded or decided, and a recording run's end, arrive here: each is part of a
          // task's story. The spec page's own listener (`useSpecEvents`) covers the spec queries.
          invalidateTaskStories(queryClient, pid)
          break
        case 'task_updated': {
          // A delete broadcasts `{id, deleted: true}` as it commits, which can reach the page before
          // the 204 does while the drawer still holds the task's story: refetching that key only
          // collects 404s (F824). Everything else under `tasks` still refreshes.
          const data = event.data as { id?: string; deleted?: boolean } | null
          const goneId = data?.deleted === true ? data.id : undefined
          inv({
            queryKey: ['project', pid, 'tasks'],
            ...(goneId ? { predicate: (q) => q.queryKey[3] !== goneId } : {}),
          })
          // An approval merges into main and moves the ledger's lanes (slice project-ledger).
          refreshWorkSoon(queryClient, pid)
          inv({ queryKey: ['project', pid, 'status'] })
          // Neither payload carries `loop_id` (`tasks.py` broadcasts only `id`/`title`/`status`),
          // and `Task.loop_id` is write-once (design D14) so there is no reassignment to track —
          // but a claimed/completed/queued task changes its loop's queue counts and current item,
          // so the loops list/detail refetch here rather than staying stale until something else
          // invalidates them.
          inv({ queryKey: ['project', pid, 'loops'] })
          // Approving or rejecting a task releases its checkout (F250).
          inv({ queryKey: ['project', pid, 'worktrees'] })
          inv({ queryKey: ['project', pid, 'worktree-conflicts'] })
          // A document reads Building or Done from its tasks (`display_phase`), so a task moving
          // changes the phase every spec view shows; `spec_updated` is not sent for it (F1089).
          invalidateSpecShownPhase(inv, pid)
          break
        }
        case 'build_updated':
        case 'build_stopped':
          // Stopping a build changes the shown phase with no task event and no `spec_updated`.
          invalidateSpecShownPhase(inv, pid)
          break
        case 'queue_entry_abandoned': {
          // The Hub stopped trying to deliver something. The queue card is where that shows, and
          // the prefix covers both that agent's entries and its status without naming either.
          const agent = (event.data as { agent?: string } | null)?.agent
          inv({ queryKey: ['project', pid, 'queue', agent] })
          inv({ queryKey: ['project', pid, 'status'] })
          break
        }
        case 'task_integration_retried':
          refreshWorkSoon(queryClient, pid)
          // The note reads a per-task key, and a retry appends a row to exactly one of them.
          inv({
            queryKey: ['project', pid, 'task', (event.data as { task_id?: string } | null)?.task_id, 'integrations'],
          })
          inv({ queryKey: ['project', pid, 'tasks'] })
          break
        case 'stall_recorded':
        case 'stall_ended':
          inv({ queryKey: ['project', pid, 'stalls'] })
          break
        case 'main_moved':
        case 'main_notice_seen':
          inv({ queryKey: ['project', pid, 'mainNotices'] })
          break
        case 'next_slice_offered':
        case 'next_slice_answered':
          inv({ queryKey: ['project', pid, 'nextSliceOffers'] })
          break
        case 'checks_flaky':
          inv({ queryKey: ['project', pid, 'checks', 'flaky'] })
          break
        case 'question_asked':
        case 'question_answered':
          inv({ queryKey: ['project', pid, 'questions'] })
          inv({ queryKey: ['project', pid, 'status'] })
          break
        case 'agent_created':
          inv({ queryKey: ['project', pid, 'tasks'] })
          inv(agentListFilter(pid))
          inv({ queryKey: ['projects'] })
          // A new agent can turn a stale delivery fresh (design D5,
          // `a-document-says-how-it-will-be-built-and-approval-starts-it`): the strip is computed
          // from the roster, not from the file, so `spec_updated` never fires for it.
          inv({ queryKey: ['project', pid, 'spec'] })
          break
        case 'agent_heartbeat':
          inv({ queryKey: ['project', pid, 'tasks'] })
          inv(agentListFilter(pid))
          inv({ queryKey: ['projects'] })
          break
        case 'task_checks_finished':
        case 'task_landing_changed': {
          // The drawer's Land wait clears on this, without a reload, and the board's cards follow;
          // a landing's state beside Land follows its batch the same way.
          const data = event.data as { task_id?: string } | null
          inv({
            queryKey: data?.task_id
              ? ['project', pid, 'task', data.task_id, 'checks']
              : ['project', pid, 'task'],
          })
          inv({ queryKey: ['project', pid, 'tasks'] })
          break
        }
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
            inv({ queryKey: ['project', pid, 'loops'] })
            // A run's end expires its unanswered permission requests and flips a question's
            // `asker_waiting` without any permission_/question_ event, and those two lists are no
            // longer polled: one refetch per run end (never per line) picks both up.
            inv({ queryKey: ['project', pid, 'permission-requests'] })
            inv({ queryKey: ['project', pid, 'questions'] })
          }
          // Run status is folded into the agents list response (agents.py's
          // agents_with_active_run), and a Hub-triggered run never posts a
          // heartbeat — without this, the running/idle badge would never
          // update for a direct-spawn run.
          inv(agentListFilter(pid))
          inv({ queryKey: ['project', pid, 'accounting'] })
          // A run's spend and divergence are ledger lanes.
          refreshWorkSoon(queryClient, pid)
          inv({ queryKey: ['projects'] })
          // A run belongs to a task's story (its cost, its duration); an open drawer refetches it.
          invalidateTaskStories(queryClient, pid)
          // F250: a turn's checkout is provisioned before `run_started` is sent, and its snapshot
          // commit lands before the terminal event, which is what moves a conflict. Only a mounted
          // Worktrees panel refetches, so the merge-tree check costs nothing while it is closed.
          inv({ queryKey: ['project', pid, 'worktrees'] })
          inv({ queryKey: ['project', pid, 'worktree-conflicts'] })
          break
        case 'accounting_budget_updated':
          inv({ queryKey: ['project', pid, 'accounting'] })
          break
        case 'queue_entry_queued':
        case 'queue_entry_delivered':
        case 'queue_entry_withdrawn':
        case 'queue_entry_released':
        case 'queue_chain_suspended': {
          const d = event.data as { agent?: string }
          inv(agentListFilter(pid))
          if (d?.agent) {
            inv({ queryKey: ['project', pid, 'queue', d.agent] })
          }
          break
        }
        case 'context_warning':
          // The payload is the reading itself: put it where the roster and the conversation lists
          // show it. Only a payload that cannot be placed falls back to a refetch.
          if (!applyContextReading(queryClient, pid, event.data)) inv(agentListFilter(pid))
          break
        case 'agent_session_changed': {
          const d = event.data as { agent?: string }
          if (d?.agent) {
            inv({ queryKey: ['project', pid, 'agent', d.agent, 'sessions'] })
          }
          break
        }
        case 'job_created':
        case 'job_updated':
        case 'job_deleted':
        case 'job_fired': {
          inv({ queryKey: ['project', pid, 'jobs'] })
          const d = event.data as { id?: string }
          if (d?.id) {
            inv({ queryKey: ['project', pid, 'jobs', d.id] })
          }
          if (event.type !== 'job_fired') {
            // An edit or a new flow from another window: the loops carry the job's settings.
            inv({ queryKey: ['project', pid, 'loops'] })
          }
          if (event.type === 'job_fired') {
            // A firing becoming "in_progress" (design D13, task A4.3) is committed before this
            // broadcasts (`scheduler.py`), so the loops list/detail's `firing_active` is already
            // true by the time a listener refetches.
            inv({ queryKey: ['project', pid, 'loops'] })
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
          inv({ queryKey: ['project', pid, 'loops'] })
          const d = event.data as { loop_id?: string; id?: string }
          const loopId = d?.loop_id ?? d?.id
          if (loopId) {
            inv({ queryKey: ['project', pid, 'loops', loopId] })
          }
          if (event.type === 'loop_edit_applied') {
            // Applying a staged agent writes `job.agent`; a busy-refused or skipped tick
            // broadcasts no `job_fired`, so nothing else would refresh the jobs.
            inv({ queryKey: ['project', pid, 'jobs'] })
          }
          break
        }
        case 'project_created':
        case 'project_opened':
        case 'project_relocated':
          inv({ queryKey: ['projects'] })
          break
        case 'permission_requested':
        case 'permission_decided':
          // Here, not only in `usePendingPermissionRequests`: that hook is mounted by the run
          // panel alone, and the Questions page's decision list (F231) is read with it unmounted.
          inv({ queryKey: ['project', pid, 'permission-requests'] })
          break
        case 'session_synced':
          // A sync that deletes an agent drops it from the rail, which reads the projects summary;
          // `useAgents` refreshes only the roster. The deleted agent's conversations are archived
          // in the same commit (F849), so the conversation lists follow too.
          inv({ queryKey: ['projects'] })
          inv({ queryKey: ['project', pid, 'conversations'] })
          inv(agentListFilter(pid))
          break
        case 'agent_archived':
        case 'agent_unarchived':
          // The rail reads its agents from `['projects']` (F193: an archived agent's conversations
          // are grouped and marked there), and the roster from the agents key.
          inv({ queryKey: ['projects'] })
          inv(agentListFilter(pid))
          // The stale-delivery flag (design D5) follows the roster without a reload: archiving or
          // unarchiving broadcasts this, not `spec_updated`, so the `spec/<path>` query would
          // otherwise stay stale until something else invalidated it.
          inv({ queryKey: ['project', pid, 'spec'] })
          break
        case 'journey_updated':
          // The project's spec steps (`spec/journey.json`) were saved: the project page's list and
          // every document's journey (the phase bar reads it from the documents view) follow.
          // `useSpecEvents` is mounted only on the spec and conversation pages, so this cannot
          // live there: the page that edits the steps is neither.
          inv({ queryKey: ['project', pid, 'specJourney'] })
          inv({ queryKey: ['project', pid, 'specDocuments'] })
          break
        case 'project_settings_updated':
          // `PUT /settings` also writes `token_budget`, the field the accounting routes read, and
          // tells listeners only this event (F237). Without the second key every budget display —
          // the status bar's exhaustion notice among them — kept the old allowance.
          inv({ queryKey: ['projects'] })
          inv({ queryKey: ['project', pid, 'accounting'] })
          // The stored settings, which the Overview's Collaboration block reads: a change made from
          // any other surface would otherwise leave it showing the old value until a reload.
          inv({ queryKey: ['project', pid, 'settings'] })
          break
      }
  // An event naming a conversation moves the conversation lists (the rail's, and that agent's).
  // A streamed line or reading moves nothing a conversation list shows beyond what is applied in
  // place, so it does not re-read the lists once per line.
  const named = (event.data ?? {}) as { conversation_id?: string; agent?: string }
  if (named.conversation_id && pid && event.type !== 'agent_output' && event.type !== 'context_warning') {
    inv({ queryKey: ['project', pid, 'conversations'] })
    if (named.agent) inv({ queryKey: ['project', pid, 'agent', named.agent, 'conversations'] })
  }
}

type InvalidateFilters = Parameters<QueryClient['invalidateQueries']>[0]

interface Coalescer {
  /** Queries a refresh was asked for while their fetch was in flight: one follow-up each. */
  pending: Set<Query>
}
const coalescers = new WeakMap<QueryClient, Coalescer>()

function coalescerFor(queryClient: QueryClient): Coalescer {
  let c = coalescers.get(queryClient)
  if (c) return c
  const created: Coalescer = { pending: new Set() }
  coalescers.set(queryClient, c = created)
  queryClient.getQueryCache().subscribe((e) => {
    if (e.type !== 'updated' || !created.pending.has(e.query)) return
    if (e.query.state.fetchStatus === 'fetching') return
    created.pending.delete(e.query)
    queryClient.invalidateQueries({ queryKey: e.query.queryKey, exact: true })
  })
  return c
}

/** `invalidateQueries`, except that a query whose request is already in flight is not cancelled
 *  and resent: it gets one follow-up refetch after the first answers, however many asks arrive. */
function invalidateCoalesced(queryClient: QueryClient, filters?: InvalidateFilters): void {
  const inFlight = queryClient
    .getQueryCache()
    .findAll(filters ?? {})
    .filter((q) => q.state.fetchStatus === 'fetching')
  if (inFlight.length === 0) {
    if (filters) queryClient.invalidateQueries(filters)
    else queryClient.invalidateQueries()
    return
  }
  const { pending } = coalescerFor(queryClient)
  inFlight.forEach((q) => pending.add(q))
  const own = filters?.predicate
  queryClient.invalidateQueries({
    ...filters,
    predicate: (q) => !pending.has(q) && (own ? own(q) : true),
  })
}

/** How long the project's work tally waits before it is read again. */
export const WORK_REFRESH_MS = 3000
const workTimers = new Map<string, ReturnType<typeof setTimeout>>()

/** The ledger and the work tally (`/stats`) are each a read over the project's whole history, and
 *  every run and task event moves them: refetch them once per few seconds, not once per event. */
export function refreshWorkSoon(queryClient: QueryClient, projectId: string | undefined): void {
  if (!projectId || workTimers.has(projectId)) return
  workTimers.set(
    projectId,
    setTimeout(() => {
      workTimers.delete(projectId)
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'ledger'] })
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'stats'] })
    }, WORK_REFRESH_MS),
  )
}

const handledKeys = new WeakMap<SSEEvent, Set<string>>()

/** `invalidateCoalesced`, at most once per event per query key: hooks that react to an event
 *  themselves (one instance per mounted component) share this, so N instances cost one refresh. */
export function invalidateOncePerEvent(
  queryClient: QueryClient,
  event: SSEEvent,
  filters?: InvalidateFilters,
): void {
  if (filters && !filters.predicate) {
    let seen = handledKeys.get(event)
    if (!seen) handledKeys.set(event, (seen = new Set()))
    const id = JSON.stringify([filters.queryKey ?? null, filters.exact ?? false])
    if (seen.has(id)) return
    seen.add(id)
  }
  invalidateCoalesced(queryClient, filters)
}

interface Invalidator {
  count: number
  listener: SSEListener
  unsubReconnect: () => void
}
const invalidators = new Map<QueryClient, Invalidator>()

/** Install the tab's one event-to-cache handler for *queryClient* (reference-counted), plus the
 *  one full refresh on reconnect. Every `useSSE()` call shares it, so N subscribers cost one
 *  refresh per event, not N. Returns the release function. */
function acquireInvalidator(queryClient: QueryClient): () => void {
  let inv = invalidators.get(queryClient)
  if (!inv) {
    const listener: SSEListener = (event) => applyInvalidation(queryClient, event)
    listeners.add(listener)
    const unsubReconnect = onSseReconnect(() => invalidateCoalesced(queryClient))
    inv = { count: 0, listener, unsubReconnect }
    invalidators.set(queryClient, inv)
  }
  inv.count += 1
  const owned = inv
  return () => {
    owned.count -= 1
    if (owned.count <= 0 && invalidators.get(queryClient) === owned) {
      listeners.delete(owned.listener)
      owned.unsubReconnect()
      invalidators.delete(queryClient)
    }
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
    if (!isConfigured) return
    return acquireInvalidator(queryClient)
  }, [queryClient, isConfigured])

  useEffect(() => {
    const handler: SSEListener = (event) => onEventRef.current?.(event)
    listenerRef.current = handler
    listeners.add(handler)
    return () => {
      listeners.delete(handler)
      listenerRef.current = null
    }
  }, [queryClient]) // onEvent intentionally omitted — use onEventRef instead
}
