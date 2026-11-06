import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useSSE } from '@/hooks/useSSE'
import { useConfigStore } from '@/store/configStore'

export interface Checkpoint {
  id: string
  conversation_id: string
  agent: string
  trigger: string
  /** `ready` means a record exists, carries a written half, and passed its probes. It has never
   *  meant "the run stopped" — that was the defect this capability replaced. */
  status: 'ready' | 'unwritten' | 'failed'
  probe_status?: string | null
  probe_findings?: Array<{ dimension: string; missing: string[]; invented: string[] }> | null
  previous_checkpoint_id?: string | null
  lineage_id: string
  files_changed?: string[] | null
  open_questions?: Array<{ id: string; question: string }> | null
  runtime_overrides?: Record<string, string> | null
  citations?: Array<{ id: string; preview: string }> | null
  body?: string | null
  generation_error?: string | null
  /** Set once this checkpoint has been cut over; the predecessor is archived and the checkpoint is spent. */
  cut_over_to_conversation_id?: string | null
  created_at?: string | null
}

export interface CutoverResult {
  checkpoint_id: string
  conversation_id: string
  successor_conversation_id: string
  queue_entry_id: string
  agent: string
}

/** Every checkpoint for a conversation, newest first.
 *
 * Refreshed on `checkpoint_ready`, which is what the Hub broadcasts when the threshold fires.
 * Without that subscription the offer existed only in the database: the checkpoint was generated,
 * probed and stored, and the operator saw nothing until they happened to reload. */
export function useCheckpoints(conversationId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    if (event.type !== 'checkpoint_ready' && event.type !== 'conversation_cut_over') return
    const data = (event.data ?? {}) as { conversation_id?: string }
    if (data.conversation_id !== conversationId) return
    queryClient.invalidateQueries({
      queryKey: ['project', projectId, 'checkpoints', conversationId],
    })
  })

  return useQuery<Checkpoint[]>({
    queryKey: ['project', projectId, 'checkpoints', conversationId],
    queryFn: () =>
      getJson<Checkpoint[]>(
        `/api/v1/projects/${projectId}/conversations/${conversationId}/checkpoints`,
      ),
    enabled: isConfigured && !!projectId && !!conversationId,
  })
}

/**
 * Generate a checkpoint now.
 *
 * The Hub produces it from the conversation's own record — it does not ask the agent to write
 * one. The previous design did, and was observed twice producing an artifact in an unreachable
 * place and then producing nothing at all, both times reporting success.
 */
export async function takeCheckpoint(
  projectId: string,
  conversationId: string,
): Promise<Checkpoint> {
  return postJson<Checkpoint>(
    `/api/v1/projects/${projectId}/conversations/${conversationId}/checkpoint`,
  )
}

/** Open the successor, hand it the checkpoint, and archive the predecessor. */
export async function cutOver(
  projectId: string,
  checkpointId: string,
): Promise<CutoverResult> {
  return postJson<CutoverResult>(
    `/api/v1/projects/${projectId}/checkpoints/${checkpointId}/cutover`,
  )
}

export interface StartedFromCheckpoint {
  checkpoint_id: string
  conversation_id: string
  agent: string
  title: string | null
  queue_entry_id: string
  started: boolean
  waiting_reason?: string | null
}

/** Start a new conversation of `agent` whose first input is this checkpoint (and the optional
 *  message). The original conversation and the checkpoint's carry-over are left as they were. */
export async function startFromCheckpoint(
  projectId: string,
  checkpointId: string,
  agent: string,
  message?: string,
): Promise<StartedFromCheckpoint> {
  const note = message?.trim()
  return postJson<StartedFromCheckpoint>(
    `/api/v1/projects/${projectId}/checkpoints/${checkpointId}/start`,
    note ? { agent, message: note } : { agent },
  )
}

export interface ContinueResult {
  agent: string
  conversation_id: string
  /**
   * Did *this* conversation's work start — not "did a turn begin for the agent" (F131).
   *
   * The turn is the agent's, and the Hub builds it from the oldest eligible input across the
   * agent's whole queue, so the conversation that starts is frequently not the one asked about.
   * This used to be the agent-level answer, and rendering it as success left the operator
   * watching a conversation where no run, no output and no error would ever appear.
   */
  started: boolean
  /** The conversation whose input the turn actually carried, or null when nothing started. */
  started_conversation_id?: string | null
  waiting_reason?: string | null
}

/**
 * Start a turn from what is already queued.
 *
 * A successor holds its checkpoint as a queue entry, so it has everything it needs and nothing to
 * say. Making the operator type a message to get it moving turned the handover into a dead end;
 * this is the same act, named for what it does.
 */
export async function continueConversation(
  projectId: string,
  conversationId: string,
): Promise<ContinueResult> {
  return postJson<ContinueResult>(
    `/api/v1/projects/${projectId}/conversations/${conversationId}/continue`,
  )
}

/** Wave away the checkpoint warning for this conversation, for good. */
export async function dismissCheckpointWarning(
  projectId: string,
  conversationId: string,
): Promise<{ conversation_id: string; checkpoint_warning: string }> {
  return postJson(
    `/api/v1/projects/${projectId}/conversations/${conversationId}/dismiss-checkpoint-warning`,
  )
}

/** What an agent asked the next checkpoint to carry (slice remaining-hidden-data). */
export interface CheckpointNote {
  id: string
  agent: string
  run_id: string | null
  intent: string
  suspicions: string[]
  warnings: string[]
  /** The checkpoint that carried it; null while it waits for the next one. */
  consumed_by_checkpoint_id: string | null
  created_at: string | null
}

/** A conversation's checkpoint notes, oldest first (`GET /conversations/{id}/checkpoint-notes`).
 *  Refreshed with the checkpoints: a checkpoint consumes the notes before it. */
export function useCheckpointNotes(conversationId: string | null, enabled = true) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ notes: CheckpointNote[] }>({
    queryKey: ['project', projectId, 'checkpoints', conversationId, 'notes'],
    queryFn: () =>
      getJson<{ notes: CheckpointNote[] }>(
        `/api/v1/projects/${projectId}/conversations/${conversationId}/checkpoint-notes`,
      ),
    enabled: isConfigured && !!projectId && !!conversationId && enabled,
  })
}

/** The run a checkpoint covers, as `GET /projects/{id}/checkpoints` names it. */
export interface CoveredRun {
  run_id: string
  agent: string
  status: string
  started_at: string | null
  ended_at: string | null
}

export interface ProjectCheckpoint extends Checkpoint {
  title?: string | null
  summary?: string | null
  /** `model`, or who made it in the model's place: `hub_from_body`, `hub_from_facts`. */
  title_made_by?: string | null
  /** Why the model's answers were rejected or could not be read. */
  title_reason?: string | null
  has_unreadable_answer?: boolean
  /** Only when the list was asked for it (`includeRaw`). */
  unreadable_answer?: string | null
  carried_into?: { conversation_id: string } | null
  covered_runs?: CoveredRun[] | null
  /** The checkpoint this checkpoint's conversation was carried over from, when it was. */
  carried_from?: { checkpoint_id: string; conversation_id: string; title?: string | null } | null
  /** Conversations the operator started from this checkpoint, oldest first; not the carry-over. */
  started_conversations?: Array<{
    conversation_id: string
    agent: string
    title?: string | null
    lifecycle?: string
    created_at?: string | null
  }> | null
}

export interface ProjectCheckpointFilters {
  agent?: string
  trigger?: string
  conversationId?: string
  includeRaw?: boolean
}

export interface ProjectCheckpointList {
  checkpoints: ProjectCheckpoint[]
  /** Present only when a conversation was named: where it came from and where it went. */
  lineage: {
    conversation_id: string
    started_from: { checkpoint_id: string; conversation_id: string; title?: string | null } | null
    carried_into: { checkpoint_id: string; conversation_id: string } | null
  } | null
}

/** Every checkpoint the project holds, newest first (`GET /projects/{id}/checkpoints`).
 *  The filters narrow it and combine. */
export function useProjectCheckpoints(
  filters: ProjectCheckpointFilters = {},
  options: { enabled?: boolean } = {},
) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()
  useSSE((event) => {
    if (event.type !== 'checkpoint_ready' && event.type !== 'conversation_cut_over') return
    queryClient.invalidateQueries({ queryKey: ['project', projectId, 'checkpoints', 'project-list'] })
  })
  const params = new URLSearchParams()
  if (filters.agent) params.set('agent', filters.agent)
  if (filters.trigger) params.set('trigger', filters.trigger)
  if (filters.conversationId) params.set('conversation_id', filters.conversationId)
  if (filters.includeRaw) params.set('include_raw', 'true')
  const query = params.toString()
  return useQuery<ProjectCheckpointList>({
    queryKey: ['project', projectId, 'checkpoints', 'project-list', query],
    queryFn: () =>
      getJson<ProjectCheckpointList>(
        `/api/v1/projects/${projectId}/checkpoints${query ? `?${query}` : ''}`,
      ),
    enabled: isConfigured && !!projectId && (options.enabled ?? true),
  })
}

/** A checkpoint as its successor receives it (`GET /projects/{id}/checkpoints/{id}/rendered`). */
export function useRenderedCheckpoint(checkpointId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ id: string; status: string; rendered: string }>({
    queryKey: ['project', projectId, 'checkpoints', checkpointId, 'rendered'],
    queryFn: () =>
      getJson<{ id: string; status: string; rendered: string }>(
        `/api/v1/projects/${projectId}/checkpoints/${checkpointId}/rendered`,
      ),
    enabled: isConfigured && !!projectId && !!checkpointId,
  })
}
