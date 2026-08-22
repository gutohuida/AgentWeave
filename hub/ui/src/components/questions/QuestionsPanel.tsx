import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { useQuestions, type Question } from '@/api/questions'
import { AnswerForm } from './AnswerForm'
import { EmptyState } from '@/components/common/EmptyState'
import { Badge } from '@/components/common/Badge'
import { hubDate } from '@/lib/hubTime'

function QuestionRow({ question, blocking = false }: { question: Question; blocking?: boolean }) {
  const labelId = `question-${question.id}`
  return (
    <article className="question-row p-4">
      <div className="mb-1 flex items-center justify-between gap-3">
        <span className="text-[13px] font-medium" style={{ color: blocking ? 'var(--red)' : 'var(--text)' }}>{question.from_agent}</span>
        <time className="shrink-0 text-[11px] tabular-nums" dateTime={question.created_at} style={{ color: 'var(--text-3)' }}>
          {formatDistanceToNow(hubDate(question.created_at), { addSuffix: true })}
        </time>
      </div>
      <p id={labelId} className="text-sm leading-6" style={{ color: 'var(--text)' }}>{question.question}</p>
      <AnswerForm questionId={question.id} agent={question.from_agent} labelledBy={labelId} />
    </article>
  )
}

export function QuestionsPanel() {
  const { data: unanswered, isLoading } = useQuestions(false)
  const { data: answered } = useQuestions(true)

  if (isLoading) {
    return (
      <div className="questions-page space-y-3 p-5" aria-label="Loading questions">
        {[0, 1].map((item) => (
          <div key={item} className="question-row p-4" aria-hidden="true">
            <div className="trust-state-skeleton w-24" />
            <div className="trust-state-skeleton mt-3 w-full" />
            <div className="trust-state-skeleton mt-2 w-3/4" />
            <div className="trust-state-skeleton mt-4 h-14 w-full" />
          </div>
        ))}
      </div>
    )
  }

  const blocking = unanswered?.filter((question) => question.blocking) ?? []
  const nonBlocking = unanswered?.filter((question) => !question.blocking) ?? []

  return (
    <div className="questions-page space-y-5 p-5">
      <header>
        <h1 className="text-lg font-semibold" style={{ color: 'var(--text)' }}>Questions</h1>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>Decisions waiting for an operator answer.</p>
      </header>

      {blocking.length > 0 && (
        <section className="rounded-[var(--radius-xl)] p-4" aria-labelledby="blocking-questions" style={{ background: 'color-mix(in srgb, var(--red) 6%, transparent)', border: '1px solid color-mix(in srgb, var(--red) 20%, transparent)' }}>
          <h2 id="blocking-questions" className="mb-3 flex items-center gap-2 text-[13px] font-medium" style={{ color: 'var(--red)' }}>
            <Icon name="warning" size={17} /> Blocking — agents are waiting for your answer
          </h2>
          <div className="space-y-3">{blocking.map((question) => <QuestionRow key={question.id} question={question} blocking />)}</div>
        </section>
      )}

      {nonBlocking.length > 0 && (
        <section aria-labelledby="unanswered-questions">
          <h2 id="unanswered-questions" className="mb-3 text-sm font-medium" style={{ color: 'var(--text)' }}>Unanswered</h2>
          <div className="space-y-2.5">{nonBlocking.map((question) => <QuestionRow key={question.id} question={question} />)}</div>
        </section>
      )}

      {unanswered?.length === 0 && <EmptyState icon="help" title="No pending questions" description="Agent questions will appear here." />}

      {answered && answered.length > 0 && (
        <details className="answered-questions mt-2">
          <summary className="flex cursor-pointer select-none items-center text-[13px] font-medium transition-colors" style={{ color: 'var(--text-3)' }}>
            <Icon name="expand_more" size={16} className="mr-1" /> Answered ({answered.length})
          </summary>
          <div className="mt-3 space-y-2">
            {answered.map((question) => (
              <article key={question.id} className="question-row p-3 opacity-65">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>{question.from_agent}</span>
                  <Badge variant="success">answered</Badge>
                </div>
                <p className="text-xs" style={{ color: 'var(--text)' }}>{question.question}</p>
                {question.answer && <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>→ {question.answer}</p>}
              </article>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
