import { describe, it, expect, vi, afterEach } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { Task } from '@/api/tasks'
import { OverviewPage } from '@/components/overview/OverviewPage'
import { TasksBoard } from '@/components/tasks/TasksBoard'

/**
 * F202: the Overview read `tasks.length` off a page the Hub had cut at `limit=100`, so a project
 * with 241 tasks was told it had 100 — a wrong number presented as a fact, pinned at the page size
 * however much the project grew. And because the ledger is ordered oldest-first, the rows the page
 * dropped were the *newest*: a task created seconds earlier was not on the board and nothing said
 * so.
 *
 * Both halves are asserted against a page that is genuinely cut (`has_more: true`, `total` well
 * above the rows), which is the state no fixture had before this test existed.
 */

const ROWS: Task[] = Array.from({ length: 3 }, (_, i) => ({
  id: `task-${i}`,
  project_id: 'proj-1',
  title: `Task ${i}`,
  description: '',
  status: 'pending',
  priority: 'medium',
  assignee: 'worker',
  created_at: '2026-09-22T10:00:00Z',
  updated: '2026-09-22T10:00:00Z',
})) as unknown as Task[]

const CUT_PAGE = { tasks: ROWS, total: 241, has_more: true }
const WHOLE_PAGE = { tasks: ROWS, total: ROWS.length, has_more: false }

let page: { tasks: Task[]; total: number; has_more: boolean } = CUT_PAGE

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'worker' }], isLoading: false }),
}))
vi.mock('@/api/questions', () => ({ useQuestions: () => ({ data: [] }) }))
vi.mock('@/api/status', () => ({ useStatus: () => ({ data: { project_name: 'AgentWeave' } }) }))
vi.mock('@/hooks/useSSE', () => ({ getBufferedEvents: () => [] }))
vi.mock('@/components/overview/OverviewBudgetSummary', () => ({
  OverviewBudgetSummary: () => null,
}))
vi.mock('@/api/spec', () => ({
  useSpecDocuments: () => ({ data: { documents: [] } }),
}))
vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useTasks: () => ({ data: page, isLoading: false, isError: false }),
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useUpdateTask: () => ({ mutate: vi.fn(), isPending: false }),
    useSetDivergenceHandling: () => ({ mutate: vi.fn() }),
    useStartWorkOnTask: () => ({ mutate: vi.fn() }),
  }
})

afterEach(() => {
  page = CUT_PAGE
  cleanup()
})

function board() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TasksBoard />
    </QueryClientProvider>,
  )
}

describe('the task count the Overview shows', () => {
  it("is the ledger's own total, not the length of the page it was handed", () => {
    const { container } = render(<OverviewPage onNavigate={vi.fn()} />)
    const text = container.textContent ?? ''

    expect(text).toContain('241 task')
    // The page it rendered holds 3 rows. Before F202 that number was the count on the screen.
    expect(text).not.toContain('3 tasks')
  })

  it('carries the same total into the card that navigates to the board', () => {
    render(<OverviewPage onNavigate={vi.fn()} />)
    expect(screen.getByText('241 total')).toBeTruthy()
  })
})

describe('the board, when the ledger is longer than one page', () => {
  it('says how many it is showing and of how many, rather than rendering a silent prefix', () => {
    board()
    const banner = screen.getByTestId('tasks-truncated-banner')
    expect(banner.textContent).toContain('241')
    expect(banner.textContent).toContain('oldest')
  })

  it('says nothing when the page is the whole ledger', () => {
    page = WHOLE_PAGE
    board()
    expect(screen.queryByTestId('tasks-truncated-banner')).toBeNull()
  })
})
