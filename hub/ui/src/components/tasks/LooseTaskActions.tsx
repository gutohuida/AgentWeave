import * as React from 'react'
import { readableApiError } from '@/api/client'
import { useCloseTasks, type CloseOutcome } from '@/api/tasks'

/** What the operator names a done-elsewhere close by: a task, or a commit on main. */
interface DoneElsewhereTarget {
  by_task?: string
  commit?: string
}

/** Read "AW-80" or "3f9a2c1" the way the Hub does: a commit looks like hex, a task like a key. */
function targetFromText(text: string): DoneElsewhereTarget {
  const value = text.trim()
  return /^[0-9a-f]{7,40}$/i.test(value) ? { commit: value } : { by_task: value }
}

/**
 * The close form shared by the drawer (one task) and the board's selection (several): done
 * elsewhere names the task or commit whose work is on main, cancelled takes an optional reason.
 * The Hub's refusals come back per task, so this lists them rather than failing the whole close.
 */
export function CloseForm({
  taskIds,
  outcomes,
  initial,
  onDone,
  onDismiss,
}: {
  taskIds: string[]
  outcomes: CloseOutcome[]
  initial?: CloseOutcome
  onDone?: () => void
  onDismiss?: () => void
}) {
  const close = useCloseTasks()
  const [outcome, setOutcome] = React.useState<CloseOutcome>(initial ?? outcomes[0] ?? 'cancelled')
  const [text, setText] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [refused, setRefused] = React.useState<{ task: string; reason: string }[]>([])
  const doneElsewhere = outcome === 'done_elsewhere'
  const canSubmit = !close.isPending && (!doneElsewhere || text.trim().length > 0)

  const submit = () => {
    setError(null)
    setRefused([])
    close.mutate(
      {
        tasks: taskIds,
        outcome,
        ...(doneElsewhere ? targetFromText(text) : text.trim() ? { reason: text.trim() } : {}),
      },
      {
        onSuccess: (result) => {
          setRefused(result.refused)
          if (result.refused.length === 0) onDone?.()
        },
        onError: (e: unknown) => setError(readableApiError(e, 'The Hub refused this close.')),
      },
    )
  }

  return (
    <div data-testid="close-form" className="flex flex-col gap-2 text-[11px]">
      <div className="flex flex-wrap items-center gap-2">
        {outcomes.length > 1 && (
          <select
            aria-label="How to close"
            data-testid="close-outcome"
            className="control-field px-2 py-1"
            value={outcome}
            onChange={(e) => setOutcome(e.target.value as CloseOutcome)}
          >
            {outcomes.includes('done_elsewhere') && <option value="done_elsewhere">Done elsewhere</option>}
            {outcomes.includes('cancelled') && <option value="cancelled">Cancelled</option>}
          </select>
        )}
        <input
          aria-label={doneElsewhere ? 'The task or commit that did this work' : 'Why it is cancelled'}
          data-testid="close-target"
          className="control-field flex-1 px-2 py-1"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={doneElsewhere ? 'Task (AW-80) or commit on main' : 'Why (optional)'}
        />
        <button
          type="button"
          data-testid="close-submit"
          disabled={!canSubmit}
          className="px-2 py-0.5 rounded"
          style={{ border: '1px solid var(--border)', ...(canSubmit ? {} : { opacity: 0.45, cursor: 'not-allowed' }) }}
          onClick={submit}
        >
          {close.isPending ? 'Closing…' : doneElsewhere ? 'Close as done elsewhere' : 'Cancel task'}
          {taskIds.length > 1 ? ` (${taskIds.length})` : ''}
        </button>
        {onDismiss && (
          <button type="button" style={{ color: 'var(--text-3)' }} onClick={onDismiss}>
            Not now
          </button>
        )}
      </div>
      {error && (
        <p role="alert" data-testid="close-error" style={{ color: 'var(--red)' }}>
          {error}
        </p>
      )}
      {refused.length > 0 && (
        <ul role="alert" data-testid="close-refused" style={{ color: 'var(--red)' }}>
          {refused.map((r) => (
            <li key={r.task}>
              <strong>{r.task}</strong> was not closed: {r.reason}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
