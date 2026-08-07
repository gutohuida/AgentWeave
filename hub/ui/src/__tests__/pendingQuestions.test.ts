import { describe, expect, it } from 'vitest'
import { activeQuestionFor } from '@/lib/pendingQuestions'
import type { Question } from '@/api/questions'

function question(overrides: Partial<Question> = {}): Question {
  return {
    id: 'q-1',
    project_id: 'proj-test',
    from_agent: 'codex-1',
    question: 'Which database?',
    blocking: true,
    options: [
      { label: 'Postgres', description: 'server' },
      { label: 'SQLite', description: 'embedded' },
    ],
    header: 'Database',
    multi_select: false,
    answered: false,
    created_at: '2026-08-07T10:00:00Z',
    batch_id: null,
    batch_index: 0,
    batch_size: 1,
    ...overrides,
  }
}

function batchOf(n: number, answeredCount = 0): Question[] {
  return Array.from({ length: n }, (_, index) =>
    question({
      id: `q-${index + 1}`,
      question: `Question ${index + 1}?`,
      batch_id: 'qbatch-1',
      batch_index: index,
      batch_size: n,
      answered: index < answeredCount,
      created_at: `2026-08-07T10:0${index}:00Z`,
    })
  )
}

describe('which question the operator is answering', () => {
  it('reports nothing when there is nothing outstanding', () => {
    expect(activeQuestionFor([], 'codex-1').question).toBeNull()
    expect(activeQuestionFor([question({ answered: true })], 'codex-1').question).toBeNull()
  })

  it('ignores another agent’s questions', () => {
    expect(activeQuestionFor([question({ from_agent: 'haiku-1' })], 'codex-1').question).toBeNull()
  })

  it('treats a lone question as a batch of one', () => {
    const active = activeQuestionFor([question()], 'codex-1')
    expect(active.question?.id).toBe('q-1')
    expect(active.step).toBe(1)
    expect(active.total).toBe(1)
  })

  it('starts a batch at its first question', () => {
    const active = activeQuestionFor(batchOf(3), 'codex-1')
    expect(active.question?.id).toBe('q-1')
    expect(active.step).toBe(1)
    expect(active.total).toBe(3)
  })

  it('advances the step as questions are answered', () => {
    // Answered rows drop out of what the panel holds; the step has to be recoverable from the
    // remainder alone, which is the whole reason batch_size rides on every row.
    const active = activeQuestionFor(batchOf(3, 1), 'codex-1')
    expect(active.question?.id).toBe('q-2')
    expect(active.step).toBe(2)
    expect(active.total).toBe(3)
  })

  it('reaches the last step', () => {
    const active = activeQuestionFor(batchOf(3, 2), 'codex-1')
    expect(active.question?.id).toBe('q-3')
    expect(active.step).toBe(3)
    expect(active.total).toBe(3)
  })

  it('orders by batch position rather than by whatever order it was handed', () => {
    const reversed = [...batchOf(3)].reverse()
    expect(activeQuestionFor(reversed, 'codex-1').question?.id).toBe('q-1')
  })

  it('falls back to creation time when two questions share a position', () => {
    // Two separate single questions both sit at batch_index 0; the older one is answered first.
    const older = question({ id: 'q-old', created_at: '2026-08-07T09:00:00Z' })
    const newer = question({ id: 'q-new', created_at: '2026-08-07T11:00:00Z' })
    expect(activeQuestionFor([newer, older], 'codex-1').question?.id).toBe('q-old')
  })

  it('counts only the active question’s own batch', () => {
    // An unrelated question outstanding at the same time must not inflate the step counter —
    // this is exactly what the old "outstanding questions" counter got wrong.
    const other = question({ id: 'q-other', batch_id: null, batch_size: 1, batch_index: 0 })
    const active = activeQuestionFor([...batchOf(2), other], 'codex-1')
    expect(active.total).toBe(2)
    expect(active.step).toBe(1)
  })

  it('survives rows that predate batching and carry no batch fields', () => {
    const legacy = {
      ...question(),
      batch_id: undefined,
      batch_index: undefined,
      batch_size: undefined,
    } as Question
    const active = activeQuestionFor([legacy], 'codex-1')
    expect(active.question?.id).toBe('q-1')
    expect(active.step).toBe(1)
    expect(active.total).toBe(1)
  })
})
