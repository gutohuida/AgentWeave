import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PermissionRequestCard } from '@/components/agents/PermissionRequestCard'
import type { PermissionRequest } from '@/api/permissions'

const decide = vi.fn()
const dismiss = vi.fn()
/** The mutation's own state, so a test can put the card in the "the run moved on" case. */
const decideState: Record<string, unknown> = {}

vi.mock('@/api/permissions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/permissions')>()),
  useDecidePermissionRequest: () => ({ mutate: decide, isPending: false, ...decideState }),
  useDismissPermissionRequest: () => ({ mutate: dismiss, isPending: false }),
}))

function request(overrides: Partial<PermissionRequest> = {}): PermissionRequest {
  return {
    id: 'perm-1',
    agent: 'haiku-1',
    run_id: 'run-1',
    tool_name: 'Write',
    tool_use_id: 'toolu_1',
    tool_input: { file_path: 'C:/outside/secrets.txt', content: 'x' },
    status: 'pending',
    dismissed: false,
    created_at: new Date().toISOString(),
    decided_at: null,
    decided_by: null,
    ...overrides,
  }
}

beforeEach(() => {
  decide.mockClear()
  dismiss.mockClear()
  for (const key of Object.keys(decideState)) delete decideState[key]
})

describe('permission request card', () => {

  it('names the agent, the tool, and what it wants to touch', () => {
    render(<PermissionRequestCard requests={[request()]} agent="haiku-1" />)
    expect(screen.getByText(/haiku-1 wants to use Write/)).toBeInTheDocument()
    // The path is what the operator decides on, not the parameter name it arrived under.
    expect(screen.getByText('C:/outside/secrets.txt')).toBeInTheDocument()
    expect(screen.getByText('File change')).toHaveAttribute('data-impact', 'mutates')
    expect(screen.getByLabelText('File change: C:/outside/secrets.txt')).toBeInTheDocument()
  })

  it('falls back to the command when there is no path', () => {
    render(
      <PermissionRequestCard
        requests={[request({ tool_name: 'Bash', tool_input: { command: 'rm -rf /tmp/x' } })]}
        agent="haiku-1"
      />
    )
    expect(screen.getByText('rm -rf /tmp/x')).toBeInTheDocument()
    expect(screen.getByText('Command')).toBeInTheDocument()
  })

  it('makes the explicit allow action primary without weakening deny', () => {
    render(<PermissionRequestCard requests={[request()]} agent="haiku-1" />)
    expect(screen.getByTestId('permission-allow-perm-1')).toHaveClass('bg-[var(--primary)]')
    expect(screen.getByTestId('permission-deny-perm-1')).toHaveClass('border-[var(--border)]')
  })

  it('states position when more than one decision is waiting', () => {
    render(<PermissionRequestCard requests={[request(), request({ id: 'perm-2' })]} agent="haiku-1" />)
    expect(screen.getByText('1/2')).toBeInTheDocument()
    expect(screen.getByText('2/2')).toBeInTheDocument()
  })

  it('offers no way to clear a request that is still being waited on', () => {
    // Tidying a live card off the screen would deny it by neglect while the run still waits.
    render(<PermissionRequestCard requests={[request()]} agent="haiku-1" />)
    expect(screen.queryByTestId('permission-dismiss-perm-1')).not.toBeInTheDocument()
  })

  it('sends the operator decision both ways', () => {
    render(<PermissionRequestCard requests={[request()]} agent="haiku-1" />)
    fireEvent.click(screen.getByTestId('permission-allow-perm-1'))
    expect(decide).toHaveBeenCalledWith({ id: 'perm-1', allow: true })
    fireEvent.click(screen.getByTestId('permission-deny-perm-1'))
    expect(decide).toHaveBeenCalledWith({ id: 'perm-1', allow: false })
  })

  it('shows nothing when there is nothing pending', () => {
    const { container } = render(<PermissionRequestCard requests={[]} agent="haiku-1" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('ignores another agent\u2019s request', () => {
    // The card sits inside one conversation; showing a peer's prompt here would have the
    // operator answering for an agent they are not looking at.
    render(<PermissionRequestCard requests={[request({ agent: 'haiku-2' })]} agent="haiku-1" />)
    expect(screen.queryByTestId('permission-request-perm-1')).not.toBeInTheDocument()
  })

  it('ignores a request that has already been decided', () => {
    render(<PermissionRequestCard requests={[request({ status: 'allowed' })]} agent="haiku-1" />)
    expect(screen.queryByTestId('permission-request-perm-1')).not.toBeInTheDocument()
  })
})

describe('permission request card — codex shapes', () => {
  it('shows the granted root for a file-change approval', () => {
    render(
      <PermissionRequestCard
        requests={[request({ tool_name: 'a file change', tool_input: { grantRoot: 'C:/work' } })]}
        agent="haiku-1"
      />
    )
    expect(screen.getByText('C:/work')).toBeInTheDocument()
  })

  it('falls back to the provider\u2019s reason when it sends no path at all', () => {
    // Measured live: codex sends {"grantRoot": null, "reason": null} for a file change, so this
    // path is reached in practice rather than being defensive.
    render(
      <PermissionRequestCard
        requests={[
          request({
            tool_name: 'a file change',
            tool_input: { grantRoot: null, reason: 'needs to write outside the sandbox' },
          }),
        ]}
        agent="haiku-1"
      />
    )
    expect(screen.getByText('needs to write outside the sandbox')).toBeInTheDocument()
  })

  it('says so plainly when the provider sent nothing', () => {
    render(
      <PermissionRequestCard
        requests={[request({ tool_name: 'a file change', tool_input: { grantRoot: null } })]}
        agent="haiku-1"
      />
    )
    expect(screen.getByText(/the provider sent none/)).toBeInTheDocument()
  })
})

describe('a request the run stopped waiting on', () => {
  it('says it is no longer waiting instead of disappearing', () => {
    // Vanishing is indistinguishable from a bug, and withholds the one fact worth having:
    // the agent gave up and carried on without the operator.
    render(<PermissionRequestCard requests={[request({ status: 'expired' })]} agent="haiku-1" />)
    expect(screen.getByTestId('permission-request-perm-1')).toBeInTheDocument()
    expect(screen.getByTestId('permission-expired-perm-1')).toBeInTheDocument()
  })

  it('cannot be answered', () => {
    render(<PermissionRequestCard requests={[request({ status: 'expired' })]} agent="haiku-1" />)
    expect(screen.queryByTestId('permission-allow-perm-1')).not.toBeInTheDocument()
    expect(screen.queryByTestId('permission-deny-perm-1')).not.toBeInTheDocument()
  })

  it('tells the operator what to change so they do not miss the next one', () => {
    render(<PermissionRequestCard requests={[request({ status: 'expired' })]} agent="haiku-1" />)
    expect(screen.getByText(/permission timeout/)).toBeInTheDocument()
  })

  it('can be cleared away once the operator has seen it', () => {
    // They accumulate deliberately, but a pile with no way to clear it stops being a signal.
    render(<PermissionRequestCard requests={[request({ status: 'expired' })]} agent="haiku-1" />)
    fireEvent.click(screen.getByTestId('permission-dismiss-perm-1'))
    expect(dismiss).toHaveBeenCalledWith({ id: 'perm-1' })
  })

  it('is not the same state as one the operator answered', () => {
    // An answered request is not shown at all, so "grey for both" is not reachable: allowed and
    // denied stay filtered out while expired stays visible.
    for (const status of ['allowed', 'denied'] as const) {
      const { unmount } = render(
        <PermissionRequestCard requests={[request({ status })]} agent="haiku-1" />
      )
      expect(screen.queryByTestId('permission-request-perm-1')).not.toBeInTheDocument()
      expect(screen.queryByTestId('permission-expired-perm-1')).not.toBeInTheDocument()
      unmount()
    }
  })
})

describe('losing the race to the run', () => {
  it('says the run moved on rather than failing silently', async () => {
    // The 409 the Hub already wrote for exactly this: answered at t=119s, given up at t=120s.
    const { ApiError } = await import('@/api/client')
    decideState.isError = true
    decideState.variables = { id: 'perm-1', allow: true }
    decideState.error = new ApiError(
      409,
      JSON.stringify({ detail: 'this request was already expired; the run has moved on' })
    )
    render(<PermissionRequestCard requests={[request()]} agent="haiku-1" />)
    expect(screen.getByTestId('permission-error-perm-1')).toHaveTextContent(/the run has moved on/)
  })

  it('does not blame a request the operator did not click', () => {
    decideState.isError = true
    decideState.variables = { id: 'perm-2', allow: true }
    decideState.error = new Error('boom')
    render(<PermissionRequestCard requests={[request()]} agent="haiku-1" />)
    expect(screen.queryByTestId('permission-error-perm-1')).not.toBeInTheDocument()
  })
})

describe('permission card wears the composer’s chrome', () => {
  it('is the shared surface, not an amber callout', () => {
    const { container } = render(
      <PermissionRequestCard requests={[request()]} agent="haiku-1" />
    )
    expect(container.querySelector('.conversation-interject')).not.toBeNull()
    expect(container.innerHTML).not.toContain('--amber')
  })
})
