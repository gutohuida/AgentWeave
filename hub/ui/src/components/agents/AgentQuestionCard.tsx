import { useEffect } from 'react'
import { Icon } from '@/components/common/Icon'
import { Question } from '@/api/questions'
import { activeQuestionFor } from '@/lib/pendingQuestions'

interface AgentQuestionCardProps {
  questions: Question[]
  /** Only this agent's questions; the card sits inside one conversation. */
  agent: string
  /** Labels chosen so far. Owned by the panel's parent, because the composer's send button is
   *  what confirms them — there is no submit control in here. */
  selected: string[]
  onToggle: (label: string) => void
  /** True while the answer is in flight. */
  isResponding: boolean
  /** Set once the operator starts typing: a written answer supersedes any selection, so the
   *  selection stops looking chosen. */
  isTyping: boolean
  /** Close this question without answering it. Omitted, no dismiss control is offered. */
  onDecline?: (questionId: string) => void
  /** True while a decline is in flight. */
  isDeclining?: boolean
}

/** The question an agent is waiting on, rendered as part of the composer.
 *
 * Deliberately has no text input and no submit button of its own. Free text goes through the
 * real composer below, and its send button confirms whatever is selected here — one place to
 * answer from, which is what makes this read as an extension of the chat box rather than a
 * widget sitting on top of one.
 */
export function AgentQuestionCard({
  questions,
  agent,
  selected,
  onToggle,
  isResponding,
  isTyping,
  onDecline,
  isDeclining = false,
}: AgentQuestionCardProps) {
  const { question, step, total } = activeQuestionFor(questions, agent)

  // Number keys pick an option, as long as the operator is not writing in a field. The badges
  // on each row are what make this discoverable; a shortcut nobody can see is not a feature.
  useEffect(() => {
    if (!question || isResponding) return
    const options = question.options ?? []
    const handler = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return
      const digit = Number.parseInt(event.key, 10)
      if (Number.isNaN(digit) || digit < 1 || digit > 9) return
      const option = options[digit - 1]
      if (!option) return
      event.preventDefault()
      onToggle(option.label)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [question, isResponding, onToggle])

  if (!question) return null
  const options = question.options ?? []
  const multi = question.multi_select === true
  // The asking run has ended, so its `ask_user` call is gone: nothing is holding for this, and an
  // answer now would only be queued as a message. Said out loud because otherwise a question that
  // reads exactly like a live one asks the operator for something nobody is waiting on.
  const nobodyWaiting = question.asker_waiting === false

  return (
    <div className={`conversation-interject${nobodyWaiting ? ' is-stale' : ''}`} data-testid={`agent-question-${question.id}`}>
      <div className="flex items-center gap-2" style={{ marginBottom: 6 }}>
        <span className="interject-eyebrow">{question.header || `${agent} is asking`}</span>
        {/* Position within this batch, not a count of everything outstanding. The old counter
            read like a step counter while being a queue depth, which said "1/2" to someone with
            one question in front of them and nothing else coming. */}
        {total > 1 && (
          <span className="interject-count" data-testid="agent-question-count">
            {step}/{total}
          </span>
        )}
        {nobodyWaiting && (
          <span
            data-testid="agent-question-stale"
            title="The run that asked this has ended. Answering now would reach it as a new message, not as the answer it was waiting for."
            style={{ fontSize: 10, color: 'var(--text-3)' }}
          >
            no longer waiting
          </span>
        )}
        {onDecline && (
          <button
            type="button"
            aria-label="Dismiss this question without answering"
            title="Dismiss without answering"
            data-testid={`agent-question-decline-${question.id}`}
            disabled={isResponding || isDeclining}
            onClick={() => onDecline(question.id)}
            className="ml-auto shrink-0 p-0.5 rounded"
            style={{ color: 'var(--text-3)', background: 'transparent', border: 'none' }}
          >
            <Icon name="x" size={14} />
          </button>
        )}
      </div>

      <p style={{ fontSize: 13, color: 'var(--text)' }}>{question.question}</p>
      {multi && (
        <p style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>
          Select one or more options.
        </p>
      )}

      <div className="flex flex-col gap-1.5" style={{ marginTop: 10 }}>
        {options.map((option, index) => {
          const isSelected = !isTyping && selected.includes(option.label)
          const shortcut = index < 9 ? index + 1 : null
          return (
            <button
              key={`${question.id}-${index}`}
              type="button"
              className="interject-choice"
              data-selected={isSelected ? 'true' : undefined}
              data-testid={`agent-question-option-${question.id}-${index}`}
              disabled={isResponding}
              onClick={() => onToggle(option.label)}
            >
              <span className="interject-choice-body">
                <span className="interject-choice-label">{option.label}</span>
                {option.description && option.description !== option.label && (
                  <span className="interject-choice-desc">{option.description}</span>
                )}
              </span>
              {isSelected ? (
                <Icon name="check" size={14} className="interject-choice-check shrink-0" />
              ) : shortcut !== null ? (
                <kbd className="interject-kbd">{shortcut}</kbd>
              ) : null}
            </button>
          )
        })}
      </div>

      <p style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 8 }}>
        {multi
          ? 'Pick what applies, then send. Or write your own answer below.'
          : 'Pick one, or write your own answer below.'}
        {/* Said once, here, rather than left for the operator to infer from the counter — an
            answer they cannot take back is worth knowing about before they give it. */}
        {step < total ? ` Then ${total - step} more.` : ''}
      </p>

      {/* Nothing reaches the agent until the batch is finished, so say so. Without it the operator
          answers two of three, sees nothing happen, and cannot tell whether the agent is waiting on
          the third or ignoring them — trading a visible annoyance for an invisible one. Distinct
          from the counter above, which is about position rather than about what has been sent. */}
      {nobodyWaiting && total > 1 && (
        <p
          data-testid="agent-question-held-batch"
          style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}
        >
          {`Your answers reach ${agent} together once you have finished all ${total}. Dismiss the rest to send what you have.`}
        </p>
      )}
    </div>
  )
}
