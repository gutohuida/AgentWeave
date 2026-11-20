import type { RunKind, TraceSummary } from '@/api/traces'

/** What a profile's or a flow's run list says about a run (`RunList`): its kind, how it ended, its task. */

export const RUN_KIND_LABEL: Record<RunKind, string> = {
  thread: 'Thread',
  task: 'Task build',
  review: 'Review',
  mender: 'Mender',
  job: 'Job',
  message: 'Message',
}

export const RUN_KIND_ICON: Record<RunKind, string> = {
  thread: 'chat',
  task: 'hammer',
  review: 'fact_check',
  mender: 'build',
  job: 'schedule',
  message: 'send',
}

export type Outcome = { label: string; icon: string; color: string }

/** How a run ended, as a word and a shape as well as a colour. */
export function runOutcome(run: TraceSummary): Outcome {
  const status = run.run_status ?? (run.ended ? null : 'running')
  switch (status) {
    case 'running':
      return { label: 'Running', icon: 'circle_dot', color: 'var(--blue)' }
    case 'completed':
      return { label: 'Completed', icon: 'check_circle', color: 'var(--green)' }
    case 'failed':
      return { label: 'Failed', icon: 'error', color: 'var(--red)' }
    case 'cancelled':
    case 'interrupted':
    case 'stopped':
      return { label: 'Stopped', icon: 'stop_circle', color: 'var(--text-2)' }
    default:
      return run.status === 'error'
        ? { label: 'Ended in error', icon: 'error', color: 'var(--red)' }
        : { label: 'Ended', icon: 'circle', color: 'var(--text-2)' }
  }
}

export function runTaskLabel(run: TraceSummary): string | null {
  if (run.task_ref && run.task_title) return `${run.task_ref} ${run.task_title}`
  if (run.task_ref || run.task_title) return run.task_ref ?? run.task_title ?? null
  if (run.task_missing) return 'A task that no longer exists'
  return null
}
