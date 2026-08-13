import { useTaskIntegrations } from '@/api/tasks'

/**
 * Where an approved task's work went — or why it did not go anywhere.
 *
 * Approval merges, so "approved" now carries a claim about the product and this is where that claim
 * is checked. The skipped case is the one that earns the component: work approved into a project
 * with no main branch chosen, or while the checkout was mid-edit, is work the operator will look
 * for on their main line and not find. Silence there is the failure this closes.
 */
export function TaskIntegrationNote({ taskId, status }: { taskId: string; status: string }) {
  // Only an approved task has reached the integration step, so nothing else is worth a request.
  const { data } = useTaskIntegrations(taskId, status === 'approved')
  const rows = data?.integrations ?? []
  if (rows.length === 0) return null

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
    </div>
  )
}
