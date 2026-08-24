import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { EmptyState } from '@/components/common/EmptyState'
import { Button } from '@/components/ui/button'
import { tint } from '@/lib/colorTint'
import { JobCard } from './JobCard'
import { JobForm } from './JobForm'
import {
  useJobs,
  useRunJob,
  usePauseJob,
  useResumeJob,
  useArchiveJob,
  useCreateJob,
  JobCreate,
} from '@/api/jobs'

function errorDetail(error: unknown): string {
  if (!(error instanceof Error)) return 'Could not archive job'
  try {
    const parsed = JSON.parse(error.message) as { detail?: string }
    return parsed.detail ?? error.message
  } catch {
    return error.message
  }
}

interface JobsPageProps {
  /** A loop's queue/current-item link, clicked: switch to the Tasks tab filtered to it. */
  onOpenTasks?: (taskIds: string[]) => void
}

export function JobsPage({ onOpenTasks }: JobsPageProps) {
  const { data: jobs, isLoading } = useJobs()
  const [showForm, setShowForm] = useState(false)
  const [filter, setFilter] = useState<'all' | 'active' | 'paused'>('all')
  const [archiveError, setArchiveError] = useState<string | null>(null)

  const runJob = useRunJob()
  const pauseJob = usePauseJob()
  const resumeJob = useResumeJob()
  const archiveJob = useArchiveJob()
  const createJob = useCreateJob()

  const isPending = runJob.isPending || pauseJob.isPending || resumeJob.isPending || archiveJob.isPending || createJob.isPending

  const handleArchive = (id: string) => {
    setArchiveError(null)
    archiveJob.mutate(id, {
      onError: (error: unknown) => setArchiveError(errorDetail(error)),
    })
  }

  const filteredJobs = jobs?.filter((job) => {
    if (filter === 'active') return job.enabled
    if (filter === 'paused') return !job.enabled
    return true
  })

  const handleCreate = (job: JobCreate) => {
    createJob.mutate(job, {
      onSuccess: () => setShowForm(false),
    })
  }

  if (isLoading) {
    return (
      <div className="p-4" aria-label="Loading jobs">
        <div className="grid max-w-3xl gap-3">
          {[0, 1, 2].map((item) => (
            <div key={item} className="elevation-resting rounded-xl p-4" aria-hidden="true">
              <div className="skeleton h-4 w-2/5" />
              <div className="skeleton mt-3 h-3 w-1/4" />
              <div className="skeleton mt-3 h-6 w-1/3" />
              <div className="mt-4 flex gap-2"><div className="skeleton h-7 w-16" /><div className="skeleton h-7 w-20" /></div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-4" style={{ borderBottom: '1px solid var(--border)' }}>
        <div>
          <h1 className="text-lg font-normal" style={{ color: 'var(--text)' }}>
            Scheduled Jobs
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-3)' }}>
            Recurring tasks that trigger agents automatically
          </p>
        </div>
        <Button variant="primary" size="md" onClick={() => setShowForm(true)}>
          <Icon name="add" size={18} />
          New Job
        </Button>
      </div>

      {archiveError && (
        <div
          role="alert"
          className="mx-4 mt-3 rounded-md px-3 py-2 text-xs"
          style={{ background: tint('var(--red)'), color: 'var(--red)' }}
        >
          {archiveError}
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex items-center gap-1 px-4 py-2" style={{ borderBottom: '1px solid var(--border)' }}>
        {(['all', 'active', 'paused'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            data-active={filter === f ? 'true' : 'false'}
            className="row-item aw-chip w-auto px-3 py-1.5 text-[11px] font-medium capitalize"
            data-pill="true"
          >
            {f}
            {f !== 'all' && jobs && (
              <span className="ml-1.5 opacity-70">
                {f === 'active' ? jobs.filter(j => j.enabled).length : jobs.filter(j => !j.enabled).length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {!jobs || jobs.length === 0 ? (
          <div className="flex flex-col items-center">
            <EmptyState
              icon="schedule"
              title="No jobs yet"
              description="Create scheduled jobs to automatically trigger agents on a cron schedule."
            />
            <Button variant="primary" size="md" onClick={() => setShowForm(true)} className="mt-4">
              <Icon name="add" size={18} />
              Create First Job
            </Button>
          </div>
        ) : filteredJobs?.length === 0 ? (
          <EmptyState
            icon="filter_list"
            title="No jobs match"
            description={`No ${filter} jobs found.`}
          />
        ) : (
          <div className="grid gap-3 max-w-3xl">
            {filteredJobs?.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                onRun={runJob.mutate}
                onPause={pauseJob.mutate}
                onResume={resumeJob.mutate}
                onArchive={handleArchive}
                isPending={isPending}
                onOpenTasks={onOpenTasks}
              />
            ))}
          </div>
        )}
      </div>

      {/* Stats footer */}
      {jobs && jobs.length > 0 && (
        <div
          className="flex items-center justify-between px-4 py-2 text-xs"
          style={{ color: 'var(--text-3)', borderTop: '1px solid var(--border)' }}
        >
          <div className="flex items-center gap-4">
            <span>Total: {jobs.length}</span>
            <span style={{ color: 'var(--green)' }}>Active: {jobs.filter(j => j.enabled).length}</span>
            <span style={{ opacity: 0.6 }}>Paused: {jobs.filter(j => !j.enabled).length}</span>
          </div>
          <div className="flex items-center gap-1">
            <Icon name="info" size={14} />
            {/* F2: "server time" was a UTC clock wearing a local label. The scheduler pins its
                CronTrigger to UTC (`scheduler.py`) and `cron.ts` computes its preview in UTC to
                match, so the value was always right and only the word was wrong — by an hour, every
                summer, on the operator's own machine. */}
            <span>Jobs fire on a UTC clock</span>
          </div>
        </div>
      )}

      {/* Create form modal */}
      {showForm && (
        <JobForm
          onSubmit={handleCreate}
          onCancel={() => setShowForm(false)}
          isPending={createJob.isPending}
        />
      )}
    </div>
  )
}
