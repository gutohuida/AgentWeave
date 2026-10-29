import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { readableApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import {
  useDetectDrift,
  useSpec,
  useSpecCoverage,
  useSpecDocuments,
  useSpecDrift,
  type SpecApprovalOutcome,
  type SpecDiagnostic,
  type SpecListResponse,
} from '@/api/spec'
import { useDocumentTasks } from '@/api/tasks'
import { useCheckVaultWarnings, useVaultChecked, useVaultWarnings } from '@/api/vault'
import { toast } from '@/lib/toast'
import { SpecApprovalReport } from '../SpecApprovalReport'
import { SpecCoverageBar } from '../SpecCoverageBar'
import { SpecDriftPanel } from '../SpecDriftPanel'
import { SpecHealthLine, type HealthFactKey } from '../SpecHealthLine'
import { SpecVaultWarnings } from '../SpecVaultWarnings'
import '@/styles/spec-header.css'

const DETAIL_TITLE: Record<HealthFactKey, string> = {
  requirements: 'Requirements',
  drift: 'Drift',
  vault: 'Vault',
  tasks: 'Tasks',
  index: 'Spec index',
  approval: 'What approval did',
}

/** Approval's report, as the history fact's sentences (`SpecApprovalReport` has the full form). */
function approvalHistory(outcome: SpecApprovalOutcome | undefined): string[] {
  if (!outcome) return []
  const lines: string[] = []
  if (outcome.created.length) {
    lines.push(`Created ${outcome.created.length} ${outcome.created.length === 1 ? 'task' : 'tasks'}: ${outcome.created.map((c) => c.title).join(', ')}.`)
  }
  if (outcome.already_served.length) lines.push(`${outcome.already_served.length} already served by existing work.`)
  if (outcome.failed) lines.push(`Creating its tasks failed: ${outcome.failed}`)
  if (outcome.dependencies_not_honoured.length) lines.push(`${outcome.dependencies_not_honoured.length} declared dependencies could not be honoured.`)
  lines.push(...(outcome.flow?.messages ?? []))
  return lines
}

/**
 * The document's facts that are not its content: how its requirements are covered, whether it has
 * drifted from its code, what the vault says, what approval did, and the index's problems. One
 * line of facts under the header, each opening its detail (carried over from the old document
 * panel; the redesigned page draws the document itself natively and keeps these alongside).
 */
export function SpecDocumentFacts({
  path,
  specList,
  onOpenTasks,
  onOpenRequirement,
}: {
  path: string
  specList: SpecListResponse | undefined
  onOpenTasks?: (taskIds: string[]) => void
  onOpenRequirement: (identifier: string) => void
}) {
  const [detail, setDetail] = useState<HealthFactKey | null>(null)
  const { data: specDoc, error: specError } = useSpec(path)
  const { data: coverage, error: coverageError } = useSpecCoverage(path)
  const { data: drift, isError: driftError } = useSpecDrift(path)
  const { data: vault } = useVaultWarnings(path)
  const { data: vaultChecked, error: vaultCheckedError } = useVaultChecked(path)
  const { data: documents, error: documentsError } = useSpecDocuments()
  const record = documents?.documents.find((entry) => entry.path === path)
  const { data: documentTasks, error: tasksError } = useDocumentTasks(record?.id ?? null)
  const unread = [specError, coverageError, vaultCheckedError, documentsError, tasksError].some(Boolean)
  const detect = useDetectDrift()
  const checkVault = useCheckVaultWarnings()

  // The Hub reports each missing document twice by design: structured in `missing` and as a
  // `missing_document` entry in `diagnostics`. Keep only the `missing` representation.
  const diagnostics: SpecDiagnostic[] = (specList?.diagnostics ?? []).filter((d) => d.code !== 'missing_document')
  const missing = specList?.missing ?? []
  const indexIssues = diagnostics.length + missing.length

  return (
    <div data-testid="spec-document-facts">
      {unread ? (
        <p className="aw-spec-message" data-tone="warn" data-testid="spec-facts-unread">
          <span className="aw-spec-message-text">Some of this document's facts could not be read, so the line below may be missing some.</span>
        </p>
      ) : null}
      <SpecHealthLine
        coverage={coverage?.requirements ?? []}
        coverageDiagnostics={coverage?.diagnostics.length ?? 0}
        driftCount={driftError || !drift ? null : drift.drift.length}
        vaultWarnings={vault === undefined ? null : vault.length}
        vaultChecked={vaultChecked}
        indexIssues={indexIssues}
        tasks={(documentTasks ?? []).map((task) => ({ id: task.id, title: task.title, status: task.status }))}
        history={approvalHistory(specDoc?.approval_outcome)}
        approvedAt={record?.phase === 'approved' && specDoc?.approval_outcome ? record.updated_at : null}
        onScanDrift={() =>
          detect.mutate(undefined, {
            onSuccess: (result) =>
              toast({
                title: result.raised.length ? `${result.raised.length} drifted` : 'No drift found',
                description: result.raised.length ? 'Answer each under Drift.' : undefined,
                tone: result.raised.length ? 'neutral' : 'success',
              }),
            onError: (error: unknown) => toast({ title: 'Could not scan for drift', description: readableApiError(error, 'The Hub did not answer.'), tone: 'error' }),
          })
        }
        onCheckVault={() =>
          checkVault.mutate(path, {
            onSuccess: () => toast({ title: 'Checking against the vault', description: 'The result arrives here when the check finishes.' }),
            onError: (error: unknown) => toast({ title: 'Could not start the check', description: readableApiError(error, 'The Hub did not answer.'), tone: 'error' }),
          })
        }
        onOpenTasks={() => onOpenTasks?.((documentTasks ?? []).map((task) => task.id))}
        onOpenRequirement={onOpenRequirement}
        activeDetail={detail}
        onShowDetail={(fact) => setDetail((current) => (current === fact ? null : fact))}
      />
      {detail && (
        <section className="aw-spec-detail aw-pop" aria-label={DETAIL_TITLE[detail]} data-testid={`spec-detail-${detail}`}>
          <div className="aw-spec-detail-head">
            {DETAIL_TITLE[detail]}
            <Button variant="ghost" size="icon-xs" aria-label="Hide details" title="Hide details" onClick={() => setDetail(null)}>
              <Icon name="close" size={13} />
            </Button>
          </div>
          <div className="aw-spec-detail-body">
            {detail === 'requirements' && <SpecCoverageBar path={path} onOpenTasks={onOpenTasks} defaultOpen />}
            {detail === 'drift' && <SpecDriftPanel path={path} />}
            {detail === 'vault' && <SpecVaultWarnings path={path} />}
            {detail === 'approval' && <SpecApprovalReport path={path} />}
            {detail === 'index' && (
              <ul className="flex flex-col gap-0.5 px-3 py-1 text-xs" data-testid="spec-index-issues" style={{ color: 'var(--text-3)' }}>
                {diagnostics.map((d, i) => (
                  <li key={`d-${i}`}>
                    {d.message ?? (
                      <>
                        {d.code}
                        {d.path ? ` — ${d.path}` : ''}
                        {d.field ? ` (${d.field}: ${d.expected} → ${d.actual})` : ''}
                      </>
                    )}
                  </li>
                ))}
                {missing.map((m) => (
                  <li key={`m-${m.path}`}>Named by the index, not on disk: {m.path}</li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}
    </div>
  )
}
