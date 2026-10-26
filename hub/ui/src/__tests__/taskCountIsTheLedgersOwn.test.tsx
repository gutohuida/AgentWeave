import { describe, it, expect, vi, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { Task } from '@/api/tasks'
import { OverviewScreen } from '@/components/overview/OverviewScreen'
import { TasksScreen } from '@/components/tasks/TasksScreen'

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
vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: [] }),
  useAnswerQuestion: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  return { ...actual, useProjectConversations: () => ({ data: { conversations: [] } }) }
})
vi.mock('@/api/ledger', () => ({ useProjectLedger: () => ({ data: undefined }) }))
vi.mock('@/api/queue', () => ({ useQueueStatuses: () => [] }))
vi.mock('@/api/stalls', () => ({ useOpenStalls: () => ({ data: [] }), useEndStall: () => ({ mutate: vi.fn() }) }))
vi.mock('@/api/flakyTests', () => ({ useFlakyTests: () => ({ data: null }), useHandleFlakyTests: () => ({ mutate: vi.fn() }) }))
vi.mock('@/api/accounting', () => ({ useAccounting: () => ({ data: undefined }) }))
// Not this test's subject; it reads hooks the mocks above do not provide.
vi.mock('@/components/overview/AgentPostureChips', () => ({ AgentPostureChips: () => null }))
vi.mock('@/api/spec', () => ({
  useSpecDocuments: () => ({ data: { documents: [] } }),
  useSpecCoverageMany: (paths: string[]) => paths.map(() => ({ data: undefined })),
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
    useRetryIntegration: () => ({ mutate: vi.fn() }),
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
      <TasksScreen />
    </QueryClientProvider>,
  )
}

describe('the task count the Overview shows', () => {
  it("is the ledger's own total, not the length of the page it was handed", () => {
    const { container } = render(<OverviewScreen onNavigate={vi.fn()} />)
    const text = container.textContent ?? ''

    expect(text).toContain('241 task')
    // The page it rendered holds 3 rows. Before F202 that number was the count on the screen.
    expect(text).not.toContain('3 tasks')
  })

  it('carries the same total into the link that navigates to the board', () => {
    const onNavigate = vi.fn()
    render(<OverviewScreen onNavigate={onNavigate} />)
    fireEvent.click(screen.getByRole('button', { name: '241 tasks' }))
    expect(onNavigate).toHaveBeenCalledWith('tasks')
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
