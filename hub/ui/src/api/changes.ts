import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

export type ChangesState = 'ok' | 'empty' | 'no_checkout' | 'unreadable'
export type ChangesScope = 'turn' | 'branch'

/** One changed file, as the Hub lists it: no diff body, which is fetched when the file is selected. */
export interface ChangedFile {
  path: string
  /** A added, M modified, D deleted, R renamed. */
  status: string
  added: number
  removed: number
  binary: boolean
  old_path?: string | null
}

/** `GET /conversations/{id}/changes`. */
export interface ConversationChanges {
  state: ChangesState
  /** Plain words for `no_checkout` / `unreadable`; never an error code. */
  message?: string | null
  agent: string
  branch?: string | null
  base?: string | null
  task?: { id: string; readable_id?: string | null; title?: string | null } | null
  turn: ChangedFile[]
  since_base: ChangedFile[]
  running: boolean
  working_now: string[]
}

/** `GET /conversations/{id}/changes/patch`. */
export interface ChangePatch {
  path: string
  patch: string
  binary: boolean
  truncated: boolean
  total_lines: number
}

/** While a turn runs, its uncommitted files are re-read this often; the end of the turn is pushed. */
const WORKING_NOW_REFRESH_MS = 3000

export function useConversationChanges(conversationId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ConversationChanges>({
    queryKey: ['project', projectId, 'changes', conversationId],
    queryFn: () =>
      getJson<ConversationChanges>(`/api/v1/projects/${projectId}/conversations/${conversationId}/changes`),
    enabled: isConfigured && !!projectId && !!conversationId,
    refetchInterval: (query) => (query.state.data?.running ? WORKING_NOW_REFRESH_MS : false),
  })
}

export function useChangePatch(conversationId: string | null, path: string | null, scope: ChangesScope) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ChangePatch>({
    queryKey: ['project', projectId, 'changes', conversationId, 'patch', scope, path],
    queryFn: () =>
      getJson<ChangePatch>(
        `/api/v1/projects/${projectId}/conversations/${conversationId}/changes/patch?path=${encodeURIComponent(
          path as string,
        )}&scope=${scope}`,
      ),
    enabled: isConfigured && !!projectId && !!conversationId && !!path,
  })
}
