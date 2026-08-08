import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import type { AgentSummary } from '@/api/agents'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

const postureMutate = vi.fn()
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
    useUpdateAgentPermissionDefault: () => ({
      mutate: postureMutate,
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

function renderExecution(summary: AgentSummary) {
  roster = [summary]
  return render(<AgentSettingsPage agent={summary.name} section="execution" />)
}

const control = () => screen.getByLabelText('Default permissions for codex-1')

vi.mock('@/api/workspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/workspace')>()
  return { ...actual, useAgentWorkspace: () => ({ data: undefined, isLoading: true, error: null }) }
})

describe('an agent has a default permission posture', () => {
  beforeEach(() => postureMutate.mockClear())

  it('offers the same postures the composer does, with the same labels', () => {
    // Not a second vocabulary for the same choice: an operator picking "Ask me" in the composer
    // and "Ask me" here must be choosing the same thing.
    renderExecution(agent())
    const labels = [...control().querySelectorAll('option')].map((o) => o.textContent)
    expect(labels).toEqual([
      'Built-in default (Edit files)',
      'Edit files',
      'Workspace only',
      'Ask me',
      'Full access',
    ])
  })

  it('sits at the built-in default until one is chosen', () => {
    // Not pre-selected to today's default, for the same reason the waiting settings are not: a
    // stored copy would keep saying it after the default moved.
    renderExecution(agent())
    expect(control()).toHaveValue('')
  })

  it('shows what is stored', () => {
    renderExecution(agent({ default_permission_mode: 'manual' }))
    expect(control()).toHaveValue('manual')
  })

  it('saves a chosen posture', () => {
    renderExecution(agent())
    fireEvent.change(control(), { target: { value: 'bypassPermissions' } })
    expect(postureMutate).toHaveBeenCalledWith({ agent: 'codex-1', mode: 'bypassPermissions' })
  })

  it('clears back to the built-in default rather than sending a blank', () => {
    renderExecution(agent({ default_permission_mode: 'manual' }))
    fireEvent.change(control(), { target: { value: '' } })
    expect(postureMutate).toHaveBeenCalledWith({ agent: 'codex-1', mode: null })
  })

  it('is offered for an agent with no runner bound', () => {
    // The postures come from the catalog's union, not from the agent's provider — an agent may
    // have none, and rebinding one must not invalidate a default already chosen.
    renderExecution(agent({ runner_id: null }))
    expect(control()).toBeInTheDocument()
  })

  it('lives under Execution, not in any other section', () => {
    const execution = renderExecution(agent())
    expect(control()).toBeInTheDocument()
    execution.unmount()

    for (const section of ['identity', 'charter', 'interaction', 'workspace'] as const) {
      const { unmount } = render(<AgentSettingsPage agent="codex-1" section={section} />)
      expect(screen.queryByLabelText('Default permissions for codex-1')).not.toBeInTheDocument()
      unmount()
    }
  })
})
