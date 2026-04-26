import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Question } from '@/api/questions'

interface QuestionInterruptCardProps {
  questions: Question[]
  compact?: boolean
  onNavigateToQuestions: () => void
}

export function QuestionInterruptCard({ questions, compact = false, onNavigateToQuestions }: QuestionInterruptCardProps) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())

  const visible = questions.filter((q) => !dismissed.has(q.id))
  if (visible.length === 0) return null

  const first = visible[0]

  return (
    <div
      style={{
        background: 'rgba(245,158,11,0.06)',
        border: '1px solid rgba(245,158,11,0.25)',
        borderRadius: 'var(--radius)',
        padding: compact ? '8px 10px' : '12px 14px',
        marginBottom: 8,
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p
            style={{
              fontSize: compact ? 11 : 12,
              fontWeight: 600,
              color: 'var(--amber)',
              marginBottom: 4,
            }}
          >
            ⚠ {first.from_agent} is waiting
          </p>
          <p
            style={{
              fontSize: compact ? 11 : 13,
              color: 'var(--text)',
              lineHeight: 1.4,
              ...(compact ? { display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' } : {}),
            }}
          >
            {first.question}
          </p>
          <p style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
            {formatDistanceToNow(new Date(first.created_at), { addSuffix: true })}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={onNavigateToQuestions}
            style={{
              background: 'var(--amber)',
              color: '#000',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              padding: '4px 10px',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Answer
          </button>
          {!compact && (
            <button
              onClick={() => setDismissed((prev) => new Set([...prev, first.id]))}
              style={{
                background: 'transparent',
                color: 'var(--text-3)',
                border: 'none',
                borderRadius: 'var(--radius-sm)',
                padding: '4px 8px',
                fontSize: 12,
                cursor: 'pointer',
              }}
            >
              Dismiss
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
