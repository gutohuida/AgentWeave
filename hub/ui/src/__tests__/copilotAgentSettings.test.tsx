import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import type { AgentSummary } from '@/api/agents'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

// Group B (`a-copilot-agent-uses-hooks-and-its-own-agents`, test 1.14, B half): the review-agents
// control. The GitHub-server control (D half) is a separate group's task and is not covered here.

const reviewAgentsMutate = vi.fn()
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

vi.mock('@/api/workspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/workspace')>()
  return { ...actual, useAgentWorkspace: () => ({ data: undefined, isLoading: true, error: null }) }
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
    useUpdateAgentPermissionDefault: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useUpdateAgentReviewAgents: () => ({
      mutate: reviewAgentsMutate,
      isPending: false,
      isError: false,
    }),
  }
})

function agent(overrides: Partial<AgentSummary> = {}): AgentSummary {
  return {
    name: 'cp5',
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

const checkbox = (label: string) => screen.getByLabelText(`Consult ${label} for cp5`)

describe('a copilot agent has a review-agents setting', () => {
  beforeEach(() => reviewAgentsMutate.mockClear())

  it('is shown for a copilot-bound agent', () => {
    renderExecution(agent({ runner: 'copilot' }))
    expect(checkbox('code-review')).toBeInTheDocument()
    expect(checkbox('security-review')).toBeInTheDocument()
    expect(checkbox('rubber-duck')).toBeInTheDocument()
  })

  it('is not shown for a claude-bound agent', () => {
    renderExecution(agent({ runner: 'claude' }))
    expect(screen.queryByLabelText('Consult code-review for cp5')).not.toBeInTheDocument()
  })

  it('is not shown for a codex-bound agent', () => {
    renderExecution(agent({ runner: 'codex' }))
    expect(screen.queryByLabelText('Consult code-review for cp5')).not.toBeInTheDocument()
  })

  it('is not shown for an agent with no runner bound', () => {
    renderExecution(agent({ runner: undefined, runner_id: null }))
    expect(screen.queryByLabelText('Consult code-review for cp5')).not.toBeInTheDocument()
  })

  it('shows the value in the served agent config', () => {
    // A fixture with the setting on renders it on (design D8's read path).
    renderExecution(agent({ runner: 'copilot', config: { copilot_review_agents: ['code-review'] } }))
    expect(checkbox('code-review')).toBeChecked()
    expect(checkbox('security-review')).not.toBeChecked()
    expect(checkbox('rubber-duck')).not.toBeChecked()
  })

  it('renders every box unchecked with no stored config', () => {
    renderExecution(agent({ runner: 'copilot' }))
    expect(checkbox('code-review')).not.toBeChecked()
    expect(checkbox('security-review')).not.toBeChecked()
    expect(checkbox('rubber-duck')).not.toBeChecked()
  })

  it('adds an entry to the stored list on check', () => {
    renderExecution(agent({ runner: 'copilot', config: { copilot_review_agents: ['code-review'] } }))
    fireEvent.click(checkbox('security-review'))
    expect(reviewAgentsMutate).toHaveBeenCalledWith({
      agent: 'cp5',
      agents: ['code-review', 'security-review'],
    })
  })

  it('removes an entry from the stored list on uncheck', () => {
    renderExecution(
      agent({ runner: 'copilot', config: { copilot_review_agents: ['code-review', 'rubber-duck'] } }),
    )
    fireEvent.click(checkbox('code-review'))
    expect(reviewAgentsMutate).toHaveBeenCalledWith({ agent: 'cp5', agents: ['rubber-duck'] })
  })

  it('states that on a provider runner these agents may not run', () => {
    renderExecution(agent({ runner: 'copilot' }))
    expect(screen.getByText(/On a provider runner, Copilot's review agents may not run\./)).toBeInTheDocument()
  })

  it('lives under Execution, not in any other section', () => {
    const execution = renderExecution(agent({ runner: 'copilot' }))
    expect(checkbox('code-review')).toBeInTheDocument()
    execution.unmount()

    for (const section of ['identity', 'charter', 'interaction', 'workspace'] as const) {
      const { unmount } = render(<AgentSettingsPage agent="cp5" section={section} />)
      expect(screen.queryByLabelText('Consult code-review for cp5')).not.toBeInTheDocument()
      unmount()
    }
  })
})
