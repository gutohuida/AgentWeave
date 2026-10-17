import { readableApiError } from '@/api/client'
import { useRerunTaskChecks, useTaskChecks, type TaskCheckRun } from '@/api/tasks'
import { Button } from '@/components/ui/button'
import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { Expander } from '@/components/common/Expander'
import { hubDate } from '@/lib/hubTime'

const LABEL: Record<TaskCheckRun['state'], string> = {
  running: 'Checks running',
  passed: 'Checks passed',
  failed: 'Checks failed',
  error: 'Checks could not run',
  interrupted: 'Checks interrupted',
}

const COLOR: Record<TaskCheckRun['state'], string> = {
  running: 'var(--text-3)',
  passed: 'var(--green)',
  failed: 'var(--red)',
  error: 'var(--red)',
  interrupted: 'var(--text-3)',
}

/**
 * The latest run of the project's checks on the work this task's approval would merge
 * (`approval-runs-the-projects-checks`). Approval is refused until they pass, so this is where the
 * operator reads why, and re-runs them once whatever broke them outside the work is fixed.
 */
/** One earlier run: its state, when, and every check's exit code and duration. */
function EarlierRun({ run }: { run: TaskCheckRun }) {
  return (
    <li data-testid={`task-check-run-${run.id}`} className="grid gap-0.5 py-1.5">
      <span className="text-[11.5px] flex items-center gap-1.5" style={{ color: COLOR[run.state] }}>
        {LABEL[run.state]}
        <span style={{ color: 'var(--text-3)' }}>
          {run.started_at ? ` · ${hubDate(run.started_at).toLocaleString()}` : ''}
          {run.merged_sha ? ` · on ${run.merged_sha.slice(0, 8)}` : ''}
        </span>
      </span>
      {run.error ? (
        <span className="text-[11px]" style={{ color: 'var(--text-3)' }}>{run.error}</span>
      ) : null}
      <span className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px]" style={{ color: 'var(--text-2)' }}>
        {run.results.map((result) => (
          <span
            key={result.name}
            data-testid={`task-check-result-${run.id}-${result.name}`}
            style={{ color: result.timed_out || result.exit_code !== 0 ? 'var(--red)' : undefined }}
          >
            {result.name} · {result.timed_out ? 'timed out' : `exit ${result.exit_code}`}
            {result.duration_seconds != null ? ` · ${result.duration_seconds}s` : ''}
          </span>
        ))}
      </span>
    </li>
  )
}

export function TaskChecksRow({ taskId }: { taskId: string }) {
  const { data, error } = useTaskChecks(taskId, true)
  const [historyOpen, setHistoryOpen] = useState(false)
  const rerun = useRerunTaskChecks(taskId)
  // A failed read is said, not shown as "no checks": approval may be waiting on them.
  if (error) {
    return (
      <p role="alert" className="text-[11px]" style={{ color: 'var(--red)' }}>
        {readableApiError(error, "This task's checks could not be read.")}
      </p>
    )
  }
  if (!data?.configured) return null
  const latest = data.runs[0]
  const state: TaskCheckRun['state'] | null = data.running ? 'running' : (latest?.state ?? null)
  const failing = (latest?.results ?? []).filter((result) => result.timed_out || result.exit_code !== 0)

  return (
    <div data-testid={`task-checks-${taskId}`} className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[12px] flex items-center gap-1.5" style={{ color: state ? COLOR[state] : 'var(--text-3)' }}>
          <Icon name={state === 'passed' ? 'check_circle' : state === 'failed' || state === 'error' ? 'error' : 'schedule'} size={14} />
          {state ? LABEL[state] : 'Checks have not run'}
          {state === 'failed' && failing.length > 0 && (
            <span>: {failing.map((result) => result.name).join(', ')}</span>
          )}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={state === 'running' || rerun.isPending}
          onClick={() => rerun.mutate()}
        >
          Re-run
        </Button>
      </div>
      {state === 'error' && latest?.error && (
        <p className="text-[11px]" style={{ color: 'var(--text-3)' }}>{latest.error}</p>
      )}
      {state === 'failed' && failing.map((result) => (
        <pre
          key={result.name}
          aria-label={`Output of ${result.name}`}
          className="text-[11px] p-2 rounded overflow-x-auto max-h-48"
          style={{ background: 'var(--surface-3)', color: 'var(--text)', whiteSpace: 'pre-wrap' }}
        >
          {result.output_tail.slice(-1500)}
        </pre>
      ))}
      {/* Earlier runs (slice remaining-hidden-data): the route returns up to ten, newest first,
          and only the newest was ever shown. */}
      {data.runs.length > 1 && (
        <>
          <button
            type="button"
            className="aw-link"
            aria-expanded={historyOpen}
            onClick={() => setHistoryOpen((open) => !open)}
            data-testid={`task-checks-history-toggle-${taskId}`}
          >
            <Icon name="chevron_right" size={12} />
            Earlier runs ({data.runs.length - 1})
          </button>
          <Expander open={historyOpen}>
            <ol className="divide-y" style={{ borderColor: 'var(--border)' }}>
              {data.runs.slice(1).map((run) => (
                <EarlierRun key={run.id} run={run} />
              ))}
            </ol>
          </Expander>
        </>
      )}
      {rerun.error && (
        <p role="alert" className="text-[11px]" style={{ color: 'var(--red)' }}>
          {readableApiError(rerun.error, 'The checks could not be started.')}
        </p>
      )}
    </div>
  )
}
