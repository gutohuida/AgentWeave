import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** A start offered to a project with no specs (`hub/hub/corpus_start.py`). */
export type CorpusStartKind = 'existing-code' | 'greenfield'

/** Whether the project's corpus is empty and who would start it (`GET .../project/corpus`). */
export interface CorpusState {
  /** No document in any phase (archived included) and no spec file waiting to be adopted. */
  empty: boolean
  /** A file outside `.git/`, `.agentweave/` and `spec/`; decides only the recommendation. */
  has_code: boolean
  /** Null once the corpus is not empty. */
  recommended: CorpusStartKind | null
  /** Both starts while the corpus is empty, recommended or not; none after. */
  starts: CorpusStartKind[]
  /** Open agents, in creation order. */
  agents: { name: string; charter: string | null }[]
  /** The one Spec Author when exactly one open agent has that charter, else the first open agent. */
  preselected_agent: string | null
  /** What makes the corpus not empty: a document's path, else an unadopted file's. */
  document: string | null
  unadopted: string[]
}

export interface CorpusStartResult {
  state: 'queued'
  start: CorpusStartKind
  agent: string
  document: { id: string; path: string; kind: string; title: string; phase: string }
  conversation_id: string
  entry_id: string
}

/** The order the starts are offered in: the recommended one first. */
export function orderStarts(starts: CorpusStartKind[], recommended: CorpusStartKind | null): CorpusStartKind[] {
  if (!recommended || !starts.includes(recommended)) return starts
  return [recommended, ...starts.filter((s) => s !== recommended)]
}

export function useCorpusState() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<CorpusState>({
    queryKey: ['project', projectId, 'corpus'],
    queryFn: () => getJson<CorpusState>(`/api/v1/projects/${projectId}/project/corpus`),
    enabled: isConfigured && !!projectId,
  })
}

/** Take a start: the Hub creates its document as the operator and queues the agent's turn in a
 *  new conversation. The choices go in the body; the route refuses them in the query string. */
export function useStartCorpus() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (args: { start: CorpusStartKind; agent: string }) =>
      postJson<CorpusStartResult>(`/api/v1/projects/${projectId}/project/corpus/start`, args),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'corpus'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specDocuments'] })
      // The project list carries the set-up items, the specification one among them.
      queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] === 'projects' })
    },
  })
}
