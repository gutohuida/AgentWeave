import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '@/api/tasks'
import { TaskCard } from '@/components/tasks/TaskCard'

/**
 * The operator's controls for a task nobody finished.
 *
 * The policy exists so that "the cheap agent does it, the expensive one picks up what the cheap
 * one dropped" is a thing the operator can set and then see, on the work it applies to. A policy
 * reachable only through an API is a policy nobody sets — so what matters here is that it is on
 * the card, that it says what it will do in words rather than in enum values, and that the
 * escalation target is offered only where naming one means something.
 */

const setHandling = vi.fn()
const startWork = vi.fn()

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useUpdateTask: () => ({ mutate: vi.fn() }),
    useSetDivergenceHandling: () => ({ mutate: setHandling }),
    useStartWorkOnTask: () => ({ mutate: startWork }),
  }
})

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'worker' }, { name: 'reviewer' }] }),
}))

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    project_id: 'proj-test',
    title: 'Ship the thing',
    status: 'in_progress',
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    ...overrides,
  }
}

async function renderExpanded(task: Task) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TaskCard task={task} />
    </QueryClientProvider>,
  )
  await userEvent.click(screen.getByText(task.title))
}

beforeEach(() => {
  setHandling.mockReset()
  startWork.mockReset()
})

afterEach(cleanup)

describe('the divergence policy is set where the work is', () => {
  it('offers all three policies in words, with the current one marked', async () => {
    await renderExpanded(makeTask({ divergence_policy: 'retry' }))

    expect(screen.getByTestId('task-policy-surface-task-1')).toHaveTextContent('Tell me')
    expect(screen.getByTestId('task-policy-retry-task-1')).toHaveTextContent('Try again once')
    expect(screen.getByTestId('task-policy-escalate-task-1')).toHaveTextContent(
      'Hand to another agent',
    )
    expect(screen.getByTestId('task-policy-retry-task-1')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('task-policy-surface-task-1')).toHaveAttribute('aria-pressed', 'false')
  })

  it('sends the chosen policy', async () => {
    await renderExpanded(makeTask())
    await userEvent.click(screen.getByTestId('task-policy-retry-task-1'))

    expect(setHandling).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'task-1', divergence_policy: 'retry' }),
      expect.anything(),
    )
  })

  it('does not re-send the policy already in force', async () => {
    await renderExpanded(makeTask({ divergence_policy: 'retry' }))
    await userEvent.click(screen.getByTestId('task-policy-retry-task-1'))

    expect(setHandling).not.toHaveBeenCalled()
  })

  it('offers an escalation target only under escalate', async () => {
    await renderExpanded(makeTask({ divergence_policy: 'surface' }))
    expect(screen.queryByTestId('task-escalation-agent-task-1')).not.toBeInTheDocument()

    cleanup()
    await renderExpanded(makeTask({ divergence_policy: 'escalate' }))
    expect(screen.getByTestId('task-escalation-agent-task-1')).toBeInTheDocument()
  })

  it('offers the project’s agents as escalation targets', async () => {
    await renderExpanded(makeTask({ divergence_policy: 'escalate' }))
    const select = screen.getByTestId('task-escalation-agent-task-1')

    expect(select).toHaveTextContent('worker')
    expect(select).toHaveTextContent('reviewer')
  })

  it('says plainly that escalating to nobody does nothing', async () => {
    await renderExpanded(makeTask({ divergence_policy: 'escalate', escalation_agent: null }))

    expect(screen.getByText(/behaves the same as/i)).toBeInTheDocument()
  })

  it('clears the escalation target when nobody is chosen', async () => {
    await renderExpanded(makeTask({ divergence_policy: 'escalate', escalation_agent: 'reviewer' }))
    await userEvent.selectOptions(screen.getByTestId('task-escalation-agent-task-1'), '')

    expect(setHandling).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'task-1', escalation_agent: null }),
      expect.anything(),
    )
  })
})

describe('a stalled task says so', () => {
  it('shows nothing when the task is fine', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <TaskCard task={makeTask()} />
      </QueryClientProvider>,
    )
    expect(screen.queryByTestId('task-divergence-task-1')).not.toBeInTheDocument()
  })

  it('marks a task a run ended without moving, in a word the operator recognised', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <TaskCard task={makeTask({ has_open_divergence: true })} />
      </QueryClientProvider>,
    )
    // "Dropped" was the first label. Shown it, the operator asked "what is a dropped task?" —
    // so the badge says "Stalled" and the title carries the whole meaning.
    const badge = screen.getByTestId('task-divergence-task-1')
    expect(badge).toHaveTextContent('Stalled')
    expect(badge).toHaveAttribute(
      'title',
      'A run worked on this and ended without changing its status. Nothing is running now.',
    )
  })
})

describe('starting work binds the run', () => {
  it('offers each agent, and starts the chosen one on this task', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <TaskCard task={makeTask()} />
      </QueryClientProvider>,
    )

    await userEvent.click(screen.getByTestId('task-start-work-task-1'))
    await userEvent.click(screen.getByText('Start reviewer on this'))

    expect(startWork).toHaveBeenCalledWith(
      expect.objectContaining({ taskId: 'task-1', agent: 'reviewer' }),
      expect.anything(),
    )
  })
})
