import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import { BoardScopePicker, type ScopeSpec } from '@/components/tasks/BoardScopePicker'
import { TaskCardCompact } from '@/components/tasks/TaskCardCompact'
import type { Task } from '@/api/tasks'

/**
 * The spec filter lists specs in the order the route gives them (most recently active first), shows
 * each by its tag with its recency and unfinished count, and searches tag and title
 * (`find-a-spec-s-tasks-without-knowing-its-name`, task `picker`).
 */

const hoursAgo = (hours: number) => new Date(Date.now() - hours * 3_600_000).toISOString()

// The route's order: P moved an hour ago, Q a week ago; Q is first alphabetically.
const specs: ScopeSpec[] = [
  { id: 'spec-p', title: 'Rework the display', tag: 'tasks board', unfinished: 3, lastActivity: hoursAgo(2) },
  { id: 'spec-q', title: 'Alpha plan', tag: 'alpha', unfinished: 1, lastActivity: hoursAgo(24 * 7) },
]

function open(list: ScopeSpec[] = specs) {
  render(
    <BoardScopePicker
      scope={{ kind: 'all' }}
      scopeLabel="All"
      specs={list}
      noSpecCount={0}
      buildingCount={0}
      onChoose={vi.fn()}
    />,
  )
  fireEvent.click(screen.getByTestId('board-scope'))
}

afterEach(cleanup)

describe('the spec filter', () => {
  it('lists the specs in the order given, All, Building and No spec first', () => {
    open()
    const keys = screen.getAllByRole('option').map((o) => o.getAttribute('data-testid'))
    expect(keys).toEqual([
      'board-scope-option-all',
      'board-scope-option-building',
      'board-scope-option-none',
      'board-scope-option-spec-p',
      'board-scope-option-spec-q',
    ])
  })

  it("shows a spec's tag, how long ago it moved and how many tasks are unfinished", () => {
    open()
    const entry = screen.getByTestId('board-scope-option-spec-p')
    expect(entry.textContent).toContain('tasks board')
    expect(entry.textContent).toContain('2 h')
    expect(entry.textContent).toContain('3')
    expect(screen.getByTestId('board-scope-option-spec-q').textContent).toContain('7 days')
  })

  it('finds a spec by its tag when the title does not hold the text', () => {
    open()
    fireEvent.change(screen.getByTestId('board-scope-filter'), { target: { value: 'BOARD' } })
    const keys = screen.getAllByRole('option').map((o) => o.getAttribute('data-testid'))
    expect(keys).toEqual(['board-scope-option-spec-p'])
  })

  it('still finds a spec by its title, keeping the order', () => {
    open()
    fireEvent.change(screen.getByTestId('board-scope-filter'), { target: { value: 'plan' } })
    expect(screen.getAllByRole('option').map((o) => o.getAttribute('data-testid'))).toEqual([
      'board-scope-option-spec-q',
    ])
  })
})

describe('the card', () => {
  it("names the task's spec by its tag", () => {
    const task = {
      id: 'task-1',
      project_id: 'p',
      title: 'Do it',
      status: 'pending',
      priority: 'medium',
      created_at: hoursAgo(1),
      updated: hoursAgo(1),
      divergence_policy: 'surface',
      has_open_divergence: false,
      spec_document_id: 'spec-p',
    } as Task
    render(<TaskCardCompact task={task} specTag="tasks board" onOpen={vi.fn()} />)
    expect(screen.getByTestId('task-spec-tag-task-1').textContent).toBe('tasks board')
  })
})
