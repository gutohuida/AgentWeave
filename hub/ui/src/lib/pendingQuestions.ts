import type { Question } from '@/api/questions'

export interface ActiveQuestion {
  /** The question the operator should be answering right now, or null if there is none. */
  question: Question | null
  /** 1-based position within its batch — the "2" in "2 of 3". */
  step: number
  /** How many questions the batch holds. 1 for a question asked on its own. */
  total: number
}

const NONE: ActiveQuestion = { question: null, step: 0, total: 0 }

/** Which of an agent's outstanding questions is being answered, and where it sits in its batch.
 *
 * One selector, used by both the card that displays the question and the panel that routes the
 * composer's submission to it. They used to derive this independently, which was harmless while
 * only one question could be outstanding. With batches it is not: if the two disagree on
 * ordering, the operator reads question 2 and their answer lands on question 1, silently.
 *
 * Ordering is `batch_index` then `created_at` — a total order, rather than whatever order the API
 * happened to return.
 */
export function activeQuestionFor(questions: Question[], agent: string): ActiveQuestion {
  const pending = questions
    .filter((q) => q.from_agent === agent && !q.answered)
    .sort((a, b) => {
      const byIndex = (a.batch_index ?? 0) - (b.batch_index ?? 0)
      if (byIndex !== 0) return byIndex
      return (a.created_at ?? '').localeCompare(b.created_at ?? '')
    })

  const question = pending[0]
  if (!question) return NONE

  const total = question.batch_size ?? 1
  // Only the *unanswered* rows are on hand — answered ones drop out of what the panel fetches.
  // `batch_size` is stored on the row precisely so the count can be recovered from what is left.
  const remaining = question.batch_id
    ? pending.filter((q) => q.batch_id === question.batch_id).length
    : 1
  const step = Math.max(1, Math.min(total, total - remaining + 1))

  return { question, step, total }
}
