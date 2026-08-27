import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WorktreesPanel } from '@/components/environment/WorktreesPanel'
import type { WorkspaceInfo } from '@/api/workspace'

let worktrees: WorkspaceInfo[] | undefined
let loading = false
let error: unknown = null

vi.mock('@/api/workspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/workspace')>()
  return { ...actual, useWorktrees: () => ({ data: worktrees, isLoading: loading, error }) }
})

function renderPanel(data: WorkspaceInfo[] | undefined, options: { loading?: boolean; error?: unknown } = {}) {
  worktrees = data
  loading = options.loading ?? false
  error = options.error ?? null
  return render(<WorktreesPanel />)
}

const AGENT: WorkspaceInfo = {
  kind: 'agent',
  name: 'codex-1',
  branch: 'agentweave/codex-1',
  path: '/repo/.agentweave/worktrees/codex-1',
}

const TASK: WorkspaceInfo = {
  kind: 'task',
  name: 'task-aa11bb22cc33',
  branch: 'agentweave/task/task-aa11bb22cc33',
  path: '/repo/.agentweave/tasks/task-aa11bb22cc33',
}

/**
 * Task 6.4b. This panel was a hard-coded `EmptyState` that called no API, so it said "No worktree
 * activity" whether the project had none or a dozen — a claim that got worse once tasks started
 * taking checkouts of their own.
 */
describe('the project’s worktrees panel', () => {
  beforeEach(() => {
    worktrees = undefined
    loading = false
    error = null
  })

  it('lists both kinds of checkout, under headings that say what each is', () => {
    renderPanel([AGENT, TASK])

    expect(screen.getByText('Agent checkouts')).toBeInTheDocument()
    expect(screen.getByText('Task checkouts')).toBeInTheDocument()
    expect(screen.getByTestId('worktree-codex-1')).toHaveTextContent('agentweave/codex-1')
    expect(screen.getByTestId('worktree-task-aa11bb22cc33')).toHaveTextContent(
      '/repo/.agentweave/tasks/task-aa11bb22cc33',
    )
  })

  it('does not claim there is no activity while checkouts exist', () => {
    // The exact defect: the stub rendered this string unconditionally.
    renderPanel([TASK])
    expect(screen.queryByText('No worktree activity')).not.toBeInTheDocument()
  })

  it('omits a heading whose group is empty rather than showing an empty one', () => {
    renderPanel([TASK])
    expect(screen.queryByText('Agent checkouts')).not.toBeInTheDocument()
    expect(screen.getByText('Task checkouts')).toBeInTheDocument()
  })

  it('still shows a checkout of a kind it does not recognise', () => {
    // A checkout that exists and is not listed is the failure being fixed, so an unknown kind is
    // grouped rather than dropped.
    renderPanel([{ kind: 'future', name: 'something', branch: 'agentweave/x', path: '/repo/x' }])
    expect(screen.getByTestId('worktree-something')).toBeInTheDocument()
  })

  it('says the project is empty only when the Hub said so', () => {
    renderPanel([])
    expect(screen.getByText('No worktree activity')).toBeInTheDocument()
  })

  it('reports a failed read as a failure, not as an empty project', () => {
    // The distinction the stub could not draw: "nothing here" and "I could not find out" are
    // different answers, and only one of them means the operator should go looking.
    renderPanel(undefined, { error: new Error('boom') })
    expect(screen.getByRole('alert')).toHaveTextContent('Could not read')
    expect(screen.queryByText('No worktree activity')).not.toBeInTheDocument()
  })

  it('says it is loading rather than rendering an empty project', () => {
    renderPanel(undefined, { loading: true })
    expect(screen.getByLabelText('Loading worktrees')).toBeInTheDocument()
    expect(screen.queryByText('No worktree activity')).not.toBeInTheDocument()
  })
})
