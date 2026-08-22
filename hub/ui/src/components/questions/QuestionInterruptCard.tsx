import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import { Question } from '@/api/questions'
import { hubDate } from '@/lib/hubTime'

interface QuestionInterruptCardProps {
  questions: Question[]
  compact?: boolean
  onNavigateToQuestions: () => void
}

export function QuestionInterruptCard({ questions, compact = false, onNavigateToQuestions }: QuestionInterruptCardProps) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const visible = questions.filter((question) => !dismissed.has(question.id))
  if (visible.length === 0) return null
  const first = visible[0]

  return (
    <div
      className="conversation-interject !w-full"
      role="region"
      aria-label={`${first.from_agent} is waiting for an answer`}
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
            <Icon name="warning" size={14} /> {first.from_agent} is waiting
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
