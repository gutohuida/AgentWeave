import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BoardView } from '@/components/tasks/BoardView'
import { TaskCardCompact } from '@/components/tasks/TaskCardCompact'
import type { Task } from '@/api/tasks'

const NOW = new Date('2026-11-12T12:00:00Z')
function task(id: string, over: Partial<Task>): Task {
  return { id, project_id: 'p', title: `Title ${id}`, status: 'approved', priority: 'medium', created_at: NOW.toISOString(), updated: NOW.toISOString(), ...over } as Task
}

describe('on main is distinct', () => {
  it('marks the on-main card and not the one still checking', () => {
    const a = render(<TaskCardCompact task={task('a', { stage: 'on_main' })} now={NOW} onOpen={() => {}} />)
    expect(a.container.querySelector('[data-task-id="a"]')?.getAttribute('data-on-main')).toBe('true')
    expect(screen.getByTestId('task-on-main-mark-a')).toBeTruthy()
    a.unmount()
    const b = render(<TaskCardCompact task={task('b', { stage: 'checking' })} now={NOW} onOpen={() => {}} />)
    expect(b.container.querySelector('[data-task-id="b"]')?.getAttribute('data-on-main')).toBe('false')
    expect(screen.queryByTestId('task-on-main-mark-b')).toBeNull()
  })
})

describe('board counts', () => {
  it('counts and lists exactly the not-on-main and working tasks', () => {
    const tasks = [
      task('n1', { stage: 'checking' }),
      task('n2', { stage: 'approved_waiting' }),
      task('w1', { status: 'in_progress', stage: 'working' }),
      task('m1', { stage: 'on_main' }),
    ]
    render(
      <BoardView tasks={tasks} agents={[]} tallies={{}} workingTaskIds={new Set()} view="board" onViewChange={() => {}}
        folds={{}} onFoldsChange={() => {}} onOpenTask={() => {}} onRetryIntegration={() => {}} now={NOW} />,
    )
    expect(screen.getByTestId('board-count-notOnMain').textContent).toContain('2')
    expect(screen.getByTestId('board-count-working').textContent).toContain('1')
    fireEvent.click(screen.getByTestId('board-count-notOnMain'))
    const list = within(screen.getByTestId('board-list-notOnMain')).getAllByRole('listitem')
    expect(list.map((li) => li.textContent)).toEqual(['Title n1', 'Title n2'])
    fireEvent.click(screen.getByTestId('board-count-working'))
    expect(within(screen.getByTestId('board-list-working')).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['Title w1'])
  })
})

describe('builder and reviewer', () => {
  it('shows both as separate labels under review, only the builder once approved', () => {
    const a = render(<TaskCardCompact task={task('a', { status: 'under_review', stage: 'under_review', builder: 'D', assignee: 'Q' })} now={NOW} onOpen={() => {}} />)
    expect(screen.getByTestId('task-built-by-a').textContent).toBe('built by D')
    expect(screen.getByTestId('task-reviewing-a').textContent).toBe('reviewing: Q')
    a.unmount()
    render(<TaskCardCompact task={task('b', { stage: 'checking', builder: 'D', assignee: 'Q' })} now={NOW} onOpen={() => {}} />)
    expect(screen.getByTestId('task-built-by-b').textContent).toBe('built by D')
    expect(screen.queryByTestId('task-reviewing-b')).toBeNull()
  })
})
