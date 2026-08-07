import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AgentQuestionCard } from '@/components/agents/AgentQuestionCard'
import type { Question, QuestionOption } from '@/api/questions'

function opt(label: string, description = ''): QuestionOption {
  return { label, description }
}

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
    expect(answer).toHaveBeenCalledWith({ id: 'q-1', answer: 'the staging one', labels: [] })
  })

  it('submits on Enter, since the agent is waiting', () => {
    render(<AgentQuestionCard questions={[question()]} agent="haiku-1" />)
    const input = screen.getByTestId('agent-question-input-q-1')
    fireEvent.change(input, { target: { value: 'postgres' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(answer).toHaveBeenCalledWith({ id: 'q-1', answer: 'postgres', labels: [] })
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

describe('agent question card — offered choices', () => {
  beforeEach(() => answer.mockClear())

  it('renders one button per offered option', () => {
    render(
      <AgentQuestionCard
        questions={[question({ options: [opt('Postgres', 'Concurrent writes; needs a server'), opt('SQLite'), opt('MySQL')] })]}
        agent="haiku-1"
      />
    )
    expect(screen.getByText('Postgres')).toBeInTheDocument()
    expect(screen.getByText('SQLite')).toBeInTheDocument()
    expect(screen.getByText('MySQL')).toBeInTheDocument()
  })

  it('answers with the exact option text when one is clicked', () => {
    render(
      <AgentQuestionCard questions={[question({ options: [opt('Postgres'), opt('SQLite')] })]} agent="haiku-1" />
    )
    fireEvent.click(screen.getByTestId('agent-question-option-q-1-1'))
    expect(answer).toHaveBeenCalledWith({ id: 'q-1', answer: 'SQLite', labels: ['SQLite'] })
  })

  it('still accepts a typed answer, and says so', () => {
    // Options are an offer, not a constraint: an operator who disagrees with all of them must
    // not be cornered into picking one.
    render(
      <AgentQuestionCard questions={[question({ options: [opt('Postgres')] })]} agent="haiku-1" />
    )
    const input = screen.getByTestId('agent-question-input-q-1')
    expect(input).toHaveAttribute('placeholder', 'Or answer in your own words')
    fireEvent.change(input, { target: { value: 'neither, use DuckDB' } })
    fireEvent.click(screen.getByTestId('agent-question-send-q-1'))
    expect(answer).toHaveBeenCalledWith({ id: 'q-1', answer: 'neither, use DuckDB', labels: [] })
  })

  it('shows no choices for an open question', () => {
    render(<AgentQuestionCard questions={[question({ options: [] })]} agent="haiku-1" />)
    expect(screen.queryByTestId('agent-question-option-q-1-0')).not.toBeInTheDocument()
    expect(screen.getByTestId('agent-question-input-q-1')).toHaveAttribute(
      'placeholder',
      'Your answer'
    )
  })

  it('tolerates a question with no options field at all', () => {
    const q = question()
    delete (q as { options?: string[] }).options
    render(<AgentQuestionCard questions={[q]} agent="haiku-1" />)
    expect(screen.getByText('Which database should I target?')).toBeInTheDocument()
  })
})

describe('interjections wear the composer’s chrome', () => {
  it('uses the shared surface rather than a coloured callout', () => {
    // The operator asked for these to read as an extension of the chat box, not an alert.
    const { container } = render(
      <AgentQuestionCard questions={[question({ options: [opt('a')] })]} agent="haiku-1" />
    )
    expect(container.querySelector('.conversation-interject')).not.toBeNull()
    expect(container.querySelector('.interject-choice')).not.toBeNull()
    expect(container.innerHTML).not.toContain('--blue')
    expect(container.innerHTML).not.toContain('--amber')
  })
})

describe('agent question card — descriptions, header, multi-select', () => {
  beforeEach(() => answer.mockClear())

  it('shows each option’s description, which is the point of options', () => {
    render(
      <AgentQuestionCard
        questions={[
          question({
            options: [
              opt('Postgres', 'Concurrent writes; needs a server'),
              opt('SQLite', 'No server; no concurrent writes'),
            ],
          }),
        ]}
        agent="haiku-1"
      />
    )
    expect(screen.getByText('Concurrent writes; needs a server')).toBeInTheDocument()
    expect(screen.getByText('No server; no concurrent writes')).toBeInTheDocument()
  })

  it('omits the description line when there is none', () => {
    const { container } = render(
      <AgentQuestionCard questions={[question({ options: [opt('Postgres')] })]} agent="haiku-1" />
    )
    expect(container.textContent).toContain('Postgres')
    expect(container.querySelectorAll('.interject-choice span')).toHaveLength(1)
  })

  it('shows the header chip only when the agent supplied one', () => {
    const { rerender } = render(
      <AgentQuestionCard questions={[question({ header: 'Database' })]} agent="haiku-1" />
    )
    expect(screen.getByTestId('agent-question-header-q-1')).toHaveTextContent('Database')
    rerender(<AgentQuestionCard questions={[question({ header: undefined })]} agent="haiku-1" />)
    expect(screen.queryByTestId('agent-question-header-q-1')).not.toBeInTheDocument()
  })

  it('answers immediately on click when only one choice is allowed', () => {
    render(
      <AgentQuestionCard
        questions={[question({ options: [opt('Postgres'), opt('SQLite')] })]}
        agent="haiku-1"
      />
    )
    fireEvent.click(screen.getByTestId('agent-question-option-q-1-0'))
    expect(answer).toHaveBeenCalledWith({ id: 'q-1', answer: 'Postgres', labels: ['Postgres'] })
  })

  it('accumulates a multi-select and sends every chosen label', () => {
    render(
      <AgentQuestionCard
        questions={[
          question({ multi_select: true, options: [opt('a'), opt('b'), opt('c')] }),
        ]}
        agent="haiku-1"
      />
    )
    fireEvent.click(screen.getByTestId('agent-question-option-q-1-0'))
    fireEvent.click(screen.getByTestId('agent-question-option-q-1-2'))
    // Nothing is sent until the operator confirms — otherwise the first click would answer.
    expect(answer).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('agent-question-send-q-1'))
    expect(answer).toHaveBeenCalledWith({ id: 'q-1', answer: 'a, c', labels: ['a', 'c'] })
  })

  it('deselects a multi-select option when clicked again', () => {
    render(
      <AgentQuestionCard
        questions={[question({ multi_select: true, options: [opt('a'), opt('b')] })]}
        agent="haiku-1"
      />
    )
    const first = screen.getByTestId('agent-question-option-q-1-0')
    fireEvent.click(first)
    expect(first).toHaveAttribute('data-selected', 'true')
    fireEvent.click(first)
    expect(first).not.toHaveAttribute('data-selected')
  })

  it('lets a typed answer override a multi-select in progress', () => {
    // The operator who bothered to type meant it; the options were only an offer.
    render(
      <AgentQuestionCard
        questions={[question({ multi_select: true, options: [opt('a'), opt('b')] })]}
        agent="haiku-1"
      />
    )
    fireEvent.click(screen.getByTestId('agent-question-option-q-1-0'))
    fireEvent.change(screen.getByTestId('agent-question-input-q-1'), {
      target: { value: 'none of these' },
    })
    fireEvent.click(screen.getByTestId('agent-question-send-q-1'))
    expect(answer).toHaveBeenCalledWith({ id: 'q-1', answer: 'none of these', labels: [] })
  })
})
