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

export interface WorkspaceFileResponse {
  path: string
  binary: boolean
  size: number
  /** `null` for a binary file — the endpoint never sends binary bytes as text. */
  content: string | null
}

/**
 * One file's content, for the panel shell's files tab (task 5.3, `2026-08-18-one-shell-three-panels`).
 * `enabled` is false while `path` is null so switching away from a file tab (or before one has
 * ever opened) issues no request.
 */
export function useWorkspaceFile(path: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<WorkspaceFileResponse>({
    queryKey: ['project', projectId, 'workspace', 'file', path],
    queryFn: () =>
      getJson<WorkspaceFileResponse>(
        `/api/v1/projects/${projectId}/workspace/file?path=${encodeURIComponent(path as string)}`,
      ),
    enabled: isConfigured && !!projectId && !!path,
    staleTime: 60_000,
  })
}

/** One live task this agent holds, and where that task's work happens. */
export interface TaskCheckoutInfo {
  task_id: string
  title?: string | null
  status: string
  branch: string
  path: string
  provisioned: boolean
  /**
   * True when this task's work began before per-task isolation, so it runs in the agent's own
   * checkout and has no directory of its own. Without saying so, an operator looking for the
   * task's checkout finds none and concludes the work was lost.
   */
  grandfathered: boolean
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
  /** The checkouts of the tasks this agent is holding. An agent working three tasks has three,
   *  and this panel used to show only the first. Absent on an older Hub. */
  task_checkouts?: TaskCheckoutInfo[]
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

/** One Hub-owned checkout under the project's repo root, and what it belongs to. */
export interface WorkspaceInfo {
  /** `'agent'` or `'task'`. Two namespaces share this list, and `name` alone cannot separate them. */
  kind: string
  name: string
  branch: string
  path: string
}

/**
 * Every provisioned checkout in the project, agent and task alike.
 *
 * Reading it provisions nothing — the Hub answers from git's own registration, so an empty list
 * means no checkout exists rather than that none was created for the asking.
 */
export function useWorktrees() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<WorkspaceInfo[]>({
    queryKey: ['project', projectId, 'worktrees'],
    queryFn: () => getJson<WorkspaceInfo[]>(`/api/v1/projects/${projectId}/worktrees`),
    enabled: isConfigured && !!projectId,
  })
}
