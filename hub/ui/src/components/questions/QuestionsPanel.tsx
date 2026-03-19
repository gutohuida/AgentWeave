import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { useQuestions } from '@/api/questions'
import { AnswerForm } from './AnswerForm'
import { EmptyState } from '@/components/common/EmptyState'
import { Badge } from '@/components/common/Badge'

export function QuestionsPanel() {
  const { data: unanswered, isLoading } = useQuestions(false)
  const { data: answered } = useQuestions(true)

  if (isLoading) {
    return <div className="p-6 m3-body-medium" style={{ color: 'var(--on-sv)' }}>Loading questions…</div>
  }

  const blocking    = unanswered?.filter((q) => q.blocking)  ?? []
  const nonBlocking = unanswered?.filter((q) => !q.blocking) ?? []

  return (
    <div className="p-5 space-y-5">
      {/* Blocking questions */}
      {blocking.length > 0 && (
        <div
          className="rounded-2xl p-4"
          style={{ background: 'color-mix(in srgb, var(--error-cont) 35%, transparent)', border: '1px solid var(--error-cont)' }}
        >
          <div className="flex items-center gap-2 mb-3" style={{ color: 'var(--destructive)' }}>
            <Icon name="warning" size={18} fill={1} />
            <span className="m3-title-small">Blocking — Agents are waiting for your answer</span>
          </div>
          <div className="space-y-3">
            {blocking.map((q) => (
              <div
                key={q.id}
                className="m3-card-outlined rounded-xl p-4"
                style={{ borderColor: 'var(--error-cont)' }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="m3-label-large" style={{ color: 'var(--destructive)' }}>{q.from_agent}</span>
                  <span className="m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
                    {formatDistanceToNow(new Date(q.created_at), { addSuffix: true })}
                  </span>
                </div>
                <p className="m3-body-medium" style={{ color: 'var(--foreground)' }}>{q.question}</p>
                <AnswerForm questionId={q.id} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Non-blocking unanswered */}
      {nonBlocking.length > 0 && (
        <div>
          <h3 className="m3-title-medium mb-3" style={{ color: 'var(--foreground)' }}>Unanswered</h3>
          <div className="space-y-2.5">
            {nonBlocking.map((q) => (
              <div key={q.id} className="m3-card-filled rounded-xl p-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="m3-label-large" style={{ color: 'var(--foreground)' }}>{q.from_agent}</span>
                  <span className="m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
                    {formatDistanceToNow(new Date(q.created_at), { addSuffix: true })}
                  </span>
                </div>
                <p className="m3-body-medium" style={{ color: 'var(--foreground)' }}>{q.question}</p>
                <AnswerForm questionId={q.id} />
              </div>
            ))}
          </div>
        </div>
      )}

      {unanswered?.length === 0 && (
        <EmptyState icon="help" title="No pending questions" description="Agent questions will appear here." />
      )}

      {/* Answered (collapsed) */}
      {answered && answered.length > 0 && (
        <details className="mt-2">
          <summary
            className="cursor-pointer m3-label-large select-none transition-colors"
            style={{ color: 'var(--on-sv)' }}
          >
            <Icon name="expand_more" size={16} className="inline mr-1" />
            Answered ({answered.length})
          </summary>
          <div className="mt-3 space-y-2">
            {answered.map((q) => (
              <div key={q.id} className="m3-card-filled rounded-xl p-3" style={{ opacity: 0.65 }}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="m3-label-large" style={{ color: 'var(--foreground)' }}>{q.from_agent}</span>
                  <Badge variant="success">answered</Badge>
                </div>
                <p className="m3-body-small" style={{ color: 'var(--foreground)' }}>{q.question}</p>
                {q.answer && (
                  <p className="m3-body-small mt-1" style={{ color: 'var(--on-sv)' }}>→ {q.answer}</p>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
