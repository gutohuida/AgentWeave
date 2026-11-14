import { useQuery } from '@tanstack/react-query'
import { ApiError, deleteJson, getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** The Hub's shells for the side panel's Terminal tab (spec `a-terminal-in-the-side-panel`). */

export type ShellLocation = 'worktree' | 'root'

export interface ShellChoice {
  id: string
  label: string
  detail?: string | null
  wsl: boolean
  last_used: boolean
}

export interface ShellMenu {
  shells: ShellChoice[]
  last_pick: { option_id: string; location: ShellLocation } | null
  /** Set when no terminal is offered: why, as a reason code (`remote`, `docker`, ...). */
  unavailable: string | null
  unavailable_reason: string | null
  /** Null when the agent has a worktree; otherwise why the worktree choice is unavailable. */
  worktree_unavailable: string | null
  limit: number
}

/** One open shell as the Hub lists it. */
export interface ShellRecord {
  id: string
  conversation_id: string
  shell: string
  label: string
  wsl: boolean
  location: ShellLocation
  directory: string
  running: boolean
  exit_code: number | null
}

const base = (projectId: string, conversationId: string) =>
  `/api/v1/projects/${projectId}/conversations/${encodeURIComponent(conversationId)}/terminals`

export function useShellMenu(conversationId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ShellMenu>({
    queryKey: ['project', projectId, 'terminal', 'menu', conversationId],
    queryFn: () =>
      getJson<ShellMenu>(
        `/api/v1/projects/${projectId}/terminal/shells` +
          (conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : ''),
      ),
    enabled: isConfigured && !!projectId,
    // What is installed does not change under the operator; the pick and the worktree do.
    staleTime: 0,
  })
}

export async function listShells(projectId: string, conversationId: string): Promise<ShellRecord[]> {
  const body = await getJson<{ shells: ShellRecord[] }>(base(projectId, conversationId))
  return body.shells
}

export function openShell(
  projectId: string,
  conversationId: string,
  request: { shell: string; location: ShellLocation; page: string; cols?: number; rows?: number },
): Promise<ShellRecord> {
  return postJson<ShellRecord>(base(projectId, conversationId), request)
}

export function closeShell(projectId: string, conversationId: string, id: string) {
  return deleteJson<{ id: string; closed: boolean }>(`${base(projectId, conversationId)}/${id}`)
}

export function restartShell(projectId: string, conversationId: string, id: string) {
  return postJson<ShellRecord & { replaces: string }>(`${base(projectId, conversationId)}/${id}/restart`)
}

/** The sentence in a refusal: the Hub's `detail`, not the JSON around it. */
export function refusalText(error: unknown): string {
  if (error instanceof ApiError) {
    try {
      const parsed = JSON.parse(error.message) as { detail?: unknown }
      if (typeof parsed.detail === 'string') return parsed.detail
    } catch {
      /* not JSON */
    }
    return error.message || `The Hub refused (${error.status})`
  }
  return error instanceof Error ? error.message : 'The shell could not be opened'
}

/** The page's own id: one per page load, so a reload ends the shells it opened (FR-9). */
export const PAGE_ID: string =
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `page-${Date.now()}-${Math.random().toString(36).slice(2)}`

async function socketUrl(projectId: string, path: string, query: Record<string, string>): Promise<string> {
  const { hubUrl } = useConfigStore.getState()
  const ticket = await getJson<{ token: string }>(`/api/v1/projects/${projectId}/events/ticket`)
  const params = new URLSearchParams({ ...query, token: ticket.token })
  const origin = (hubUrl || window.location.origin).replace(/^http/, 'ws')
  return `${origin}/api/v1/projects/${projectId}${path}?${params.toString()}`
}

export async function openPageSocket(projectId: string): Promise<WebSocket> {
  return new WebSocket(await socketUrl(projectId, '/terminal/page', { page: PAGE_ID }))
}

export async function openAttachSocket(projectId: string, conversationId: string, id: string): Promise<WebSocket> {
  return new WebSocket(await socketUrl(projectId, `/conversations/${encodeURIComponent(conversationId)}/terminals/${id}/attach`, {}))
}
