import type { PermissionRequest } from '@/api/permissions'

/** The permission requests a conversation shows for `agent`: pending, and expired ones kept
 *  alongside them. Answered ones are not — those the operator dealt with, and re-showing them
 *  would bury the one they missed.
 *
 *  One rule for both readers: `PermissionRequestCard` renders by it, and the conversation panel
 *  decides by it whether its interjection tray has anything in it. */
export function openPermissionRequestsFor(
  requests: PermissionRequest[],
  agent: string,
): PermissionRequest[] {
  return requests.filter(
    (r) => r.agent === agent && (r.status === 'pending' || r.status === 'expired'),
  )
}
