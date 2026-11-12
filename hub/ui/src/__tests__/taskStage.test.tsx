import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TaskCardCompact } from '@/components/tasks/TaskCardCompact'
import { formatStageAge, STAGE_LABELS } from '@/lib/taskStage'
import type { Task } from '@/api/tasks'

const NOW = new Date('2026-11-12T12:00:00Z')
const MIN = 60_000
const ago = (ms: number) => new Date(NOW.getTime() - ms).toISOString()

function task(over: Partial<Task>): Task {
  return { id: 't1', project_id: 'p', title: 'T', status: 'approved', priority: 'medium', created_at: ago(0), updated: ago(0), ...over } as Task
}

function card(t: Task, now?: Date) {
  return <TaskCardCompact task={t} now={now} onOpen={() => {}} />
}

afterEach(() => vi.useRealTimers())

describe('stage on the card', () => {
  it('shows each stage once', () => {
    for (const stage of Object.keys(STAGE_LABELS)) {
      const { unmount } = render(card(task({ stage, stage_since: ago(MIN) }), NOW))
      expect(screen.getAllByTestId('task-stage-t1')).toHaveLength(1)
      expect(screen.getByTestId('task-stage-t1').textContent).toContain(STAGE_LABELS[stage])
      unmount()
    }
  })

  it('shows the commit, what a hold waits on and why a landing failed', () => {
    const a = render(card(task({ stage: 'on_main', stage_detail: 'abcdef1', stage_since: ago(MIN) }), NOW))
    expect(screen.getByTestId('task-stage-detail-t1').textContent).toContain('abcdef1')
    a.unmount()
    const b = render(card(task({ stage: 'landing_held', stage_waits_on: 'AW-7', stage_since: ago(MIN) }), NOW))
    expect(screen.getByTestId('task-stage-waits-on-t1').textContent).toContain('AW-7')
    b.unmount()
    render(card(task({ stage: 'did_not_land', stage_detail: 'checkout is dirty', stage_since: ago(MIN) }), NOW))
    expect(screen.getByTestId('task-stage-detail-t1').textContent).toContain('checkout is dirty')
  })

  it('reads the time at the stage compactly', () => {
    expect(formatStageAge(ago(14 * MIN), NOW)).toBe('14 min')
    expect(formatStageAge(ago(2 * 24 * 60 * MIN), NOW)).toBe('2 days')
    render(card(task({ stage: 'checking', stage_since: ago(14 * MIN) }), NOW))
    expect(screen.getByTestId('task-stage-age-t1').textContent).toContain('14 min')
  })

  it('advances the time without a reload', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(NOW.getTime() + MIN))
    render(card(task({ stage: 'checking', stage_since: NOW.toISOString() })))
    expect(screen.getByTestId('task-stage-age-t1').textContent).toContain('1 min')
    act(() => {
      vi.advanceTimersByTime(2 * MIN)
    })
    expect(screen.getByTestId('task-stage-age-t1').textContent).toContain('3 min')
  })

  it('names what a waiting task waits on and nothing for one that is not waiting', () => {
    const a = render(card(task({ stage: 'waiting_for_answer', stage_waits_on: 'Q', stage_since: ago(MIN) }), NOW))
    expect(screen.getByTestId('task-stage-waits-on-t1').textContent).toContain('Q')
    a.unmount()
    render(card(task({ stage: 'working', stage_since: ago(MIN) }), NOW))
    expect(screen.queryByTestId('task-stage-waits-on-t1')).toBeNull()
  })
})
