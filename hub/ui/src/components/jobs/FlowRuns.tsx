import { RunList } from '@/components/traces/RunList'
import type { Job } from '@/api/jobs'

/** Every run a flow (or loop) started, newest first, with its profile, task, start and outcome
 *  (profiles-threads-and-builds-everywhere FR-13). Read from the runs themselves, so a stopped or
 *  archived flow keeps them; each opens its trace and conversation. */
export function FlowRuns({ job }: { job: Job }) {
  if (!job.loop) return null
  return (
    <RunList
      filters={{ loop_id: job.loop.id }}
      label={`Runs of ${job.name}`}
      emptyText="It has not started a run yet."
      showProfile
    />
  )
}
