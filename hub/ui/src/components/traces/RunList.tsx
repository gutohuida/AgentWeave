import * as React from 'react'
import { useRunList, type TraceFilters, type TraceSummary } from '@/api/traces'
import { readableApiError } from '@/api/client'
import { Icon } from '@/components/common/Icon'
import { LoadingThread } from '@/components/common/LoadingThread'
import { Button } from '@/components/ui/button'
import { TraceDrawerPanel } from '@/components/traces/TraceDrawer'
import { agentDestination, goTo } from '@/lib/navigation'
import { formatAgo, formatDateTime } from '@/lib/format'
import { RUN_KIND_ICON, RUN_KIND_LABEL, runOutcome, runTaskLabel } from './runListModel'
import { useConfigStore } from '@/store/configStore'
import '@/styles/builds.css'
import '@/styles/runs.css'

/**
 * The runs a profile or a flow started (profiles-threads-and-builds-everywhere FR-6, FR-13): one
 * line each, newest first, with its kind, its profile, its task, when it started and how it ended.
 * Choosing one opens its trace in the drawer the build view uses, with a link to its conversation.
 * The list reads the traces route (D5) and pages on its cursor.
 */

export interface RunListViewProps {
  runs: TraceSummary[]
  status: 'loading' | 'error' | 'ready'
  errorMessage?: string | null
  /** Whether the profile column is shown: a flow's runs are on several profiles, a profile's are not. */
  showProfile?: boolean
  /** Said when there is no run at all. */
  emptyText: string
  hasMore?: boolean
  loadingMore?: boolean
  onMore?: () => void
  onRetry?: () => void
  onOpen: (run: TraceSummary, trigger: HTMLButtonElement) => void
  now: Date
  /** The list's accessible name. */
  label: string
}

/** The list, presentational: rows in, the chosen run out. */
export function RunListView({
  runs,
  status,
  errorMessage,
  showProfile = false,
  emptyText,
  hasMore,
  loadingMore,
  onMore,
  onRetry,
  onOpen,
  now,
  label,
}: RunListViewProps) {
  if (status === 'error' && runs.length === 0) {
    return (
      <div className="aw-run-list-note" role="alert" data-testid="run-list-error">
        <span>The runs could not be read: {errorMessage ?? 'the Hub did not answer.'}</span>
        {onRetry ? (
          <Button variant="outline" size="xs" onClick={onRetry}>
            Try again
          </Button>
        ) : null}
      </div>
    )
  }
  if (status === 'loading' && runs.length === 0) {
    return (
      <div data-testid="run-list-loading">
        <LoadingThread label={`Loading ${label}`} minHeight={102} />
      </div>
    )
  }
  if (runs.length === 0) {
    return (
      <p className="aw-run-list-note" data-testid="run-list-empty">
        {emptyText}
      </p>
    )
  }
  return (
    <div className="aw-run-list-host">
      <ul className="aw-run-list" aria-label={label} data-testid="run-list">
        {runs.map((run) => {
          const kind = run.run_kind ?? 'message'
          const outcome = runOutcome(run)
          const task = runTaskLabel(run)
          const started = formatDateTime(run.start_time, now)
          return (
            <li key={run.trace_id} className="aw-run-row" data-run-id={run.run_id ?? ''} data-kind={kind}>
              <button
                type="button"
                data-slot="run-list-open"
                className="aw-run-open"
                aria-label={`Open the trace of the ${RUN_KIND_LABEL[kind].toLowerCase()} run ${showProfile ? `by ${run.agent ?? 'a profile'} ` : ''}started ${started}`}
                onClick={(event) => onOpen(run, event.currentTarget)}
              >
                <span className="aw-run-kind">
                  <Icon name={RUN_KIND_ICON[kind]} size={13} />
                  {RUN_KIND_LABEL[kind]}
                </span>
                {showProfile ? <span className="aw-run-profile">{run.agent ?? 'Unknown profile'}</span> : null}
                <span className="aw-run-task" title={task ?? undefined}>
                  {task ?? (run.conversation_title || 'No task')}
                </span>
                <span className="aw-run-outcome" style={{ color: outcome.color }}>
                  <Icon name={outcome.icon} size={13} />
                  <span className="aw-run-outcome-word">{outcome.label}</span>
                </span>
                <time className="aw-run-time" dateTime={run.start_time} title={started}>
                  {formatAgo(run.start_time, now)}
                </time>
              </button>
            </li>
          )
        })}
      </ul>
      {status === 'error' ? (
        <p className="aw-run-list-note" role="alert">
          More runs could not be read: {errorMessage ?? 'the Hub did not answer.'}
        </p>
      ) : null}
      {hasMore && onMore ? (
        <Button variant="ghost" size="xs" className="aw-run-more" onClick={onMore} disabled={loadingMore}>
          {loadingMore ? 'Loading…' : 'Show older runs'}
        </Button>
      ) : null}
    </div>
  )
}

/** The run list, wired: the traces route's pages in, the trace drawer and the conversation out. */
export function RunList({
  filters,
  label,
  emptyText,
  showProfile,
}: {
  filters: Pick<TraceFilters, 'profile' | 'loop_id'>
  label: string
  emptyText: string
  showProfile?: boolean
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data, isLoading, isError, error, hasNextPage, fetchNextPage, isFetchingNextPage, refetch } = useRunList(filters)
  const runs = React.useMemo(() => data?.pages.flatMap((page) => page.traces) ?? [], [data])
  const [opened, setOpened] = React.useState<TraceSummary | null>(null)
  const trigger = React.useRef<HTMLButtonElement | null>(null)
  const now = new Date()
  return (
    <>
      <RunListView
        runs={runs}
        status={isError ? 'error' : isLoading ? 'loading' : 'ready'}
        errorMessage={isError ? readableApiError(error, 'the Hub did not answer.') : null}
        showProfile={showProfile}
        emptyText={emptyText}
        hasMore={hasNextPage}
        loadingMore={isFetchingNextPage}
        onMore={() => void fetchNextPage()}
        onRetry={() => void refetch()}
        onOpen={(run, button) => {
          trigger.current = button
          setOpened(run)
        }}
        now={now}
        label={label}
      />
      <TraceDrawerPanel
        open={opened !== null}
        onOpenChange={(open) => {
          if (!open) setOpened(null)
        }}
        runId={opened?.run_id ?? undefined}
        traceId={opened?.run_id ? undefined : opened?.trace_id}
        triggerRef={trigger}
        header={opened ? <RunDrawerHeader run={opened} projectId={projectId} /> : null}
      />
    </>
  )
}

function RunDrawerHeader({ run, projectId }: { run: TraceSummary; projectId: string | null }) {
  const kind = run.run_kind ?? 'message'
  const task = runTaskLabel(run)
  return (
    <div className="aw-bv-drawer-head">
      <span className="aw-bv-drawer-title">
        <Icon name={RUN_KIND_ICON[kind]} size={13} />
        {RUN_KIND_LABEL[kind]}
        <span className="aw-bv-drawer-sub">
          {run.agent ?? 'Unknown profile'}
          {task ? ` · ${task}` : ''}
        </span>
      </span>
      {run.conversation_id && run.agent && projectId ? (
        <button
          type="button"
          data-slot="link-button"
          className="aw-bv-link"
          onClick={() => goTo(agentDestination(projectId, run.agent!, run.conversation_id))}
        >
          Open the conversation
          <Icon name="arrow_forward" size={12} />
        </button>
      ) : (
        <span className="aw-bv-drawer-sub">No conversation recorded</span>
      )}
    </div>
  )
}
