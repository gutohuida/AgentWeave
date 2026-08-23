import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QuestionsPanel } from '@/components/questions/QuestionsPanel'
import type { Question } from '@/api/questions'
import type { AgentSummary } from '@/api/agents'

const answer = vi.fn()
const reset = vi.fn()
let loading = false
/** The unanswered fetch's failure, so a test can put the panel in "the Hub did not answer". */
const questionsState: Record<string, unknown> = {}
/** The answer mutation's own state, so a test can put the form in "it never left". */
const answerState: Record<string, unknown> = {}
/** The roster this panel joins against for each agent's `question_timeout_seconds`. */
let roster: AgentSummary[] = []
const pending: Question[] = [{
  id: 'question-1',
  project_id: 'project-1',
  from_agent: 'codex-1',
  question: 'Which migration should run?',
  blocking: true,
  answered: false,
  created_at: new Date().toISOString(),
}]

vi.mock('@/api/questions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/questions')>()),
  useQuestions: (answered?: boolean) =>
    answered
      ? { data: [], isLoading: false }
      : { data: pending, isLoading: loading, ...questionsState },
  useAnswerQuestion: () => ({ mutate: answer, isPending: false, reset, ...answerState }),
}))

vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: roster }) }))

function agent(overrides: Partial<AgentSummary> = {}): AgentSummary {
  return {
    name: 'codex-1',
    status: 'idle',
    message_count: 0,
    active_task_count: 0,
    ...overrides,
  }
}

/** A `created_at` the given number of seconds in the past. */
function secondsAgo(seconds: number): string {
  return new Date(Date.now() - seconds * 1000).toISOString()
}

beforeEach(() => {
  answer.mockClear()
  reset.mockClear()
  loading = false
  roster = []
  pending.length = 0
  pending.push({
    id: 'question-1',
    project_id: 'project-1',
    from_agent: 'codex-1',
    question: 'Which migration should run?',
    blocking: true,
    answered: false,
    created_at: new Date().toISOString(),
  })
  for (const key of Object.keys(questionsState)) delete questionsState[key]
  for (const key of Object.keys(answerState)) delete answerState[key]
})

describe('QuestionsPanel trust surface', () => {
  it('names the question, answer field, and submit action for assistive technology', () => {
    render(<QuestionsPanel />)
    const field = screen.getByRole('textbox', { name: 'Answer codex-1' })
    const submit = screen.getByRole('button', { name: 'Submit answer to codex-1' })
    expect(submit).toBeDisabled()
    fireEvent.change(field, { target: { value: 'Run 0085 first' } })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)
    expect(answer).toHaveBeenCalledWith(
      { id: 'question-1', answer: 'Run 0085 first' },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
  })

  it('uses question-shaped loading content with a named status', () => {
    loading = true
    render(<QuestionsPanel />)
    expect(screen.getByLabelText('Loading questions')).toBeInTheDocument()
    expect(document.querySelectorAll('.question-row')).toHaveLength(2)
  })

  it('starts at the top when navigation replaces a scrolled overview', () => {
    const workspace = document.createElement('div')
    workspace.className = 'workspace-content'
    workspace.scrollTo = vi.fn()
    document.body.appendChild(workspace)

    render(<QuestionsPanel />, { container: workspace })

    expect(workspace.scrollTo).toHaveBeenCalledWith({ top: 0 })
  })

  it('renders structured choices and submits their labels without forcing a text answer', () => {
    pending[0].options = [
      { label: 'Incremental', description: 'Apply the smallest safe migration first.' },
      { label: 'Full rebuild', description: 'Recreate the schema in one operation.' },
    ]
    render(<QuestionsPanel />)

    fireEvent.click(screen.getByRole('button', { name: /Incremental/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit answer to codex-1' }))

    expect(answer).toHaveBeenCalledWith(
      { id: 'question-1', answer: 'Incremental', labels: ['Incremental'] },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
    delete pending[0].options
  })
})

describe('a blocking question running out of its asker’s window', () => {
  it('says nothing while there is time left', () => {
    // 60s of a 240s window. The cue exists to mark the end of the wait, not to narrate it.
    pending[0].created_at = secondsAgo(60)
    render(<QuestionsPanel />)
    const stamp = screen.getByTestId('question-time-question-1')
    expect(stamp).not.toHaveClass('is-urgent')
    expect(stamp).not.toHaveAttribute('title')
  })

  it('turns the timestamp amber once most of the window has gone', () => {
    pending[0].created_at = secondsAgo(200)
    render(<QuestionsPanel />)
    const stamp = screen.getByTestId('question-time-question-1')
    expect(stamp).toHaveClass('is-urgent')
    expect(stamp).toHaveTextContent('asker times out soon')
  })

  it('measures against this agent’s own window rather than the default', () => {
    // 200s is urgent under the 240s default and comfortable under a 600s override — the whole
    // reason the panel joins the roster instead of assuming one number for every agent.
    pending[0].created_at = secondsAgo(200)
    roster = [agent({ question_timeout_seconds: 600 })]
    render(<QuestionsPanel />)
    expect(screen.getByTestId('question-time-question-1')).not.toHaveClass('is-urgent')
  })

  it('never counts down', () => {
    // Colour and a phrase, deliberately: a ticking number is the answer the research rejected,
    // and the permission card states its expiry in words for the same reason.
    pending[0].created_at = secondsAgo(230)
    render(<QuestionsPanel />)
    expect(screen.getByTestId('question-time-question-1').textContent).not.toMatch(/\d+\s*s\b/)
  })

  it('does not fire for a question nobody is blocked on', () => {
    // Non-blocking: the agent asked and carried on, so there is no window to run out of.
    pending[0].blocking = false
    pending[0].created_at = secondsAgo(1200)
    render(<QuestionsPanel />)
    expect(screen.getByTestId('question-time-question-1')).not.toHaveClass('is-urgent')
  })

  it('does not fire once the asker has already stopped waiting', () => {
    pending[0].asker_waiting = false
    pending[0].created_at = secondsAgo(1200)
    render(<QuestionsPanel />)
    expect(screen.getByTestId('question-time-question-1')).not.toHaveClass('is-urgent')
  })
})

describe('whether anyone is still waiting', () => {
  it('marks a row whose asking run has ended', () => {
    pending[0].asker_waiting = false
    render(<QuestionsPanel />)
    expect(screen.getByTestId('question-stale-question-1')).toHaveTextContent('no longer waiting')
    expect(document.querySelector('.question-row.is-stale')).not.toBeNull()
  })

  it('keeps a dead question out from under the banner that claims agents are waiting', () => {
    pending[0].asker_waiting = false
    render(<QuestionsPanel />)
    expect(screen.queryByText(/Blocking — agents are waiting/)).not.toBeInTheDocument()
    expect(screen.getByText('Unanswered')).toBeInTheDocument()
  })

  it('still shows the banner for a blocking question with someone on the other end', () => {
    render(<QuestionsPanel />)
    expect(screen.getByText(/Blocking — agents are waiting/)).toBeInTheDocument()
    expect(screen.queryByTestId('question-stale-question-1')).not.toBeInTheDocument()
  })
})

describe('when the panel cannot be trusted', () => {
  it('says the fetch failed instead of reporting an empty queue', async () => {
    // "No pending questions" for a failed fetch is an error rendered as reassurance, on the one
    // screen where being wrongly reassuring costs the most.
    const { ApiError } = await import('@/api/client')
    questionsState.isError = true
    questionsState.data = undefined
    questionsState.error = new ApiError(503, JSON.stringify({ detail: 'the Hub is restarting' }))
    render(<QuestionsPanel />)
    expect(screen.getByTestId('questions-error')).toHaveTextContent('the Hub is restarting')
    expect(screen.queryByText('No pending questions')).not.toBeInTheDocument()
  })

  it('keeps the last good list when a poll drops, and says it may be stale', async () => {
    // The 3s poll makes a single dropped request routine. Trading a screen of real questions for
    // an error card would cost more than the blip did, so the list stays and gains a caveat.
    const { ApiError } = await import('@/api/client')
    questionsState.isError = true
    questionsState.error = new ApiError(502, JSON.stringify({ detail: 'the Hub stopped answering' }))
    render(<QuestionsPanel />)
    expect(screen.getByText('Which migration should run?')).toBeInTheDocument()
    expect(screen.getByTestId('questions-stale')).toHaveTextContent('a newer question may be missing')
    expect(screen.queryByTestId('questions-error')).not.toBeInTheDocument()
  })

  it('says an answer never left rather than clearing the form silently', async () => {
    const { ApiError } = await import('@/api/client')
    answerState.isError = true
    answerState.error = new ApiError(409, JSON.stringify({ detail: 'this question was declined' }))
    render(<QuestionsPanel />)
    expect(screen.getByTestId('answer-error-question-1')).toHaveTextContent('this question was declined')
  })

  it('clears a stale failure as soon as the operator edits the answer', () => {
    answerState.isError = true
    answerState.error = new Error('boom')
    render(<QuestionsPanel />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Answer codex-1' }), { target: { value: 'retry' } })
    expect(reset).toHaveBeenCalled()
  })
})
