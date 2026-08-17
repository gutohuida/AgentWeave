import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { EmptyState } from '@/components/common/EmptyState'
import { Button } from '@/components/ui/button'
import { JobCard } from './JobCard'
import { JobForm } from './JobForm'
import {
  useJobs,
  useRunJob,
  usePauseJob,
  useResumeJob,
  useDeleteJob,
  useCreateJob,
  JobCreate,
} from '@/api/jobs'

interface JobsPageProps {
  /** A loop's queue/current-item link, clicked: switch to the Tasks tab filtered to it. */
  onOpenTasks?: (taskIds: string[]) => void
}

export function JobsPage({ onOpenTasks }: JobsPageProps) {
  const { data: jobs, isLoading } = useJobs()
  const [showForm, setShowForm] = useState(false)
  const [filter, setFilter] = useState<'all' | 'active' | 'paused'>('all')

  const runJob = useRunJob()
  const pauseJob = usePauseJob()
  const resumeJob = useResumeJob()
  const deleteJob = useDeleteJob()
  const createJob = useCreateJob()

  const isPending = runJob.isPending || pauseJob.isPending || resumeJob.isPending || deleteJob.isPending || createJob.isPending

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
      <div className="flex items-center justify-center h-full">
        <div className="flex items-center gap-3">
          <Icon name="sync" size={24} className="animate-spin" style={{ color: 'var(--text-3)' }} />
          <span className="text-sm" style={{ color: 'var(--text-3)' }}>Loading jobs…</span>
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

      {/* Filter tabs */}
      <div className="flex items-center gap-1 px-4 py-2" style={{ borderBottom: '1px solid var(--border)' }}>
        {(['all', 'active', 'paused'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            data-active={filter === f ? 'true' : 'false'}
            className="row-item w-auto rounded-full px-3 py-1.5 text-[11px] font-medium capitalize"
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
                onDelete={deleteJob.mutate}
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
            <span>Jobs fire based on server time</span>
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
