import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Question, useAnswerQuestion } from '@/api/questions'

interface AgentQuestionCardProps {
  questions: Question[]
  /** Only this agent's questions; the card sits inside one conversation. */
  agent: string
}

/** An unanswered question from the agent whose conversation this is.
 *
 * `QuestionsPanel` already lists questions elsewhere, but a blocking agent is waiting *now* and
 * the operator is reading the conversation, not the overview. This puts the question where they
 * already are.
 */
export function AgentQuestionCard({ questions, agent }: AgentQuestionCardProps) {
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const answer = useAnswerQuestion()
  const pending = questions.filter((q) => q.from_agent === agent && !q.answered)
  if (pending.length === 0) return null

  return (
    <div className="flex flex-col gap-2" data-testid="agent-questions">
      {pending.map((question) => {
        const draft = drafts[question.id] ?? ''
        const submit = () => {
          if (!draft.trim()) return
          answer.mutate({ id: question.id, answer: draft.trim() })
          setDrafts((d) => ({ ...d, [question.id]: '' }))
        }
        return (
          <div
            key={question.id}
            data-testid={`agent-question-${question.id}`}
            style={{
              background: 'color-mix(in srgb, var(--blue) 6%, transparent)',
              border: '1px solid color-mix(in srgb, var(--blue) 25%, transparent)',
              borderRadius: 'var(--radius)',
              padding: '10px 12px',
            }}
          >
            <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--blue)', marginBottom: 4 }}>
              {agent} is asking
            </p>
            <p style={{ fontSize: 13, color: 'var(--text)', marginBottom: 8 }}>
              {question.question}
            </p>
            <div className="flex items-center gap-2">
              <input
                data-testid={`agent-question-input-${question.id}`}
                value={draft}
                placeholder="Your answer"
                onChange={(e) => setDrafts((d) => ({ ...d, [question.id]: e.target.value }))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    submit()
                  }
                }}
                style={{
                  flex: 1,
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  padding: '6px 8px',
                  fontSize: 12,
                  color: 'var(--text)',
                }}
              />
              <Button
                size="sm"
                data-testid={`agent-question-send-${question.id}`}
                disabled={answer.isPending || !draft.trim()}
                onClick={submit}
              >
                Answer
              </Button>
            </div>
            {question.blocking && (
              <p style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 6 }}>
                The agent is waiting, and will continue without an answer if nobody replies.
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
