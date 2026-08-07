import { Button } from '@/components/ui/button'
import {
  PermissionRequest,
  useDecidePermissionRequest,
} from '@/api/permissions'

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
  const pending = requests.filter((r) => r.agent === agent && r.status === 'pending')
  if (pending.length === 0) return null

  return (
    <div className="flex flex-col gap-2" data-testid="permission-requests">
      {pending.map((request) => (
        <div
          key={request.id}
          data-testid={`permission-request-${request.id}`}
          style={{
            background: 'color-mix(in srgb, var(--amber) 6%, transparent)',
            border: '1px solid color-mix(in srgb, var(--amber) 25%, transparent)',
            borderRadius: 'var(--radius)',
            padding: '10px 12px',
          }}
        >
          <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--amber)', marginBottom: 4 }}>
            {agent} wants to use {request.tool_name}
          </p>
          <p
            style={{
              fontSize: 12,
              color: 'var(--text-2)',
              marginBottom: 8,
              fontFamily: 'var(--font-mono)',
              wordBreak: 'break-all',
            }}
          >
            {describe(request)}
          </p>
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
        </div>
      ))}
    </div>
  )
}
