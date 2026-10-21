import * as React from 'react'
import type { Job } from '@/api/jobs'
import { JobsView } from '@/components/jobs/JobsView'
import { toast } from '@/lib/toast'
import { agents, jobs as fixtureJobs } from '../fixtures'
import type { ScreenProps } from '../routes'

// mock state: the replica's two jobs are both finished loops, so one plain scheduled job is added
// to show an active row and the switch.
const SIMULATED: Job = {
  id: 'job-mock-nightly',
  project_id: fixtureJobs[0]?.project_id ?? '',
  name: 'Nightly drift scan',
  agent: 'QA1',
  message: 'Scan the spec documents for drift against master and report anything new.',
  cron: '0 2 * * *',
  session_mode: 'new',
  enabled: true,
  source: 'hub',
  created_at: '2026-10-15T09:00:00Z',
  last_run: '2026-10-17T02:00:00Z',
  next_run: '2026-10-18T02:00:00Z',
  run_count: 3,
  archived_at: null,
  loop: null,
}

export default function Jobs({ go, now }: ScreenProps) {
  const [jobs, setJobs] = React.useState<Job[]>(() => [SIMULATED, ...fixtureJobs])
  return (
    <JobsView
      jobs={jobs}
      colorIndexOf={(name) => agents.find((a) => a.name === name)?.color_index}
      onToggle={(job, enabled) => {
        setJobs((all) => all.map((j) => (j.id === job.id ? { ...j, enabled } : j)))
        toast({
          title: enabled ? `${job.name} is active` : `${job.name} is paused`,
          tone: 'success',
          action: { label: 'Undo', onClick: () => setJobs((all) => all.map((j) => (j.id === job.id ? { ...j, enabled: !enabled } : j))) },
        })
      }}
      onRunNow={(job) => toast({ title: `${job.name} fired`, description: `${job.agent} starts a turn now.` })}
      onEdit={() => undefined}
      onArchive={(job) => {
        setJobs((all) => all.filter((j) => j.id !== job.id))
        toast({ title: `${job.name} archived`, action: { label: 'Undo', onClick: () => setJobs((all) => [job, ...all]) } })
      }}
      onNew={() => undefined}
      onOpenTasks={() => go({ kind: 'tab', tab: 'tasks' })}
      now={now}
    />
  )
}
