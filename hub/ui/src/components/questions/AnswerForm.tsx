import { useState } from 'react'
import { useAnswerQuestion } from '@/api/questions'

interface AnswerFormProps {
  questionId: string
  onAnswered?: () => void
}

export function AnswerForm({ questionId, onAnswered }: AnswerFormProps) {
  const [answer, setAnswer] = useState('')
  const { mutate, isPending } = useAnswerQuestion()

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!answer.trim()) return
    mutate({ id: questionId, answer: answer.trim() }, { onSuccess: () => { setAnswer(''); onAnswered?.() } })
  }

  return (
    <form onSubmit={handleSubmit} className="mt-3 space-y-2">
      <textarea
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        placeholder="Type your answer…"
        rows={3}
        className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
        disabled={isPending}
      />
      <button
        type="submit"
        disabled={isPending || !answer.trim()}
        className="rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isPending ? 'Submitting…' : 'Submit Answer'}
      </button>
    </form>
  )
}
