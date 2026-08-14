import { useRetryTaskIntegration, useTaskIntegrations, type TaskIntegration } from '@/api/tasks'

/** The exact wording the Hub records when no merge target has been chosen. */
const NO_MAIN_BRANCH = 'no main branch set'

/**
 * The newest attempt per target, newest last.
 *
 * The record is append-only, so a task that skipped and was later merged holds both rows. Rendering
 * every row gives a stale "Not merged" equal weight beside the merge that followed it, which is the
 * opposite of what the operator needs to read off a card.
 */
function newestPerTarget(rows: TaskIntegration[]): TaskIntegration[] {
  const newest = new Map<string, TaskIntegration>()
  for (const row of rows) {
    newest.set(`${row.commit_sha ?? ''}@${row.target_branch ?? ''}`, row)
  }
  return [...newest.values()]
}

/**
 * Where an approved task's work went — or why it did not go anywhere, and what to do about it.
 *
 * Approval merges, so "approved" now carries a claim about the product and this is where that claim
 * is checked. The skipped case is the one that earns the component: work approved into a project
 * with no main branch chosen, or while the checkout was mid-edit, is work the operator will look
 * for on their main line and not find. Silence there is the failure this closes.
 *
 * A skip used to be terminal — approving again cannot re-run the merge — so the note stated a
 * remediation and then offered no way to act on it. It now does, except where the reason is a
 * missing main branch: retrying there would only skip again, so that one points at the setting
 * instead, which re-attempts the merge on save.
 */
export function TaskIntegrationNote({ taskId, status }: { taskId: string; status: string }) {
  // Only an approved task has reached the integration step, so nothing else is worth a request.
  const { data } = useTaskIntegrations(taskId, status === 'approved')
  const retry = useRetryTaskIntegration(taskId)
  const rows = newestPerTarget(data?.integrations ?? [])
  if (rows.length === 0) return null

  const stuck = rows.some((row) => row.outcome !== 'merged')
  const wantsABranch = rows.some(
    (row) => row.outcome !== 'merged' && row.reason.includes(NO_MAIN_BRANCH),
  )

  return (
    <div className="mt-2 space-y-1" data-testid={`task-integrations-${taskId}`}>
      {rows.map((row) => {
        const merged = row.outcome === 'merged'
        const failed = row.outcome === 'failed'
        const color = merged ? 'var(--green)' : failed ? 'var(--red)' : 'var(--text-muted)'
        return (
          <p key={row.id} className="text-[11px]" style={{ color }}>
            {merged ? (
              <>
                Merged <code>{(row.commit_sha ?? '').slice(0, 8)}</code> into{' '}
                <strong>{row.target_branch}</strong>
              </>
            ) : (
              <>
                {failed ? 'Merge failed' : 'Not merged'} — {row.reason}
              </>
            )}
          </p>
        )
      })}
      {stuck && !wantsABranch && (
        <button
          data-testid={`task-integration-retry-${taskId}`}
          className="text-[11px] underline"
          style={{ color: 'var(--text-3)' }}
          disabled={retry.isPending}
          onClick={(e) => {
            e.stopPropagation()
            retry.mutate()
          }}
        >
          {retry.isPending ? 'Trying…' : 'Try again'}
        </button>
      )}
      {retry.isError && (
        <p className="text-[11px]" style={{ color: 'var(--red)' }}>
          Could not retry the merge.
        </p>
      )}
    </div>
  )
}
