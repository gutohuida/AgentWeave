import { Button } from '@/components/ui/button'
import { UnaskedQuestion, useResolveUnaskedQuestion } from '@/api/unaskedQuestions'

interface UnaskedQuestionCardProps {
  questions: UnaskedQuestion[]
  /** Only this agent's questions are shown; the card sits inside one conversation. */
  agent: string
}

/** A question the agent wrote as text and then stopped on, without asking anyone.
 *
 * It sits beside `PermissionRequestCard` rather than in the scrolling timeline for the same
 * reason: this is something the operator has to act on, and it must not scroll away. The tone is
 * lower-key than a permission request, because nothing is blocked and the detection is allowed to
 * be occasionally wrong — dismissing costs one click.
 */
export function UnaskedQuestionCard({ questions, agent }: UnaskedQuestionCardProps) {
  const resolve = useResolveUnaskedQuestion()
  const pending = questions.filter((q) => q.agent === agent && q.status === 'pending')
  if (pending.length === 0) return null

  return (
    <div className="flex flex-col gap-2" data-testid="unasked-questions">
      {pending.map((question) => (
        <div
          key={question.id}
          data-testid={`unasked-question-${question.id}`}
          className="conversation-interject"
        >
          <p className="interject-eyebrow" style={{ marginBottom: 4 }}>
            {agent} ended its turn on a question it never asked
          </p>
          <p style={{ fontSize: 13, color: 'var(--text)', marginBottom: 10 }}>
            {question.question}
          </p>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              data-testid={`unasked-ask-${question.id}`}
              disabled={resolve.isPending}
              onClick={() => resolve.mutate({ id: question.id, action: 'ask' })}
            >
              Ask this properly
            </Button>
            <Button
              size="sm"
              variant="outline"
              data-testid={`unasked-dismiss-${question.id}`}
              disabled={resolve.isPending}
              onClick={() => resolve.mutate({ id: question.id, action: 'dismiss' })}
            >
              Dismiss
            </Button>
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
              Asking starts a new turn, so {agent} can put the question to you properly.
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
