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
        className="w-full resize-none text-sm"
        disabled={isPending}
        style={{
          background: 'var(--surface-3)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--text)',
          padding: '8px 12px',
        }}
      />
      <button
        type="submit"
        disabled={isPending || !answer.trim()}
        className="disabled:opacity-50 disabled:cursor-not-allowed"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '8px',
          height: 36,
          borderRadius: 'var(--radius-sm)',
          padding: '0 20px',
          background: 'var(--surface-3)',
          color: 'var(--text-2)',
          border: '1px solid var(--border)',
          fontSize: 13,
          fontWeight: 500,
          cursor: 'pointer',
        }}
      >
        {isPending ? 'Submitting…' : 'Submit Answer'}
      </button>
    </form>
  )
}
