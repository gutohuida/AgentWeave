import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ApprovalReportEntry, Task } from '@/api/tasks'
import { TaskCardHost } from './testUtils/TaskCardHost'

// F169: the approval advisory arrives on the approving response and nowhere else, and no screen
// read it. F315: "Mark waiting" said nothing for the seconds its write and refetch took, and a
// second press wrote the move again.

const OPERATOR_TRANSITIONS: Record<string, string[]> = {
  in_progress: ['assigned', 'blocked', 'completed', 'rejected'],
  completed: ['rejected', 'under_review'],
  under_review: ['approved', 'rejected', 'revision_needed'],
}

const land = vi.fn()
const update = vi.fn()
let updatePending = false

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useAllowedTransitions: () => ({
      data: { actor_kind: 'operator', transitions: OPERATOR_TRANSITIONS },
    }),
    useUpdateTask: () => ({ mutate: update, isPending: updatePending }),
    useLandTask: () => ({ mutate: land, isPending: false }),
    useTaskIntegrationPreview: () => ({ data: null }),
  }
})

function makeTask(status: string, overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    project_id: 'proj-test',
    title: 'A task',
    status,
    assignee: 'builder',
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    ...overrides,
  }
}

async function openDrawer(task: Task) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TaskCardHost task={task} />
    </QueryClientProvider>,
  )
  const user = userEvent.setup()
  await user.click(screen.getByTestId(`task-open-${task.id}`))
  return user
}

// The two kinds `requirement_gate` builds, as the route sends them.
const REPORT: ApprovalReportEntry[] = [
  {
    kind: 'requirement',
    identifier: 'FR-3',
    requirement_id: 'req-3',
    state: 'unverified',
    remedy: 'record evidence that it holds',
  },
  {
    kind: 'awaiting_evidence',
    evidence_id: 'ev-9',
    identifier: 'FR-4',
    commit_sha: 'cecbc88751ea0000',
    target_branch: 'master',
  },
]

beforeEach(() => {
  land.mockReset()
  update.mockReset()
  updatePending = false
})

describe('the approval advisory reaches the drawer that approved (F169)', () => {
  it('lists what the approval went through despite, after landing', async () => {
    land.mockImplementation((_vars: unknown, options: { onSuccess: (t: Task) => void }) => {
      options.onSuccess(makeTask('approved', { approval_report: REPORT }))
    })
    const user = await openDrawer(makeTask('completed'))
    await user.click(screen.getByTestId('task-land-task-1'))

    const report = screen.getByTestId('task-approval-report-task-1')
    expect(report).toHaveTextContent('Approved, with 2 things to know')
    expect(report).toHaveTextContent('FR-3 is unverified: record evidence that it holds.')
    expect(report).toHaveTextContent(
      'Evidence ev-9 for FR-4 is still awaiting review; its commit cecbc88751ea merges into master when it is accepted.',
    )
  })

  it('shows it after an approval from the status menu too', async () => {
    update.mockImplementation((_vars: unknown, options: { onSuccess: (t: Task) => void }) => {
      options.onSuccess(makeTask('approved', { approval_report: [REPORT[0]] }))
    })
    const user = await openDrawer(makeTask('under_review'))
    await user.click(screen.getByTestId('task-status-menu-task-1'))
    await user.click(screen.getByTestId('task-status-menu-task-1-approved'))

    expect(screen.getByTestId('task-approval-report-task-1')).toHaveTextContent('one thing to know')
  })

  it('shows nothing for an approval with nothing to report', async () => {
    land.mockImplementation((_vars: unknown, options: { onSuccess: (t: Task) => void }) => {
      options.onSuccess(makeTask('approved', { approval_report: [] }))
    })
    const user = await openDrawer(makeTask('completed'))
    await user.click(screen.getByTestId('task-land-task-1'))

    expect(screen.queryByTestId('task-approval-report-task-1')).toBeNull()
  })
})

describe('marking a task waiting acknowledges the press (F315)', () => {
  it('says it is working and refuses a second press while the write is in flight', async () => {
    const user = await openDrawer(makeTask('in_progress'))
    await user.click(screen.getByTestId('task-status-menu-task-1'))
    await user.click(screen.getByTestId('task-status-menu-task-1-blocked'))
    await user.type(screen.getByPlaceholderText('e.g. the staging API key'), 'the staging API key')

    updatePending = true
    // Re-render with the mutation pending, as React Query would after the first press.
    await user.type(screen.getByPlaceholderText('e.g. the staging API key'), ' ')

    const confirm = screen.getByTestId('task-block-confirm-task-1')
    expect(confirm).toBeDisabled()
    expect(confirm).toHaveTextContent('Marking waiting…')
  })
})
