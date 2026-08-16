import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecDocumentTasksLink } from '@/components/spec/SpecDocumentTasksLink'

let documents: unknown[] = []
let tasks: unknown[] = []

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecDocuments: () => ({ data: { documents } }),
  }
})

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useDocumentTasks: () => ({ data: tasks }),
  }
})

function doc(overrides: Record<string, unknown> = {}) {
  return {
    id: 'spdoc-1',
    path: 'spec/changes/demo/spec.html',
    title: 'Demo',
    kind: 'change-spec',
    phase: 'approved',
    explore_closed: true,
    updated_at: '2026-08-16T00:00:00Z',
    ...overrides,
  }
}

function renderLink(onOpenTasks?: (taskIds: string[]) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecDocumentTasksLink path="spec/changes/demo/spec.html" onOpenTasks={onOpenTasks} />
    </QueryClientProvider>,
  )
}

describe('SpecDocumentTasksLink', () => {
  it('renders nothing when the document has no declared tasks', () => {
    documents = [doc()]
    tasks = []
    const { container } = renderLink()
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the document is not found', () => {
    documents = []
    tasks = [{ id: 'task-1' }]
    const { container } = renderLink()
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the count and opens every declared task id on click', async () => {
    const user = userEvent.setup()
    documents = [doc()]
    tasks = [{ id: 'task-1' }, { id: 'task-2' }]
    const onOpenTasks = vi.fn()
    renderLink(onOpenTasks)

    expect(screen.getByText('2 tasks declared by this document')).toBeInTheDocument()
    await user.click(screen.getByText('2 tasks declared by this document'))
    expect(onOpenTasks).toHaveBeenCalledWith(['task-1', 'task-2'])
  })

  it('renders a plain span with no click target when onOpenTasks is omitted', () => {
    documents = [doc()]
    tasks = [{ id: 'task-1' }]
    renderLink(undefined)

    expect(screen.getByText('1 task declared by this document')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
