import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import { Question } from '@/api/questions'
import { hubDate } from '@/lib/hubTime'
import { isWaitedOn } from '@/lib/pendingQuestions'

interface QuestionInterruptCardProps {
  questions: Question[]
  compact?: boolean
  onNavigateToQuestions: () => void
}

export function QuestionInterruptCard({ questions, compact = false, onNavigateToQuestions }: QuestionInterruptCardProps) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  // `?answered=false` leaves declined rows out since F228; kept for a Hub older than that, where
  // `declined` being its own column meant closing a question did not make it answered (F386).
  const visible = questions.filter((question) => !question.declined && !dismissed.has(question.id))
  if (visible.length === 0) return null
  // A question someone is waiting on comes first. The route orders oldest first, and a question
  // nobody waits on (the Hub's non-blocking record of a refused capability is never swept) would
  // otherwise sit in front of every later one an agent is blocked on.
  const first = visible.find(isWaitedOn) ?? visible[0]
  const waiting = isWaitedOn(first)

  return (
    <div
      className="conversation-interject !w-full"
      role="region"
      aria-label={waiting ? `${first.from_agent} is waiting for an answer` : `${first.from_agent} is asking a question`}
      style={{
        background: 'color-mix(in srgb, var(--amber) 6%, var(--surface-2))',
        borderColor: 'color-mix(in srgb, var(--amber) 25%, var(--border))',
        padding: compact ? '8px 10px' : '12px 14px',
        marginBottom: 8,
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5" style={{ fontSize: compact ? 11 : 12, fontWeight: 600, color: 'var(--amber)', marginBottom: 4 }}>
            <Icon name={waiting ? 'warning' : 'help'} size={14} /> {first.from_agent} {waiting ? 'is waiting' : 'is asking'}
          </p>
          <p style={{ fontSize: compact ? 11 : 13, color: 'var(--text)', lineHeight: 1.4, ...(compact ? { display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' } : {}) }}>
            {first.question}
          </p>
          <p style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
            {formatDistanceToNow(hubDate(first.created_at), { addSuffix: true })}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button onClick={onNavigateToQuestions} variant="primary" size="xs">Answer</Button>
          {!compact && (
            <Button variant="ghost" size="xs" onClick={() => setDismissed((previous) => new Set([...previous, first.id]))}>Dismiss</Button>
          )}
        </div>
      </div>
    </div>
  )
}
