import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AgentQuestionCard } from '@/components/agents/AgentQuestionCard'
import type { Question, QuestionOption } from '@/api/questions'

function opt(label: string, description = ''): QuestionOption {
  return { label, description }
}

function question(overrides: Partial<Question> = {}): Question {
  return {
    id: 'q-1',
    project_id: 'proj-1',
    from_agent: 'haiku-1',
    question: 'Which database should I target?',
    header: 'Database',
    blocking: true,
    answered: false,
    multi_select: false,
    options: [opt('Postgres', 'Concurrent writes; needs a server'), opt('SQLite', 'No server')],
    created_at: new Date().toISOString(),
    ...overrides,
  }
}

const toggle = vi.fn()

function renderCard(q: Question, props: Partial<Parameters<typeof AgentQuestionCard>[0]> = {}) {
  return render(
    <AgentQuestionCard
      questions={[q]}
      agent="haiku-1"
      selected={[]}
      onToggle={toggle}
      isResponding={false}
      isTyping={false}
      {...props}
    />
  )
}

describe('agent question panel', () => {
  beforeEach(() => toggle.mockClear())

  it('shows the header, the question, and each option with its description', () => {
    renderCard(question())
    expect(screen.getByText('Database')).toBeInTheDocument()
    expect(screen.getByText('Which database should I target?')).toBeInTheDocument()
    expect(screen.getByText('Concurrent writes; needs a server')).toBeInTheDocument()
  })

  it('has no input and no submit of its own — the composer is the only place to answer from', () => {
    // This is what makes it read as part of the chat box rather than a widget on top of one.
    const { container } = renderCard(question())
    expect(container.querySelector('input')).toBeNull()
    expect(container.querySelector('textarea')).toBeNull()
    expect(screen.queryByText('Answer')).not.toBeInTheDocument()
  })

  it('reports a click without deciding what it means', () => {
    renderCard(question())
    fireEvent.click(screen.getByTestId('agent-question-option-q-1-1'))
    expect(toggle).toHaveBeenCalledWith('SQLite')
  })

  it('shows a numbered badge per option, and a check once chosen', () => {
    const { container, rerender } = renderCard(question())
    expect(container.querySelectorAll('.interject-kbd')).toHaveLength(2)
    rerender(
      <AgentQuestionCard
        questions={[question()]}
        agent="haiku-1"
        selected={['Postgres']}
        onToggle={toggle}
        isResponding={false}
        isTyping={false}
      />
    )
    expect(screen.getByTestId('agent-question-option-q-1-0')).toHaveAttribute(
      'data-selected',
      'true'
    )
    expect(container.querySelectorAll('.interject-kbd')).toHaveLength(1)
  })

  it('picks an option when its number key is pressed', () => {
    renderCard(question())
    fireEvent.keyDown(document, { key: '2' })
    expect(toggle).toHaveBeenCalledWith('SQLite')
  })

  it('ignores number keys while the operator is typing in a field', () => {
    // Otherwise writing "use option 2" would silently answer the question.
    renderCard(question())
    const field = document.createElement('input')
    document.body.appendChild(field)
    fireEvent.keyDown(field, { key: '2' })
    expect(toggle).not.toHaveBeenCalled()
    field.remove()
  })

  it('ignores a number with no matching option', () => {
    renderCard(question())
    fireEvent.keyDown(document, { key: '7' })
    expect(toggle).not.toHaveBeenCalled()
  })

  it('stops looking chosen once the operator starts writing', () => {
    // A typed answer supersedes the selection, so the selection must not still look live.
    renderCard(question(), { selected: ['Postgres'], isTyping: true })
    expect(screen.getByTestId('agent-question-option-q-1-0')).not.toHaveAttribute('data-selected')
  })

  it('disables every option while the answer is in flight', () => {
    renderCard(question(), { isResponding: true })
    expect(screen.getByTestId('agent-question-option-q-1-0')).toBeDisabled()
    fireEvent.keyDown(document, { key: '1' })
    expect(toggle).not.toHaveBeenCalled()
  })

  it('says when several can be chosen, and not when they cannot', () => {
    const { rerender } = renderCard(question({ multi_select: true }))
    expect(screen.getByText('Select one or more options.')).toBeInTheDocument()
    rerender(
      <AgentQuestionCard
        questions={[question({ multi_select: false })]}
        agent="haiku-1"
        selected={[]}
        onToggle={toggle}
        isResponding={false}
        isTyping={false}
      />
    )
    expect(screen.queryByText('Select one or more options.')).not.toBeInTheDocument()
  })

  it('counts outstanding questions only when there is more than one', () => {
    const { rerender } = renderCard(question())
    expect(screen.queryByTestId('agent-question-count')).not.toBeInTheDocument()
    rerender(
      <AgentQuestionCard
        questions={[question(), question({ id: 'q-2' })]}
        agent="haiku-1"
        selected={[]}
        onToggle={toggle}
        isResponding={false}
        isTyping={false}
      />
    )
    expect(screen.getByTestId('agent-question-count')).toHaveTextContent('1/2')
  })

  it('shows nothing for another agent, or when nothing is pending', () => {
    const { container: a } = render(
      <AgentQuestionCard
        questions={[question({ from_agent: 'haiku-2' })]}
        agent="haiku-1"
        selected={[]}
        onToggle={toggle}
        isResponding={false}
        isTyping={false}
      />
    )
    expect(a).toBeEmptyDOMElement()
    const { container: b } = render(
      <AgentQuestionCard
        questions={[]}
        agent="haiku-1"
        selected={[]}
        onToggle={toggle}
        isResponding={false}
        isTyping={false}
      />
    )
    expect(b).toBeEmptyDOMElement()
  })

  it('wears the composer’s chrome rather than a coloured callout', () => {
    const { container } = renderCard(question())
    expect(container.querySelector('.conversation-interject')).not.toBeNull()
    expect(container.innerHTML).not.toContain('--blue')
    expect(container.innerHTML).not.toContain('--amber')
  })
})
