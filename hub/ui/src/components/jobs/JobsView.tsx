import * as React from 'react'
import type { Job, JobRun } from '@/api/jobs'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import { Segmented } from '@/components/ui/segmented'
import { Switch } from '@/components/ui/switch'
import { agentColorVars } from '@/lib/agentColors'
import { cronDayAmbiguity } from '@/lib/cron'
import { describeCron, formatAgo, formatDateTime, formatIn } from '@/lib/format'
import { jobState, loopStateLabel } from '@/lib/jobState'
import { TrendDots } from './JobDetails'
import '@/styles/jobs.css'
import { LoadingThread } from '@/components/common/LoadingThread'

/** The Jobs tab: one full-width row per job.
 *
 *  Replaces half-width cards that showed the raw cron string as a chip, three unexplained tags
 *  ("Complete · new · 14 fired"), a grey Run button and a red icon, over a footer repeating the
 *  filter's counts. A row now reads left to right: what it is and who runs it, when it runs (in
 *  words, the cron in its title), what its loop has got through, when it last ran, and whether it
 *  is on. A loop that has finished says so instead of offering a switch it would refuse (F821).
 *
 *  A row opens (the chevron) to its message, recent firings and loop state. `renderRow` lets the
 *  container hold each row's open state and fetch its history only while it is open. */

export type JobFilter = 'all' | 'active' | 'paused' | 'archived'

/** What a row needs beyond the job itself; the container supplies these per row. */
export interface JobRowExtras {
  /** Recent firings when in hand (the list response carries none; the open row fetches them). */
  history?: JobRun[]
  /** The open row's body. */
  details?: React.ReactNode
  expanded?: boolean
  onToggleExpanded?: () => void
  /** Opens this row's loop tasks; takes precedence over the view's `onOpenTasks`. */
  openTasks?: () => void
}

export function JobsView({
  jobs,
  archived = [],
  archivedError,
  loading,
  notice,
  pending,
  colorIndexOf,
  onToggle,
  onRunNow,
  onEdit,
  onArchive,
  onNew,
  onOpenTasks,
  renderRow,
  now,
}: {
  jobs: Job[]
  /** Archived jobs, read-only (F637): listed under their own filter, counted in the empty state. */
  archived?: Job[]
  archivedError?: string | null
  loading?: boolean
  /** The Hub's sentence for a refused Run or Archive (F411), shown until the next action. */
  notice?: string | null
  pending?: boolean
  colorIndexOf: (agent: string) => number | null | undefined
  onToggle: (job: Job, enabled: boolean) => void
  onRunNow: (job: Job) => void
  /** Omitted where no editor exists; the row then offers no Edit. */
  onEdit?: (job: Job) => void
  onArchive: (job: Job) => void
  onNew: () => void
  onOpenTasks?: (job: Job) => void
  /** Wraps a row so its container can hold per-row state. Defaults to the bare row. */
  renderRow?: (job: Job, row: (extras: JobRowExtras) => React.ReactNode) => React.ReactNode
  now: Date
}) {
  const [filter, setFilter] = React.useState<JobFilter>('all')
  const counts = {
    all: jobs.length,
    active: jobs.filter((j) => jobState(j) === 'active').length,
    paused: jobs.filter((j) => jobState(j) !== 'active').length,
  }
  const shown = jobs.filter((j) => filter === 'all' || (filter === 'active' ? jobState(j) === 'active' : jobState(j) !== 'active'))
  const options = [
    { value: 'all' as const, label: 'All', count: counts.all },
    { value: 'active' as const, label: 'Active', count: counts.active },
    { value: 'paused' as const, label: 'Paused or finished', count: counts.paused },
    ...(archived.length > 0 ? [{ value: 'archived' as const, label: 'Archived', count: archived.length }] : []),
  ]

  const row = (job: Job) => (extras: JobRowExtras) => (
    <JobRow
      job={job}
      colorIndex={colorIndexOf(job.agent)}
      onToggle={onToggle}
      onRunNow={onRunNow}
      onEdit={onEdit}
      onArchive={onArchive}
      onOpenTasks={onOpenTasks}
      pending={pending}
      now={now}
      {...extras}
    />
  )

  return (
    <div className="aw-jobs">
      <div className="aw-jobs-toolbar">
        <Segmented label="Show jobs" value={filter} onChange={setFilter} options={options} />
        <span className="aw-jobs-clock" title="Schedules fire on the Hub's UTC clock">
          <Icon name="schedule" size={12} /> Times in UTC
        </span>
        <Button variant="primary" size="sm" onClick={onNew}>
          <Icon name="add" size={14} /> New job
        </Button>
      </div>

      {notice ? (
        <div className="aw-jobs-notice" role="alert">
          <Icon name="error_outline" size={14} /> {notice}
        </div>
      ) : null}

      {loading ? (
        <LoadingThread label="Loading jobs" />
      ) : filter === 'archived' ? (
        archivedError ? (
          // Not "No archived jobs": a list that could not be read is not an empty one.
          <p className="aw-jobs-notice" role="alert">
            Could not read the archived jobs: {archivedError}
          </p>
        ) : (
          <ArchivedJobs jobs={archived} now={now} />
        )
      ) : jobs.length === 0 && archived.length > 0 ? (
        // F637: archiving every job is not having none. Say what is archived, and where.
        <div className="aw-jobs-empty">
          <span className="aw-jobs-empty-icon" aria-hidden="true">
            <Icon name="schedule" size={18} />
          </span>
          <p className="aw-jobs-empty-title">No active or paused jobs</p>
          <p className="aw-jobs-empty-text">
            {archived.length} archived {archived.length === 1 ? 'job is' : 'jobs are'} kept with their history.
          </p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setFilter('archived')}>
              Show archived
            </Button>
            <Button variant="primary" size="sm" onClick={onNew}>
              <Icon name="add" size={14} /> Create a job
            </Button>
          </div>
        </div>
      ) : shown.length === 0 ? (
        <JobsEmpty filter={filter} onNew={onNew} />
      ) : (
        <ul className="aw-jobs-list" aria-label="Jobs">
          {shown.map((job) => (
            <React.Fragment key={job.id}>{renderRow ? renderRow(job, row(job)) : row(job)({})}</React.Fragment>
          ))}
        </ul>
      )}
    </div>
  )
}

export function JobRow({
  job,
  colorIndex,
  onToggle,
  onRunNow,
  onEdit,
  onArchive,
  onOpenTasks,
  pending,
  history,
  details,
  expanded: expandedProp,
  onToggleExpanded,
  openTasks: openTasksProp,
  now,
}: {
  job: Job
  colorIndex: number | null | undefined
  onToggle: (job: Job, enabled: boolean) => void
  onRunNow: (job: Job) => void
  onEdit?: (job: Job) => void
  onArchive: (job: Job) => void
  onOpenTasks?: (job: Job) => void
  pending?: boolean
  now: Date
} & JobRowExtras) {
  const [expandedLocal, setExpandedLocal] = React.useState(false)
  const expanded = expandedProp ?? expandedLocal
  const toggleExpanded = onToggleExpanded ?? (() => setExpandedLocal((v) => !v))
  const [confirmArchive, setConfirmArchive] = React.useState(false)
  const openTasks = openTasksProp ?? (onOpenTasks ? () => onOpenTasks(job) : undefined)

  const state = jobState(job)
  const loopState = loopStateLabel(job)
  const stopping = loopState === 'Stopping'
  const color = agentColorVars(colorIndex)
  const loop = job.loop
  const queue = loop?.queue ?? {}
  const total = Object.values(queue).reduce((n, v) => n + v, 0)
  const done = queue.approved ?? 0
  const current = loop?.current_tasks?.[0]
  // Firings the queue refused never reach `run_count`, so they are named beside it (F25).
  const refused = (history ?? []).filter((run) => run.status === 'skipped').length
  // F1: a schedule restricting both day fields fires on a different day than croniter's next_run.
  const ambiguity = cronDayAmbiguity(job.cron)

  return (
    <li className="aw-job-item" data-open={expanded ? 'true' : 'false'}>
      <div className="aw-job-row" data-state={state}>
        <span className="aw-job-icon" aria-hidden="true">
          <Icon name={loop ? 'sync' : 'schedule'} size={15} />
        </span>

        <div className="aw-job-main">
          <div className="aw-job-name">
            <span className="truncate">{job.name}</span>
            {loop ? <span className="aw-job-kind">{loop.spec_document_id ? 'Flow' : 'Loop'}</span> : null}
            {/* Where a job is defined is a category, not a state: neutral, never amber. */}
            {job.source === 'local' ? (
              <span className="aw-chip aw-job-kind" style={{ color: 'var(--text-2)' }} title="Defined in the project's own files">
                <Icon name="home" size={10} /> Local
              </span>
            ) : null}
          </div>
          <div className="aw-job-sub">
            <span className="aw-job-agent" style={{ '--agent-accent': color.accent } as React.CSSProperties}>
              <span className="aw-agent-dot" /> {job.agent}
            </span>
            <span aria-hidden="true">·</span>
            <span title={`${job.cron} (UTC)`}>{describeCron(job.cron)}</span>
            {job.session_mode === 'resume' ? (
              <>
                <span aria-hidden="true">·</span>
                <span>continues one conversation</span>
              </>
            ) : null}
          </div>
        </div>

        <div className="aw-job-progress">
          {loop && total > 0 ? (
            <>
              <button
                data-slot="job-progress"
                type="button"
                className="aw-job-progress-label"
                onClick={() => openTasks?.()}
                title="Show this loop's tasks"
              >
                {done} of {total} tasks approved
              </button>
              <span className="aw-job-bar" aria-hidden="true">
                <span style={{ width: `${(done / total) * 100}%` }} />
              </span>
              <span className="aw-job-progress-note">
                {state === 'finished'
                  ? loop.ending_state === 'completed'
                    ? 'Finished: every task approved'
                    : 'Stopped'
                  : current
                    ? `Now: ${current.title}`
                    : (loop.stall_reason ?? 'Waiting for its next firing')}
              </span>
            </>
          ) : (
            <span className="aw-job-progress-note">{job.message}</span>
          )}
        </div>

        <div className="aw-job-last" title={job.last_run ? formatDateTime(job.last_run, now) : undefined}>
          <span>{job.last_run ? `Ran ${formatAgo(job.last_run, now)} ago` : 'Never run'}</span>
          <span className="aw-job-last-count">
            {/* "fired", not "runs": a wide firing starts several agents but counts once (design D1). */}
            <span>{job.run_count} fired</span>
            {refused > 0 ? (
              <span className="aw-job-refused" data-testid={`job-refused-${job.id}`}>
                {' · '}
                {refused} refused
              </span>
            ) : null}
          </span>
          {ambiguity ? (
            <span className="aw-job-next" data-tone="amber" data-testid={`job-cron-ambiguity-${job.id}`} title={ambiguity}>
              Next: not knowable — this schedule restricts both day-of-month and day-of-week
            </span>
          ) : job.next_run && job.enabled && !stopping && state !== 'finished' ? (
            <span className="aw-job-next" title={formatDateTime(job.next_run, now)}>
              Next: {formatIn(job.next_run, now)}
            </span>
          ) : null}
          {history && history.length > 0 ? <TrendDots runs={history} /> : null}
        </div>

        <div className="aw-job-state">
          {state === 'finished' ? (
            <span className="aw-job-finished">
              <Icon name="check_circle" size={13} /> {loopState}
            </span>
          ) : (
            <label className="aw-job-switch">
              <span>{stopping ? 'Stopping' : state === 'active' ? 'Active' : 'Paused'}</span>
              <Switch
                size="sm"
                checked={state === 'active'}
                disabled={pending}
                onCheckedChange={(v) => onToggle(job, v)}
                aria-label={state === 'active' ? `Pause ${job.name}` : `Resume ${job.name}`}
              />
            </label>
          )}
        </div>

        <div className="aw-job-actions">
          <Button
            variant="outline"
            size="xs"
            disabled={pending || !job.enabled || state === 'finished'}
            onClick={() => onRunNow(job)}
            title={state === 'finished' ? 'A finished loop does not fire again' : !job.enabled ? 'Resume it to fire it' : 'Fire once now'}
          >
            <Icon name="play_arrow" size={12} /> Run now
          </Button>
          <Menu>
            <MenuTrigger asChild>
              <Button variant="ghost" size="icon-xs" aria-label={`More for ${job.name}`}>
                <Icon name="more_horiz" size={15} />
              </Button>
            </MenuTrigger>
            <MenuContent>
              {onEdit ? (
                <MenuItem icon="edit" onSelect={() => onEdit(job)}>
                  Edit
                </MenuItem>
              ) : null}
              {loop && openTasks ? (
                <MenuItem icon="task_alt" onSelect={() => openTasks()}>
                  Show its tasks
                </MenuItem>
              ) : null}
              {onEdit || (loop && openTasks) ? <MenuSeparator /> : null}
              <MenuItem icon="archive" onSelect={() => setConfirmArchive(true)}>
                Archive
              </MenuItem>
            </MenuContent>
          </Menu>
          {details !== undefined ? (
            <Button
              variant="ghost"
              size="icon-xs"
              aria-expanded={expanded}
              aria-label={expanded ? 'Collapse job details' : 'Expand job details'}
              onClick={toggleExpanded}
            >
              <Icon name="expand_more" size={15} className="aw-job-chevron" />
            </Button>
          ) : null}
        </div>
      </div>

      {expanded && details ? <div className="aw-job-detail-host">{details}</div> : null}

      <Dialog open={confirmArchive} onOpenChange={setConfirmArchive}>
        {confirmArchive ? (
          <DialogContent
            title={`Archive ${job.name}?`}
            description="It stops firing. Nothing is deleted: its history stays, listed under Archived."
            width={420}
            footer={
              <>
                <DialogClose asChild>
                  <Button variant="ghost" size="sm">
                    Cancel
                  </Button>
                </DialogClose>
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={pending}
                  onClick={() => {
                    setConfirmArchive(false)
                    onArchive(job)
                  }}
                >
                  Archive
                </Button>
              </>
            }
          />
        ) : null}
      </Dialog>
    </li>
  )
}

/** Archived jobs, read-only (F637): nothing is deleted on archive. */
function ArchivedJobs({ jobs, now }: { jobs: Job[]; now: Date }) {
  if (jobs.length === 0) {
    return (
      <div className="aw-jobs-empty">
        <p className="aw-jobs-empty-title">No archived jobs</p>
      </div>
    )
  }
  return (
    <ul className="aw-jobs-list" aria-label="Archived jobs">
      {jobs.map((job) => (
        <li key={job.id} className="aw-job-archived" data-testid={`archived-job-${job.id}`}>
          <span className="aw-job-name">{job.name}</span>
          <span className="aw-job-sub">
            {job.agent} · fired {job.run_count} time{job.run_count === 1 ? '' : 's'}
            {job.archived_at ? <span title={formatDateTime(job.archived_at, now)}> · archived {formatAgo(job.archived_at, now)} ago</span> : null}
          </span>
        </li>
      ))}
    </ul>
  )
}

function JobsEmpty({ filter, onNew }: { filter: JobFilter; onNew: () => void }) {
  return (
    <div className="aw-jobs-empty">
      <span className="aw-jobs-empty-icon" aria-hidden="true">
        <Icon name="schedule" size={18} />
      </span>
      <p className="aw-jobs-empty-title">{filter === 'all' ? 'No jobs yet' : filter === 'active' ? 'Nothing is running on a schedule' : 'Nothing paused or finished'}</p>
      <p className="aw-jobs-empty-text">
        A job gives an agent a message on a schedule. A loop works through a document's tasks until they are done.
      </p>
      {filter === 'all' ? (
        <Button variant="outline" size="sm" onClick={onNew}>
          <Icon name="add" size={14} /> Create the first job
        </Button>
      ) : null}
    </div>
  )
}
