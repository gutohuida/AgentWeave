import { useState } from 'react'
import { useAnswerQuestion, type Question } from '@/api/questions'
import { readableApiError } from '@/api/client'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'

interface AnswerFormProps {
  question: Question
  labelledBy: string
  onAnswered?: () => void
}

export function AnswerForm({ question, labelledBy, onAnswered }: AnswerFormProps) {
  const [answer, setAnswer] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const { mutate, isPending, isError, error, reset } = useAnswerQuestion()
  const options = question.options ?? []

  // A failure clears itself the moment the operator touches the form again: the message describes
  // the attempt they just made, and leaving it standing over an edited answer would have it
  // describing something else.
  function toggleOption(label: string) {
    reset()
    setAnswer('')
    setSelected((current) => {
      if (!question.multi_select) return current.includes(label) ? [] : [label]
      return current.includes(label) ? current.filter((item) => item !== label) : [...current, label]
    })
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const writtenAnswer = answer.trim()
    const submittedAnswer = writtenAnswer || selected.join(', ')
    if (!submittedAnswer) return
    const payload = writtenAnswer
      ? { id: question.id, answer: writtenAnswer }
      : { id: question.id, answer: submittedAnswer, labels: selected }
    mutate(payload, {
      onSuccess: () => {
        setAnswer('')
        setSelected([])
        onAnswered?.()
      },
    })
  }

  return (
    <form onSubmit={handleSubmit} className="mt-3 space-y-2" aria-labelledby={labelledBy} aria-busy={isPending}>
      {options.length > 0 && (
        <fieldset className="space-y-1.5">
          <legend className="sr-only">
            {question.multi_select ? 'Select one or more answers' : 'Select an answer'}
          </legend>
          {options.map((option) => {
            const isSelected = selected.includes(option.label) && !answer.trim()
            return (
              <button
                key={option.label}
                type="button"
                className="interject-choice w-full"
                data-selected={isSelected ? 'true' : undefined}
                aria-pressed={isSelected}
                disabled={isPending}
                onClick={() => toggleOption(option.label)}
              >
                <span className="interject-choice-body">
                  <span className="interject-choice-label">{option.label}</span>
                  {option.description && option.description !== option.label && (
                    <span className="interject-choice-desc">{option.description}</span>
                  )}
                </span>
                {isSelected && <Icon name="check" size={14} className="interject-choice-check shrink-0" />}
              </button>
            )
          })}
          <p className="pt-1 text-[11px]" style={{ color: 'var(--text-3)' }}>
            {question.multi_select ? 'Select all that apply, or write your own answer.' : 'Choose one, or write your own answer.'}
          </p>
        </fieldset>
      )}
      <textarea
        value={answer}
        onChange={(event) => {
          reset()
          setAnswer(event.target.value)
          if (event.target.value) setSelected([])
        }}
        placeholder="Type your answer…"
        rows={3}
        aria-label={`Answer ${question.from_agent}`}
        className="control-field min-h-16 resize-none px-3 py-2 text-sm"
        disabled={isPending}
      />
      <Button
        type="submit"
        variant="primary"
        size="sm"
        disabled={isPending || (!answer.trim() && selected.length === 0)}
        aria-label={`Submit answer to ${question.from_agent}`}
      >
        {isPending ? 'Submitting…' : 'Submit answer'}
      </Button>
      {/* An answer that never left is the worst thing this form can be silent about: the agent is
          still blocked, and a form that cleared nothing and said nothing reads as one that simply
          did not register the click. Same shape as `PermissionRequestCard`'s 409 line — the Hub's
          own sentence where it sent one, a plain fallback where it did not. */}
      {isError && (
        <p role="alert" data-testid={`answer-error-${question.id}`} className="text-[11px]" style={{ color: 'var(--red)' }}>
          {readableApiError(error, 'The answer did not reach the Hub.')} Nothing was sent — your
          answer is still here, so you can try again.
        </p>
      )}
    </form>
  )
}
