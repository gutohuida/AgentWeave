import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CloseAlreadyBuilt } from '@/components/spec/CloseAlreadyBuilt'
import { parseCommits } from '@/lib/commits'
import { ApiError } from '@/api/client'

/**
 * `every-task-can-always-be-moved-on` FR-5, the app half: an approved change with open tasks offers
 * to close them as already built, sends the commits typed, and says what the Hub answered. The
 * answer below is the shape `POST /documents/{path}/close-already-built` returns, pinned by
 * `hub/tests/test_close_spec_tasks_already_built.py`.
 */
const mutate = vi.fn()
let tasks: { id: string; status: string }[] = []

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return { ...actual, useCloseAlreadyBuilt: () => ({ mutate, isPending: false }) }
})

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return { ...actual, useDocumentTasks: () => ({ data: tasks }) }
})

const PATH = 'spec/changes/built-already/spec.json'
const SHA = '91b59b5aaaaabbbbbccccdddddeeeeefffff0000'

const ANSWER = {
  document: PATH,
  commits: [SHA],
  tasks: [
    { id: 'task-1', title: 'Build alpha', from_status: 'pending', status: 'under_review', evidence: ['ev-1'] },
    { id: 'task-2', title: 'Build beta', from_status: 'pending', status: 'under_review', evidence: ['ev-2'] },
  ],
}

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  tasks = [
    { id: 'task-1', status: 'pending' },
    { id: 'task-2', status: 'pending' },
    { id: 'task-0', status: 'approved' },
  ]
})

describe('CloseAlreadyBuilt', () => {
  it('splits the commits typed on spaces and commas', () => {
    expect(parseCommits(' 91b59b5, c2eabc3\n8ddfe38 ')).toEqual(['91b59b5', 'c2eabc3', '8ddfe38'])
  })

  it('offers nothing when the document has no open task', () => {
    tasks = [{ id: 'task-0', status: 'approved' }]
    wrap(<CloseAlreadyBuilt path={PATH} documentId="spdoc-1" />)
    expect(screen.queryByTestId('already-built-open')).toBeNull()
  })

  it('closes the open tasks against the commits typed and says what happened', async () => {
    const user = userEvent.setup()
    mutate.mockImplementation((_args, { onSuccess }) => onSuccess(ANSWER))
    wrap(<CloseAlreadyBuilt path={PATH} documentId="spdoc-1" />)

    await user.click(screen.getByTestId('already-built-open'))
    expect(screen.getByTestId('already-built-close')).toBeDisabled()
    await user.type(screen.getByTestId('already-built-commits'), '91b59b5')
    await user.click(screen.getByTestId('already-built-close'))

    expect(mutate).toHaveBeenCalledWith(
      { path: PATH, commits: ['91b59b5'] },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
    const result = screen.getByTestId('already-built-result')
    expect(result.textContent).toContain('Closed 2 tasks as already built at 91b59b5aaaaa')
    expect(result.textContent).toContain('2 pieces of evidence await a decision')
  })

  it('shows the Hub refusal in place', async () => {
    const user = userEvent.setup()
    mutate.mockImplementation((_args, { onError }) =>
      // The route's own 422 body, as `postJson` carries it.
      onError(
        new ApiError(
          422,
          JSON.stringify({
            detail: {
              message: 'every commit named must be on the main branch; not on main: abc1234',
              code: 'commit_not_on_main',
              unknown: [],
              off_main: ['abc1234'],
            },
          }),
        ),
      ),
    )
    wrap(<CloseAlreadyBuilt path={PATH} documentId="spdoc-1" />)

    await user.click(screen.getByTestId('already-built-open'))
    await user.type(screen.getByTestId('already-built-commits'), 'abc1234')
    await user.click(screen.getByTestId('already-built-close'))

    expect(screen.getByRole('alert').textContent).toContain('not on main')
  })
})
