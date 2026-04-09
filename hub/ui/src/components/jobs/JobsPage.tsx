import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { EmptyState } from '@/components/common/EmptyState'
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

export function JobsPage() {
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
          <Icon name="sync" size={24} className="animate-spin" style={{ color: 'var(--on-sv)' }} />
          <span className="m3-body-large" style={{ color: 'var(--on-sv)' }}>Loading jobs…</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-4" style={{ borderBottom: '1px solid var(--outline-variant)' }}>
        <div>
          <h1 className="m3-headline-small" style={{ color: 'var(--foreground)' }}>
            Scheduled Jobs
          </h1>
          <p className="m3-body-small mt-0.5" style={{ color: 'var(--on-sv)' }}>
            Recurring tasks that trigger agents automatically
          </p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="m3-btn m3-btn-primary flex items-center gap-2"
        >
          <Icon name="add" size={18} />
          New Job
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-1 px-4 py-2" style={{ borderBottom: '1px solid var(--outline-variant)' }}>
        {(['all', 'active', 'paused'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className="px-3 py-1.5 rounded-full m3-label-small capitalize transition-colors"
            style={{
              background: filter === f ? 'var(--p-cont)' : 'transparent',
              color: filter === f ? 'var(--on-p-cont)' : 'var(--on-sv)',
            }}
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
            <button
              onClick={() => setShowForm(true)}
              className="m3-btn m3-btn-primary flex items-center gap-2 mt-4"
            >
              <Icon name="add" size={18} />
              Create First Job
            </button>
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
              />
            ))}
          </div>
        )}
      </div>

      {/* Stats footer */}
      {jobs && jobs.length > 0 && (
        <div
          className="flex items-center justify-between px-4 py-2 m3-body-small"
          style={{ color: 'var(--on-sv)', borderTop: '1px solid var(--outline-variant)' }}
        >
          <div className="flex items-center gap-4">
            <span>Total: {jobs.length}</span>
            <span style={{ color: 'var(--success)' }}>Active: {jobs.filter(j => j.enabled).length}</span>
            <span style={{ color: 'var(--on-sv)', opacity: 0.6 }}>Paused: {jobs.filter(j => !j.enabled).length}</span>
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
