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
        className="m3-input w-full resize-none m3-body-medium"
        disabled={isPending}
      />
      <button
        type="submit"
        disabled={isPending || !answer.trim()}
        className="m3-btn-tonal disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ height: 36, padding: '0 20px', fontSize: 13 }}
      >
        {isPending ? 'Submitting…' : 'Submit Answer'}
      </button>
    </form>
  )
}
