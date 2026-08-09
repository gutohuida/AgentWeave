import { useQuery } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface Checkpoint {
  id: string
  conversation_id: string
  agent: string
  trigger: string
  /** `ready` means a record exists, carries a written half, and passed its probes. It has never
   *  meant "the run stopped" — that was the defect this capability replaced. */
  status: 'ready' | 'unwritten' | 'failed'
  visibility: 'private' | 'project' | 'granted'
  probe_status?: string | null
  probe_findings?: Array<{ dimension: string; missing: string[]; invented: string[] }> | null
  previous_checkpoint_id?: string | null
  lineage_id: string
  files_changed?: string[] | null
  open_questions?: Array<{ id: string; question: string }> | null
  runtime_overrides?: Record<string, string> | null
  citations?: Array<{ id: string; preview: string }> | null
  body?: string | null
  created_at?: string | null
}

export interface CutoverResult {
  checkpoint_id: string
  conversation_id: string
  successor_conversation_id: string
  queue_entry_id: string
  agent: string
}

/** Every checkpoint for a conversation, newest first. */
export function useCheckpoints(conversationId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
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

export interface ContinueResult {
  agent: string
  conversation_id: string
  started: boolean
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
