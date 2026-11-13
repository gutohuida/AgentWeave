import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { useStartReviewOfTask, type Task } from '@/api/tasks'
import { TaskCard } from '@/components/tasks/TaskCard'
import { TaskCardCompact } from '@/components/tasks/TaskCardCompact'
import { useConfigStore } from '@/store/configStore'

/**
 * `a-hand-started-task-reaches-review-and-merge`, FR-1 (ac-card-menu). On a `completed` card the
 * start menu offers "Review with <agent>" for every open agent but the author, and choosing one
 * posts `/agent/trigger` with `review_task_id` — a review turn, not the work turn "Start <agent> on
 * this" used to start (the 2026-11-13 quickstart drive). The card reads who may review from the
 * Hub's `/tasks/{id}/moves`, driven here through `fetch` with the real hooks; the fake answers as
 * the route does, never naming the author (`hub/tests/test_review_with_from_the_card.py` asserts
 * the real route's list and the trigger's effect on the task).
 */

const AUTHOR = 'builder'
const REVIEWER = 'reviewer'

const fetchMock = vi.fn()
let hub: { task: Task; agents: string[]; triggers: Record<string, unknown>[] }

function completedTask(): Task {
  return {
    id: 'task-1',
    project_id: 'proj-a',
    title: 'Add a greeting',
    status: 'completed',
    priority: 'medium',
    assignee: AUTHOR,
    created_at: '2026-11-13T10:00:00Z',
    updated: '2026-11-13T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
  }
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  useConfigStore.setState({ apiKey: 'aw_live_test', hubUrl: 'http://hub.test', isConfigured: true, selectedProjectId: 'proj-a' })
  hub = { task: completedTask(), agents: [AUTHOR, REVIEWER], triggers: [] }
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const u = new URL(url)
    const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body })
    if (u.pathname === '/api/v1/projects/proj-a/tasks/task-1/moves') {
      return ok({
        task_id: 'task-1',
        status: hub.task.status,
        moves: ['under_review'],
        reviewers: hub.task.status === 'completed' ? hub.agents.filter((a) => a !== AUTHOR) : [],
      })
    }
    if (u.pathname === '/api/v1/projects/proj-a/agent/trigger' && init?.method === 'POST') {
      const body = JSON.parse(String(init.body)) as Record<string, unknown>
      hub.triggers.push(body)
      if (body.review_task_id === hub.task.id) hub.task = { ...hub.task, status: 'under_review', assignee: String(body.agent) }
      return ok({ success: true, status: 'queued', conversation_id: 'conv-1' })
    }
    return { ok: false, status: 404, json: async () => ({ detail: `no route ${u.pathname}` }) }
  })
})
afterEach(() => {
  cleanup()
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

function Board({ compact }: { compact?: boolean }) {
  const review = useStartReviewOfTask()
  const props = {
    task: hub.task,
    onOpen: () => undefined,
    startAgents: hub.agents,
    onStartWork: () => {
      throw new Error('a completed card must not start a work turn')
    },
    onReviewTask: (taskId: string, agent: string) => review.mutate({ taskId, agent, title: hub.task.title }),
  }
  return compact ? <TaskCardCompact {...props} /> : <TaskCard {...props} />
}

function renderBoard(compact = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Board compact={compact} />
    </QueryClientProvider>,
  )
}

describe.each([
  ['TaskCard', false],
  ['TaskCardCompact', true],
])('%s on a completed task', (_name, compact) => {
  it('lists "Review with reviewer" and not the author, and starts a review turn', async () => {
    renderBoard(compact)
    fireEvent.keyDown(screen.getByRole('button', { name: 'Start review of Add a greeting' }), { key: 'Enter' })

    const item = await screen.findByRole('menuitem', { name: `Review with ${REVIEWER}` })
    expect(screen.queryByRole('menuitem', { name: `Review with ${AUTHOR}` })).toBeNull()
    expect(screen.queryByRole('menuitem', { name: /Start .* on this/ })).toBeNull()

    fireEvent.click(item)
    await waitFor(() => expect(hub.triggers).toHaveLength(1))
    expect(hub.triggers[0]).toMatchObject({ agent: REVIEWER, review_task_id: 'task-1' })
    expect(hub.triggers[0]).not.toHaveProperty('task_id')
    expect(hub.task).toMatchObject({ status: 'under_review', assignee: REVIEWER })
  })

  it('says nobody can review it when the author is the only agent', async () => {
    hub.agents = [AUTHOR]
    renderBoard(compact)
    fireEvent.keyDown(screen.getByRole('button', { name: 'Start review of Add a greeting' }), { key: 'Enter' })
    expect(await screen.findByText('No agent other than its author can review it')).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Review with/ })).toBeNull()
  })
})

describe('a card not yet finished', () => {
  it('keeps "Start <agent> on this" and reads no reviewers', () => {
    hub.task = { ...completedTask(), status: 'assigned' }
    const onStartWork = vi.fn()
    const client = new QueryClient()
    render(
      <QueryClientProvider client={client}>
        <TaskCard task={hub.task} onOpen={() => undefined} startAgents={hub.agents} onStartWork={onStartWork} onReviewTask={vi.fn()} />
      </QueryClientProvider>,
    )
    fireEvent.keyDown(screen.getByRole('button', { name: 'Start work on Add a greeting' }), { key: 'Enter' })
    fireEvent.click(screen.getByRole('menuitem', { name: `Start ${REVIEWER} on this` }))
    expect(onStartWork).toHaveBeenCalledWith('task-1', REVIEWER)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
