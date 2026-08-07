import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PermissionRequestCard } from '@/components/agents/PermissionRequestCard'
import type { PermissionRequest } from '@/api/permissions'

const decide = vi.fn()

vi.mock('@/api/permissions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/permissions')>()),
  useDecidePermissionRequest: () => ({ mutate: decide, isPending: false }),
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
    created_at: new Date().toISOString(),
    decided_at: null,
    decided_by: null,
    ...overrides,
  }
}

describe('permission request card', () => {
  beforeEach(() => decide.mockClear())

  it('names the agent, the tool, and what it wants to touch', () => {
    render(<PermissionRequestCard requests={[request()]} agent="haiku-1" />)
    expect(screen.getByText(/haiku-1 wants to use Write/)).toBeInTheDocument()
    // The path is what the operator decides on, not the parameter name it arrived under.
    expect(screen.getByText('C:/outside/secrets.txt')).toBeInTheDocument()
  })

  it('falls back to the command when there is no path', () => {
    render(
      <PermissionRequestCard
        requests={[request({ tool_name: 'Bash', tool_input: { command: 'rm -rf /tmp/x' } })]}
        agent="haiku-1"
      />
    )
    expect(screen.getByText('rm -rf /tmp/x')).toBeInTheDocument()
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
