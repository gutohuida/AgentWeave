import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Task, TaskIntegrationPreview } from '@/api/tasks'
import { TaskDetailDrawer } from '@/components/tasks/TaskDetailDrawer'

/**
 * F9 — approving writes to the operator's repository, and the drawer says so first.
 *
 * Not a defect: the integration design is careful and held under test on 2026-08-23 (merge a
 * commit and never a branch, never into a branch nobody named, never push). What was missing is
 * that approving a card on a task board *is* a write to main, and nothing announced it on the
 * successful path — only the refusal path ever explained itself.
 *
 * Deliberately an inline note and not a confirmation dialog: the behaviour is correct and a modal
 * would train the operator to dismiss it.
 */

let preview: { data?: TaskIntegrationPreview } = { data: undefined }
let transitions: Record<string, string[]> = {}

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions } }),
    useUpdateTask: () => ({ mutate: vi.fn() }),
    useSetDivergenceHandling: () => ({ mutate: vi.fn() }),
    useTaskIntegrationPreview: () => preview,
  }
})

vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: [] }) }))
vi.mock('@/api/spec', () => ({ useSpecDocuments: () => ({ data: { documents: [] } }) }))

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    project_id: 'proj-test',
    title: 'Balance the ledger',
    status: 'under_review',
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    ...overrides,
  }
}

function renderDrawer(task: Task) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TaskDetailDrawer task={task} onClose={() => {}} />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  preview = { data: undefined }
  transitions = {}
})

describe('the approve control states what approving writes (F9)', () => {
  it('names the commit, the branch it came from, and the branch it goes into', () => {
    transitions = { under_review: ['approved', 'revision_needed'] }
    preview = {
      data: {
        task_id: 'task-1',
        main_branch: 'master',
        targets: [{ commit_sha: 'cecbc88751eaff', source_branch: 'agentweave/builder' }],
        will_merge: true,
        reason: '',
      },
    }
    renderDrawer(makeTask())

    const note = screen.getByTestId('task-approval-writes-task-1')
    expect(note).toHaveTextContent('Approving writes to your repository')
    // Twelve characters, matching what `task_integration` puts in its own commit message.
    expect(note).toHaveTextContent('cecbc88751ea')
    expect(note).toHaveTextContent('from agentweave/builder')
    expect(note).toHaveTextContent('into master')
  })

  it('says plainly when approving will merge nothing, and why', () => {
    transitions = { under_review: ['approved'] }
    preview = {
      data: {
        task_id: 'task-1',
        main_branch: 'master',
        targets: [],
        will_merge: false,
        reason: 'no accepted evidence names a commit, so there is nothing to merge',
      },
    }
    renderDrawer(makeTask())

    const note = screen.getByTestId('task-approval-writes-task-1')
    expect(note).toHaveTextContent('will not merge anything')
    expect(note).toHaveTextContent('no accepted evidence names a commit')
    // No repository changes, so no warning weight.
    expect(note.getAttribute('style')).not.toContain('--amber')
  })

  it('is absent where approval is not a move the operator can make from here', () => {
    transitions = { pending: ['assigned'] }
    preview = {
      data: {
        task_id: 'task-1',
        main_branch: 'master',
        targets: [{ commit_sha: 'cecbc88751ea', source_branch: 'agentweave/builder' }],
        will_merge: true,
        reason: '',
      },
    }
    renderDrawer(makeTask({ status: 'pending' }))
    expect(screen.queryByTestId('task-approval-writes-task-1')).toBeNull()
  })

  it('renders nothing until the preview has arrived, rather than guessing', () => {
    transitions = { under_review: ['approved'] }
    renderDrawer(makeTask())
    expect(screen.queryByTestId('task-approval-writes-task-1')).toBeNull()
  })
})
