import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import type { AgentSummary } from '@/api/agents'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'
import { chooseMenuOption, menuSelect, openMenuSelect } from './support/menuSelect'

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
    useAgentLaunchability: () => ({ data: undefined }),
    useAgents: () => ({ data: roster, isLoading: false }),
    useArchiveAgent: () => ({ mutate: vi.fn(), isPending: false, error: null }),
    useUpdateAgentDescription: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useUpdateAgentReachGrants: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
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
  return render(<AgentSettingsPage agent={summary.name} section="execution" onSelectSection={vi.fn()} onBack={vi.fn()} />)
}

const control = () => menuSelect('Default permissions for codex-1')
const choices = async (user: ReturnType<typeof userEvent.setup>) =>
  (await openMenuSelect(user, 'Default permissions for codex-1')).map((o) => o.querySelector('.block')?.textContent)

vi.mock('@/api/workspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/workspace')>()
  return { ...actual, useAgentWorkspace: () => ({ data: undefined, isLoading: true, error: null }) }
})

describe('an agent has a default permission posture', () => {
  beforeEach(() => postureMutate.mockClear())

  it('offers the same postures the composer does, with the same labels', async () => {
    // Not a second vocabulary for the same choice: an operator picking "Ask me" in the composer
    // and "Ask me" here must be choosing the same thing.
    const user = userEvent.setup()
    renderExecution(agent())
    expect(await choices(user)).toEqual([
      'Built-in default (depends on the runner)',
      'Edit files',
      'Workspace only',
      'Ask me',
      'Full access',
    ])
  })

  it('names the built-in default the run would get (F283)', async () => {
    const user = userEvent.setup()
    renderExecution(agent({ runner_id: 'runner-1', permission_mode_built_in: 'workspace' }))
    expect((await choices(user))[0]).toBe('Built-in default (Workspace only)')
  })

  it('names what clearing gives, not the Full access this agent has now', async () => {
    // Choosing Full access sets the autonomy flag and clearing clears it, so the blank option is
    // the posture without it (design D3, operator review).
    const user = userEvent.setup()
    renderExecution(
      agent({
        runner_id: 'runner-1',
        default_permission_mode: 'bypassPermissions',
        permission_mode_at_rest: 'bypassPermissions',
        permission_mode_built_in: 'workspace',
      }),
    )
    expect(control()).toHaveTextContent('Full access')
    expect((await choices(user))[0]).toBe('Built-in default (Workspace only)')
  })

  it('sits at the built-in default until one is chosen', () => {
    // Not pre-selected to today's default, for the same reason the waiting settings are not: a
    // stored copy would keep saying it after the default moved.
    renderExecution(agent())
    expect(control()).toHaveTextContent('Built-in default (depends on the runner)')
  })

  it('shows what is stored', () => {
    renderExecution(agent({ default_permission_mode: 'manual' }))
    expect(control()).toHaveTextContent('Ask me')
  })

  it('says Claude Code still runs read-only commands without asking under Ask me (F453)', () => {
    renderExecution(agent({ default_permission_mode: 'manual', runner: 'claude' }))
    expect(screen.getByText(/Claude Code still runs commands it treats as read-only/)).toBeInTheDocument()
  })

  it('says nothing of it for another posture', () => {
    renderExecution(agent({ default_permission_mode: 'acceptEdits', runner: 'claude' }))
    expect(screen.queryByText(/treats as read-only/)).toBeNull()
  })

  it('saves a chosen posture', async () => {
    const user = userEvent.setup()
    renderExecution(agent())
    await chooseMenuOption(user, 'Default permissions for codex-1', /^Full access/)
    expect(postureMutate).toHaveBeenCalledWith({ agent: 'codex-1', mode: 'bypassPermissions' }, expect.anything())
  })

  it('clears back to the built-in default rather than sending a blank', async () => {
    const user = userEvent.setup()
    renderExecution(agent({ default_permission_mode: 'manual' }))
    await chooseMenuOption(user, 'Default permissions for codex-1', /^Built-in default/)
    expect(postureMutate).toHaveBeenCalledWith({ agent: 'codex-1', mode: null }, expect.anything())
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
      const { unmount } = render(<AgentSettingsPage agent="codex-1" section={section} onSelectSection={vi.fn()} onBack={vi.fn()} />)
      expect(screen.queryByRole('button', { name: 'Default permissions for codex-1' })).not.toBeInTheDocument()
      unmount()
    }
  })
})
