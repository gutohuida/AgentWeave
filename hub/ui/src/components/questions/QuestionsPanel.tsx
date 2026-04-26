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
    return <div className="p-6 text-sm" style={{ color: 'var(--text-3)' }}>Loading questions…</div>
  }

  const blocking    = unanswered?.filter((q) => q.blocking)  ?? []
  const nonBlocking = unanswered?.filter((q) => !q.blocking) ?? []

  return (
    <div className="p-5 space-y-5">
      {/* Blocking questions */}
      {blocking.length > 0 && (
        <div
          className="rounded-xl p-4"
          style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)' }}
        >
          <div className="flex items-center gap-2 mb-3" style={{ color: 'var(--red)' }}>
            <Icon name="warning" size={18} fill={1} />
            <span className="text-[13px] font-medium">Blocking — Agents are waiting for your answer</span>
          </div>
          <div className="space-y-3">
            {blocking.map((q) => (
              <div
                key={q.id}
                className="rounded-lg p-4"
                style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[13px] font-medium" style={{ color: 'var(--red)' }}>{q.from_agent}</span>
                  <span className="text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
                    {formatDistanceToNow(new Date(q.created_at), { addSuffix: true })}
                  </span>
                </div>
                <p className="text-sm" style={{ color: 'var(--text)' }}>{q.question}</p>
                <AnswerForm questionId={q.id} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Non-blocking unanswered */}
      {nonBlocking.length > 0 && (
        <div>
          <h3 className="text-sm font-medium mb-3" style={{ color: 'var(--text)' }}>Unanswered</h3>
          <div className="space-y-2.5">
            {nonBlocking.map((q) => (
              <div
                key={q.id}
                className="rounded-lg p-4"
                style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>{q.from_agent}</span>
                  <span className="text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
                    {formatDistanceToNow(new Date(q.created_at), { addSuffix: true })}
                  </span>
                </div>
                <p className="text-sm" style={{ color: 'var(--text)' }}>{q.question}</p>
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
            className="cursor-pointer text-[13px] font-medium select-none transition-colors"
            style={{ color: 'var(--text-3)' }}
          >
            <Icon name="expand_more" size={16} className="inline mr-1" />
            Answered ({answered.length})
          </summary>
          <div className="mt-3 space-y-2">
            {answered.map((q) => (
              <div key={q.id} className="rounded-lg p-3" style={{ background: 'var(--surface-2)', opacity: 0.65 }}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>{q.from_agent}</span>
                  <Badge variant="success">answered</Badge>
                </div>
                <p className="text-xs" style={{ color: 'var(--text)' }}>{q.question}</p>
                {q.answer && (
                  <p className="text-xs mt-1" style={{ color: 'var(--text-3)' }}>→ {q.answer}</p>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
