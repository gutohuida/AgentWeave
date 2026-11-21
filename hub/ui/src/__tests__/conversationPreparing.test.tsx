import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ConversationPreparing } from '@/components/agents/ConversationPreparing'
import { stageVisual } from '@/lib/taskStageVisual'
import { stageLabel } from '@/lib/taskStage'

const STARTED = '2026-11-21T14:35:00Z'

afterEach(() => vi.useRealTimers())

describe("a thread whose checkout is being prepared", () => {
  it('keeps its status region rendered when nothing is being prepared', () => {
    render(<ConversationPreparing agent="Developer" preparation={undefined} />)
    const region = screen.getByRole('status')
    expect(region).toBeEmptyDOMElement()
  })

  it('says what it waits on in words, behind the loader delay, and counts the wait', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-21T14:35:12Z'))
    render(
      <ConversationPreparing
        agent="Developer"
        preparation={{ id: 'prep-1', agent: 'Developer', task_id: null, conversation_id: 'conv-1', started_at: STARTED }}
      />,
    )
    const region = screen.getByRole('status')
    expect(region).toHaveTextContent("Preparing this thread's checkout. Developer starts once git has written it.")
    expect(region.querySelector('.aw-delayed')).not.toBeNull()
    expect(region).toHaveTextContent('12s')
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(region).toHaveTextContent('15s')
  })

  it("names the task's checkout for a task's turn", () => {
    render(
      <ConversationPreparing
        agent="Developer"
        preparation={{ id: 'prep-2', agent: 'Developer', task_id: 'task-1', conversation_id: 'conv-1', started_at: STARTED }}
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent("Preparing the task's checkout.")
  })
})

describe('the task stage', () => {
  it('words preparing_checkout with a glyph, never as the raw stage', () => {
    expect(stageLabel('preparing_checkout')).toBe('Preparing its checkout')
    const visual = stageVisual('preparing_checkout')
    expect(visual.word).toBe('Preparing checkout')
    expect(visual.glyph).toBe('git_branch_plus')
  })
})
