import { formatDistanceToNow } from 'date-fns'
import { AlertTriangle, HelpCircle } from 'lucide-react'
import { useQuestions } from '@/api/questions'
import { AnswerForm } from './AnswerForm'
import { EmptyState } from '@/components/common/EmptyState'
import { Badge } from '@/components/common/Badge'

export function QuestionsPanel() {
  const { data: unanswered, isLoading } = useQuestions(false)
  const { data: answered } = useQuestions(true)

  if (isLoading) {
    return <div className="p-6 text-sm text-white/40">Loading questions…</div>
  }

  const blocking = unanswered?.filter((q) => q.blocking) ?? []
  const nonBlocking = unanswered?.filter((q) => !q.blocking) ?? []

  return (
    <div className="p-5 space-y-5">
      {blocking.length > 0 && (
        <div className="rounded-xl p-4" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.20)' }}>
          <div className="flex items-center gap-2 mb-3 text-red-400">
            <AlertTriangle className="h-4 w-4" />
            <span className="text-sm font-semibold">Blocking — Agents are waiting for your answer</span>
          </div>
          <div className="space-y-3">
            {blocking.map((q) => (
              <div key={q.id} className="glass-card rounded-xl p-4" style={{ borderColor: 'rgba(239,68,68,0.25)' }}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-red-400">{q.from_agent}</span>
                  <span className="text-xs text-white/25">
                    {formatDistanceToNow(new Date(q.created_at), { addSuffix: true })}
                  </span>
                </div>
                <p className="text-sm text-white/80">{q.question}</p>
                <AnswerForm questionId={q.id} />
              </div>
            ))}
          </div>
        </div>
      )}

      {nonBlocking.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold mb-3 text-white/40 uppercase tracking-wider">Unanswered</h3>
          <div className="space-y-2.5">
            {nonBlocking.map((q) => (
              <div key={q.id} className="glass-card rounded-xl p-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-white/60">{q.from_agent}</span>
                  <span className="text-xs text-white/25">
                    {formatDistanceToNow(new Date(q.created_at), { addSuffix: true })}
                  </span>
                </div>
                <p className="text-sm text-white/80">{q.question}</p>
                <AnswerForm questionId={q.id} />
              </div>
            ))}
          </div>
        </div>
      )}

      {unanswered?.length === 0 && (
        <EmptyState icon={HelpCircle} title="No pending questions" description="Agent questions will appear here." />
      )}

      {answered && answered.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-semibold text-white/30 hover:text-white/60 uppercase tracking-wider">
            Answered ({answered.length})
          </summary>
          <div className="mt-3 space-y-2">
            {answered.map((q) => (
              <div key={q.id} className="glass-card rounded-xl p-3 opacity-50">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-white/50">{q.from_agent}</span>
                  <Badge variant="success">answered</Badge>
                </div>
                <p className="text-xs text-white/60">{q.question}</p>
                {q.answer && <p className="text-xs text-white/30 mt-1">→ {q.answer}</p>}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
