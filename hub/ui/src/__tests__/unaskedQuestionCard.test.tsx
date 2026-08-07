import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { UnaskedQuestionCard } from '@/components/agents/UnaskedQuestionCard'
import type { UnaskedQuestion } from '@/api/unaskedQuestions'
import { summaryForEvent } from '@/lib/eventSummary'
import { eventBelongsToTimeline } from '@/api/agents'

const resolve = vi.fn()

vi.mock('@/api/unaskedQuestions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/unaskedQuestions')>()),
  useResolveUnaskedQuestion: () => ({ mutate: resolve, isPending: false }),
}))

function unasked(overrides: Partial<UnaskedQuestion> = {}): UnaskedQuestion {
  return {
    id: 'unasked-1',
    agent: 'codex-1',
    run_id: 'run-1',
    conversation_id: 'conv-1',
    question: 'Which package manager should I use?',
    status: 'pending',
    created_at: new Date().toISOString(),
    resolved_at: null,
    ...overrides,
  }
}

describe('unasked question card', () => {
  beforeEach(() => resolve.mockClear())

  it('shows the question the agent stopped on, in its own words', () => {
    render(<UnaskedQuestionCard questions={[unasked()]} agent="codex-1" />)
    expect(screen.getByText('Which package manager should I use?')).toBeInTheDocument()
    expect(screen.getByText(/never asked/)).toBeInTheDocument()
  })

  it('offers both actions and sends the one pressed', () => {
    render(<UnaskedQuestionCard questions={[unasked()]} agent="codex-1" />)
    fireEvent.click(screen.getByTestId('unasked-ask-unasked-1'))
    expect(resolve).toHaveBeenCalledWith({ id: 'unasked-1', action: 'ask' })
    fireEvent.click(screen.getByTestId('unasked-dismiss-unasked-1'))
    expect(resolve).toHaveBeenCalledWith({ id: 'unasked-1', action: 'dismiss' })
  })

  it('shows nothing when there is nothing pending', () => {
    const { container } = render(<UnaskedQuestionCard questions={[]} agent="codex-1" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('ignores another agent’s unasked question', () => {
    render(<UnaskedQuestionCard questions={[unasked({ agent: 'haiku-1' })]} agent="codex-1" />)
    expect(screen.queryByTestId('unasked-question-unasked-1')).not.toBeInTheDocument()
  })

  it('ignores one that has already been acted on', () => {
    render(<UnaskedQuestionCard questions={[unasked({ status: 'asked' })]} agent="codex-1" />)
    expect(screen.queryByTestId('unasked-question-unasked-1')).not.toBeInTheDocument()
  })

  it('wears the composer’s chrome rather than an alarm colour', () => {
    // Operator, on these cards: "it should be like the chat box but maybe a little lighter".
    const { container } = render(<UnaskedQuestionCard questions={[unasked()]} agent="codex-1" />)
    expect(container.querySelector('.conversation-interject')).not.toBeNull()
    expect(container.innerHTML).not.toContain('--amber')
  })
})

describe('an unasked question reaches the operator’s other views', () => {
  it('belongs to the agent’s timeline', () => {
    expect(
      eventBelongsToTimeline(
        { type: 'question_not_asked', data: { agent: 'codex-1' } } as never,
        'codex-1'
      )
    ).toBe(true)
  })

  it('summarises to the question itself, not to its own event name', () => {
    const summary = summaryForEvent('question_not_asked', {
      agent: 'codex-1',
      question: 'Which package manager should I use?',
    })
    expect(summary).toContain('codex-1')
    expect(summary).toContain('Which package manager should I use?')
  })

  it('summarises a refusal to its reason, which previously rendered nowhere', () => {
    const summary = summaryForEvent('permission_denied', {
      agent: 'haiku-1',
      tool_name: 'Write',
      reason: 'outside your workspace',
    })
    expect(summary).toContain('Write')
    expect(summary).toContain('outside your workspace')
    expect(summary).not.toBe('permission_denied')
  })
})
