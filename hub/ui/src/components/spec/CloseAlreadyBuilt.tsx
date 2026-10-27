import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { readableApiError } from '@/api/client'
import { useCloseAlreadyBuilt, type AlreadyBuiltResult } from '@/api/spec'
import { useDocumentTasks } from '@/api/tasks'
import { parseCommits } from '@/lib/commits'

/** The statuses a task is closed from; `approved` and `rejected` are decided already. */
const OPEN = new Set([
  'pending',
  'assigned',
  'in_progress',
  'blocked',
  'revision_needed',
  'completed',
  'under_review',
])

/**
 * Close an approved change's open tasks as already built (`every-task-can-always-be-moved-on`
 * FR-5/FR-6): the operator names the commit or commits on the main branch that hold the work, and
 * every open task moves to under review, with evidence pointing at those commits awaiting a
 * decision. No agent run starts. A task is approved once its evidence is accepted.
 */
export function CloseAlreadyBuilt({ path, documentId }: { path: string; documentId: string }) {
  const close = useCloseAlreadyBuilt()
  const { data: tasks, isError: tasksUnreadable } = useDocumentTasks(documentId)
  const openCount = (tasks ?? []).filter((task) => OPEN.has(task.status)).length
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [refusal, setRefusal] = useState<string | null>(null)
  const [result, setResult] = useState<AlreadyBuiltResult | null>(null)
  const commits = parseCommits(text)

  function onClose() {
    if (commits.length === 0) return
    setRefusal(null)
    close.mutate(
      { path, commits },
      {
        onSuccess: (answer) => {
          setResult(answer)
          setOpen(false)
          setText('')
        },
        onError: (error: unknown) =>
          setRefusal(readableApiError(error, 'The Hub refused to close the tasks.')),
      },
    )
  }

  if (result) {
    const evidence = result.tasks.reduce((sum, task) => sum + task.evidence.length, 0)
    return (
      <p className="aw-spec-message" data-testid="already-built-result">
        <Icon name="task_alt" size={13} />
        <span className="aw-spec-message-text">
          Closed {result.tasks.length} {result.tasks.length === 1 ? 'task' : 'tasks'} as already
          built at {result.commits.map((sha) => sha.slice(0, 12)).join(', ')}.{' '}
          {evidence === 1 ? '1 piece of evidence awaits' : `${evidence} pieces of evidence await`} a
          decision; each task is approved once its evidence is accepted.
        </span>
      </p>
    )
  }

  // Nothing to close, or not known yet: offer nothing rather than a move the Hub would refuse.
  // Where the tasks cannot be read, it is offered anyway, and the Hub says if nothing is open.
  if (openCount === 0 && !tasksUnreadable) return null

  if (!open) {
    return (
      <div className="aw-spec-message">
        <Button
          variant="outline"
          size="xs"
          data-testid="already-built-open"
          title="The work is already on the main branch: close the open tasks without running an agent"
          onClick={() => setOpen(true)}
        >
          {tasksUnreadable
            ? 'Close the open tasks as already built…'
            : `Close ${openCount} open ${openCount === 1 ? 'task' : 'tasks'} as already built…`}
        </Button>
      </div>
    )
  }

  return (
    <div className="aw-spec-message flex-col items-start" data-testid="already-built-form">
      <span className="aw-spec-message-text">
        Name the commit or commits on the main branch that already hold this change's work. Every
        open task moves to under review, no agent runs, and evidence naming the commits waits for a
        decision; each task is approved once its evidence is accepted.
      </span>
      <div className="flex w-full items-center gap-1.5">
        <Input
          aria-label="Commits on the main branch"
          data-testid="already-built-commits"
          placeholder="e.g. 91b59b5 c2eabc3"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') onClose()
          }}
        />
        <Button
          variant="primary"
          size="xs"
          data-testid="already-built-close"
          disabled={commits.length === 0 || close.isPending}
          title={commits.length === 0 ? 'Name at least one commit first' : undefined}
          onClick={onClose}
        >
          Close tasks
        </Button>
        <Button variant="ghost" size="xs" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
      {refusal && (
        <span role="alert" style={{ color: 'var(--red)' }}>
          {refusal}
        </span>
      )}
    </div>
  )
}
