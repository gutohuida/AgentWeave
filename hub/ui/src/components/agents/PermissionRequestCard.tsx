import { Button } from '@/components/ui/button'
import {
  PermissionRequest,
  useDecidePermissionRequest,
} from '@/api/permissions'
import { readableApiError } from '@/api/client'

interface PermissionRequestCardProps {
  requests: PermissionRequest[]
  /** Only requests from this agent are shown; the card sits inside one conversation. */
  agent: string
}

/** What the agent is asking to do, in the operator's terms rather than the tool's.
 *
 * The operator is deciding in seconds under a run's timeout, so the path or command matters far
 * more than the parameter names it arrived under.
 */
function describe(request: PermissionRequest): string {
  const input = request.tool_input ?? {}
  const path = input.file_path ?? input.path ?? input.notebook_path
  if (typeof path === 'string' && path) return path
  const command = input.command
  if (typeof command === 'string' && command) return command
  // Codex's file-change approvals carry only the root they want granted; the individual paths
  // are not in the request, so this is the most specific thing there is to show.
  const grantRoot = input.grantRoot
  if (typeof grantRoot === 'string' && grantRoot) return grantRoot
  const cwd = input.cwd
  if (typeof cwd === 'string' && cwd) return cwd
  // Codex often sends a file-change approval with grantRoot null. Its own stated reason is then
  // the only thing describing the request, and is better than telling the operator nothing.
  const reason = input.reason
  if (typeof reason === 'string' && reason) return reason
  return 'no details given — the provider sent none'
}

export function PermissionRequestCard({ requests, agent }: PermissionRequestCardProps) {
  const decide = useDecidePermissionRequest()
  // Expired ones are kept alongside pending. Answered ones are not: those the operator dealt
  // with, and re-showing them would bury the one they missed.
  const open = requests.filter(
    (r) => r.agent === agent && (r.status === 'pending' || r.status === 'expired')
  )
  if (open.length === 0) return null

  return (
    <div className="flex flex-col gap-2" data-testid="permission-requests">
      {open.map((request) => {
        const expired = request.status === 'expired'
        // The residual race: the run gave up between this render and the click. The 409 says
        // what happened, and is worth more than a generic failure — an operator who is not told
        // reads it as the app being broken.
        const raceDetail =
          decide.isError && decide.variables?.id === request.id
            ? readableApiError(decide.error, 'this request could not be answered')
            : null

        return (
          <div
            key={request.id}
            data-testid={`permission-request-${request.id}`}
            className="conversation-interject"
          >
            <div className="flex items-center gap-2" style={{ marginBottom: 4 }}>
              <p className="interject-eyebrow">
                {agent} wants to use {request.tool_name}
              </p>
              {expired && (
                <span
                  data-testid={`permission-expired-${request.id}`}
                  title="Nobody answered in time, so the agent was refused and carried on without this."
                  style={{ fontSize: 10, color: 'var(--text-3)' }}
                >
                  no longer waiting
                </span>
              )}
            </div>
            <p
              style={{
                fontSize: 12,
                color: expired ? 'var(--text-3)' : 'var(--text)',
                marginBottom: 10,
                fontFamily: 'var(--font-mono)',
                wordBreak: 'break-all',
              }}
            >
              {describe(request)}
            </p>
            {expired ? (
              <p style={{ fontSize: 11, color: 'var(--text-3)' }}>
                The agent stopped waiting and was refused. Give yourself longer to answer by
                raising this agent's permission timeout.
              </p>
            ) : (
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  data-testid={`permission-allow-${request.id}`}
                  disabled={decide.isPending}
                  onClick={() => decide.mutate({ id: request.id, allow: true })}
                >
                  Allow
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  data-testid={`permission-deny-${request.id}`}
                  disabled={decide.isPending}
                  onClick={() => decide.mutate({ id: request.id, allow: false })}
                >
                  Deny
                </Button>
                <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
                  The agent is waiting, and will be refused if nobody answers.
                </span>
              </div>
            )}
            {raceDetail && (
              <p
                role="alert"
                data-testid={`permission-error-${request.id}`}
                style={{ fontSize: 11, color: 'var(--red)', marginTop: 8 }}
              >
                {raceDetail}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
