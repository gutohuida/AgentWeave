import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import { useCheckVaultWarnings, useVaultWarnings } from '@/api/vault'
import { ManagerIcon } from '@/components/manager/ManagerIcon'
import { useManagerItem } from '@/components/manager/useManagerItem'
import { useQueryClient } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'

const JOB = 'spec-vault-check'

/**
 * What the project's vault says against this document's requirements
 * (`a-requirement-is-checked-against-what-the-vault-recorded`, FR-6): a cited fact that is
 * disputed, superseded, reported or missing, and the conflicts the spec-vault-check job kept.
 *
 * These are warnings, never a refusal, and the same ones appear as gaps when the document is
 * approved. A Hub without the route (404) renders nothing. A document with nothing
 * against it gets one quiet line that still offers Check now, since a check is how a conflict is
 * found in the first place (F658).
 *
 * The manager's icon says whether a check of this document is running, and keeps a failed one
 * shown until it is seen (`background-manager-work-you-can-see`, FR-4 to FR-6). This list is the
 * document's warning list, so showing its failure here is the operator seeing it. When a check
 * ends the list is read again, so its result shows without a reload.
 */
export function SpecVaultWarnings({ path }: { path: string }) {
  const { data } = useVaultWarnings(path)
  const check = useCheckVaultWarnings()
  const queryClient = useQueryClient()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const manager = useManagerItem({
    job: JOB,
    matches: (subject) => subject.document === path,
    seeOnShow: true,
    onEnded: () => {
      check.reset()
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'vault', 'warnings', path] })
    },
  })

  if (data === undefined || !manager.ready) return null
  const warnings = data

  return (
    <section
      data-testid="spec-vault-warnings"
      className="flex shrink-0 flex-col gap-1.5 px-3 py-2 text-xs"
      style={{ borderTop: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-2">
        <ManagerIcon
          state={manager.state}
          job={JOB}
          detail={manager.state === 'failed' ? manager.failure?.detail : manager.state === 'working' ? 'checking this document against the vault' : null}
        />
        {warnings.length > 0 ? (
          <>
            <span style={{ color: 'var(--text-2)', fontWeight: 600 }}>Vault warnings</span>
            <span style={{ color: 'var(--amber)' }}>{warnings.length}</span>
          </>
        ) : (
          <span style={{ color: 'var(--text-3)' }}>No vault warnings</span>
        )}
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="xs"
          data-testid="spec-vault-warnings-check"
          disabled={check.isPending || manager.state === 'working'}
          title="Check this document against the vault again. The result reaches this list when the check finishes."
          onClick={() => {
            manager.starting()
            check.mutate(path, { onError: manager.cancelStarting })
          }}
        >
          Check now
        </Button>
      </div>
      {check.isError && (
        <p style={{ color: 'var(--amber)' }}>
          Could not start the check: {readableApiError(check.error, 'the Hub did not answer.')}
        </p>
      )}
      {manager.state === 'working' && (
        <p role="status" style={{ color: 'var(--text-3)' }}>
          Checking against the vault; the result shows here when it ends.
        </p>
      )}
      {manager.state === 'failed' && manager.failure && (
        <p role="alert" data-testid="spec-vault-warnings-failure" style={{ color: 'var(--red)' }}>
          The last check failed: {manager.failure.detail ?? 'the Hub recorded no reason.'}
        </p>
      )}
      <ul className="flex flex-col gap-1">
        {warnings.map((warning, position) => (
          <li
            key={`${warning.key}-${warning.kind}-${warning.fact ?? position}`}
            data-testid={`spec-vault-warning-${warning.key}`}
            style={{ color: 'var(--text-2)' }}
          >
            <strong style={{ color: 'var(--text)' }}>{warning.identifier}</strong> · {warning.message}
          </li>
        ))}
      </ul>
    </section>
  )
}
