import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { TraceDrawerPanel } from '@/components/traces/TraceDrawer'
import { Button } from '@/components/ui/button'
import { Segmented } from '@/components/ui/segmented'
import { agentColorVars } from '@/lib/agentColors'
import { hubDate } from '@/lib/hubTime'
import {
  formatAgo,
  formatAgoLong,
  formatCost,
  formatCostExact,
  formatDateTime,
  formatDuration,
  formatTokenBreakdown,
  UNPRICED_TITLE,
  type CostCell,
} from '@/lib/format'
import {
  BUILD_STATE,
  buildTotals,
  checkerOf,
  EVIDENCE,
  evidenceSummary,
  filterTasks,
  leftOut,
  leftOutShort,
  NEEDS,
  ROLE,
  stoppedLine,
  taskFigures,
  taskKey,
  taskName,
  taskOfRun,
  taskStateOf,
  timelineOf,
  totalCell,
  type BuildAddress,
  type BuildRead,
  type BuildRunRead,
  type BuildTaskRead,
  type CostTotal,
  type TaskFilter,
  type TimelineGroup,
  type TimelineItem,
  type TimelineRun,
  type TimelineSendBack,
} from './buildViewModel'
import '@/styles/builds.css'

export interface BuildViewProps {
  /** The build's read; null until the first answer. */
  read: BuildRead | null
  /** `loading` before the first answer, `error` when the first read failed. */
  status: 'loading' | 'error' | 'ready'
  errorMessage?: string | null
  /** A later refresh failed: what is on screen is as of `read.as_of`, and says so. */
  refreshError?: string | null
  now: Date
  /** The task expanded, the run whose trace is open and the filter, all from the view's address. */
  address: BuildAddress
  onAddressChange: (address: BuildAddress) => void
  onRetry: () => void
  onOpenDocument: () => void
  /** The trace's link to the conversation the run happened in. */
  onOpenConversation: (run: BuildRunRead) => void
  colorIndexOf?: (agent: string) => number | null | undefined
}

/** One build: its tasks in their document's order, each opening one timeline of the runs that
 *  worked it and the send-backs between them; a run opens its trace (spec
 *  `a-build-view-showing-every-task-and-run-of-a-build`). */
export function BuildView(props: BuildViewProps) {
  const { read, status } = props
  if (!read) {
    return (
      <div className="aw-bv" data-testid="build-view">
        {status === 'error' ? (
          <div className="aw-bv-failed" role="alert">
            <Icon name="error_outline" size={18} />
            <p>{props.errorMessage || 'This build could not be read.'}</p>
            <Button size="xs" variant="outline" onClick={props.onRetry}>
              Try again
            </Button>
          </div>
        ) : (
          <BuildSkeleton />
        )}
      </div>
    )
  }
  return <BuildViewLoaded {...props} read={read} />
}

/** Shaped like the view, shown only after a short delay (`.aw-delayed`), announced once: the
 *  header's lines, the five figures, and task rows on the table's own grid, so nothing moves when
 *  the build arrives (P19). */
function BuildSkeleton() {
  // Widths of each cell's bar, per column of `.aw-bv-row` (chevron, task, status, people,
  // evidence, runs, sent back, cost, changed).
  const cells = ['12px', '78%', '70%', '80%', '70%', '18px', '18px', '48px', '26px']
  return (
    <div className="aw-bv-placeholder aw-delayed" role="status" aria-busy="true" aria-label="Loading the build">
      <div className="aw-bv-header" aria-hidden="true">
        <div className="aw-bv-skel-line" style={{ width: 44, height: 12 }} />
        <div className="aw-bv-skel-line" style={{ width: '36%', height: 22 }} />
        <div className="aw-bv-skel-line" style={{ width: '28%', height: 14 }} />
        <div className="aw-bv-figures">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="aw-bv-figure">
              <div className="aw-bv-skel-line" style={{ width: '40%', height: 11 }} />
              <div className="aw-bv-skel-line" style={{ width: '55%', height: 18 }} />
            </div>
          ))}
        </div>
      </div>
      <div className="aw-bv-table" aria-hidden="true">
        {[0, 1, 2, 3, 4].map((row) => (
          <div key={row} className="aw-bv-row aw-bv-skel-row">
            {cells.map((width, i) => (
              <div key={i} className="aw-bv-skel-line" style={{ width, height: 12, justifySelf: i >= 5 ? 'end' : undefined }} />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

function BuildViewLoaded({ read, now, address, onAddressChange, refreshError, onRetry, onOpenDocument, onOpenConversation, colorIndexOf }: BuildViewProps & { read: BuildRead }) {
  const totals = buildTotals(read, now)
  const addressedTask = address.task ? read.tasks.find((t) => taskKey(t) === address.task || t.id === address.task) : address.run ? taskOfRun(read, address.run) : null
  const [expanded, setExpanded] = React.useState<Set<string>>(() => new Set(addressedTask ? [addressedTask.id] : []))
  const runButtons = React.useRef(new Map<string, HTMLButtonElement>())
  const drawerTrigger = React.useRef<HTMLButtonElement | null>(null)

  // An address that names a task (a copied link, a summary's task) opens it and brings it into view.
  React.useEffect(() => {
    if (!addressedTask) return
    setExpanded((current) => (current.has(addressedTask.id) ? current : new Set(current).add(addressedTask.id)))
    // Scrolled to only when it is out of view, so a link to the second task keeps the header in sight.
    const row = document.getElementById(rowId(addressedTask.id))
    const top = row?.getBoundingClientRect().top ?? 0
    if (row && (top < 0 || top > window.innerHeight * 0.6)) row.scrollIntoView({ block: 'start' })
    // Only when the address changes, never on a live refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addressedTask?.id])

  const toggle = (task: BuildTaskRead) => {
    const open = !expanded.has(task.id)
    setExpanded((current) => {
      const next = new Set(current)
      if (open) next.add(task.id)
      else next.delete(task.id)
      return next
    })
    const key = taskKey(task)
    if (open) onAddressChange({ ...address, task: key })
    else if (address.task === key) onAddressChange({ ...address, task: null, run: task.runs.some((r) => r.id === address.run) ? null : address.run })
  }

  const openRun = (task: BuildTaskRead | null, run: BuildRunRead) => {
    drawerTrigger.current = runButtons.current.get(run.id) ?? null
    onAddressChange({ ...address, task: task ? taskKey(task) : address.task, run: run.id })
  }

  const openedRun = address.run ? [...read.tasks.flatMap((t) => t.runs), ...read.build_runs].find((r) => r.id === address.run) ?? null : null
  if (openedRun && !drawerTrigger.current) drawerTrigger.current = runButtons.current.get(openedRun.id) ?? null
  const openedLabel = openedRun ? runLabelOf(read, openedRun, now) : ''

  const shown = filterTasks(read.tasks, address.filter)
  const setFilter = (filter: TaskFilter) => onAddressChange({ ...address, filter })

  return (
    <div className="aw-bv" data-testid="build-view" data-build-id={read.build.id}>
      <BuildHeader read={read} now={now} totals={totals} refreshError={refreshError ?? null} onRetry={onRetry} onOpenDocument={onOpenDocument} onShowNeeds={() => setFilter('needs-you')} />

      <section className="aw-bv-tasks" aria-label="Tasks">
        <div className="aw-bv-toolbar">
          <h2 className="aw-bv-h2">
            Tasks <span className="aw-bv-count">{read.tasks.length}</span>
          </h2>
          <span className="aw-bv-order">In the order the document declares them{read.tasks.some((t) => !t.declared) ? ', then those added later' : ''}</span>
          <Segmented<TaskFilter>
            label="Filter tasks"
            size="xs"
            value={address.filter}
            onChange={setFilter}
            options={[
              { value: 'all', label: 'All', count: read.tasks.length },
              { value: 'needs-you', label: 'Needs you', count: totals.needsOperator },
            ]}
          />
        </div>

        {read.tasks.length === 0 ? (
          <div className="aw-bv-empty">
            <Icon name="circle_dashed" size={18} />
            <p>This build has no tasks yet.</p>
            <p className="aw-bv-empty-hint">A build files its tasks from the approved document when it starts.</p>
          </div>
        ) : shown.length === 0 ? (
          <div className="aw-bv-empty">
            <Icon name="check_circle" size={18} />
            <p>Nothing in this build needs you.</p>
            <Button size="xs" variant="outline" onClick={() => setFilter('all')}>
              Show all tasks
            </Button>
          </div>
        ) : (
          <div className="aw-bv-table">
            <div className="aw-bv-row aw-bv-head-row" aria-hidden="true">
              <span />
              <span>Task</span>
              <span>Status</span>
              <span>Builder · checker</span>
              <span>Evidence</span>
              <span className="aw-bv-num">Runs</span>
              <span className="aw-bv-num">Sent back</span>
              <span className="aw-bv-num">Cost</span>
              <span className="aw-bv-num">Changed</span>
            </div>
            <ul className="aw-bv-list">
              {shown.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  now={now}
                  open={expanded.has(task.id)}
                  openedRunId={address.run}
                  onToggle={() => toggle(task)}
                  onOpenRun={(run) => openRun(task, run)}
                  runButtons={runButtons.current}
                  colorIndexOf={colorIndexOf}
                />
              ))}
            </ul>
          </div>
        )}
      </section>

      {read.build_runs.length ? (
        <section className="aw-bv-buildwide" aria-label="Runs of the build itself">
          <h2 className="aw-bv-h2">
            Runs of the build itself <span className="aw-bv-count">{read.build_runs.length}</span>
          </h2>
          <p className="aw-bv-order">Counted in the build’s totals; they worked the build’s flow, not one task.</p>
          <Timeline
            items={timelineOf(read.build_runs, [], now)}
            regionLabel="Runs of the build itself"
            now={now}
            openedRunId={address.run}
            onOpenRun={(run) => openRun(null, run)}
            runButtons={runButtons.current}
            colorIndexOf={colorIndexOf}
          />
        </section>
      ) : null}

      <TraceDrawerPanel
        open={openedRun !== null}
        onOpenChange={(open) => {
          if (!open) onAddressChange({ ...address, run: null })
        }}
        runId={openedRun?.id}
        triggerRef={drawerTrigger}
        header={
          openedRun ? (
            <div className="aw-bv-drawer-head">
              <span className="aw-bv-drawer-title">
                <Icon name={ROLE[openedRun.role].icon} size={13} />
                {openedLabel}
                <span className="aw-bv-drawer-sub">
                  {openedRun.agent}
                  {openedRun.model ? ` · ${openedRun.model}` : ''}
                </span>
              </span>
              {openedRun.conversation_id ? (
                <button type="button" data-slot="link-button" className="aw-bv-link" onClick={() => onOpenConversation(openedRun)}>
                  Open the thread
                  <Icon name="arrow_forward" size={12} />
                </button>
              ) : (
                <span className="aw-bv-drawer-sub">No thread recorded</span>
              )}
            </div>
          ) : null
        }
      />
    </div>
  )
}

function rowId(taskId: string): string {
  return `build-task-${taskId}`
}

/** A run's label as its timeline shows it ("Build 2"), for the drawer's head. */
function runLabelOf(read: BuildRead, run: BuildRunRead, now: Date): string {
  const task = taskOfRun(read, run.id)
  const items = task ? timelineOf(task.runs, task.send_backs, now) : timelineOf(read.build_runs, [], now)
  const flat = items.flatMap((i) => (i.kind === 'group' ? i.runs : [i]))
  const found = flat.find((i): i is TimelineRun => i.kind === 'run' && i.run.id === run.id)
  return `${found?.label ?? ROLE[run.role].label}${task ? ` of ${taskName(task)}` : ''}`
}

// ── Header ──────────────────────────────────────────────────────────────

function BuildHeader({
  read,
  now,
  totals,
  refreshError,
  onRetry,
  onOpenDocument,
  onShowNeeds,
}: {
  read: BuildRead
  now: Date
  totals: ReturnType<typeof buildTotals>
  refreshError: string | null
  onRetry: () => void
  onOpenDocument: () => void
  onShowNeeds: () => void
}) {
  const b = read.build
  const state = BUILD_STATE[b.state]
  const elapsed = Math.max(0, ((b.stopped_at ? hubDate(b.stopped_at) : now).getTime() - hubDate(b.created_at).getTime()) / 1000)
  const pct = totals.tasks ? (totals.approved / totals.tasks) * 100 : 0
  const cost = totalCell(totals.cost)
  const note = leftOut(totals.cost)
  const stopped = b.needs_operator?.kind === 'stopped'
  return (
    <header className="aw-bv-header">
      <div className="aw-bv-titleline">
        <div className="aw-bv-titles">
          <span className="aw-bv-kicker">
            <Icon name="hammer" size={12} />
            Build
          </span>
          <h1 className="aw-bv-title" title={b.document_title}>
            {b.document_title}
          </h1>
        </div>
        <Button variant="outline" size="xs" onClick={onOpenDocument}>
          <Icon name="description" size={13} />
          Open the spec
        </Button>
      </div>

      <div className="aw-bv-meta">
        <span className="aw-bv-state" data-state={b.state}>
          {b.state === 'running' ? <span className="aw-bv-live" aria-hidden="true" /> : <Icon name={state.icon} size={13} />}
          {state.label}
        </span>
        <span>
          started{' '}
          <time dateTime={b.created_at} title={formatDateTime(b.created_at, now)}>
            {formatAgoLong(b.created_at, now)}
          </time>
        </span>
        {b.stopped_at ? (
          <span>
            {b.state === 'stopped' ? 'stopped' : 'finished'}{' '}
            <time dateTime={b.stopped_at} title={formatDateTime(b.stopped_at, now)}>
              {formatAgoLong(b.stopped_at, now)}
            </time>
          </span>
        ) : null}
        <span className="tabular">{formatDuration(elapsed)} from start{b.stopped_at ? ' to end' : ''}</span>
        {b.stop_reason && b.state === 'stopped' ? <span>{b.stop_reason}</span> : null}
        {b.state === 'running' && !refreshError ? (
          <span className="aw-bv-fresh" role="status">
            updated <time dateTime={read.as_of} title={formatDateTime(read.as_of, now)}>{formatAgoLong(read.as_of, now)}</time>
          </span>
        ) : null}
      </div>

      {refreshError ? (
        <div className="aw-bv-stale" role="alert">
          <Icon name="alert_triangle" size={14} />
          <span>
            Not up to date: {refreshError} Showing the build as of{' '}
            <time dateTime={read.as_of}>{formatDateTime(read.as_of, now)}</time>.
          </span>
          <Button size="xs" variant="outline" onClick={onRetry}>
            Try again
          </Button>
        </div>
      ) : null}

      <dl className="aw-bv-figures" aria-label="Totals">
        <div className="aw-bv-figure">
          <dt>Tasks</dt>
          <dd>
            <strong className="tabular" data-testid="build-approved">
              {totals.approved} of {totals.tasks}
            </strong>{' '}
            approved
            <span className="aw-bv-bar" aria-hidden="true">
              <span style={{ width: `${pct}%` }} />
            </span>
          </dd>
        </div>
        <div className="aw-bv-figure">
          <dt>Cost</dt>
          <dd>
            <strong data-testid="build-cost">
              <CostText cell={cost} />
            </strong>
            <small data-testid="build-cost-note">{note ?? (totals.cost.priced ? 'Every finished run priced' : totals.cost.unpriced ? 'No run of it was priced' : 'Nothing has finished')}</small>
          </dd>
        </div>
        <div className="aw-bv-figure">
          <dt>Runs</dt>
          <dd>
            <strong className="tabular" data-testid="build-runs">
              {totals.runs}
            </strong>
            <small className="tabular">
              {formatDuration(totals.seconds)} of profile work{totals.live ? ` · ${totals.live} running now` : ''}
            </small>
          </dd>
        </div>
        <div className="aw-bv-figure">
          <dt>Send-backs</dt>
          <dd>
            <strong className="tabular" data-testid="build-send-backs">
              {totals.sendBacks}
            </strong>
            <small>{totals.sendBacks ? `across ${read.tasks.filter((t) => t.send_backs.length).length} of ${totals.tasks} tasks` : totals.tasks ? 'No task was sent back' : 'No task yet'}</small>
          </dd>
        </div>
        <div className="aw-bv-figure" data-attention={totals.needsOperator || stopped ? 'true' : undefined}>
          <dt>Needs you</dt>
          <dd>
            {totals.needsOperator ? (
              <>
                <strong className="aw-bv-needs-figure tabular" data-testid="build-needs">
                  <Icon name="alert_triangle" size={15} />
                  {totals.needsOperator} {totals.needsOperator === 1 ? 'task' : 'tasks'}
                </strong>
                <button type="button" data-slot="link-button" className="aw-bv-link" onClick={onShowNeeds}>
                  Show {totals.needsOperator === 1 ? 'it' : 'them'}
                </button>
                {stopped ? <small data-testid="build-needs-stopped">{stoppedLine(read)}</small> : null}
              </>
            ) : stopped ? (
              <>
                <strong className="aw-bv-needs-figure" data-testid="build-needs">
                  <Icon name="alert_triangle" size={15} />
                  Stopped
                </strong>
                <small data-testid="build-needs-stopped" title={read.build.needs_operator?.text}>
                  {stoppedLine(read)}
                </small>
              </>
            ) : (
              <>
                <strong className="aw-bv-quiet-figure" data-testid="build-needs">
                  Nothing
                </strong>
                <small>No task waits on you</small>
              </>
            )}
          </dd>
        </div>
      </dl>
    </header>
  )
}

/** A total's figure: the priced sum with its "+N unpriced" beside it, or the word. */
function CostFigure({ cell, total }: { cell: CostCell; total: CostTotal }) {
  const short = leftOutShort(total)
  return (
    <>
      <CostText cell={cell} />
      {short ? <span className="aw-bv-cost-more">{short}</span> : null}
    </>
  )
}

/** The cost cell (`lib/format`'s one rule, shared with Traces): a figure with its exact value in
 *  the title, the word "unpriced", or a dash with a reason. */
export function CostText({ cell, noneTitle = 'No cost yet: still running, or no usage was reported' }: { cell: CostCell; noneTitle?: string }) {
  if (cell.kind === 'cost') {
    return (
      <span className="aw-bv-cost tabular" data-value={cell.usd} title={formatCostExact(cell.usd)}>
        {formatCost(cell.usd)}
      </span>
    )
  }
  if (cell.kind === 'unpriced') {
    return (
      <span className="aw-bv-unpriced" title={UNPRICED_TITLE}>
        unpriced
      </span>
    )
  }
  return (
    <span className="aw-bv-none" title={noneTitle}>
      —
    </span>
  )
}

// ── Task rows ───────────────────────────────────────────────────────────

function AgentName({ name, colorIndexOf, role }: { name: string | null; colorIndexOf?: BuildViewProps['colorIndexOf']; role: string }) {
  if (!name) return <span className="aw-bv-agent aw-bv-agent-none">{role === 'checker' ? 'no checker' : 'unassigned'}</span>
  return (
    <span className="aw-bv-agent" style={{ '--agent-accent': agentColorVars(colorIndexOf?.(name)).accent } as React.CSSProperties}>
      <span className="aw-agent-dot" aria-hidden="true" />
      {name}
    </span>
  )
}

function TaskRow({
  task,
  now,
  open,
  openedRunId,
  onToggle,
  onOpenRun,
  runButtons,
  colorIndexOf,
}: {
  task: BuildTaskRead
  now: Date
  open: boolean
  openedRunId: string | null
  onToggle: () => void
  onOpenRun: (run: BuildRunRead) => void
  runButtons: Map<string, HTMLButtonElement>
  colorIndexOf?: BuildViewProps['colorIndexOf']
}) {
  const state = taskStateOf(task.status)
  const figures = taskFigures(task, now)
  const cost = totalCell(figures.cost)
  const panelId = `build-task-runs-${task.id}`
  const name = taskName(task)
  const title = task.title ?? 'A task with no title'
  const worstEvidence = figures.evidence[0]?.state ?? null
  const checker = checkerOf(task)
  return (
    <li className="aw-bv-item" id={rowId(task.id)} data-open={open ? 'true' : 'false'} data-needs={task.needs_operator ? 'true' : undefined} data-status={task.status}>
      {/* The row's cells are read as one line; the button is the disclosure, and a click anywhere on
          the row is the same as pressing it. */}
      <div className="aw-bv-row" onClick={(e) => (e.target as HTMLElement).closest('button') === null && onToggle()}>
        <span className="aw-bv-chevron" aria-hidden="true">
          <Icon name={open ? 'expand_more' : 'chevron_right'} size={14} />
        </span>
        <span className="aw-bv-task">
          <button
            type="button"
            data-slot="build-task-row"
            className="aw-bv-task-button"
            aria-label={`Open runs of ${name}`}
            aria-expanded={open}
            aria-controls={panelId}
            onClick={onToggle}
            title={task.ref ? `${task.ref}: ${title}` : title}
          >
            {task.ref ? <span className="aw-bv-ref">{task.ref}</span> : null}
            <span className="aw-bv-task-title">{title}</span>
          </button>
          {!task.declared ? (
            <span className="aw-bv-tag" title="Added to the build after it started: a Hub-filed fix or an amendment">
              added later
            </span>
          ) : null}
        </span>
        <span className="aw-bv-status" data-status={task.status}>
          <Icon name={state.icon} size={13} />
          {state.label}
        </span>
        <span className="aw-bv-people">
          <AgentName name={task.builder} role="builder" colorIndexOf={colorIndexOf} />
          <span className="aw-bv-sep" aria-hidden="true">·</span>
          <span className="aw-bv-checker" title={checker.named ? `${checker.name} checks it` : checker.name ? `No checker was named; ${checker.name} reviewed it` : 'No checker was named and nobody has reviewed it'}>
            <AgentName name={checker.name} role="checker" colorIndexOf={colorIndexOf} />
            {checker.name && !checker.named ? <span className="aw-bv-reviewed">reviewed</span> : null}
          </span>
        </span>
        <span className="aw-bv-evidence" data-worst={worstEvidence ?? undefined} title={task.requirements.map((r) => `${r.identifier}: ${EVIDENCE[r.evidence].label}`).join('\n') || 'Serves no named requirement'}>
          {worstEvidence ? <Icon name={EVIDENCE[worstEvidence].icon} size={13} /> : null}
          {evidenceSummary(task.requirements)}
        </span>
        <span className="aw-bv-num tabular">{figures.runs}</span>
        <span className="aw-bv-num tabular" data-some={figures.sendBacks ? 'true' : undefined}>
          {figures.sendBacks ? (
            <>
              <Icon name="undo" size={12} />
              {figures.sendBacks}
            </>
          ) : (
            '0'
          )}
        </span>
        <span className="aw-bv-num" aria-label={`Cost ${cost.kind === 'cost' ? formatCost(cost.usd) : cost.kind === 'unpriced' ? 'unpriced' : 'none'}`}>
          <CostFigure cell={cost} total={figures.cost} />
        </span>
        <span className="aw-bv-num">
          {task.last_change_at ? (
            <time dateTime={task.last_change_at} title={formatDateTime(task.last_change_at, now)} className="tabular">
              {formatAgo(task.last_change_at, now)}
            </time>
          ) : (
            '—'
          )}
        </span>
      </div>

      {task.needs_operator ? (
        <div className="aw-bv-needs">
          <Icon name={task.needs_operator.kind === 'question' ? 'help_circle' : 'alert_triangle'} size={13} />
          <b>{NEEDS[task.needs_operator.kind]}:</b>
          <span className="aw-bv-needs-text" title={task.needs_operator.text}>
            {task.needs_operator.text}
          </span>
        </div>
      ) : null}

      {open ? (
        <div className="aw-bv-panel" id={panelId}>
          {task.requirements.length ? (
            <ul className="aw-bv-reqs" aria-label={`Evidence of ${name}`}>
              {task.requirements.map((r) => (
                <li key={r.identifier} className="aw-bv-req" data-evidence={r.evidence} title={EVIDENCE[r.evidence].meaning}>
                  <Icon name={EVIDENCE[r.evidence].icon} size={12} />
                  <b>{r.identifier}</b> {EVIDENCE[r.evidence].label}
                </li>
              ))}
            </ul>
          ) : (
            <p className="aw-bv-reqs-none">Serves no named requirement.</p>
          )}
          <Timeline
            items={timelineOf(task.runs, task.send_backs, now)}
            regionLabel={`Runs of ${name}`}
            now={now}
            openedRunId={openedRunId}
            onOpenRun={onOpenRun}
            runButtons={runButtons}
            colorIndexOf={colorIndexOf}
          />
          <p className="aw-bv-panel-total tabular">
            {figures.runs} {figures.runs === 1 ? 'run' : 'runs'} · {formatDuration(figures.seconds)} of work · <CostText cell={cost} />
            {leftOut(figures.cost) ? <span className="aw-bv-left-out"> ({leftOut(figures.cost)})</span> : null}
          </p>
        </div>
      ) : null}
    </li>
  )
}

// ── Timeline ────────────────────────────────────────────────────────────

function Timeline({
  items,
  regionLabel,
  now,
  openedRunId,
  onOpenRun,
  runButtons,
  colorIndexOf,
}: {
  items: TimelineItem[]
  regionLabel: string
  now: Date
  openedRunId: string | null
  onOpenRun: (run: BuildRunRead) => void
  runButtons: Map<string, HTMLButtonElement>
  colorIndexOf?: BuildViewProps['colorIndexOf']
}) {
  if (!items.length) {
    return <p className="aw-bv-timeline-empty">No run has worked it yet.</p>
  }
  return (
    <ol className="aw-bv-timeline" aria-label={regionLabel}>
      {items.map((item) =>
        item.kind === 'run' ? (
          <RunLine key={item.key} item={item} now={now} opened={openedRunId === item.run.id} onOpen={() => onOpenRun(item.run)} runButtons={runButtons} colorIndexOf={colorIndexOf} />
        ) : item.kind === 'send-back' ? (
          <SendBackLine key={item.key} item={item} now={now} />
        ) : (
          <GroupLine key={item.key} item={item} now={now} openedRunId={openedRunId} onOpenRun={onOpenRun} runButtons={runButtons} colorIndexOf={colorIndexOf} />
        ),
      )}
    </ol>
  )
}

function RunLine({
  item,
  now,
  opened,
  onOpen,
  runButtons,
  colorIndexOf,
}: {
  item: TimelineRun
  now: Date
  opened: boolean
  onOpen: () => void
  runButtons: Map<string, HTMLButtonElement>
  colorIndexOf?: BuildViewProps['colorIndexOf']
}) {
  const { run } = item
  const tokens = run.tokens
    ? formatTokenBreakdown({ input_tokens: run.tokens.input ?? undefined, output_tokens: run.tokens.output ?? undefined, cache_read_tokens: run.tokens.cache_read ?? undefined, cache_write_tokens: run.tokens.cache_write ?? undefined })
    : undefined
  return (
    <li className="aw-bv-event" data-kind="run" data-role={run.role} data-latest={item.latest ? 'true' : undefined} data-tone={item.move.tone}>
      <span className="aw-bv-rail" aria-hidden="true">
        <Icon name={ROLE[run.role].icon} size={12} />
      </span>
      <button
        type="button"
        data-slot="build-run"
        className="aw-bv-run"
        data-run-id={run.id}
        aria-label={`Open trace: ${item.label}`}
        aria-current={opened ? 'true' : undefined}
        ref={(el) => {
          if (el) runButtons.set(run.id, el)
          else runButtons.delete(run.id)
        }}
        onClick={onOpen}
      >
        <span className="aw-bv-run-label">{item.label}</span>
        <span className="aw-bv-run-who">
          <AgentName name={run.agent} role="builder" colorIndexOf={colorIndexOf} />
          <span className="aw-bv-model">{run.model ?? 'model not reported'}</span>
        </span>
        <time className="aw-bv-run-when tabular" dateTime={run.started_at} title={`Started ${formatDateTime(run.started_at, now)} (${formatAgoLong(run.started_at, now)})`}>
          {formatDateTime(run.started_at, now)}
        </time>
        <span className="aw-bv-run-took tabular">
          {run.status === 'running' ? <span className="aw-bv-live" aria-hidden="true" /> : null}
          {formatDuration(item.seconds)}
        </span>
        <span className="aw-bv-move" data-tone={item.move.tone} title={run.mend?.detail ?? undefined}>
          <Icon name={item.move.tone === 'bad' ? 'alert_triangle' : item.move.tone === 'good' ? 'check' : item.move.tone === 'live' ? 'play_arrow' : 'remove_circle'} size={12} />
          {item.move.text}
        </span>
        <span className="aw-bv-num" title={tokens}>
          {run.status === 'running' ? <span className="aw-bv-none">running</span> : <CostText cell={item.cost} noneTitle="This run reported no usage" />}
        </span>
      </button>
    </li>
  )
}

const LONG_REASON = 220

function SendBackLine({ item, now }: { item: TimelineSendBack; now: Date }) {
  const [full, setFull] = React.useState(false)
  const long = item.text.length > LONG_REASON
  return (
    <li className="aw-bv-event aw-bv-sendback" data-kind="send-back">
      <span className="aw-bv-rail" aria-hidden="true">
        <Icon name="undo" size={12} />
      </span>
      <div className="aw-bv-sendback-body">
        <div className="aw-bv-sendback-head">
          <b>{item.sendBack.to === 'rejected' ? 'Rejected' : 'Sent back'}</b>
          <span>by {item.by}</span>
          {item.reasonClass ? <span className="aw-bv-class">{item.reasonClass}</span> : null}
          <time className="aw-bv-sendback-when tabular" dateTime={item.sendBack.at} title={formatAgoLong(item.sendBack.at, now)}>
            {formatDateTime(item.sendBack.at, now)}
          </time>
        </div>
        {item.text ? (
          <p className="aw-bv-sendback-text" data-full={full || !long ? 'true' : 'false'}>
            {item.text}
          </p>
        ) : (
          <p className="aw-bv-sendback-text aw-bv-none">No reason was given.</p>
        )}
        {long ? (
          <button type="button" data-slot="link-button" className="aw-bv-link" aria-expanded={full} aria-label={full ? `Show less of ${item.label}` : `Show the whole reason of ${item.label}`} onClick={() => setFull((f) => !f)}>
            {full ? 'Show less' : 'Show the whole reason'}
          </button>
        ) : null}
      </div>
    </li>
  )
}

function GroupLine({
  item,
  now,
  openedRunId,
  onOpenRun,
  runButtons,
  colorIndexOf,
}: {
  item: TimelineGroup
  now: Date
  openedRunId: string | null
  onOpenRun: (run: BuildRunRead) => void
  runButtons: Map<string, HTMLButtonElement>
  colorIndexOf?: BuildViewProps['colorIndexOf']
}) {
  const [open, setOpen] = React.useState(item.runs.some((r) => r.run.id === openedRunId))
  return (
    <li className="aw-bv-event aw-bv-group" data-kind="group" data-tone={item.move.tone}>
      <span className="aw-bv-rail" aria-hidden="true">
        <Icon name={ROLE[item.runs[0]!.run.role].icon} size={12} />
      </span>
      <div className="aw-bv-group-body">
        <button
          type="button"
          data-slot="build-run-group"
          className="aw-bv-run"
          aria-expanded={open}
          aria-label={`${open ? 'Hide' : 'Show'} ${item.label}: ${item.detail}`}
          onClick={() => setOpen((o) => !o)}
        >
          <span className="aw-bv-run-label">
            <Icon name={open ? 'expand_more' : 'chevron_right'} size={12} />
            {item.label}
          </span>
          <span className="aw-bv-run-who">
            <span className="aw-bv-model" title={item.detail}>
              {item.detail}
            </span>
          </span>
          <span className="aw-bv-run-when" />
          <span className="aw-bv-run-took tabular">{formatDuration(item.seconds)}</span>
          <span className="aw-bv-move" data-tone={item.move.tone}>
            <Icon name={item.move.tone === 'bad' ? 'alert_triangle' : 'check'} size={12} />
            {item.move.text}
          </span>
          <span className="aw-bv-num">
            <CostFigure cell={totalCell(item.cost)} total={item.cost} />
          </span>
        </button>
        {item.reason && !open ? (
          <p className="aw-bv-group-reason" title={item.reason}>
            {item.reason}
          </p>
        ) : null}
        {open ? (
          <ol className="aw-bv-timeline aw-bv-group-runs">
            {item.items.map((r) =>
              r.kind === 'run' ? (
                <RunLine key={r.key} item={r} now={now} opened={openedRunId === r.run.id} onOpen={() => onOpenRun(r.run)} runButtons={runButtons} colorIndexOf={colorIndexOf} />
              ) : (
                <SendBackLine key={r.key} item={r} now={now} />
              ),
            )}
          </ol>
        ) : null}
      </div>
    </li>
  )
}
