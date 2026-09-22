import { describe, expect, it } from 'vitest'
import { activeQuestionFor } from '@/lib/pendingQuestions'
import type { Question } from '@/api/questions'

// From the adversarial review of 229a708. Design D14 accepts that the
// record can be the question the refused agent's tray shows. The consequence D14 does not state:
// AgentOutputPanel routes the composer's reply to `activeQuestionFor(...).question`, so the
// operator's answer to the question the live run is blocked on lands on the refusal record.
function q(overrides: Partial<Question>): Question {
  return { id: 'x', project_id: 'p', from_agent: 'lead', question: '?', blocking: true, answered: false, created_at: '2026-09-22T10:00:00Z', ...overrides }
}

describe('refused agent tray', () => {
  it('shows the question the live run is blocked on, not the older refusal record', () => {
    const rows = [
      // Shape GET /questions?answered=false returns for the record: no run → asker_waiting true.
      q({ id: 'q-record', blocking: false, asker_waiting: true, created_at: '2026-09-22T10:00:00Z' }),
      q({ id: 'q-live', blocking: true, asker_waiting: true, created_at: '2026-09-22T10:05:00Z' }),
    ]
    expect(activeQuestionFor(rows, 'lead').question?.id).toBe('q-live')
  })
})

describe('a question no run asked stays out of the agent tray', () => {
  it('leaves the refusal record out, so it cannot own the composer', () => {
    // The record alone: the tray used to show it and route every typed message to it as an answer.
    const rows = [q({ id: 'q-record', blocking: false, asker_waiting: true, created_by_run_id: null })]
    expect(activeQuestionFor(rows, 'lead').question).toBeNull()
  })

  it('keeps a question a run asked, blocking or not', () => {
    const rows = [
      q({ id: 'q-record', blocking: false, created_by_run_id: null }),
      q({ id: 'q-note', blocking: false, asker_waiting: true, created_by_run_id: 'run-1' }),
    ]
    expect(activeQuestionFor(rows, 'lead').question?.id).toBe('q-note')
  })

  it('does not let an older question posted through the operator route outrank a live one (F381)', () => {
    // The operator route stores `created_by_run_id: null`, and the Hub presumes an unknown asker
    // is waiting — so this row reads `blocking` and `asker_waiting` both true, like the live ask.
    const rows = [
      q({ id: 'q-posted', blocking: true, asker_waiting: true, created_by_run_id: null, created_at: '2026-09-22T10:00:00Z' }),
      q({ id: 'q-live', blocking: true, asker_waiting: true, created_by_run_id: 'run-1', created_at: '2026-09-22T10:05:00Z' }),
    ]
    expect(activeQuestionFor(rows, 'lead').question?.id).toBe('q-live')
  })

  it('reads an absent field as asked by a run, so an older Hub keeps its tray', () => {
    // A bundle reaches the operator's app on reload, before their Hub restarts onto the field.
    const rows = [q({ id: 'q-live' })]
    expect(activeQuestionFor(rows, 'lead').question?.id).toBe('q-live')
  })
})
