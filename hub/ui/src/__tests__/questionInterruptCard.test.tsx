import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QuestionInterruptCard } from '@/components/questions/QuestionInterruptCard'
import type { Question } from '@/api/questions'

// F386. The Overview card is the dashboard's route to an unanswered question, and it said
// "<agent> is waiting" for every question it rendered, including ones nobody waits on and ones the
// operator had declined. `GET /questions?answered=false` filters on `answered` only, so the rows
// below are shaped like that route's response: declined rows come back with `answered: false`.

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

function renderCard(questions: Question[]) {
  return render(<QuestionInterruptCard questions={questions} onNavigateToQuestions={vi.fn()} />)
}

describe('Overview question card', () => {
  it('says the agent is waiting when the question blocks and its asker is still waiting', () => {
    renderCard([question({ asker_waiting: true })])
    expect(screen.getByText(/haiku-1 is waiting/)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'haiku-1 is waiting for an answer' })).toBeInTheDocument()
  })

  it('presumes a blocking question with no asker_waiting field is waited on, as the Hub does', () => {
    renderCard([question()])
    expect(screen.getByText(/haiku-1 is waiting/)).toBeInTheDocument()
  })

  it('does not say anyone is waiting on a non-blocking question', () => {
    renderCard([question({ blocking: false })])
    expect(screen.queryByText(/is waiting/)).not.toBeInTheDocument()
    expect(screen.getByText(/haiku-1 is asking/)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'haiku-1 is asking a question' })).toBeInTheDocument()
  })

  it('does not say anyone is waiting once the run that asked has ended', () => {
    renderCard([question({ asker_waiting: false })])
    expect(screen.queryByText(/is waiting/)).not.toBeInTheDocument()
    expect(screen.getByText(/haiku-1 is asking/)).toBeInTheDocument()
  })

  it('does not render a question the operator declined', () => {
    const { container } = renderCard([question({ declined: true, declined_at: new Date().toISOString() })])
    expect(container).toBeEmptyDOMElement()
  })

  it('skips a declined question and shows the next one', () => {
    renderCard([
      question({ id: 'q-old', declined: true, question: 'Declined already?' }),
      question({ id: 'q-new', from_agent: 'sonnet-2', question: 'Ship it?' }),
    ])
    expect(screen.queryByText('Declined already?')).not.toBeInTheDocument()
    expect(screen.getByText('Ship it?')).toBeInTheDocument()
    expect(screen.getByText(/sonnet-2 is waiting/)).toBeInTheDocument()
  })
})

// From the adversarial review of 6ab4a4a + 229a708. F376's question of
// record is non-blocking, carries no run, and is never swept, so it sits oldest in
// `?answered=false` (ordered by created_at ascending) for as long as the operator leaves it.
describe('Overview question card with a refusal record open', () => {
  it('still surfaces a later blocking question someone is waiting on', () => {
    renderCard([
      question({ id: 'q-record', from_agent: 'lead', blocking: false, asker_waiting: true, question: 'May agents schedule work in this project?' }),
      question({ id: 'q-live', from_agent: 'sonnet-2', blocking: true, asker_waiting: true, question: 'Ship it?' }),
    ])
    expect(screen.getByText(/sonnet-2 is waiting/)).toBeInTheDocument()
  })
})
