import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ManagerIcon } from '@/components/manager/ManagerIcon'
import { useManagerItem } from '@/components/manager/useManagerItem'
import { formatDateTime } from '@/lib/format'
import { useConfigStore } from '@/store/configStore'

const JOB = 'vault-distillation'

/**
 * The manager's icon in the Vault's header (`background-manager-work-you-can-see`, FR-4 to FR-6):
 * working while any source is being distilled, failed while a distillation failed unseen. The
 * failed icon opens its failures in place, which is the operator seeing them. When a distillation
 * ends, the map, the contradictions and the reports are read again, so its facts show at once.
 */
export function VaultDistillationStatus() {
  const queryClient = useQueryClient()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const [open, setOpen] = React.useState(false)
  const manager = useManagerItem({
    job: JOB,
    onEnded: () => {
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'vault', 'map'] })
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'vault', 'contradictions'] })
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'vault', 'reports'] })
    },
  })
  const failed = manager.state === 'failed'
  const detail =
    manager.state === 'working'
      ? `distilling ${manager.runs.length === 1 ? 'a source' : `${manager.runs.length} sources`}`
      : failed
        ? manager.failure?.detail
        : null
  return (
    <span className="relative mr-auto inline-flex items-center" data-testid="vault-distillation-status">
      <ManagerIcon
        state={manager.state}
        job={JOB}
        detail={detail}
        onOpen={
          failed
            ? () => {
                setOpen((was) => !was)
                manager.seeFailures()
              }
            : undefined
        }
      />
      {failed && open ? (
        <span className="aw-manager-popover aw-pop" role="dialog" aria-label="Distillation failures" style={{ left: 0, right: 'auto' }}>
          <span className="aw-manager-failures" data-testid="vault-distillation-failures">
            {manager.failures.map((failure) => (
              <span key={failure.run_id}>
                <strong>Distillation failed</strong> · {formatDateTime(failure.ended_at)}
                <br />
                {failure.detail ?? 'The Hub recorded no reason.'}
              </span>
            ))}
          </span>
        </span>
      ) : null}
    </span>
  )
}
