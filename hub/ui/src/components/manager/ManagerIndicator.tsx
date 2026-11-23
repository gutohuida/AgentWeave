import * as React from 'react'
import { readableApiError } from '@/api/client'
import {
  isNoManager,
  useManagerJobs,
  useMarkManagerRunsSeen,
  useRecentManagerRuns,
  useRunningManagerRuns,
  useUnseenManagerFailures,
  type ManagerEndedRun,
  type ManagerRunningRun,
  type ManagerUnseenFailure,
} from '@/api/manager'
import { useSpecDocuments } from '@/api/spec'
import { Icon } from '@/components/common/Icon'
import { LoadingThread } from '@/components/common/LoadingThread'
import { useSSE } from '@/hooks/useSSE'
import { formatDateTime, formatDuration } from '@/lib/format'
import { endedAs, jobTitle, MENDER_JOB, secondsSince, subjectLabel } from './managerRuns'
import '@/styles/manager.css'

/** How long the popover stays after the pointer leaves, so it can be reached from the trigger. */
const CLOSE_DELAY_MS = 250

/** One row of the popover: a run in progress, one that ended, or an unseen failure. */
type Row =
  | { kind: 'running'; run: ManagerRunningRun }
  | { kind: 'ended'; run: ManagerEndedRun }
  | { kind: 'unseen'; run: ManagerUnseenFailure }

/**
 * The manager in the project top bar (`background-manager-work-you-can-see`, FR-7, FR-8): a robot
 * that, while manager runs are in progress, shows the brand's moving thread (the spec's spinner:
 * AgentWeave shows activity with the thread, never a spinning icon) and counts them (conversation titles and the
 * mender included). Hovering or clicking it opens the popover: each run in progress with its
 * elapsed time from its start in Hub time, unseen failures, and the most recent ends. A row opens
 * that run in Settings › Manager; a mender row also opens its conversation.
 *
 * Hovering while failures are listed is the operator seeing them (FR-6): they are marked seen.
 */
export function ManagerIndicator({
  onOpenRun,
  onOpenConversation,
}: {
  onOpenRun: (runId: string) => void
  onOpenConversation: (conversationId: string) => void
}) {
  // The stream keeps the running list current (`useSSE`'s manager cases): one shared connection.
  useSSE()
  const runningRead = useRunningManagerRuns()
  const unseenRead = useUnseenManagerFailures()
  const recentRead = useRecentManagerRuns()
  const jobsRead = useManagerJobs()
  const documentsRead = useSpecDocuments()
  const running = runningRead.data ?? []
  const unseen = unseenRead.data ?? []
  const recent = recentRead.runs
  const jobs = jobsRead.data
  const documents = documentsRead.data?.documents
  // What could not be read, said in the popover: an unread list is not an empty one.
  const unreadable = [
    runningRead.error && !isNoManager(runningRead.error) ? readableApiError(runningRead.error, 'The runs in progress could not be read.') : null,
    unseenRead.error && !isNoManager(unseenRead.error) ? readableApiError(unseenRead.error, 'The failures could not be read.') : null,
    recentRead.error && !isNoManager(recentRead.error) ? readableApiError(recentRead.error, 'The recent runs could not be read.') : null,
    jobsRead.error && !isNoManager(jobsRead.error) ? 'The job names could not be read; runs show their job keys.' : null,
    documentsRead.error ? 'The spec titles could not be read; runs show their document names.' : null,
  ].filter((line): line is string => Boolean(line))
  const markSeen = useMarkManagerRunsSeen()
  const [open, setOpen] = React.useState(false)
  const closeTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null)
  const posted = React.useRef(new Set<string>())
  const now = useTicking(open && running.length > 0)

  const count = running.length
  const unseenIds = new Set(unseen.map((f) => f.run_id))
  const rows: Row[] = [
    ...running.map((run) => ({ kind: 'running' as const, run })),
    ...unseen.slice().reverse().map((run) => ({ kind: 'unseen' as const, run })),
    ...recent.filter((run) => !unseenIds.has(run.run_id)).map((run) => ({ kind: 'ended' as const, run })),
  ]

  const see = () => {
    const fresh = unseen.map((f) => f.run_id).filter((id) => !posted.current.has(id))
    if (!fresh.length) return
    fresh.forEach((id) => posted.current.add(id))
    markSeen.mutate(fresh)
  }
  const show = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current)
    closeTimer.current = null
    setOpen(true)
    see()
  }
  const hide = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current)
    closeTimer.current = setTimeout(() => setOpen(false), CLOSE_DELAY_MS)
  }
  React.useEffect(() => () => {
    if (closeTimer.current) clearTimeout(closeTimer.current)
  }, [])

  // A Hub that predates the runs routes: a committed bundle reaches the app before its restart.
  if (isNoManager(runningRead.error)) return null

  const label = count
    ? `Manager: ${count} ${count === 1 ? 'run' : 'runs'} in progress`
    : unseen.length
      ? `Manager: ${unseen.length} unseen ${unseen.length === 1 ? 'failure' : 'failures'}`
      : 'Manager: nothing running'

  return (
    <div
      className="aw-manager-indicator-wrap"
      onMouseEnter={show}
      onMouseLeave={hide}
      onKeyDown={(e) => {
        if (e.key === 'Escape') setOpen(false)
      }}
    >
      <button
        type="button"
        data-slot="topbar-icon"
        data-testid="manager-indicator"
        data-running={count ? 'true' : 'false'}
        data-failed={unseen.length ? 'true' : 'false'}
        className="aw-topbar-icon aw-manager-indicator"
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="dialog"
        title={label}
        onClick={() => (open ? setOpen(false) : show())}
      >
        <Icon name={unseen.length && !count ? 'smart_toy_off' : 'smart_toy'} size={15} />
        {count ? (
          <span className="aw-manager-busy" data-testid="manager-indicator-busy" aria-hidden="true">
            <LoadingThread label="Manager runs in progress" size="control" />
          </span>
        ) : null}
        {count ? (
          <span className="aw-topbar-tab-count aw-manager-indicator-count" data-testid="manager-indicator-count">
            {count}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="aw-manager-popover aw-pop" role="dialog" aria-label="Manager runs" data-testid="manager-popover">
          <div className="aw-manager-popover-head">
            {count ? `${count} in progress` : 'Nothing in progress'}
          </div>
          {unreadable.map((line) => (
            <p key={line} className="aw-manager-popover-empty" role="alert">
              {line}
            </p>
          ))}
          {rows.length ? (
            <ul className="aw-manager-popover-list">
              {rows.map((row) => (
                <PopoverRow
                  key={`${row.kind}-${row.run.run_id}`}
                  row={row}
                  title={jobTitle(row.run.job, jobs)}
                  subject={subjectLabel(row.run.subject, documents)}
                  now={now}
                  onOpenRun={() => {
                    setOpen(false)
                    onOpenRun(row.run.run_id)
                  }}
                  onOpenConversation={onOpenConversation}
                />
              ))}
            </ul>
          ) : (
            <p className="aw-manager-popover-empty">No manager runs yet in this window.</p>
          )}
        </div>
      ) : null}
    </div>
  )
}

function PopoverRow({
  row,
  title,
  subject,
  now,
  onOpenRun,
  onOpenConversation,
}: {
  row: Row
  title: string
  subject: string | null
  now: number
  onOpenRun: () => void
  onOpenConversation: (conversationId: string) => void
}) {
  const { run } = row
  const conversationId = 'conversation_id' in run ? run.conversation_id : null
  const status =
    row.kind === 'running'
      ? `Running ${formatDuration(secondsSince(row.run.started_at, now))}`
      : row.kind === 'unseen'
        ? `Failed ${formatDateTime(row.run.ended_at)}`
        : `${endedAs(row.run) === 'failed' ? 'Failed' : 'Finished'} ${formatDateTime(row.run.ended_at)}`
  const outcome = row.kind === 'running' ? 'running' : row.kind === 'unseen' ? 'failed' : endedAs(row.run)
  return (
    <li className="aw-manager-popover-row" data-outcome={outcome}>
      <button type="button" className="aw-manager-popover-run" data-testid={`manager-popover-run-${run.run_id}`} onClick={onOpenRun}>
        <span className="aw-manager-popover-mark" aria-hidden="true">
          {outcome === 'running' ? <LoadingThread label="Running" size="control" /> : <Icon name={outcome === 'failed' ? 'error' : 'check'} size={12} />}
        </span>
        <span className="aw-manager-popover-text">
          <span className="aw-manager-popover-job">{title}</span>
          {subject ? <span className="aw-manager-popover-subject">{subject}</span> : null}
          {'detail' in run && outcome === 'failed' && run.detail ? (
            <span className="aw-manager-popover-detail">{run.detail}</span>
          ) : null}
        </span>
        <span className="aw-manager-popover-time">{status}</span>
      </button>
      {run.job === MENDER_JOB && conversationId ? (
        <button
          type="button"
          className="aw-manager-popover-link"
          data-testid={`manager-popover-run-${run.run_id}-conversation`}
          onClick={() => onOpenConversation(conversationId)}
        >
          Open the mender’s thread
        </button>
      ) : null}
    </li>
  )
}

/** This window's clock in milliseconds, re-read every second while *active* (elapsed times). */
function useTicking(active: boolean): number {
  const [now, setNow] = React.useState(() => Date.now())
  React.useEffect(() => {
    setNow(Date.now())
    if (!active) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [active])
  return now
}

