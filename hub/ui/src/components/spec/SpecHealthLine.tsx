import * as React from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Icon } from '@/components/common/Icon'
import type { CoverageEntry } from '@/api/spec'
import { formatDateTime, formatDay } from '@/lib/format'
import '@/styles/spec-header.css'

/** A fact whose full detail can open under the header. */
export type HealthFactKey = 'requirements' | 'drift' | 'vault' | 'tasks' | 'index' | 'approval'

export interface HealthTask {
  id: string
  title: string
  status: string
}

/** Everything the eight status strips said, as one line of facts. Each fact is a button that
 *  opens its detail in a popover anchored to it, so the document starts right under its title
 *  instead of 380px down. Facts that are fine stay quiet (muted text); a fact that needs the
 *  operator takes its colour.
 *
 *  A fact the Hub could not answer is left out rather than shown as fine (a document with no
 *  requirements, a project with no vault, a document with no tasks). When the host passes
 *  `onShowDetail`, each popover ends with "Show details", which opens that fact's full panel
 *  (every action the old strip had) under the header. */
export function SpecHealthLine({
  coverage,
  coverageDiagnostics = 0,
  driftCount,
  lastDriftScan,
  vaultWarnings,
  indexIssues,
  tasks,
  history,
  approvedAt,
  now,
  onScanDrift,
  onCheckVault,
  onOpenTasks,
  onOpenRequirement,
  activeDetail = null,
  onShowDetail,
}: {
  coverage: CoverageEntry[]
  /** Coverage rows the Hub could not resolve. */
  coverageDiagnostics?: number
  /** Null when the drift route did not answer; the fact is then left out. */
  driftCount: number | null
  lastDriftScan?: string | null
  /** Null when the project has no vault (or the route is absent); the fact is then left out. */
  vaultWarnings: number | null
  /** Spec index (manifest) problems. */
  indexIssues: number
  tasks: HealthTask[]
  /** What approving the document did, in the Hub's own sentences (approval outcome). */
  history: string[]
  approvedAt?: string | null
  now?: Date
  onScanDrift: () => void
  onCheckVault: () => void
  onOpenTasks: () => void
  onOpenRequirement: (identifier: string) => void
  activeDetail?: HealthFactKey | null
  onShowDetail?: (fact: HealthFactKey) => void
}) {
  const count = (state: string) => coverage.filter((r) => r.state === state).length
  const verified = count('verified')
  const rejected = count('rejected')
  // Every other state is named as it is: a requirement nobody has touched is not "in progress",
  // and a drifting or stale one is a warning, not progress (F945).
  const open = OPEN_STATES.map((s) => ({ ...s, n: count(s.state) })).filter((s) => s.n > 0)
  const needsLook = open.some((s) => s.warn)
  const decided = tasks.filter((t) => t.status === 'approved' || t.status === 'rejected').length
  const notMerged = coverage.filter((r) => r.state === 'verified' && r.integration === 'not_integrated')

  const details = (fact: HealthFactKey) =>
    onShowDetail ? (
      <>
        <DropdownMenu.Separator className="aw-menu-separator" />
        <DropdownMenu.Item className="aw-menu-item" onSelect={() => onShowDetail(fact)}>
          <Icon name={activeDetail === fact ? 'unfold_less' : 'unfold_more'} size={14} className="aw-menu-item-icon" />
          {activeDetail === fact ? 'Hide details' : 'Show details'}
        </DropdownMenu.Item>
      </>
    ) : null

  return (
    <div className="aw-health" role="group" aria-label="Document health">
      {coverage.length > 0 || coverageDiagnostics > 0 ? (
        <Fact
          fact="requirements"
          active={activeDetail === 'requirements'}
          tone={notMerged.length || coverageDiagnostics || needsLook ? 'warn' : undefined}
          label={
            <>
              <span className="aw-health-bar" aria-hidden="true">
                <span style={{ width: `${(verified / Math.max(1, coverage.length)) * 100}%`, background: 'var(--green)' }} />
                <span style={{ width: `${(rejected / Math.max(1, coverage.length)) * 100}%`, background: 'var(--red)' }} />
              </span>
              <strong>{verified}</strong>/{coverage.length} verified
              {rejected ? <span className="aw-health-bad"> · {rejected} rejected</span> : null}
              {open.map((s) => (
                <span key={s.state} className={s.warn ? 'aw-health-warn' : undefined}>
                  {' · '}
                  {s.n} {s.label}
                </span>
              ))}
              {notMerged.length ? <span> · {notMerged.length} not merged</span> : null}
              {coverageDiagnostics ? <span> · {coverageDiagnostics} broken</span> : null}
            </>
          }
          title="Requirements"
          width={340}
        >
          <ul className="aw-health-reqs">
            {coverage.map((r) => (
              <li key={r.requirement_id}>
                <DropdownMenu.Item className="aw-menu-item aw-health-req" onSelect={() => onOpenRequirement(r.identifier)}>
                  <span className="aw-health-req-id">{r.identifier}</span>
                  <span className="aw-health-state" data-state={r.state}>
                    {STATE_LABEL[r.state] ?? r.state.replace(/_/g, ' ')}
                  </span>
                  <span className="aw-health-req-note">
                    {r.integration === 'integrated' ? 'on master' : r.integration === 'not_integrated' && r.state === 'verified' ? 'not merged' : ''}
                  </span>
                </DropdownMenu.Item>
              </li>
            ))}
          </ul>
          {notMerged.length ? (
            <p className="aw-health-note">Verified, not in the main line: {notMerged.map((r) => r.identifier).join(', ')}.</p>
          ) : null}
          {details('requirements')}
        </Fact>
      ) : null}

      {driftCount !== null ? (
        <Fact
          fact="drift"
          active={activeDetail === 'drift'}
          tone={driftCount ? 'warn' : undefined}
          label={driftCount ? `${driftCount} drifted` : 'No drift'}
          title="Drift"
          width={300}
        >
          <p className="aw-health-note">
            {driftCount
              ? `${driftCount} watched ${driftCount === 1 ? 'file has' : 'files have'} changed since the evidence for them was accepted.`
              : 'Nothing this document’s evidence watches has changed.'}
            {lastDriftScan ? ` Last scan ${formatDateTime(lastDriftScan, now)}.` : ''}
          </p>
          <DropdownMenu.Item className="aw-menu-item" onSelect={onScanDrift}>
            <Icon name="refresh" size={14} className="aw-menu-item-icon" />
            Scan for drift now
          </DropdownMenu.Item>
          {details('drift')}
        </Fact>
      ) : null}

      {vaultWarnings !== null ? (
        <Fact
          fact="vault"
          active={activeDetail === 'vault'}
          tone={vaultWarnings ? 'warn' : undefined}
          label={vaultWarnings ? `${vaultWarnings} vault ${vaultWarnings === 1 ? 'conflict' : 'conflicts'}` : 'Vault agrees'}
          title="Vault"
          width={300}
        >
          <p className="aw-health-note">
            {vaultWarnings ? 'Some requirements contradict facts in the vault.' : 'No requirement contradicts what the vault knows.'}
          </p>
          <DropdownMenu.Item className="aw-menu-item" onSelect={onCheckVault}>
            <Icon name="refresh" size={14} className="aw-menu-item-icon" />
            Check against the vault again
          </DropdownMenu.Item>
          {details('vault')}
        </Fact>
      ) : null}

      {tasks.length > 0 ? (
        <Fact fact="tasks" active={activeDetail === 'tasks'} label={`${decided}/${tasks.length} tasks decided`} title="Tasks" width={320}>
          <ul className="aw-health-tasks">
            {tasks.map((t) => (
              <li key={t.id} className="aw-health-task">
                <span className="aw-health-state" data-state={t.status === 'approved' ? 'verified' : t.status}>
                  {TASK_LABEL[t.status] ?? t.status.replace(/_/g, ' ')}
                </span>
                <span className="truncate">{t.title}</span>
              </li>
            ))}
          </ul>
          <DropdownMenu.Separator className="aw-menu-separator" />
          <DropdownMenu.Item className="aw-menu-item" onSelect={onOpenTasks}>
            <Icon name="task_alt" size={14} className="aw-menu-item-icon" />
            Show these on the board
          </DropdownMenu.Item>
        </Fact>
      ) : null}

      {indexIssues ? (
        <Fact
          fact="index"
          active={activeDetail === 'index'}
          tone="warn"
          label={`${indexIssues} index ${indexIssues === 1 ? 'issue' : 'issues'}`}
          title="Spec index"
          width={300}
        >
          <p className="aw-health-note">The spec index lists documents differently from the files on disk.</p>
          {details('index')}
        </Fact>
      ) : null}

      {approvedAt ? (
        <Fact
          fact="approval"
          active={activeDetail === 'approval'}
          label={`Approved ${formatDay(approvedAt, now)}`}
          title="What approval did"
          width={380}
          muted
        >
          <ul className="aw-health-history">
            {history.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
          {details('approval')}
        </Fact>
      ) : null}
    </div>
  )
}

/** The unfinished states, as the header's count names them (the popover lists each by name). */
const OPEN_STATES: { state: string; label: string; warn?: boolean }[] = [
  { state: 'drifting', label: 'drifting', warn: true },
  { state: 'stale', label: 'stale', warn: true },
  { state: 'amendment_unreviewed', label: 'changed, unreviewed', warn: true },
  { state: 'evidence_awaiting_review', label: 'awaiting review' },
  { state: 'in_progress', label: 'in progress' },
  { state: 'not_started', label: 'not started' },
  { state: 'unserved', label: 'with no task' },
]

const STATE_LABEL: Record<string, string> = {
  verified: 'Verified',
  in_progress: 'In progress',
  rejected: 'Rejected',
  not_started: 'Not started',
  drifting: 'Drifting',
  stale: 'Stale',
  evidence_awaiting_review: 'Awaiting review',
  amendment_unreviewed: 'Changed, unreviewed',
  unserved: 'No task',
}

const TASK_LABEL: Record<string, string> = {
  approved: 'Approved',
  in_progress: 'In progress',
  under_review: 'In review',
  rejected: 'Rejected',
  revision_needed: 'Sent back',
  pending: 'Pending',
  assigned: 'Assigned',
  completed: 'Completed',
}

function Fact({
  fact,
  active,
  label,
  title,
  tone,
  width,
  muted,
  children,
}: {
  fact: HealthFactKey
  active?: boolean
  label: React.ReactNode
  title: string
  tone?: 'warn'
  width: number
  muted?: boolean
  children: React.ReactNode
}) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        data-slot="health-fact"
        className="aw-health-fact"
        data-testid={`spec-health-${fact}`}
        data-tone={tone}
        data-muted={muted ? 'true' : undefined}
        data-active={active ? 'true' : undefined}
      >
        <span className="aw-health-label">{label}</span>
        <Icon name="expand_more" size={12} className="aw-health-chevron" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="start" sideOffset={6} collisionPadding={12} className="aw-menu aw-pop aw-health-pop" style={{ width }}>
          <DropdownMenu.Label className="aw-menu-label">{title}</DropdownMenu.Label>
          {children}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
