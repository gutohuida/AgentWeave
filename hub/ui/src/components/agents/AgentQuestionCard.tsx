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
 * already are, in the composer's own chrome.
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
        const send = (value: string) => {
          if (!value.trim()) return
          answer.mutate({ id: question.id, answer: value.trim() })
          setDrafts((d) => ({ ...d, [question.id]: '' }))
        }
        const options = question.options ?? []
        return (
          <div
            key={question.id}
            data-testid={`agent-question-${question.id}`}
            className="conversation-interject"
          >
            <p className="interject-eyebrow" style={{ marginBottom: 4 }}>
              {agent} is asking
            </p>
            <p style={{ fontSize: 13, color: 'var(--text)', marginBottom: 10 }}>
              {question.question}
            </p>

            {options.length > 0 && (
              <div className="flex flex-col gap-1.5" style={{ marginBottom: 10 }}>
                {options.map((option, index) => (
                  <button
                    key={`${question.id}-${index}`}
                    type="button"
                    className="interject-choice"
                    data-testid={`agent-question-option-${question.id}-${index}`}
                    disabled={answer.isPending}
                    onClick={() => send(option)}
                  >
                    {option}
                  </button>
                ))}
              </div>
            )}

            <div className="flex items-center gap-2">
              <input
                data-testid={`agent-question-input-${question.id}`}
                value={draft}
                // Offered options never confine the operator; the box stays, and says so.
                placeholder={options.length > 0 ? 'Or answer in your own words' : 'Your answer'}
                onChange={(e) => setDrafts((d) => ({ ...d, [question.id]: e.target.value }))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    send(draft)
                  }
                }}
                className="interject-input"
              />
              <Button
                size="sm"
                data-testid={`agent-question-send-${question.id}`}
                disabled={answer.isPending || !draft.trim()}
                onClick={() => send(draft)}
              >
                Answer
              </Button>
            </div>

            {question.blocking && (
              <p style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 8 }}>
                The agent is waiting, and will continue without an answer if nobody replies.
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
