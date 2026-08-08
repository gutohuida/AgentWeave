import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import type { AgentSummary } from '@/api/agents'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

const describeMutate = vi.fn()
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

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentSessions: () => ({ data: { sessions: [] }, isLoading: false }),
    useUpdateAgentPermissionDefault: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useAgents: () => ({ data: roster, isLoading: false }),
    useArchiveAgent: () => ({ mutate: vi.fn(), isPending: false, error: null }),
    useUpdateAgentDescription: () => ({
      mutate: describeMutate,
      isPending: false,
      isError: false,
    }),
  }
})

function agent(overrides: Partial<AgentSummary> = {}): AgentSummary {
  return {
    name: 'codex-1',
    status: 'idle',
    message_count: 0,
    active_task_count: 0,
    lifecycle: 'open',
    ...overrides,
  }
}

function renderIdentity(summary: AgentSummary) {
  roster = [summary]
  return render(<AgentSettingsPage agent={summary.name} section="identity" />)
}

const field = () => screen.getByLabelText('Description for codex-1')

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE, isLoading: false }) }
})

vi.mock('@/api/workspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/workspace')>()
  return { ...actual, useAgentWorkspace: () => ({ data: undefined, isLoading: true, error: null }) }
})

describe('what an agent is for', () => {
  beforeEach(() => describeMutate.mockClear())

  it('is empty until written, and says what it is for', () => {
    renderIdentity(agent())
    expect(field()).toHaveValue('')
    expect(field()).toHaveAttribute('placeholder', 'What this agent is for.')
  })

  it('shows what is stored', () => {
    renderIdentity(agent({ description: 'Reviews migrations before they ship.' }))
    expect(field()).toHaveValue('Reviews migrations before they ship.')
  })

  it('saves on blur, not on every keystroke', () => {
    // A mutation per keystroke would write the sentence one character at a time — the same
    // reason `WaitingSetting` commits on blur.
    renderIdentity(agent())
    fireEvent.change(field(), { target: { value: 'Rev' } })
    fireEvent.change(field(), { target: { value: 'Reviews migrations.' } })
    expect(describeMutate).not.toHaveBeenCalled()

    fireEvent.blur(field())
    expect(describeMutate).toHaveBeenCalledWith({
      agent: 'codex-1',
      description: 'Reviews migrations.',
    })
  })

  it('clears to null rather than saving a blank', () => {
    // "" and "no description" are the same state; storing both would make every reader test for
    // both. The API normalizes it too — this is the client half of the same rule.
    renderIdentity(agent({ description: 'Reviews migrations.' }))
    fireEvent.change(field(), { target: { value: '   ' } })
    fireEvent.blur(field())
    expect(describeMutate).toHaveBeenCalledWith({ agent: 'codex-1', description: null })
  })

  it('does not save a value that has not changed', () => {
    renderIdentity(agent({ description: 'Reviews migrations.' }))
    fireEvent.blur(field())
    expect(describeMutate).not.toHaveBeenCalled()
  })

  it('lives under Identity, not in any other section', () => {
    // A section is a claim about what the operator came to do. "What this agent is for" is who it
    // is, not what it runs as.
    const identity = renderIdentity(agent())
    expect(field()).toBeInTheDocument()
    identity.unmount()

    for (const section of ['execution', 'charter', 'interaction', 'workspace'] as const) {
      const { unmount } = render(<AgentSettingsPage agent="codex-1" section={section} />)
      expect(screen.queryByLabelText('Description for codex-1')).not.toBeInTheDocument()
      unmount()
    }
  })
})
