import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CollaborationSummary } from '@/components/overview/CollaborationSummary'
import { ApiError } from '@/api/client'
import { useConfigStore } from '@/store/configStore'

// `the-settings-that-gate-collaboration-are-on-the-project-page` FR-1, FR-2, FR-3, FR-8.

const mutate = vi.fn()
let updateError: Error | null = null
let settings = makeSettings()
let budget = { limit_tokens: null as number | null, used_tokens: 2_600_000, remaining_tokens: null as number | null, exhausted: false }
let settingsError: Error | null = null
let accountingError: Error | null = null
let agentsError: Error | null = null
let queueStatuses: Array<{ agent: string; waiting_count: number; running: boolean; waiting_reason: string | null }> = []

function makeSettings() {
  return {
    name: 'Website',
    hop_budget: 6,
    turn_delivery_cap: 10,
    agent_budget: 8,
    token_budget: null as number | null,
    allow_agent_jobs: false,
    conversation_title_mode: 'truncate' as const,
    conversation_title_runner_id: null,
    checkpoint_mode: 'offered' as const,
    checkpoint_threshold_mode: null,
    checkpoint_threshold_value: null,
    checkpoint_notes_value: null,
    checkpoint_runner_id: null,
    checkpoint_model: null,
    checkpoint_auto_continue: false,
    main_branch: null as string | null,
    checks: [
      { name: 'unit', command: 'pytest', timeout_seconds: 600 },
      { name: 'lint', command: 'ruff check', timeout_seconds: 60 },
    ] as Array<{ name: string; command: string; timeout_seconds: number }> | null,
  }
}

vi.mock('@/api/projects', () => ({
  useProjectSettings: () => (settingsError ? { data: undefined, error: settingsError } : { data: settings, error: null }),
  useUpdateProjectSettings: () => ({ mutate, isPending: false, error: updateError }),
}))
vi.mock('@/api/accounting', () => ({
  useAccounting: () => (accountingError ? { data: undefined, error: accountingError } : { data: { budget }, error: null }),
}))
vi.mock('@/api/agents', () => ({
  useAgents: () => (agentsError ? { data: undefined, error: agentsError } : { data: [{ name: 'alpha' }, { name: 'beta' }], error: null }),
}))
vi.mock('@/api/queue', () => ({
  useQueueStatuses: () => queueStatuses,
}))

const row = (id: string) => screen.getByTestId(`collab-row-${id}`)

describe('Overview Collaboration block', () => {
  beforeEach(() => {
    mutate.mockReset()
    updateError = null
    settings = makeSettings()
    budget = { limit_tokens: null, used_tokens: 2_600_000, remaining_tokens: null, exhausted: false }
    queueStatuses = []
    settingsError = null
    accountingError = null
    agentsError = null
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
  })

  it('reads every gating setting as a live value, flagging no limit and no branch', () => {
    render(<CollaborationSummary onNavigate={vi.fn()} />)
    expect(row('flows')).toHaveTextContent('Off')
    expect(within(row('flows')).getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    expect(row('hop')).toHaveTextContent('6 hops')
    expect(row('token')).toHaveTextContent('No limit')
    expect(row('token')).toHaveTextContent('2,600,000 used')
    expect(row('token').querySelector('[data-flag="true"]')).not.toBeNull()
    expect(row('branch')).toHaveTextContent('Not set')
    expect(row('branch').querySelector('[data-flag="true"]')).not.toBeNull()
    expect(row('checks')).toHaveTextContent('2 checks')
    expect(row('checks').querySelector('[data-flag="true"]')).toBeNull()
    expect(row('limits')).toHaveTextContent('10 per turn')
    expect(row('limits')).toHaveTextContent('2 of 8 agents')
  })

  it('says what agent budget caps, and not that it limits agents running at once (FR-8)', () => {
    render(<CollaborationSummary onNavigate={vi.fn()} />)
    expect(row('limits').textContent).toMatch(/staff/i)
    expect(row('limits').textContent).not.toMatch(/at the same time/i)
  })

  it('reads a set limit as used of limit, and a chosen branch by name', () => {
    budget = { limit_tokens: 5000, used_tokens: 1200, remaining_tokens: 3800, exhausted: false }
    settings = { ...makeSettings(), main_branch: 'main', checks: null }
    render(<CollaborationSummary onNavigate={vi.fn()} />)
    expect(row('token')).toHaveTextContent('1,200 of 5,000 used')
    expect(row('token').querySelector('[data-flag="true"]')).toBeNull()
    expect(row('branch')).toHaveTextContent('main')
    expect(row('branch').querySelector('[data-flag="true"]')).toBeNull()
    expect(row('checks')).toHaveTextContent('None')
  })

  it('flags an exhausted token budget', () => {
    budget = { limit_tokens: 5000, used_tokens: 5100, remaining_tokens: 0, exhausted: true }
    render(<CollaborationSummary onNavigate={vi.fn()} />)
    expect(row('token').querySelector('[data-flag="true"]')).not.toBeNull()
  })

  it('switches agents may start flows by sending that one field (FR-2)', () => {
    settings = { ...makeSettings(), hop_budget: 9 }
    render(<CollaborationSummary onNavigate={vi.fn()} />)
    fireEvent.click(within(row('flows')).getByRole('switch'))
    expect(mutate).toHaveBeenCalledTimes(1)
    expect(mutate.mock.calls[0][0]).toEqual({ allow_agent_jobs: true })
  })

  it('shows a refused save and keeps showing the stored value', () => {
    // The shape `fetchWithAuth` raises: the route's own JSON body as the message.
    updateError = new ApiError(422, JSON.stringify({ detail: 'The Hub refused it' }))
    render(<CollaborationSummary onNavigate={vi.fn()} />)
    expect(screen.getByRole('alert')).toHaveTextContent('The Hub refused it')
    expect(within(row('flows')).getByRole('switch')).toHaveAttribute('aria-checked', 'false')
  })

  it('says how many agents the hop budget is holding (FR-3)', () => {
    queueStatuses = [
      { agent: 'alpha', waiting_count: 0, running: false, waiting_reason: null },
      { agent: 'beta', waiting_count: 3, running: false, waiting_reason: 'hop budget exhausted' },
    ]
    render(<CollaborationSummary onNavigate={vi.fn()} />)
    expect(row('hop')).toHaveTextContent('1 agent held')
    expect(row('hop').querySelector('[data-flag="true"]')).not.toBeNull()
  })

  it('links each value to where it is edited', () => {
    const onNavigate = vi.fn()
    render(<CollaborationSummary onNavigate={onNavigate} />)
    fireEvent.click(row('token'))
    expect(onNavigate).toHaveBeenLastCalledWith('budgets')
    fireEvent.click(row('branch'))
    expect(onNavigate).toHaveBeenLastCalledWith('settings')
    fireEvent.click(row('hop'))
    expect(onNavigate).toHaveBeenLastCalledWith('settings')
  })

  // A failed read is said, never shown as a value (n11's MISREPORT shape; CI's surface ratchet).
  it('says the settings could not be read instead of vanishing', () => {
    settingsError = new ApiError(500, JSON.stringify({ detail: 'database is locked' }))
    render(<CollaborationSummary onNavigate={vi.fn()} />)
    expect(screen.getByRole('alert')).toHaveTextContent(/settings could not be read.*database is locked/i)
  })

  it('does not read zero agents or zero held when the agent list failed', () => {
    agentsError = new Error('boom')
    render(<CollaborationSummary onNavigate={vi.fn()} />)
    expect(row('limits')).not.toHaveTextContent('0 of 8 agents')
    expect(row('limits')).toHaveTextContent(/agents could not be read/i)
    expect(row('hop')).toHaveTextContent(/queues could not be read/i)
  })

  it('does not read No limit when the budget could not be read', () => {
    accountingError = new Error('boom')
    render(<CollaborationSummary onNavigate={vi.fn()} />)
    expect(row('token')).not.toHaveTextContent('No limit')
    expect(row('token')).toHaveTextContent(/usage could not be read/i)
  })
})
