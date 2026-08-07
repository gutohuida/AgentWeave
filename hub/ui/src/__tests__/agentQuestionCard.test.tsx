import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AgentQuestionCard } from '@/components/agents/AgentQuestionCard'
import type { Question } from '@/api/questions'

const answer = vi.fn()

vi.mock('@/api/questions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/questions')>()),
  useAnswerQuestion: () => ({ mutate: answer, isPending: false }),
}))

function question(overrides: Partial<Question> = {}): Question {
  return {
    id: 'q-1',
    project_id: 'proj-1',
    from_agent: 'haiku-1',
    question: 'Which database should I target?',
    blocking: true,
    answered: false,
    created_at: new Date().toISOString(),
    ...overrides,
  }
}

describe('agent question card', () => {
  beforeEach(() => answer.mockClear())

  it('shows the question and who is asking', () => {
    render(<AgentQuestionCard questions={[question()]} agent="haiku-1" />)
    expect(screen.getByText('haiku-1 is asking')).toBeInTheDocument()
    expect(screen.getByText('Which database should I target?')).toBeInTheDocument()
  })

  it('sends the typed answer', () => {
    render(<AgentQuestionCard questions={[question()]} agent="haiku-1" />)
    fireEvent.change(screen.getByTestId('agent-question-input-q-1'), {
      target: { value: 'the staging one' },
    })
    fireEvent.click(screen.getByTestId('agent-question-send-q-1'))
    expect(answer).toHaveBeenCalledWith({ id: 'q-1', answer: 'the staging one' })
  })

  it('submits on Enter, since the agent is waiting', () => {
    render(<AgentQuestionCard questions={[question()]} agent="haiku-1" />)
    const input = screen.getByTestId('agent-question-input-q-1')
    fireEvent.change(input, { target: { value: 'postgres' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(answer).toHaveBeenCalledWith({ id: 'q-1', answer: 'postgres' })
  })

  it('refuses to send an empty answer', () => {
    render(<AgentQuestionCard questions={[question()]} agent="haiku-1" />)
    fireEvent.change(screen.getByTestId('agent-question-input-q-1'), { target: { value: '   ' } })
    fireEvent.click(screen.getByTestId('agent-question-send-q-1'))
    expect(answer).not.toHaveBeenCalled()
  })

  it('says the agent is waiting only when it actually is', () => {
    const { rerender } = render(<AgentQuestionCard questions={[question()]} agent="haiku-1" />)
    expect(screen.getByText(/The agent is waiting/)).toBeInTheDocument()
    rerender(
      <AgentQuestionCard questions={[question({ blocking: false })]} agent="haiku-1" />
    )
    expect(screen.queryByText(/The agent is waiting/)).not.toBeInTheDocument()
  })

  it('ignores another agent and already-answered questions', () => {
    const { container } = render(
      <AgentQuestionCard
        questions={[question({ from_agent: 'haiku-2' }), question({ id: 'q-2', answered: true })]}
        agent="haiku-1"
      />
    )
    expect(container).toBeEmptyDOMElement()
  })
})
