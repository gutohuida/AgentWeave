import { Button } from '@/components/ui/button'
import {
  PermissionRequest,
  useDecidePermissionRequest,
  useDismissPermissionRequest,
} from '@/api/permissions'
import { readableApiError } from '@/api/client'
import { Icon } from '@/components/common/Icon'

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

function requestKind(request: PermissionRequest): { label: string; impact: 'neutral' | 'mutates' } {
  const input = request.tool_input ?? {}
  const tool = request.tool_name.toLowerCase()
  if (typeof input.command === 'string') return { label: 'Command', impact: 'mutates' }
  const hasPath = [input.file_path, input.path, input.notebook_path].some((value) => typeof value === 'string' && value)
  if (hasPath && (tool.includes('read') || tool.includes('view'))) return { label: 'File read', impact: 'neutral' }
  if (hasPath || 'grantRoot' in input || tool.includes('edit') || tool.includes('write') || tool.includes('change')) {
    return { label: 'File change', impact: 'mutates' }
  }
  return { label: 'Tool request', impact: 'neutral' }
}

export function PermissionRequestCard({ requests, agent }: PermissionRequestCardProps) {
  const decide = useDecidePermissionRequest()
  const dismiss = useDismissPermissionRequest()
  // Expired ones are kept alongside pending. Answered ones are not: those the operator dealt
  // with, and re-showing them would bury the one they missed.
  const open = requests.filter(
    (r) => r.agent === agent && (r.status === 'pending' || r.status === 'expired')
  )
  if (open.length === 0) return null

  return (
    <div className="flex flex-col gap-2" data-testid="permission-requests">
      {open.map((request, index) => {
        const expired = request.status === 'expired'
        const kind = requestKind(request)
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
            className={`conversation-interject${expired ? ' is-stale' : ''}`}
          >
            <div className="flex items-center gap-2" style={{ marginBottom: 4 }}>
              <span className="permission-kind" data-impact={kind.impact}>{kind.label}</span>
              <p className="interject-eyebrow">
                {agent} wants to use {request.tool_name}
              </p>
              {open.length > 1 && <span className="interject-count ml-auto">{index + 1}/{open.length}</span>}
              {expired && (
                <span
                  data-testid={`permission-expired-${request.id}`}
                  title="Nobody answered in time, so the agent was refused and carried on without this."
                  style={{ fontSize: 10, color: 'var(--text-3)' }}
                >
                  no longer waiting
                </span>
              )}
              {/* Only on an expired card. A pending request must be answered, not cleared away:
                  tidying it off the screen would deny it by neglect while the run still waits. */}
              {expired && (
                <button
                  type="button"
                  aria-label="Dismiss this expired request"
                  title="Clear this from view. The agent has already moved on."
                  data-testid={`permission-dismiss-${request.id}`}
                  disabled={dismiss.isPending}
                  onClick={() => dismiss.mutate({ id: request.id })}
                  className={`${open.length > 1 ? '' : 'ml-auto'} shrink-0 rounded p-0.5`}
                  style={{ color: 'var(--text-3)', background: 'transparent', border: 'none' }}
                >
                  <Icon name="x" size={14} />
                </button>
              )}
            </div>
            <code
              className={`permission-detail${expired ? ' is-stale' : ''}`}
              aria-label={`${kind.label}: ${describe(request)}`}
            >
              {describe(request)}
            </code>
            {expired ? (
              <p style={{ fontSize: 11, color: 'var(--text-3)' }}>
                The agent stopped waiting and was refused. Give yourself longer to answer by
                raising this agent's permission timeout.
              </p>
            ) : (
              <div className="permission-actions">
                <Button
                  size="sm"
                  variant="primary"
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
                {/* The clock is what makes this read as a deadline rather than as a caption.
                    Still no countdown behind it — the sentence states the consequence, which is
                    the decision `RESEARCH.md` reached about not putting an operator under a
                    ticking number on the highest-stakes control in the product. */}
                <span className="permission-waiting">
                  <Icon name="schedule" size={12} />
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
