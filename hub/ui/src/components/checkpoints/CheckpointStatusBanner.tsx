import { useConfigStore } from '@/store/configStore'
import { checkpointsDestination, goTo } from '@/lib/navigation'
import { useCheckpointOperationStore } from '@/store/checkpointOperationStore'

export function CheckpointStatusBanner() {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const operations = useCheckpointOperationStore((state) => state.operations)
  const dismiss = useCheckpointOperationStore((state) => state.dismiss)
  const active = Object.entries(operations)
    .filter(([, operation]) => operation.projectId === projectId)
    .sort(([, left], [, right]) => right.startedAt - left.startedAt)[0]
  if (!active) return null
  const [key, operation] = active

  return (
    <div
      role="status"
      data-testid="checkpoint-global-status"
      className="fixed bottom-4 right-4 z-[100] flex max-w-md items-center gap-3 rounded border px-4 py-3 text-xs shadow-lg"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text)' }}
    >
      <span>{operation.message}</span>
      {operation.checkpointId && projectId ? (
        <button
          type="button"
          data-slot="checkpoint-status-open"
          data-testid="checkpoint-status-open"
          className="aw-link"
          onClick={() => {
            goTo(checkpointsDestination(projectId, { checkpoint: operation.checkpointId }))
            dismiss(key)
          }}
        >
          View checkpoint
        </button>
      ) : null}
      {operation.status !== 'writing' && (
        <button
          type="button"
          aria-label="Dismiss checkpoint status"
          onClick={() => dismiss(key)}
          style={{ color: 'var(--text-3)' }}
        >
          ×
        </button>
      )}
    </div>
  )
}
