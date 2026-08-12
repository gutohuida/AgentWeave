import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import type { AgentSummary } from '@/api/agents'
import type { AgentWorkspaceInfo } from '@/api/workspace'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

let workspace: AgentWorkspaceInfo | undefined
let workspaceLoading = false
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
  return {
    ...actual,
    useAgentWorkspace: () => ({
      data: workspace,
      isLoading: workspaceLoading,
      error: null,
    }),
  }
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
  }
})

function info(overrides: Partial<AgentWorkspaceInfo> = {}): AgentWorkspaceInfo {
  return {
    agent: 'codex-1',
    repo_root: '/repo',
    working_dir: '/repo/.agentweave/worktrees/codex-1',
    isolated: true,
    branch: 'agentweave/codex-1',
    provisioned: true,
    ...overrides,
  }
}

function renderWorkspace(data: AgentWorkspaceInfo | undefined, loading = false) {
  workspace = data
  workspaceLoading = loading
  roster = [
    { name: 'codex-1', status: 'idle', message_count: 0, active_task_count: 0, lifecycle: 'open' },
  ]
  return render(<AgentSettingsPage agent="codex-1" section="workspace" />)
}

describe('where an agent works on disk', () => {
  beforeEach(() => {
    workspace = undefined
    workspaceLoading = false
  })

  it('shows the directory a turn runs in', () => {
    renderWorkspace(info())
    expect(screen.getByTestId('agent-working-dir')).toHaveTextContent(
      '/repo/.agentweave/worktrees/codex-1',
    )
  })

  it('says the checkout is the agent’s own, and names the branch', () => {
    // The branch is what makes isolation actionable: it is where the work has to be merged from.
    renderWorkspace(info())
    const worktree = screen.getByTestId('agent-worktree')
    expect(worktree).toHaveTextContent('Its own git worktree')
    expect(worktree).toHaveTextContent('agentweave/codex-1')
    expect(worktree).toHaveTextContent('checked out and ready')
  })

  it('says an unprovisioned worktree is coming rather than missing', () => {
    // Reading this page provisions nothing, so "not there yet" is the normal state for an agent
    // that has never run — presenting it as an absence would read as a fault.
    renderWorkspace(info({ provisioned: false }))
    expect(screen.getByTestId('agent-worktree')).toHaveTextContent(
      'created the first time this agent runs',
    )
  })

  it('says so plainly when the agent shares the project checkout', () => {
    renderWorkspace(info({ isolated: false, branch: null, working_dir: '/repo' }))
    const worktree = screen.getByTestId('agent-worktree')
    expect(worktree).toHaveTextContent('Shares the project checkout')
    expect(worktree).not.toHaveTextContent('agentweave/')
  })

  it('reports an absent repository as a note, not as an alert', () => {
    // This field once meant "your turns will be refused until you fix this". A writing agent in
    // a project with no repository now runs in the project directory, so nothing is failing and
    // nothing should be announced as failing — but it is still said, because it is the one thing
    // telling the operator `git init` would change something.
    renderWorkspace(
      info({
        isolated: false,
        provisioned: true,
        branch: null,
        working_dir: '/repo',
        unavailable_reason:
          '/repo is not a git repository, so there is no isolated checkout to give this agent.',
      }),
    )
    expect(screen.getByText(/not a git repository/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByTestId('agent-worktree')).toHaveTextContent('Shares the project checkout')
  })

  it('offers no control over isolation', () => {
    // Deliberate: flipping an agent with uncommitted work in its worktree to the shared checkout
    // would strand that work. It needs its own change, not a control added behind a read panel.
    renderWorkspace(info())
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/isolation for/i)).not.toBeInTheDocument()
  })

  it('says it is loading rather than rendering an empty workspace', () => {
    renderWorkspace(undefined, true)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })
})
