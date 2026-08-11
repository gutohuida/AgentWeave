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

describe('a question nobody is waiting on gets out of the way', () => {
  it('never picks a declined question', () => {
    const questions = [
      question({ id: 'q-declined', declined: true, created_at: '2026-08-07T09:00:00Z' }),
      question({ id: 'q-open', created_at: '2026-08-07T10:00:00Z' }),
    ]

    expect(activeQuestionFor(questions, 'codex-1').question?.id).toBe('q-open')
  })

  it('returns nothing when every question has been declined', () => {
    const questions = [question({ id: 'q-a', declined: true }), question({ id: 'q-b', declined: true })]

    expect(activeQuestionFor(questions, 'codex-1').question).toBeNull()
  })

  it('asks the live question first, even though the stale one is older', () => {
    /**
     * The case that started this: an agent asks, gives up, asks again. Strict oldest-first showed
     * the dead question and routed the answer to it — correctly, and confusingly.
     */
    const questions = [
      question({ id: 'q-stale', asker_waiting: false, created_at: '2026-08-07T09:00:00Z' }),
      question({ id: 'q-live', asker_waiting: true, created_at: '2026-08-07T10:00:00Z' }),
    ]

    expect(activeQuestionFor(questions, 'codex-1').question?.id).toBe('q-live')
  })

  it('treats an absent asker_waiting as still waiting', () => {
    // Matches the Hub's own presumption for a question with no recorded asking run.
    const questions = [
      question({ id: 'q-known-stale', asker_waiting: false, created_at: '2026-08-07T09:00:00Z' }),
      question({ id: 'q-unknown', created_at: '2026-08-07T11:00:00Z' }),
    ]

    expect(activeQuestionFor(questions, 'codex-1').question?.id).toBe('q-unknown')
  })

  it('keeps a batch contiguous — the property the live-first sort depends on', () => {
    /**
     * Putting a whole-queue predicate ahead of the within-batch order is only safe because every
     * question in a batch comes from one `ask_user` call by one run, so they share one
     * `asker_waiting`. If that ever stopped holding, a batch would interleave with another and the
     * "2 of 3" counter would step through questions from two different asks.
     */
    const stale = batchOf(3).map((q) => ({ ...q, id: `stale-${q.id}`, asker_waiting: false }))
    const live = batchOf(3).map((q) => ({
      ...q,
      id: `live-${q.id}`,
      batch_id: 'qbatch-2',
      asker_waiting: true,
      created_at: `2026-08-07T11:0${q.batch_index}:00Z`,
    }))

    // Interleaved on the way in, so ordering is doing the work rather than input order.
    const mixed = [stale[0], live[0], stale[1], live[1], stale[2], live[2]]
    const active = activeQuestionFor(mixed, 'codex-1')

    expect(active.question?.id).toBe('live-q-1')
    expect(active.step).toBe(1)
    expect(active.total).toBe(3)
  })

  it('falls back to the stale batch once the live one is answered', () => {
    const stale = batchOf(1).map((q) => ({ ...q, id: 'stale-only', asker_waiting: false }))
    const active = activeQuestionFor(stale, 'codex-1')

    // Still offered — declining is what removes it, not staleness on its own.
    expect(active.question?.id).toBe('stale-only')
  })
})
