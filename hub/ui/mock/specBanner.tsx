import type { SpecAmendment } from '@/api/spec'
import type { HeaderNotice } from '@/components/spec/page/SpecNotices'
import { toast } from '@/lib/toast'

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

/** The messages, as the compact header's notices. */
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
