import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson, putJson } from './client'

/** The document a conversation has open — the conversation's own, held by the Hub
 *  (`every-spec-entry-point-leads-into-the-journey`, FR-11/FR-12). */
export interface AttachedSpecDocument {
  path: string
  title: string
  phase: string
  step: string | null
}

/** A change document an agent created in this conversation, offered to the operator. */
export interface SpecDocumentOffer {
  path: string
  title: string
  step: string | null
  /** The run whose turn created it: the offer is drawn under that turn's message. Absent from an
   *  older Hub. */
  run_id?: string | null
  created_by: string | null
  created_at: string | null
}

export interface ConversationSpecDocuments {
  attached: AttachedSpecDocument | null
  offers: SpecDocumentOffer[]
}

export const conversationSpecKey = (projectId: string | null, conversationId: string | null) =>
  ['project', projectId, 'conversation', conversationId, 'spec-documents'] as const

const base = (projectId: string, conversationId: string) =>
  `/api/v1/projects/${projectId}/conversations/${conversationId}`

/** What the Hub holds for this conversation. Disabled with no conversation (the new-conversation
 *  surface has none, and so starts with no document). */
export function useConversationSpecDocuments(projectId: string | null, conversationId: string | null) {
  return useQuery({
    queryKey: conversationSpecKey(projectId, conversationId),
    queryFn: () => getJson<ConversationSpecDocuments>(`${base(projectId!, conversationId!)}/spec-documents`),
    enabled: !!projectId && !!conversationId,
  })
}

/** Open a document in a conversation, or clear it with `null` (Stop exploring). The answer is
 *  written into the read above, so the conversation shows it without another request. */
export function useSetConversationDocumentFor(projectId: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ conversationId, path }: { conversationId: string; path: string | null }) =>
      putJson<{ attached: AttachedSpecDocument | null }>(`${base(projectId!, conversationId)}/spec-document`, { path }),
    onSuccess: (result, { conversationId }) => {
      queryClient.setQueryData<ConversationSpecDocuments>(
        conversationSpecKey(projectId, conversationId),
        (old) => ({ offers: old?.offers ?? [], attached: result.attached }),
      )
    },
  })
}

/** Open a document in a conversation: a document an agent created there, offered. */
export function useAnswerSpecDocumentOffer(projectId: string | null, conversationId: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ path, answer }: { path: string; answer: 'open' | 'not_now' }) =>
      postJson<{ path: string; answer: string; attached: AttachedSpecDocument | null }>(
        `${base(projectId!, conversationId!)}/spec-documents/answer`,
        { path, answer },
      ),
    // The answer is recorded on the Hub, so the read is refetched and the notice is gone after a
    // reload as well as now.
    onSettled: () => queryClient.invalidateQueries({ queryKey: conversationSpecKey(projectId, conversationId) }),
  })
}
