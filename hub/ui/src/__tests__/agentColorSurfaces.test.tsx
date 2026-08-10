import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { TaskCard } from '@/components/tasks/TaskCard'
import { EventRow } from '@/components/activity/EventRow'
import type { Task } from '@/api/tasks'

const task = {
  id: 'task-1', project_id: 'proj-a', title: 'Ship it', status: 'in_progress', priority: 'high', assignee: 'claude',
  assigner: 'user', created_at: '2026-08-04T09:00:00Z', updated: '2026-08-04T09:00:00Z',
} satisfies Task

describe('phase 5 agent identity colors across project surfaces', () => {
  it('shows the task assignee name with its project-assigned color', () => {
    // TaskCard reads the operator's transition map (B1 §7) to decide which status moves to
    // offer, so it now needs a query client. The colours this test is about are unaffected.
    render(
      <QueryClientProvider client={new QueryClient()}>
        <TaskCard task={task} assigneeColorIndex={2} />
      </QueryClientProvider>,
    )
    expect(screen.getByText('@claude')).toBeInTheDocument()
    expect(screen.getByTestId('task-assignee-color-claude')).toHaveStyle({ background: 'var(--agent-3)' })
  })

  it('shows the activity actor name with the same project-assigned color', () => {
    render(<EventRow event={{ type: 'task_created', data: { agent: 'claude' }, timestamp: '2026-08-04T09:00:00Z', localId: 1 }} actorName="claude" actorColorIndex={2} />)
    expect(screen.getByText('claude')).toBeInTheDocument()
    expect(screen.getByTestId('activity-actor-color-claude')).toHaveStyle({ background: 'var(--agent-3)' })
  })
})
