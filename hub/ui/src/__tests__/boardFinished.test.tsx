import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import * as React from 'react'
import { BoardView } from '@/components/tasks/BoardView'
import type { Task } from '@/api/tasks'

const NOW = new Date('2026-11-12T12:00:00Z')
function task(id: string, over: Partial<Task>): Task {
  return { id, project_id: 'p', title: `Title ${id}`, status: 'approved', priority: 'medium', created_at: NOW.toISOString(), updated: NOW.toISOString(), ...over } as Task
}
const tasks = [
  ...[1, 2, 3, 4, 5].map((n) => task(`m${n}`, { stage: 'on_main' })),
  task('c1', { status: 'rejected', stage: 'closed' }),
  task('w1', { status: 'in_progress', stage: 'working' }),
  task('w2', { status: 'in_progress', stage: 'working' }),
  task('f1', { title: 'Fix flaky test X', stage: 'on_main' }),
]

function Host({ initial = false, list = tasks }: { initial?: boolean; list?: Task[] }) {
  // Stands in for the container, which remembers the switch per project.
  const [show, setShow] = React.useState(() => (localStorage.getItem('t') ?? String(initial)) === 'true')
  return (
    <BoardView tasks={list} agents={[]} tallies={{}} workingTaskIds={new Set()} view="board" onViewChange={() => {}}
      folds={{}} onFoldsChange={() => {}} onOpenTask={() => {}} onRetryIntegration={() => {}} now={NOW}
      showFinished={show} onShowFinishedChange={(v) => { localStorage.setItem('t', String(v)); setShow(v) }} />
  )
}

describe('finished tasks leave the board', () => {
  it('shows the in-progress tasks and counts the finished ones hidden', () => {
    localStorage.clear()
    const list = tasks.filter((t) => t.id !== 'f1')
    render(<Host list={list} />)
    expect(screen.queryByTestId('task-open-w1')).toBeTruthy()
    expect(screen.queryByTestId('task-open-w2')).toBeTruthy()
    expect(screen.queryByTestId('task-open-m1')).toBeNull()
    expect(screen.getByTestId('board-hidden-finished').textContent).toContain('6 finished')
  })

  it('shows finished tasks once the switch is on, and keeps it on after a remount', () => {
    localStorage.clear()
    const first = render(<Host />)
    fireEvent.click(screen.getByTestId('board-show-finished'))
    expect(screen.getByTestId('task-open-m1')).toBeTruthy()
    first.unmount()
    render(<Host />)
    expect((screen.getByTestId('board-show-finished') as HTMLInputElement).checked).toBe(true)
    expect(screen.getByTestId('task-open-c1')).toBeTruthy()
  })

  it('search reaches a finished task while the switch is off', () => {
    localStorage.clear()
    render(<Host />)
    expect(screen.queryByTestId('task-open-f1')).toBeNull()
    fireEvent.change(screen.getByLabelText('Search tasks'), { target: { value: 'flaky test X' } })
    expect(screen.getByTestId('task-open-f1')).toBeTruthy()
  })
})
