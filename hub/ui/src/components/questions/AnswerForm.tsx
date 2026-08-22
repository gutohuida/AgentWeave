import { useState } from 'react'
import { useAnswerQuestion } from '@/api/questions'
import { Button } from '@/components/ui/button'

interface AnswerFormProps {
  questionId: string
  agent: string
  labelledBy: string
  onAnswered?: () => void
}

export function AnswerForm({ questionId, agent, labelledBy, onAnswered }: AnswerFormProps) {
  const [answer, setAnswer] = useState('')
  const { mutate, isPending } = useAnswerQuestion()

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!answer.trim()) return
    mutate({ id: questionId, answer: answer.trim() }, { onSuccess: () => { setAnswer(''); onAnswered?.() } })
  }

  return (
    <form onSubmit={handleSubmit} className="mt-3 space-y-2" aria-labelledby={labelledBy} aria-busy={isPending}>
      <textarea
        value={answer}
        onChange={(event) => setAnswer(event.target.value)}
        placeholder="Type your answer…"
        rows={3}
        aria-label={`Answer ${agent}`}
        className="control-field min-h-16 resize-none px-3 py-2 text-sm"
        disabled={isPending}
      />
      <Button type="submit" variant="primary" size="sm" disabled={isPending || !answer.trim()} aria-label={`Submit answer to ${agent}`}>
        {isPending ? 'Submitting…' : 'Submit answer'}
      </Button>
    </form>
  )
}
