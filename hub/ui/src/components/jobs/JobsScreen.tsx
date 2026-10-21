import * as React from 'react'
import { useAgents } from '@/api/agents'
import {
  useArchiveJob,
  useArchivedJobs,
  useCreateJob,
  useJobHistory,
  useJobs,
  usePauseJob,
  useResumeJob,
  useRunJob,
  type Job,
  type JobCreate,
} from '@/api/jobs'
import { useTasks } from '@/api/tasks'
import { QueryErrorNotice } from '@/components/common/QueryErrorNotice'
import { toast } from '@/lib/toast'
import { JobDetails } from './JobDetails'
import { JobForm } from './JobForm'
import { JobsView, type JobRowExtras } from './JobsView'

/** The Hub's own sentence for a refused request: its `detail` when the body carries one, else the
 *  raw message. `fallback` covers a rejection that is not an Error at all. */
function errorDetail(error: unknown, fallback: string): string {
  if (!(error instanceof Error)) return fallback
  try {
    const parsed = JSON.parse(error.message) as { detail?: unknown }
    return typeof parsed.detail === 'string' ? parsed.detail : error.message
  } catch {
    return error.message
  }
}

/** The Jobs tab, wired: `JobsView` fed from the jobs hooks. Drop-in for the old `JobsPage`. */
export function JobsScreen({ onOpenTasks }: { onOpenTasks?: (taskIds: string[]) => void }) {
  const { data: jobs, isLoading, error: jobsError } = useJobs()
  const { data: archived, error: archivedError } = useArchivedJobs()
  const { data: agents = [], error: agentsError } = useAgents()
  const [showForm, setShowForm] = React.useState(false)
  // A refused Run or Archive names why (F411); it stays until the next action starts.
  const [notice, setNotice] = React.useState<string | null>(null)

  const runJob = useRunJob()
  const pauseJob = usePauseJob()
  const resumeJob = useResumeJob()
  const archiveJob = useArchiveJob()
  const createJob = useCreateJob()
  const pending = runJob.isPending || pauseJob.isPending || resumeJob.isPending || archiveJob.isPending || createJob.isPending

  const setEnabled = (job: Job, enabled: boolean, undo = true) => {
    setNotice(null)
    const mutation = enabled ? resumeJob : pauseJob
    mutation.mutate(job.id, {
      onSuccess: () =>
        toast({
          title: enabled ? `${job.name} is active` : `${job.name} is paused`,
          tone: 'success',
          action: undo ? { label: 'Undo', onClick: () => setEnabled(job, !enabled, false) } : undefined,
        }),
      onError: (error: unknown) => setNotice(errorDetail(error, enabled ? 'Could not resume job' : 'Could not pause job')),
    })
  }

  // A failed list must not read as "no jobs yet": say so instead of the empty state.
  if (jobsError && !jobs) {
    return <QueryErrorNotice failures={[['the jobs', jobsError]]} />
  }

  return (
    <>
      <QueryErrorNotice failures={[['the agents', agentsError]]} />
      <JobsView
        jobs={jobs ?? []}
        archived={archived ?? []}
        archivedError={archivedError ? errorDetail(archivedError, 'the Hub did not answer.') : null}
        loading={isLoading}
        notice={notice}
        pending={pending}
        colorIndexOf={(name) => agents.find((a) => a.name === name)?.color_index}
        onToggle={(job, enabled) => setEnabled(job, enabled)}
        onRunNow={(job) => {
          setNotice(null)
          runJob.mutate(job.id, {
            onSuccess: () => toast({ title: `${job.name} fired`, description: `${job.agent} starts a turn now.` }),
            onError: (error: unknown) => setNotice(errorDetail(error, 'Could not run job')),
          })
        }}
        onArchive={(job) => {
          setNotice(null)
          archiveJob.mutate(job.id, {
            onSuccess: () => toast({ title: `${job.name} archived`, description: 'Its history is kept under Archived.' }),
            onError: (error: unknown) => setNotice(errorDetail(error, 'Could not archive job')),
          })
        }}
        onNew={() => setShowForm(true)}
        renderRow={(job, row) => <LiveJobRow job={job} row={row} onOpenTasks={onOpenTasks} />}
        now={new Date()}
      />
      {showForm ? (
        <JobForm
          onSubmit={(job: JobCreate) => createJob.mutate(job, { onSuccess: () => setShowForm(false) })}
          onCancel={() => setShowForm(false)}
          isPending={createJob.isPending}
        />
      ) : null}
    </>
  )
}

/** One row's live state: open or not, and its history, fetched only while open (the list response
 *  carries none). A loop's row also holds its tasks' ids, which its progress link and its current
 *  items open on the Tasks tab. */
function LiveJobRow(props: { job: Job; row: (extras: JobRowExtras) => React.ReactNode; onOpenTasks?: (taskIds: string[]) => void }) {
  return props.job.loop ? <LiveLoopJobRow {...props} /> : <LiveRow {...props} />
}

function LiveLoopJobRow(props: { job: Job; row: (extras: JobRowExtras) => React.ReactNode; onOpenTasks?: (taskIds: string[]) => void }) {
  const { data: loopTaskPage, error: loopTasksError } = useTasks({ loopId: props.job.loop!.id })
  // Unknown, not none: a failed read leaves the loop's task link absent rather than empty.
  return <LiveRow {...props} loopTaskIds={loopTasksError ? undefined : loopTaskPage?.tasks?.map((t) => t.id)} />
}

function LiveRow({
  job,
  row,
  onOpenTasks,
  loopTaskIds,
}: {
  job: Job
  row: (extras: JobRowExtras) => React.ReactNode
  onOpenTasks?: (taskIds: string[]) => void
  loopTaskIds?: string[]
}) {
  const [expanded, setExpanded] = React.useState(false)
  const { data: fetched, isLoading, error: historyError } = useJobHistory(job.id, expanded)
  const history = job.history ?? fetched
  const canOpen = Boolean(onOpenTasks && loopTaskIds && loopTaskIds.length > 0)
  return (
    <>
      {row({
        expanded,
        onToggleExpanded: () => setExpanded((v) => !v),
        history,
        openTasks: canOpen ? () => onOpenTasks!(loopTaskIds!) : undefined,
        details: (
          <JobDetails job={job} runs={history} runsLoading={isLoading} runsError={historyError ? errorDetail(historyError, 'the Hub did not answer.') : null} loopTaskIds={loopTaskIds} onOpenTasks={onOpenTasks} now={new Date()} />
        ),
      })}
    </>
  )
}
