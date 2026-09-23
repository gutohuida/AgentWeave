import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WorktreesPanel } from '@/components/environment/WorktreesPanel'
import type { WorkspaceInfo, WorktreeConflict, WorktreeListing } from '@/api/workspace'

let worktrees: WorktreeListing | undefined
let loading = false
let error: unknown = null
let conflicts: WorktreeConflict[] | undefined = []
let conflictsError: unknown = null

vi.mock('@/api/workspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/workspace')>()
  return {
    ...actual,
    useWorktrees: () => ({ data: worktrees, isLoading: loading, error }),
    useWorktreeConflicts: () => ({
      data: conflicts === undefined ? undefined : { repository: true, conflicts },
      error: conflictsError,
    }),
  }
})

function renderPanel(
  data: WorkspaceInfo[] | undefined,
  options: {
    loading?: boolean
    error?: unknown
    conflicts?: WorktreeConflict[] | undefined
    conflictsError?: unknown
  } = {},
) {
  // The route's envelope (F249) around the checkouts each test names.
  worktrees = data === undefined ? undefined : { repository: true, unavailable_reason: null, worktrees: data }
  loading = options.loading ?? false
  error = options.error ?? null
  conflicts = 'conflicts' in options ? options.conflicts : []
  conflictsError = options.conflictsError ?? null
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

/**
 * F241. `GET /worktrees/conflicts` computed which branches would not merge, and no screen read it.
 * The fixture is the route's shape: `detect_conflicts` reports each branch against main first,
 * then the pairs among the workspaces.
 */
describe('the worktrees panel reports conflicts (F241)', () => {
  const CONFLICTS: WorktreeConflict[] = [
    {
      workspaces: [
        { kind: 'main', name: 'main', branch: 'main' },
        { kind: 'task', name: 'task-aa11bb22cc33', branch: 'agentweave/task/task-aa11bb22cc33' },
      ],
      paths: ['README.md'],
    },
    {
      workspaces: [
        { kind: 'agent', name: 'codex-1', branch: 'agentweave/codex-1' },
        { kind: 'task', name: 'task-aa11bb22cc33', branch: 'agentweave/task/task-aa11bb22cc33' },
      ],
      paths: ['calc.py', 'tests/test_calc.py'],
    },
  ]

  it('names both sides of each conflict and the files it is on', () => {
    renderPanel([AGENT, TASK], { conflicts: CONFLICTS })

    const block = screen.getByTestId('worktree-conflicts')
    expect(block).toHaveTextContent('2 conflicts')
    expect(block).toHaveTextContent('agent codex-1 and task task-aa11bb22cc33')
    expect(block).toHaveTextContent('the main branch (main) and task task-aa11bb22cc33')
    expect(block).toHaveTextContent('calc.py')
    expect(block).toHaveTextContent('tests/test_calc.py')
    expect(block).toHaveTextContent('README.md')
  })

  it('says there are none when the Hub found none', () => {
    renderPanel([AGENT, TASK], { conflicts: [] })

    expect(screen.getByTestId('worktree-conflicts-none')).toBeInTheDocument()
    expect(screen.queryByTestId('worktree-conflicts')).not.toBeInTheDocument()
  })

  it('does not call a failed check clean', () => {
    renderPanel([AGENT, TASK], { conflicts: undefined, conflictsError: new Error('boom') })

    expect(screen.getByRole('alert')).toHaveTextContent('Could not check these checkouts for conflicts.')
    expect(screen.queryByTestId('worktree-conflicts-none')).not.toBeInTheDocument()
  })

  it("reports a retained branch's conflict even with no checkout listed", () => {
    renderPanel([], { conflicts: [CONFLICTS[0]] })

    expect(screen.getByTestId('worktree-conflicts')).toHaveTextContent('1 conflict')
  })

  it('adds no conflict line to an empty project', () => {
    renderPanel([], { conflicts: [] })

    expect(screen.queryByTestId('worktree-conflicts-none')).not.toBeInTheDocument()
  })

  it('says nothing about conflicts while the check is still running', () => {
    renderPanel([AGENT, TASK], { conflicts: undefined })

    expect(screen.queryByTestId('worktree-conflicts-none')).not.toBeInTheDocument()
    expect(screen.queryByTestId('worktree-conflicts')).not.toBeInTheDocument()
  })
})

describe('the worktrees panel in a project that is not a repository (F249)', () => {
  it("says so in the Hub's words, and promises no checkouts", () => {
    worktrees = {
      repository: false,
      unavailable_reason: '/p is not a git repository, so agents here work in the project directory and no isolated checkout is made. Running `git init` there would give each writing agent its own.',
      worktrees: [],
    }
    loading = false
    error = null
    conflicts = []
    render(<WorktreesPanel />)

    expect(screen.getByTestId('worktrees-not-a-repository')).toHaveTextContent('/p is not a git repository')
    expect(screen.queryByText(/appear here when an agent starts work/)).not.toBeInTheDocument()
    expect(screen.queryByTestId('worktree-conflicts-none')).not.toBeInTheDocument()
  })
})
