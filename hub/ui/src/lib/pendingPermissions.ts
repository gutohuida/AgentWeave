import type { PermissionRequest } from '@/api/permissions'

/** The permission requests a conversation shows for `agent`: pending, and expired ones kept
 *  alongside them. Answered ones are not — those the operator dealt with, and re-showing them
 *  would bury the one they missed.
 *
 *  `conversationId` scopes the list to the conversation on screen (F928): a request belongs to the
 *  conversation whose run asked, and under another conversation of the same agent it reads as that
 *  conversation asking. `null` is "no conversation open" and matches none; leaving it out keeps
 *  the agent-wide reading. A request that names no conversation shows wherever the agent is.
 *
 *  One rule for both readers: `PermissionRequestCard` renders by it, and the conversation panel
 *  decides by it whether its interjection tray has anything in it. */
export function openPermissionRequestsFor(
  requests: PermissionRequest[],
  agent: string,
  conversationId?: string | null,
): PermissionRequest[] {
  return requests.filter(
    (r) =>
      r.agent === agent
      && (r.status === 'pending' || r.status === 'expired')
      && (conversationId === undefined || !r.conversation_id || r.conversation_id === conversationId),
  )
}
