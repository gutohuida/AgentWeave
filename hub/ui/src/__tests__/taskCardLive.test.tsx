import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { Task } from '@/api/tasks'
import { TaskCard } from '@/components/tasks/TaskCard'

afterEach(cleanup)

// The tasks route's payload shape, every field filled, priority medium.
const task = {
  id: 'task-1',
  readable_id: 'TCSR-2',
  title: 'New card on the live board',
  description: 'A long description that belongs in the opened task.',
  status: 'in_progress',
  priority: 'medium',
  assignee: 'DeveloperSonnet2',
  builder: 'DeveloperSonnet2',
  checker: 'QA2WithAVeryLongNameIndeed',
  stage: 'waiting_for_answer',
  stage_since: '2026-11-12T21:00:00Z',
  stage_waits_on: 'DeveloperSonnet2',
  acceptance_criteria: ['ac-content: Given a task, when it renders, then ...'],
  requirement_ids: ['FR-2'],
} as unknown as Task

describe('the live board card (task-card-and-story-redesign)', () => {
  it('shows only its listed items: no description, criteria or medium priority', () => {
    const { container } = render(<TaskCard task={task} specTag="TCSR" now={new Date('2026-11-12T21:20:00Z')} onOpen={() => {}} />)
    expect(screen.getByText('New card on the live board')).toBeInTheDocument()
    expect(screen.getByTestId('task-stage-task-1').querySelector('svg')).not.toBeNull()
    expect(screen.queryByText('20 min')).toBeNull() // time at stage gives way to the waits-on line
    expect(screen.getByText('by builder')).toBeInTheDocument() // the asker is the builder, already named below
    expect(screen.getByText('TCSR')).toBeInTheDocument()
    expect(container.textContent).not.toContain('long description')
    expect(container.textContent).not.toContain('ac-content')
    expect(container.querySelector('[data-kind="critical"]')).toBeNull()
  })

  it('names the build\'s checker as the reviewer before review starts, and marks critical only', () => {
    const { container } = render(<TaskCard task={{ ...task, priority: 'critical' }} onOpen={() => {}} />)
    expect(screen.getByText('QA2WithAVeryLongNameIndeed')).toBeInTheDocument()
    expect(container.querySelector('[data-kind="critical"]')).not.toBeNull()
  })

  it('hides the failing-checks marker while the count is absent and shows it with one', () => {
    const { rerender } = render(<TaskCard task={task} onOpen={() => {}} />)
    expect(screen.queryByTestId('task-failed-checks-task-1')).toBeNull()
    rerender(<TaskCard task={task} failedChecks={2} onOpen={() => {}} />)
    expect(screen.getByTestId('task-failed-checks-task-1')).toHaveTextContent('2')
  })

  it('reads the count from the tasks route failed_checks, hiding it at zero or null', () => {
    const { rerender } = render(<TaskCard task={{ ...task, failed_checks: null }} onOpen={() => {}} />)
    expect(screen.queryByTestId('task-failed-checks-task-1')).toBeNull()
    rerender(<TaskCard task={{ ...task, failed_checks: 0 }} onOpen={() => {}} />)
    expect(screen.queryByTestId('task-failed-checks-task-1')).toBeNull()
    rerender(<TaskCard task={{ ...task, failed_checks: 2 }} onOpen={() => {}} />)
    expect(screen.getByTestId('task-failed-checks-task-1')).toHaveTextContent('2')
  })
})
