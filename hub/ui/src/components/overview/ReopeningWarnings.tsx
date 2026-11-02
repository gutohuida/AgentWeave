import { readableApiError } from '@/api/client'
import { useDismissReopeningWarning, useStopReopenedBuild, type ReopeningWarning } from '@/api/reopeningWarnings'
import { toast } from '@/lib/toast'

/** A finished build a follow-up reopened: the operator learns while they can still stop it
 *  (`reopening-warns`). One per build, naming every task filed while it stands. */
export function ReopeningWarnings({ warnings }: { warnings: ReopeningWarning[] }) {
  const stop = useStopReopenedBuild()
  const dismiss = useDismissReopeningWarning()
  const refusal = (title: string) => (error: unknown) =>
    toast({ title, description: readableApiError(error, error instanceof Error ? error.message : 'The Hub refused it.'), tone: 'error' })
  if (warnings.length === 0) return null
  return (
    <div className="mb-3 flex flex-col gap-2">
      {warnings.map((warning) => (
        <div
          key={warning.build_id}
          role="alert"
          data-testid="reopening-warning"
          className="rounded-md border border-[var(--amber)] p-3 text-sm"
        >
          <p className="font-medium">“{warning.title}” was reopened</p>
          <p className="mt-1">Its build had finished {warning.finished_ago} ago. A new follow-up started it again:</p>
          <ul className="mt-1 list-disc pl-5">
            {warning.tasks.map((task) => (
              <li key={task.id}>
                {task.display_id} “{task.title}”, filed by {task.filer}
              </li>
            ))}
          </ul>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              data-testid="reopening-warning-stop"
              className="rounded-md border border-current px-2 py-1 font-medium"
              disabled={stop.isPending}
              onClick={() => stop.mutate(warning.build_id, { onError: refusal('The build was not stopped') })}
            >
              Stop the build
            </button>
            <button
              type="button"
              data-testid="reopening-warning-dismiss"
              className="rounded-md px-2 py-1"
              disabled={dismiss.isPending}
              onClick={() => dismiss.mutate(warning.build_id, { onError: refusal('The warning was not dismissed') })}
            >
              Dismiss
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
