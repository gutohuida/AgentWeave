import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import { useCheckVaultWarnings, useVaultWarnings } from '@/api/vault'

/**
 * What the project's vault says against this document's requirements
 * (`a-requirement-is-checked-against-what-the-vault-recorded`, FR-6): a cited fact that is
 * disputed, superseded, reported or missing, and the conflicts the spec-vault-check job kept.
 *
 * These are warnings, never a refusal, and the same ones appear as gaps when the document is
 * proposed or approved. A Hub without the route (404) renders nothing. A document with nothing
 * against it gets one quiet line that still offers Check now, since a check is how a conflict is
 * found in the first place (F658).
 */
export function SpecVaultWarnings({ path }: { path: string }) {
  const { data } = useVaultWarnings(path)
  const check = useCheckVaultWarnings()

  if (data === undefined) return null
  const warnings = data

  return (
    <section
      data-testid="spec-vault-warnings"
      className="flex shrink-0 flex-col gap-1.5 px-3 py-2 text-xs"
      style={{ borderTop: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-2">
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
          disabled={check.isPending}
          title="Check this document against the vault again. The result reaches this list when the check finishes."
          onClick={() => check.mutate(path)}
        >
          Check now
        </Button>
      </div>
      {check.isError && (
        <p style={{ color: 'var(--amber)' }}>
          Could not start the check: {readableApiError(check.error, 'the Hub did not answer.')}
        </p>
      )}
      {check.isSuccess && <p style={{ color: 'var(--text-3)' }}>Checking in the background; reload the list in a minute.</p>}
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
