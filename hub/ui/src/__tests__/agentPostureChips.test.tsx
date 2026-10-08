import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentPostureChips } from '@/components/overview/AgentPostureChips'
import type { AgentSummary } from '@/api/agents'

// `the-settings-that-gate-collaboration-are-on-the-project-page` FR-3, FR-4, FR-5.

const grant = vi.fn()
let launchability: Record<string, { present: boolean; authorized: boolean; runnable: boolean; reason?: string | null }> = {}
let waitingReason: string | null = null

vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useUpdateAgentGrant: () => ({ mutate: grant, isPending: false, error: null }),
  useAgentLaunchability: () => ({ data: { agents: launchability } }),
}))
vi.mock('@/api/queue', () => ({
  useQueueStatus: (agent: string | null) => ({
    data: { agent, waiting_count: waitingReason ? 2 : 0, running: false, waiting_reason: waitingReason },
  }),
}))
let runnersLoading = false
vi.mock('@/api/runners', () => ({
  useRunners: () => runnersLoading
    ? { data: undefined, isLoading: true }
    : { data: [{ id: 'runner-haiku', name: 'Haiku 4.5', cli: 'claude', model: 'claude-haiku-4-5-20251001' }], isLoading: false },
}))
vi.mock('@/api/modelCatalog', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/modelCatalog')>()),
  useModelCatalog: () => ({ data: undefined }),
}))

const alpha: AgentSummary = {
  name: 'alpha', status: 'idle', message_count: 0, active_task_count: 0,
  runner_id: 'runner-haiku', charter_id: 'charter-1',
  can_accept_evidence: true, can_read_checkpoints: false, can_recall: false,
  default_permission_mode: null, permission_timeout_seconds: null, question_timeout_seconds: null,
}
const beta: AgentSummary = {
  ...alpha, name: 'beta', charter_id: null, can_accept_evidence: false,
  permission_timeout_seconds: 300,
}

describe('agent posture on the Overview card', () => {
  beforeEach(() => {
    grant.mockReset()
    launchability = {}
    waitingReason = null
    runnersLoading = false
  })

  it('shows each grant as a pressed or unpressed chip (FR-4)', () => {
    render(<AgentPostureChips agent={alpha} onNavigate={vi.fn()} />)
    expect(screen.getByTestId('agent-grant-alpha-can_accept_evidence')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('agent-grant-alpha-can_read_checkpoints')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('agent-grant-alpha-can_recall')).toHaveAttribute('aria-pressed', 'false')
  })

  it('switches one grant for one agent in place', () => {
    render(<AgentPostureChips agent={beta} onNavigate={vi.fn()} />)
    fireEvent.click(screen.getByTestId('agent-grant-beta-can_accept_evidence'))
    expect(grant).toHaveBeenCalledWith({ agent: 'beta', grant: 'can_accept_evidence', enabled: true })
  })

  it("flags a missing charter and links to the agent's Charter section", () => {
    const onNavigate = vi.fn()
    render(<AgentPostureChips agent={beta} onNavigate={onNavigate} />)
    fireEvent.click(screen.getByText('no charter'))
    expect(onNavigate).toHaveBeenCalledWith('agent-settings:beta:charter')
  })

  it('does not flag an agent that has a charter', () => {
    render(<AgentPostureChips agent={alpha} onNavigate={vi.fn()} />)
    expect(screen.queryByText('no charter')).toBeNull()
  })

  it("flags an agent that cannot launch, with the Hub's sentence", () => {
    launchability = { beta: { present: false, authorized: false, runnable: false, reason: 'claude is not on PATH' } }
    render(<AgentPostureChips agent={beta} onNavigate={vi.fn()} />)
    expect(screen.getByText("can't run")).toBeInTheDocument()
    expect(screen.getByText('claude is not on PATH')).toBeInTheDocument()
  })

  it('flags an agent with no runner bound', () => {
    render(<AgentPostureChips agent={{ ...beta, runner_id: null }} onNavigate={vi.fn()} />)
    expect(screen.getByText('no runner')).toBeInTheDocument()
  })

  it('says the agent is held by the hop budget (FR-3)', () => {
    waitingReason = 'hop budget exhausted'
    render(<AgentPostureChips agent={beta} onNavigate={vi.fn()} />)
    expect(screen.getByText('held by hop budget')).toBeInTheDocument()
  })

  it('keeps the details collapsed until asked, then shows posture, runner and waits (FR-5)', () => {
    render(<AgentPostureChips agent={beta} onNavigate={vi.fn()} />)
    const toggle = screen.getByTestId('agent-details-toggle-beta')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('agent-details-beta')).toBeNull()

    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const details = screen.getByTestId('agent-details-beta')
    expect(details).toHaveTextContent(/built-in default/i)
    expect(details).toHaveTextContent('Haiku 4.5')
    expect(details).toHaveTextContent('300s')
    expect(details).toHaveTextContent('240s (default)')
    expect(details).not.toHaveTextContent('300s (default)')
  })

  // Found by the acceptance drive: the runner list is first fetched when the details open, and a
  // bound agent read "None bound" until it arrived.
  it('does not call a bound runner missing while the runner list is still loading', () => {
    runnersLoading = true
    render(<AgentPostureChips agent={beta} onNavigate={vi.fn()} />)
    fireEvent.click(screen.getByTestId('agent-details-toggle-beta'))
    expect(screen.getByTestId('agent-details-beta')).not.toHaveTextContent('None bound')
  })

  it('says None bound only for an agent with no runner', () => {
    render(<AgentPostureChips agent={{ ...beta, runner_id: null }} onNavigate={vi.fn()} />)
    fireEvent.click(screen.getByTestId('agent-details-toggle-beta'))
    expect(screen.getByTestId('agent-details-beta')).toHaveTextContent('None bound')
  })
})
