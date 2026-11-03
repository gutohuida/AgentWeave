import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { CoverageEntry, SpecAmendment } from '@/api/spec'
import { Icon } from '@/components/common/Icon'
import { SpecAmendmentsPanel } from '@/components/spec/SpecAmendmentsPanel'
import { SpecHealthLine } from '@/components/spec/SpecHealthLine'
import type { HeaderNotice } from '@/components/spec/page/SpecNotices'
import { toast } from '@/lib/toast'
import { PROJECT_ID } from './fixtures'
import documentsJson from './fixtures/spec_documents.json'

/** How much the banner under the header carries, for the compact-header slice
 *  (`spec/changes/the-spec-header-redesigned`): nothing but the health line, one unreviewed
 *  amendment (the retrospective spec on 2026-11-02, when QA2 added a task mid-build), or a pile. */
export type NoticeLevel = 'none' | 'one' | 'many'

export const NOTICE_LEVELS: Array<{ value: NoticeLevel; label: string }> = [
  { value: 'none', label: 'Messages: none' },
  { value: 'one', label: 'Messages: one amendment' },
  { value: 'many', label: 'Messages: many' },
]

// mock state: the amendment QA2 recorded on "A finished spec gets a build retrospective"
// (amd-af1520e0f673, read from the operator's Hub), before the operator reviewed it.
const AMENDMENT: SpecAmendment = {
  id: 'amd-af1520e0f673',
  op: 'add_task',
  target: 'automatic-choice-on-the-manager-page',
  requirement: 'fires-when-the-last-task-is-approved',
  identifier: 'FR-2',
  reason:
    "FR-2 says 'on with automatic firing', FR-3 says 'whatever the automatic choice', and the request-on-unfinished-build criterion starts from 'automatic firing off'. On a Hub on :8020 at 3e7caff, PATCH /manager/jobs/build-retrospective {\"mode\":\"button\"} answered 200 and the requested firing then wrote a report, so the API works. But ManagerSettings.tsx:135 gates the control on job.key === 'chapters', so an operator cannot make this choice on the page. No remaining task covers it: FSGBR-4's files are the spec page, api, tests and bundle. The author's FR-1 evidence names the same gap.",
  how_to_check:
    'On a Hub on :8020, open Project settings → Manager with the Build retrospective job present: the automatic/button control shows for it, and choosing Button sends PATCH mode=button so GET /manager/jobs returns mode \'button\'. Approving a document\'s last task then records no firing, and Review this build still fires one.',
  author: 'QA2',
  run_id: 'run-8c1cd7e63adf',
  created_at: '2026-11-01T21:20:12Z',
  reviewed: false,
  reviewed_at: null,
  reviewed_by: null,
  relaxing: false,
  change: null,
  before: null,
  state: 'applied',
}

/** Seeds the amendment panel's two reads, so the real panel renders it. */
function useSeedAmendments(path: string, level: NoticeLevel) {
  const client = useQueryClient()
  React.useMemo(() => {
    const has = level !== 'none'
    const documents = (documentsJson as unknown as { documents: Array<{ path: string }> }).documents.map((d) =>
      d.path === path ? { ...d, amendments: has ? { total: 1, unreviewed: 1, proposed: 0 } : { total: 0, unreviewed: 0, proposed: 0 } } : d,
    )
    client.setQueryData(['project', PROJECT_ID, 'specDocuments'], { documents })
    client.setQueryData(['project', PROJECT_ID, 'specs', 'amendments', path], { amendments: has ? [AMENDMENT] : [] })
  }, [client, path, level])
}

export type HeaderChoice = 'today' | 'line' | 'badge' | 'rail'

export const HEADER_CHOICES: Array<{ value: HeaderChoice; label: string }> = [
  { value: 'today', label: 'Header: today' },
  { value: 'line', label: 'Header: A, one line' },
  { value: 'badge', label: 'Header: B, a count' },
  { value: 'rail', label: 'Header: C, beside the spec' },
]

export type PanelNavChoice = 'today' | 'row'

export const PANEL_NAV_CHOICES: Array<{ value: PanelNavChoice; label: string }> = [
  { value: 'today', label: 'Panel navigation: today (4 rows)' },
  { value: 'row', label: 'Panel navigation: one row' },
]

/** The same messages as today's banner, as the compact header's notices. */
export function noticesFor(level: NoticeLevel): HeaderNotice[] {
  if (level === 'none') return []
  const amendment: HeaderNotice = {
    id: AMENDMENT.id,
    tone: 'warn',
    summary: (
      <>
        Added task <code>{AMENDMENT.target}</code> ({AMENDMENT.identifier}) · @{AMENDMENT.author} · not reviewed
      </>
    ),
    body: (
      <>
        <p>{AMENDMENT.reason}</p>
        <p className="aw-notice-muted">How to check: {AMENDMENT.how_to_check}</p>
      </>
    ),
    action: { label: 'Mark reviewed', onClick: () => toast({ title: 'Marked reviewed', tone: 'success' }) },
  }
  if (level === 'one') return [amendment]
  return [
    {
      id: 'delivery-stale',
      tone: 'warn',
      summary: 'The recommended build names DeveloperOpus3, which is not an agent on this project.',
      body: <p>Building will not start a flow unless you choose another agent in the Build dialog.</p>,
    },
    amendment,
    {
      id: 'build-outcome',
      tone: 'info',
      summary: 'The flow A finished spec gets a build retrospective was started as DeveloperOpus2; it fires at its next tick.',
    },
    {
      id: 'approval-notes',
      tone: 'info',
      summary: 'Approved. For your information: 2 notes',
      body: (
        <ul>
          <li>roadmap — the approved roadmap AgentWeave performance overhaul has slices no document names: off-main-thread-io, lazy-spec-reads</li>
          <li>tasks — two tasks edit hub/ui/src/components/spec/page/SpecPageHeader.tsx with no order between them</li>
        </ul>
      ),
    },
  ]
}

/** The health facts, as the compact header draws them beside the phase. */
export function MockHealth({ level, coverage, tasks }: { level: NoticeLevel; coverage: CoverageEntry[]; tasks: Array<{ id: string; title: string; status: string }> }) {
  return (
    <SpecHealthLine
      coverage={coverage}
      driftCount={0}
      vaultWarnings={level === 'many' ? 2 : 0}
      indexIssues={0}
      tasks={tasks}
      history={[]}
      now={new Date('2026-10-17T12:10:00Z')}
      onScanDrift={() => toast({ title: 'Scans for drift' })}
      onCheckVault={() => toast({ title: 'Checks against the vault' })}
      onOpenTasks={() => toast({ title: 'Opens the tasks' })}
      onOpenRequirement={() => undefined}
    />
  )
}

/** Today's banner, as useSpecSurface stacks it under the header: the messages, the facts line and
 *  the amendments, every one adding its own height. */
export function TodayBanner({ path, level, coverage, tasks }: { path: string; level: NoticeLevel; coverage: CoverageEntry[]; tasks: Array<{ id: string; title: string; status: string }> }) {
  useSeedAmendments(path, level)
  return (
    <div className="aw-sp-banner" data-testid="spec-banner">
      {level === 'many' ? (
        <>
          <div className="aw-spec-message" data-tone="warn" data-testid="delivery-stale-strip">
            <Icon name="warning" size={13} />
            <span className="aw-spec-message-text">
              The recommended build names DeveloperOpus3, which is not an agent on this project. Building will not start a flow unless you choose another agent in the Build dialog.
            </span>
          </div>
          <div className="aw-spec-message" data-testid="spec-build-outcome">
            <span className="aw-spec-message-text">The flow A finished spec gets a build retrospective was started as DeveloperOpus2; it fires at its next tick.</span>
          </div>
          <div className="aw-spec-message" data-testid="approval-notes">
            <span className="aw-spec-message-text">Approved. For your information:</span>
            <ul className="flex flex-col gap-0.5">
              <li>roadmap — the approved roadmap AgentWeave performance overhaul has slices no document names: off-main-thread-io, lazy-spec-reads</li>
              <li>tasks — two tasks edit hub/ui/src/components/spec/page/SpecPageHeader.tsx with no order between them</li>
            </ul>
          </div>
        </>
      ) : null}
      <div data-testid="spec-document-facts">
        <SpecHealthLine
          coverage={coverage}
          driftCount={0}
          vaultWarnings={level === 'many' ? 2 : 0}
          indexIssues={0}
          tasks={tasks}
          history={[]}
          now={new Date('2026-10-17T12:10:00Z')}
          onScanDrift={() => toast({ title: 'Scans for drift' })}
          onCheckVault={() => toast({ title: 'Checks against the vault' })}
          onOpenTasks={() => toast({ title: 'Opens the tasks' })}
          onOpenRequirement={() => undefined}
        />
      </div>
      <SpecAmendmentsPanel path={path} />
    </div>
  )
}
