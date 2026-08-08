import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import type { AgentSummary } from '@/api/agents'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

const thresholdMutate = vi.fn()
const modeMutate = vi.fn()
const grantMutate = vi.fn()
let roster: AgentSummary[] = []

vi.mock('@/api/runners', () => ({
  useRunners: () => ({ data: [], isLoading: false }),
  useBindAgentRunner: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useUpdateAgentWaiting: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  MIN_WAITING_SECONDS: 10,
  MAX_WAITING_SECONDS: 600,
}))

vi.mock('@/api/charters', () => ({
  useCharters: () => ({ data: [], isLoading: false }),
  useBindAgentCharter: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

vi.mock('@/api/workspace', () => ({
  useAgentWorkspace: () => ({ data: undefined, isLoading: false }),
}))

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE, isLoading: false }) }
})

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentSessions: () => ({ data: { sessions: [] }, isLoading: false }),
    useAgents: () => ({ data: roster, isLoading: false }),
    useArchiveAgent: () => ({ mutate: vi.fn(), isPending: false, error: null }),
    useUpdateAgentDescription: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useUpdateAgentPermissionDefault: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useUpdateAgentCheckpointOverride: () => ({
      mutate: thresholdMutate, isPending: false, isError: false,
    }),
    useUpdateAgentCheckpointMode: () => ({ mutate: modeMutate, isPending: false, isError: false }),
    useUpdateAgentGrant: () => ({ mutate: grantMutate, isPending: false, isError: false }),
  }
})

function agent(overrides: Partial<AgentSummary> = {}): AgentSummary {
  return {
    name: 'claude-1',
    status: 'idle',
    message_count: 0,
    active_task_count: 0,
    runner: 'claude',
    ...overrides,
  } as AgentSummary
}

describe('per-agent checkpoint policy', () => {
  beforeEach(() => {
    thresholdMutate.mockReset()
    modeMutate.mockReset()
    grantMutate.mockReset()
    roster = [agent()]
  })

  it('inherits the project by default rather than showing a value nobody set', () => {
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    expect(screen.getByLabelText('Automatic checkpointing for claude-1')).toHaveValue('')
    expect(screen.getByLabelText('Checkpoint threshold for claude-1')).toHaveValue(null)
  })

  it('submits a token threshold in canonical units, entered in thousands', () => {
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    fireEvent.change(screen.getByLabelText('Threshold unit for claude-1'), {
      target: { value: 'tokens' },
    })
    const input = screen.getByLabelText('Checkpoint threshold for claude-1')
    fireEvent.change(input, { target: { value: '120' } })
    fireEvent.blur(input)

    expect(thresholdMutate).toHaveBeenCalledWith({
      agent: 'claude-1', mode: 'tokens', value: 120_000, notes: null,
    })
  })

  it('clears the whole override when the value is emptied, never half of it', () => {
    // An override that kept its mode while losing its value would be a number in a unit nobody
    // chose — the Hub refuses it, and the control must not be able to ask.
    roster = [agent({ checkpoint_threshold_mode: 'percent', checkpoint_threshold_value: 60 })]
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    const input = screen.getByLabelText('Checkpoint threshold for claude-1')
    fireEvent.change(input, { target: { value: '' } })
    fireEvent.blur(input)

    expect(thresholdMutate).toHaveBeenCalledWith(
      expect.objectContaining({ value: null, notes: null }),
    )
  })

  it('lets an agent opt out while still inheriting the threshold', () => {
    render(<AgentSettingsPage agent="claude-1" section="context" />)
    fireEvent.change(screen.getByLabelText('Automatic checkpointing for claude-1'), {
      target: { value: 'off' },
    })
    expect(modeMutate).toHaveBeenCalledWith({ agent: 'claude-1', mode: 'off' })
    // Turning it off says nothing about the threshold, so nothing was submitted for it.
    expect(thresholdMutate).not.toHaveBeenCalled()
  })
})

describe('per-agent access grants', () => {
  beforeEach(() => {
    grantMutate.mockReset()
    roster = [agent()]
  })

  it('shows both grants closed by default', () => {
    render(<AgentSettingsPage agent="claude-1" section="access" />)
    expect(screen.getByLabelText(/Read other agents’ checkpoints for claude-1/)).not.toBeChecked()
    expect(screen.getByLabelText(/Recall the observations behind them for claude-1/)).not.toBeChecked()
  })

  it('grants each one separately', () => {
    // The whole reason there are two: a peer allowed to see what was concluded is not thereby
    // allowed to read everything that agent's tools ever printed.
    render(<AgentSettingsPage agent="claude-1" section="access" />)
    fireEvent.click(screen.getByLabelText(/Read other agents’ checkpoints for claude-1/))

    expect(grantMutate).toHaveBeenCalledWith({
      agent: 'claude-1', grant: 'can_read_checkpoints', enabled: true,
    })
    expect(grantMutate).toHaveBeenCalledTimes(1)
  })

  it('reflects a grant that is already open', () => {
    roster = [agent({ can_read_checkpoints: true })]
    render(<AgentSettingsPage agent="claude-1" section="access" />)
    expect(screen.getByLabelText(/Read other agents’ checkpoints for claude-1/)).toBeChecked()
    expect(screen.getByLabelText(/Recall the observations behind them for claude-1/)).not.toBeChecked()
  })
})
