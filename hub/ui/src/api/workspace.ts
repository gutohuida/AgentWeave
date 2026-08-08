import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

/**
 * Fetched once and cached (design.md's caching mitigation for `composer-intelligence`):
 * the composer's `@path`/`$skill` triggers filter this list client-side per keystroke
 * rather than issuing a request per query.
 */
export function useWorkspacePaths() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<string[]>({
    queryKey: ['project', projectId, 'workspace', 'paths'],
    queryFn: () => getJson<string[]>(`/api/v1/projects/${projectId}/workspace/paths`),
    enabled: isConfigured && !!projectId,
    staleTime: 60_000,
  })
}

export interface AgentWorkspaceInfo {
  agent: string
  repo_root: string
  working_dir: string
  /** True when this agent gets its own git worktree; false when it shares the project checkout. */
  isolated: boolean
  branch?: string | null
  provisioned: boolean
  /** Set when isolation cannot be prepared — the same condition that refuses a turn. */
  unavailable_reason?: string | null
}

/** Where one agent works on disk. Reading it provisions nothing: the Hub answers from the paths
 *  it would use, so an agent that has never run still says where it will work. */
export function useAgentWorkspace(agent: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<AgentWorkspaceInfo>({
    queryKey: ['project', projectId, 'worktrees', agent],
    queryFn: () =>
      getJson<AgentWorkspaceInfo>(`/api/v1/projects/${projectId}/worktrees/${agent}`),
    enabled: isConfigured && !!projectId && !!agent,
  })
}
