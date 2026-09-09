import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { AgentRunFacts, ContextUsage } from './agents'
import { ApiError, deleteJson, getJson, patchJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { useSSE } from '@/hooks/useSSE'
import { NEW_SESSION_ID } from '@/lib/constants'

export type TimelineEntryKind = 'operator_input' | 'agent_output' | 'inbound_peer' | 'outbound_peer'

export type AgentOutputKind =
  | 'text'
  | 'thinking'
  | 'tool_use'
  | 'tool_result'
  | 'status'
  | 'diagnostic'
  | 'error'

/** One entry in the merged conversation timeline (task 8.3) — matches
 * hub/hub/api/v1/agent_chat.py's `TimelineEntry`. */
export interface TimelineEntry {
  id: string
  kind: TimelineEntryKind
  content: string
  timestamp: string
  /** `abandoned` means the Hub stopped trying to deliver it — the input is gone, and this is
   *  the only thing that says so. See `agent_chat.py`'s `TimelineEntry`. */
  delivery_state: 'delivered' | 'queued' | 'abandoned'
  /** The *other* agent's name — set for inbound_peer/outbound_peer only. */
  participant?: string | null
  /** outbound_peer only. Nullable — required by `send_message` going forward, but the column
   *  predates that requirement, so an older row has none. */
  subject?: string | null
  /** agent_output only. */
  output_kind?: AgentOutputKind | null
  payload?: Record<string, unknown> | null
  run_id?: string | null
  sequence?: number | null
  /** operator_input/inbound_peer only. */
  hop_depth?: number | null
  hop_budget_exceeded?: boolean | null
  /** Why the Hub gave up. Set only with `delivery_state === 'abandoned'`. */
  abandoned_reason?: string | null
}

export interface ChatHistoryResponse {
  conversation_id: string | null
  session_id: string | null
  agent: string
  entries: TimelineEntry[]
  /** How every run these `entries` name ended, keyed by `run_id` — the same `RunFacts` shape the
   *  timeline route serves, carried here so the facts arrive on the response that carries the
   *  turns they describe.
   *
   *  The timeline route's map is scoped to its own fifty-event window; this one is scoped to
   *  these entries, so a turn on screen always has its run's row (F274). A lookup miss means
   *  "no run row for this id", never "this run has not ended".
   *
   *  Required rather than optional, matching `AgentTimelineResponse.runs`: the server always
   *  serves the key (`default_factory=dict`), and the only absence a reader has to handle is the
   *  query having no data yet. */
  runs: Record<string, AgentRunFacts>
}

/** Whether a conversation needs the operator, without opening it. `waiting` outranks `running`:
 *  a run blocked on a question is still running, but stopping for the operator is the part they
 *  have to see. */
export type ConversationAttention = 'running' | 'waiting' | 'idle'

/** Where a conversation came from, recorded at creation and immutable. `handoff` and `spec` are
 *  accepted by the Hub with no producer yet. */
export type ConversationOrigin = 'operator' | 'peer' | 'handoff' | 'spec' | 'job'

/** Which loop's firing created this conversation. `label` is the loop's job name, the same
 *  pairing the loops index uses, so one loop is named one way wherever it appears. */
export interface ConversationLoop {
  id: string
  label: string
}

export interface AgentConversation {
  id: string
  agent: string
  provider_session_id: string | null
  lifecycle: 'open' | 'archived'
  /** Null until the first message names it. Never render `id` as the label — see
   *  `conversationLabel` below. */
  title: string | null
  title_set_by_operator: boolean
  origin: ConversationOrigin
  /**
   * Set only when a loop firing created this thread; null otherwise.
   *
   * `origin === 'job'` cannot stand in for it — a plain scheduled job carries the same origin and
   * has no loop. Optional so a Hub predating the field degrades to "no marker" rather than to a
   * crash.
   */
  loop?: ConversationLoop | null
  /**
   * How full *this* conversation's context is — not its agent's.
   *
   * `AgentSummary.context_usage` is one reading per agent, the newest across all of that agent's
   * threads. The composer is conversation-scoped, so reading the agent's value showed whichever
   * conversation last reported, in every conversation: measured on the trial Hub 2026-08-19,
   * agent `verifier` had three conversations at 18.56%, 16.6% and 15.9%, and all three composers
   * showed 15.9%.
   *
   * Null when this conversation has produced no reading yet — deliberately without falling back
   * to the agent's, since that fallback is the bug.
   */
  context_usage?: ContextUsage | null
  attention: ConversationAttention
  /** Where this conversation stands with its checkpoint threshold. `due` warns; `dismissed`
   *  does not warn again while there is still room to keep working, because re-asking an
   *  operator who said "not yet" is the same as not letting them say it; `final` is the one
   *  exception — near the window a dismissal has run out of room, and that warning carries no
   *  dismiss action because dismissal was already spent to reach it. */
  checkpoint_warning?: 'due' | 'dismissed' | 'final' | null
  created_at: string
  updated_at: string
  archived_at?: string | null
  /** Control id -> value (e.g. {"model": "claude-opus-5", "effort": "high"}). Null/empty
   * means the conversation inherits its agent's runner and the catalog's defaults. */
  runtime_overrides?: Record<string, string> | null
  /**
   * The task this thread is about, if it is about one.
   *
   * Every turn here binds to it and is checked at its end — which is the whole reason the operator
   * has to be able to see it. A binding that silently governs whether work is checked, and cannot
   * be read anywhere, is the mechanism enforcing invisibly.
   */
  task_id?: string | null
}

export interface ProjectConversations {
  conversations: AgentConversation[]
  /** Archived rows are excluded from `conversations`, so their count has to be carried
   *  separately — a "Show archived (N)" control cannot state N from a list that omitted them. */
  archived_count: number
  /** The same count per agent, for the agent row's own "Show archived (N)". Agents with none
   *  are absent, not zero. Optional so a Hub that predates it degrades to "nothing archived"
   *  rather than to a crash. */
  archived_by_agent?: Record<string, number>
}

/** What navigation shows for a conversation. A conversation with no message yet is labelled as
 *  new; its identifier is never a label, on any surface. */
export function conversationLabel(conversation: AgentConversation): string {
  return conversation.title?.trim() || 'New conversation'
}

export function useAgentConversations(agent: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    const data = (event.data ?? {}) as Record<string, unknown>
    if (data.project_id !== projectId) return
    if (agent && data.agent === agent && data.conversation_id) {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agent', agent, 'conversations'] })
    }
  })

  return useQuery<AgentConversation[]>({
    queryKey: ['project', projectId, 'agent', agent, 'conversations'],
    queryFn: () =>
      getJson<AgentConversation[]>(`/api/v1/projects/${projectId}/agent/${agent}/conversations`),
    enabled: isConfigured && !!projectId && !!agent,
  })
}

/** Every conversation in one project, across its agents — what the rail draws.
 *
 * One request rather than one per expanded agent: the tree groups these by agent and the recency
 * view lists them as they come, so switching views costs nothing and expanding an agent shows its
 * conversations immediately instead of starting a fetch.
 *
 * `projectId` is explicit rather than taken from the config store, because the rail renders every
 * registered project, not only the selected one. */
export function useProjectConversations(projectId: string | null, lifecycle: 'open' | 'archived' = 'open') {
  const { isConfigured } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    const data = (event.data ?? {}) as Record<string, unknown>
    if (data.project_id !== projectId) return
    if (event.type === 'conversation_updated' || data.conversation_id) {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'conversations'] })
    }
  })

  return useQuery<ProjectConversations>({
    queryKey: ['project', projectId, 'conversations', lifecycle],
    queryFn: () =>
      getJson<ProjectConversations>(
        `/api/v1/projects/${projectId}/conversations?lifecycle=${lifecycle}`,
      ),
    enabled: isConfigured && !!projectId,
  })
}

/** What the Hub said when it refused, rather than the raw response body.
 *
 * Archiving is refused with a stated reason (a live run, an undelivered queue entry) and that
 * reason is the entire point of the refusal — surfacing "409" instead would leave the operator
 * with a row menu that silently does nothing. */
export function conversationErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    try {
      const detail = (JSON.parse(error.message) as { detail?: unknown }).detail
      if (typeof detail === 'string' && detail.trim()) return detail
    } catch {
      // Not a JSON body — fall through to the caller's wording.
    }
  }
  return fallback
}

interface ConversationRef {
  projectId: string
  agent: string
  conversationId: string
}

function conversationPath({ projectId, agent, conversationId }: ConversationRef): string {
  return `/api/v1/projects/${projectId}/agent/${agent}/conversations/${conversationId}`
}

/** Invalidates by the project prefix, so both the open and the archived listing refetch — an
 *  archive moves a row from one to the other, and refreshing only the one the operator was
 *  looking at leaves the other stale. */
function useConversationMutation<Variables extends ConversationRef>(
  run: (variables: Variables) => Promise<AgentConversation>,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: run,
    onSuccess: (_data, { projectId, agent }) => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'conversations'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agent', agent, 'conversations'] })
    },
  })
}

export function useRenameConversation() {
  return useConversationMutation<ConversationRef & { title: string }>((variables) =>
    patchJson<AgentConversation>(conversationPath(variables), { title: variables.title }),
  )
}

/**
 * Stop attributing this thread's turns to the task it is bound to.
 *
 * The operator's half of the release rule. The other half is automatic — approving or rejecting the
 * task releases every thread bound to it. Nothing infers a release from what the conversation seems
 * to be about, because a wrong guess silently stops checking runs.
 *
 * A plain function rather than a mutation hook, matching `dismissCheckpointWarning` and
 * `withdrawQueueEntry`: the panel that calls it is rendered in tests without a QueryClientProvider,
 * so a hook here would make every one of those tests fail on a provider they do not need.
 */
export function releaseConversationTask(
  projectId: string,
  agent: string,
  conversationId: string,
): Promise<AgentConversation> {
  return deleteJson<AgentConversation>(
    `/api/v1/projects/${projectId}/agent/${agent}/conversations/${conversationId}/task`,
  )
}

export function useArchiveConversation() {
  return useConversationMutation<ConversationRef>((variables) =>
    postJson<AgentConversation>(`${conversationPath(variables)}/archive`),
  )
}

export function useUnarchiveConversation() {
  return useConversationMutation<ConversationRef>((variables) =>
    postJson<AgentConversation>(`${conversationPath(variables)}/unarchive`),
  )
}

const QUEUE_EVENT_TYPES = new Set([
  'queue_entry_queued',
  'queue_entry_delivered',
  'queue_entry_withdrawn',
  'queue_entry_released',
  'queue_chain_suspended',
])

/** A run reaching a terminal status. These are here because the chat response carries `runs`
 *  now, and that map is only as fresh as the query it rides on.
 *
 *  The run row — not the streamed status line — is what `AgentTimeline` treats as authoritative
 *  for a turn's outcome, and the row is written by the code that broadcasts these four. An
 *  operator **stop** is the case with no cover at all: `stop_agent_run`
 *  (`agent_trigger.py:1571-1627`) force-terminates the process and writes no `AgentOutput` row,
 *  so nothing this predicate already matched will fire, and `run_stopped` is the only event a
 *  chat listener hears about that run ending. On the paths that do write a terminal status line,
 *  the `agent_output` event and the run row's commit are separate broadcasts, so a refetch
 *  triggered by the output alone can read the row while it still says `started`; these are what
 *  correct that.
 *
 *  Not `run_started` — a deliberate divergence from `eventBelongsToTimeline`, which takes it. A
 *  starting run adds nothing to a chat response that is not already carried by the
 *  `queue_entry_delivered` above it (the delivered entry names the new run in the same commit
 *  that creates it — see `AgentTimeline`'s `anotherRunIsUnderway`), and the conversation-scoped
 *  response is unbounded, so an extra refetch of it is a real cost.
 *
 *  `run_interrupted` is here for completeness of "the row changed", not because it rescues the
 *  Hub-restart case: `reconcile_interrupted_runs()` is awaited inside the lifespan
 *  (`main.py:402`, before `yield`), so it broadcasts before uvicorn serves anything and no
 *  reconnecting client can be subscribed yet. That case is served by `useSSE`'s reconnect
 *  handler, which invalidates every query (`useSSE.ts:404-412`). */
const RUN_TERMINAL_EVENT_TYPES = new Set([
  'run_completed',
  'run_failed',
  'run_stopped',
  'run_interrupted',
])

/** True if an SSE event names `agent` as its target, across the various
 * payload shapes used by message_created (`to` or `recipient`), agent_output
 * (`agent`), the queue lifecycle events (`agent`) that move entries
 * between the undelivered and delivered states this timeline renders, and the
 * run-terminal events (`agent`) that settle the `runs` map those turns are labelled from. */
export function eventTargetsAgent(eventType: string, data: unknown, agent: string): boolean {
  if (
    eventType !== 'message_created' &&
    eventType !== 'agent_output' &&
    !QUEUE_EVENT_TYPES.has(eventType) &&
    !RUN_TERMINAL_EVENT_TYPES.has(eventType)
  ) {
    return false
  }
  const d = (data ?? {}) as Record<string, unknown>
  return d.to === agent || d.recipient === agent || d.agent === agent
}

export function useAgentChatHistory(agent: string | null, conversationId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    const d = (event.data ?? {}) as { project_id?: string }
    if (agent && d.project_id === projectId && eventTargetsAgent(event.type, event.data, agent)) {
      queryClient.invalidateQueries({
        queryKey: ['project', projectId, 'agent', agent, 'chat', conversationId],
      })
    }
  })

  return useQuery<ChatHistoryResponse>({
    queryKey: ['project', projectId, 'agent', agent, 'chat', conversationId],
    queryFn: () =>
      getJson<ChatHistoryResponse>(
        `/api/v1/projects/${projectId}/agent/${agent}/chat/${conversationId}`,
      ),
    enabled:
      isConfigured && !!projectId && !!agent && !!conversationId && conversationId !== NEW_SESSION_ID,
  })
}

export function useAgentRecentChat(agent: string | null, limit: number = 50) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    const d = (event.data ?? {}) as { project_id?: string }
    if (agent && d.project_id === projectId && eventTargetsAgent(event.type, event.data, agent)) {
      queryClient.invalidateQueries({
        queryKey: ['project', projectId, 'agent', agent, 'chat', 'recent', limit],
      })
    }
  })

  return useQuery<ChatHistoryResponse>({
    queryKey: ['project', projectId, 'agent', agent, 'chat', 'recent', limit],
    queryFn: () =>
      getJson<ChatHistoryResponse>(`/api/v1/projects/${projectId}/agent/${agent}/chat?limit=${limit}`),
    enabled: isConfigured && !!projectId && !!agent,
  })
}
