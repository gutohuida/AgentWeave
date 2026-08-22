import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QuestionsPanel } from '@/components/questions/QuestionsPanel'
import type { Question } from '@/api/questions'

const answer = vi.fn()
let loading = false
const pending: Question[] = [{
  id: 'question-1',
  project_id: 'project-1',
  from_agent: 'codex-1',
  question: 'Which migration should run?',
  blocking: true,
  answered: false,
  created_at: new Date().toISOString(),
}]

vi.mock('@/api/questions', () => ({
  useQuestions: (answered?: boolean) => ({ data: answered ? [] : pending, isLoading: answered ? false : loading }),
  useAnswerQuestion: () => ({ mutate: answer, isPending: false }),
}))

describe('QuestionsPanel trust surface', () => {
  beforeEach(() => { answer.mockClear(); loading = false })

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
})
