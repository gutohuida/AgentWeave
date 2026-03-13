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
    return <div className="p-6 text-sm text-muted-foreground">Loading questions…</div>
  }

  const blocking = unanswered?.filter((q) => q.blocking) ?? []
  const nonBlocking = unanswered?.filter((q) => !q.blocking) ?? []

  return (
    <div className="p-6 space-y-6 overflow-auto">
      {blocking.length > 0 && (
        <div className="rounded-lg border border-red-300 bg-red-50 p-4">
          <div className="flex items-center gap-2 mb-3 text-red-700">
            <AlertTriangle className="h-4 w-4" />
            <span className="text-sm font-semibold">Blocking — Agents are waiting for your answer</span>
          </div>
          <div className="space-y-4">
            {blocking.map((q) => (
              <div key={q.id} className="rounded-lg border border-red-200 bg-white p-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-red-600">{q.from_agent}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatDistanceToNow(new Date(q.created_at), { addSuffix: true })}
                  </span>
                </div>
                <p className="text-sm">{q.question}</p>
                <AnswerForm questionId={q.id} />
              </div>
            ))}
          </div>
        </div>
      )}

      {nonBlocking.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-3">Unanswered</h3>
          <div className="space-y-3">
            {nonBlocking.map((q) => (
              <div key={q.id} className="rounded-lg border p-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium">{q.from_agent}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatDistanceToNow(new Date(q.created_at), { addSuffix: true })}
                  </span>
                </div>
                <p className="text-sm">{q.question}</p>
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
        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-semibold text-muted-foreground hover:text-foreground">
            Answered ({answered.length})
          </summary>
          <div className="mt-3 space-y-2">
            {answered.map((q) => (
              <div key={q.id} className="rounded-lg border bg-muted/20 p-3 opacity-70">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium">{q.from_agent}</span>
                  <Badge variant="success">answered</Badge>
                </div>
                <p className="text-xs">{q.question}</p>
                {q.answer && <p className="text-xs text-muted-foreground mt-1">→ {q.answer}</p>}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
