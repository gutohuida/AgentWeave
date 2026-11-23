import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { MenuSelect } from '@/components/ui/menu'
import { SettingsGroup, SettingsPage, SettingsRow } from '@/components/ui/settings'
import { Switch } from '@/components/ui/switch'
import { MarkdownMessage } from '@/components/agents/MarkdownMessage'
import type { ManagerFiring, ManagerJob, ManagerJobInput, ManagerJobRunTotals, ManagerLoggedRun, ManagerRunDetail } from '@/api/manager'
import type { Runner } from '@/api/runners'
import type { ModelDescriptor } from '@/api/modelCatalog'
import { formatDateTime, formatDuration, formatTokenBreakdown, formatUsage } from '@/lib/format'
import { catalogModelOptions, runnerChoiceOptions } from './settingsOptions'
import { LoadingThread } from '@/components/common/LoadingThread'

/** Project settings → Manager: the work the Hub does in the background with a model.
 *
 *  Before, four jobs were laid out as twelve rows at one level (a checkbox, then Runner, then
 *  Model, four times), so nothing showed where one job ended. Each job is now its own group: the
 *  switch is in the group's heading, and its runner and model sit beneath it, greyed while the job
 *  is off. The history is a table with one date style and a disclosure for the model's answer. */

const OUTCOME: Record<ManagerFiring['outcome'], { label: string; tone: string }> = {
  written: { label: 'Written', tone: 'good' },
  answered: { label: 'Answered', tone: 'good' },
  empty: { label: 'Nothing to do', tone: 'neutral' },
  failed: { label: 'Failed', tone: 'bad' },
}

/** What a run was about, in words: "Conversation conv-…" becomes the conversation's title when
 *  the container knows it. */
export type SubjectLabel = (run: { subject?: Record<string, unknown> | null }) => string | null

/** What the log shows of the runs, and how it is narrowed and continued. */
export interface RunLogView {
  runs: ManagerLoggedRun[]
  totals: Record<string, ManagerJobRunTotals>
  hasMore: boolean
  /** The job the log is narrowed to; null for every job. */
  job: string | null
  onJob: (job: string | null) => void
  onShowOlder: () => void
  loadingOlder?: boolean
}

/** The run a `run=<run_id>` link opened: the run once read, and why it could not be. */
export interface RunDetailView {
  runId: string
  run: ManagerRunDetail | undefined
  error?: string | null
  onClose: () => void
}

export function ManagerSettings({
  jobs,
  log,
  logError,
  detail,
  onOpenRun,
  onOpenConversation,
  runners,
  modelsFor,
  modelPart,
  subjectLabel,
  controlsUnavailable,
  notices,
  now,
  onChange,
}: {
  jobs: ManagerJob[]
  /** Undefined while the run log is on its way. */
  log: RunLogView | undefined
  /** Why the log could not be read; it is never shown as empty when it was not read. */
  logError?: string | null
  /** The run the location names, when it names one. */
  detail?: RunDetailView | null
  /** A row's link: open that run's detail (its address carries `run=<run_id>`). */
  onOpenRun: (runId: string) => void
  /** A mender row's link to the thread it ran in. */
  onOpenConversation?: (conversationId: string) => void
  runners: Runner[]
  /** The models a runner's provider offers. */
  modelsFor: (runner: Runner | undefined) => ModelDescriptor[]
  /** A runner's model in words (F268), for the runner menu's second line. */
  modelPart?: (runner: Runner) => string
  subjectLabel?: SubjectLabel
  /** Why the jobs' runner and model cannot be shown truthfully (the runners or the catalog could
   *  not be read): those controls are withheld rather than shown wrong. */
  controlsUnavailable?: string | null
  /** A refused save, under the page heading. */
  notices?: React.ReactNode
  now: Date
  onChange: (key: string, input: ManagerJobInput, said: string) => void
}) {
  return (
    <SettingsPage icon="memory" title="Manager" description="Work the Hub does in the background with a model. Each job runs only while it is on, on the runner and model you choose for it.">
      {notices}
      {controlsUnavailable ? (
        <p className="aw-inline-warning" role="alert">
          <Icon name="warning" size={13} /> {controlsUnavailable}
        </p>
      ) : null}
      {jobs.map((job) => {
        const runner = runners.find((r) => r.id === job.runner_id)
        const blocked = job.enabled && job.needs_runner && !job.runner_id
        const chooseRunner = (runnerId: string | null) => {
          const next = runners.find((r) => r.id === runnerId)
          // A model belongs to a CLI: one chosen for another CLI's runner is cleared, not carried over.
          const keepsModel = !job.model || (next && runner && next.cli === runner.cli)
          onChange(
            job.key,
            keepsModel ? { runner_id: runnerId } : { runner_id: runnerId, model: null },
            `${job.title} runs on ${next?.name ?? (job.needs_runner ? 'no runner' : 'each profile’s own runner')}`,
          )
        }
        return (
          <SettingsGroup
            key={job.key}
            title={job.title}
            description={job.description.replace(/ Needs a runner\./, '').replace(/ Off: .*$/, '')}
            aside={
              <Switch
                aria-label={`${job.title} enabled`}
                data-testid={`manager-job-${job.key}-enabled`}
                checked={job.enabled}
                onCheckedChange={(v) => onChange(job.key, { enabled: v }, `${job.title} ${v ? 'on' : 'off'}`)}
              />
            }
          >
            <div className="aw-manager-job" data-on={job.enabled ? 'true' : 'false'} data-testid={`manager-job-${job.key}`}>
              {controlsUnavailable ? null : (
              <>
              <SettingsRow
                label="Runner"
                inactive={!job.enabled}
                description={job.needs_runner ? 'This job does nothing until a runner is chosen.' : 'None: each thread’s own profile runner.'}
                control={
                  <MenuSelect
                    label={`${job.title} runner`}
                    value={job.runner_id ?? ''}
                    onChange={(v) => chooseRunner(v || null)}
                    options={runnerChoiceOptions(
                      runners,
                      job.needs_runner
                        ? { label: 'No runner', detail: 'The job does nothing until one is chosen' }
                        : { label: 'The profile’s own runner', detail: 'Each thread’s own profile runner' },
                      modelPart ?? ((r) => r.model ?? 'Provider default'),
                    )}
                  />
                }
              />
              <SettingsRow
                label="Model"
                inactive={!job.enabled}
                description={runner || job.model ? 'Only for this job, so it need not cost what the runner’s turns cost.' : 'Choose a runner first: with none, the job uses each profile’s runner, whose models are not known here.'}
                control={
                  <MenuSelect
                    label={`${job.title} model`}
                    value={job.model ?? ''}
                    disabled={!runner && !job.model}
                    onChange={(v) => onChange(job.key, { model: v || null }, `${job.title} uses ${modelsFor(runner).find((m) => m.id === v)?.label ?? (v || job.default_model?.label || 'the runner’s model')}`)}
                    options={catalogModelOptions(modelsFor(runner), { unsetLabel: job.default_model ? `${job.default_model.label} (the ${job.key}’s default)` : 'The runner’s model', stored: job.model, aliases: false })}
                  />
                }
              />
              {job.firing_choice && job.mode ? (
                <SettingsRow
                  label="Fires"
                  inactive={!job.enabled}
                  description={`Automatic: ${job.firing_choice.automatic}, and on the button. Button only: just when you press ${job.firing_choice.button} on ${job.firing_choice.where}.`}
                  control={
                    <MenuSelect
                      label={`${job.title} firing`}
                      value={job.mode}
                      onChange={(v) => onChange(job.key, { mode: v }, `${job.title} fires ${v === 'automatic' ? 'automatically' : 'only on the button'}`)}
                      options={[
                        { value: 'automatic' as const, label: 'Automatic', detail: 'On major events and on the button' },
                        { value: 'button' as const, label: 'Button only', detail: `Only when you press ${job.firing_choice.button}` },
                      ]}
                    />
                  }
                />
              ) : null}
              {job.usage_total ? (
                <SettingsRow
                  label="Cost so far"
                  description="Everything this job has spent in this project; each run's own cost is in the run log below."
                  control={
                    <span className="tabular" data-testid={`manager-job-${job.key}-total`} title={formatTokenBreakdown(job.usage_total)}>
                      {job.usage_total.firings === 0
                        ? 'No firings yet'
                        : `${job.usage_total.firings} ${job.usage_total.firings === 1 ? 'firing' : 'firings'} · ${formatUsage(job.usage_total)}`}
                    </span>
                  }
                />
              ) : null}
              {blocked ? (
                <p className="aw-inline-warning">
                  <Icon name="warning" size={13} /> On, but it has no runner, so it will not run.
                </p>
              ) : null}
              </>
              )}
            </div>
          </SettingsGroup>
        )
      })}

      <SettingsGroup title="Run log" description="Every run of every job, the mender's included, newest first.">
        {detail ? <RunDetail view={detail} jobs={jobs} subjectLabel={subjectLabel} now={now} onOpenConversation={onOpenConversation} /> : null}
        <RunLog log={log} error={logError} jobs={jobs} subjectLabel={subjectLabel} now={now} selected={detail?.runId ?? null} onOpenRun={onOpenRun} onOpenConversation={onOpenConversation} />
      </SettingsGroup>
    </SettingsPage>
  )
}


/** `check_now` → "Check now": the trigger as words. */
function triggerLabel(trigger: string | null | undefined): string {
  if (!trigger) return '—'
  const words = trigger.replace(/[_-]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** Whether the operator asked for the run (a button or a request) or the Hub started it. */
function startedBy(run: { initiator?: string | null }): 'Manual' | 'Automatic' {
  return run.initiator === 'operator' ? 'Manual' : 'Automatic'
}

/** A run's cost, or why it has none: never an empty cell, never a zero that was not measured. */
function costOf(run: Pick<ManagerLoggedRun, 'usage' | 'no_cost_reason'>): { text: string; title?: string } {
  if (run.usage && run.usage.cost_usd_micros != null) return { text: formatUsage(run.usage), title: formatTokenBreakdown(run.usage) }
  return { text: run.no_cost_reason ?? 'No cost recorded', title: formatTokenBreakdown(run.usage) }
}

function totalsText(total: ManagerJobRunTotals): string {
  const parts = [`${total.runs} ${total.runs === 1 ? 'run' : 'runs'}`, `${total.failed} failed`]
  parts.push(total.cost_usd_micros == null ? 'no cost recorded' : formatUsage({ cost_usd_micros: total.cost_usd_micros }))
  return parts.join(' · ')
}

function RunLog({
  log,
  error,
  jobs,
  subjectLabel,
  now,
  selected,
  onOpenRun,
  onOpenConversation,
}: {
  log: RunLogView | undefined
  error?: string | null
  jobs: ManagerJob[]
  subjectLabel?: SubjectLabel
  now: Date
  selected: string | null
  onOpenRun: (runId: string) => void
  onOpenConversation?: (conversationId: string) => void
}) {
  if (error) {
    return (
      <p className="aw-inline-warning" role="alert">
        <Icon name="warning" size={13} /> {error}
      </p>
    )
  }
  if (!log) return <LoadingThread label="Loading run log" size="inline" className="my-3" />
  const title = (key: string) => jobs.find((j) => j.key === key)?.title ?? key
  const totalled = Object.entries(log.totals)
  const filterOptions = [{ value: '', label: 'Every job' }, ...totalled.map(([key]) => ({ value: key, label: title(key) }))]
  return (
    <div className="aw-run-log">
      <SettingsRow
        label="Show"
        description="Narrow the log to one job."
        control={
          <span data-testid="manager-run-filter">
            <MenuSelect label="Filter the run log by job" value={log.job ?? ''} onChange={(v) => log.onJob(v || null)} options={filterOptions} />
          </span>
        }
      />
      {totalled.length ? (
        <ul className="aw-run-totals" aria-label="Totals per job">
          {totalled.map(([key, total]) => (
            <li key={key} data-testid={`manager-job-${key}-totals`} data-active={log.job === key ? 'true' : 'false'}>
              <span className="aw-history-job">{title(key)}</span> <span className="tabular">{totalsText(total)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {log.runs.length === 0 ? (
        <p className="aw-empty-line">{log.job ? `${title(log.job)} has not run yet.` : 'No job has run yet.'}</p>
      ) : (
        <div className="aw-history" role="table" aria-label="Manager run log">
          <div className="aw-history-row aw-history-head" role="row">
            <span role="columnheader">Started</span>
            <span role="columnheader">Job</span>
            <span role="columnheader">Result</span>
            <span role="columnheader" className="text-right">Time</span>
            <span role="columnheader" className="text-right">Cost</span>
          </div>
          {log.runs.map((run) => {
            const outcome = OUTCOME[run.outcome as ManagerFiring['outcome']] ?? { label: run.outcome, tone: 'neutral' }
            const cost = costOf(run)
            const subject = subjectLabel?.(run)
            return (
              <div key={run.run_id} className="aw-history-item" data-open={selected === run.run_id ? 'true' : 'false'} data-testid={`manager-run-${run.run_id}`}>
                <div className="aw-history-row" role="row">
                  <span role="cell" className="aw-history-when" title={run.started_at}>
                    {formatDateTime(run.started_at, now)}
                  </span>
                  <span role="cell" className="min-w-0">
                    <span className="aw-history-job">{title(run.job)}</span>
                    <span className="aw-history-detail" data-testid={`manager-run-${run.run_id}-subject`}>{subject ?? ''}</span>
                    <span className="aw-history-meta" data-testid={`manager-run-${run.run_id}-trigger`}>
                      {triggerLabel(run.trigger)} · {startedBy(run)}
                    </span>
                    <button
                      type="button"
                      className="aw-history-link"
                      data-testid={`manager-run-${run.run_id}-link`}
                      aria-label={`Open run ${run.run_id}`}
                      onClick={() => onOpenRun(run.run_id)}
                    >
                      {run.run_id}
                    </button>
                    {run.conversation_id && onOpenConversation ? (
                      <button
                        type="button"
                        className="aw-history-link"
                        data-testid={`manager-run-${run.run_id}-conversation`}
                        onClick={() => onOpenConversation(run.conversation_id!)}
                      >
                        Open the thread
                      </button>
                    ) : null}
                  </span>
                  <span role="cell">
                    <span className="aw-state-chip" data-tone={outcome.tone}>
                      <span className="aw-state-dot" />
                      {outcome.label}
                    </span>
                    {run.outcome === 'failed' && run.detail ? (
                      <span className="aw-history-detail" data-testid={`manager-run-${run.run_id}-reason`}>{run.detail}</span>
                    ) : null}
                  </span>
                  <span role="cell" className="tabular text-right">{run.duration_ms == null ? '—' : formatDuration(run.duration_ms / 1000)}</span>
                  <span role="cell" className="tabular text-right" title={cost.title} data-testid={`manager-run-${run.run_id}-cost`}>{cost.text}</span>
                </div>
              </div>
            )
          })}
          {log.hasMore ? (
            <button type="button" data-slot="history-more" className="aw-history-more" disabled={log.loadingOlder} onClick={log.onShowOlder}>
              Show older runs
            </button>
          ) : null}
        </div>
      )}
    </div>
  )
}

/** The run a link names, opened above the log: what it was about, how it went, and what the model
 *  answered. A run the Hub does not know says so rather than showing nothing. */
function RunDetail({
  view,
  jobs,
  subjectLabel,
  now,
  onOpenConversation,
}: {
  view: RunDetailView
  jobs: ManagerJob[]
  subjectLabel?: SubjectLabel
  now: Date
  onOpenConversation?: (conversationId: string) => void
}) {
  const { run } = view
  const close = (
    <button type="button" className="aw-history-link" data-testid="manager-run-detail-close" onClick={view.onClose}>
      Close
    </button>
  )
  if (view.error) {
    return (
      <div className="aw-history-answer" data-testid="manager-run-detail" role="alert">
        <p className="aw-inline-warning"><Icon name="warning" size={13} /> {view.error}</p>
        {close}
      </div>
    )
  }
  if (!run) return <LoadingThread label="Loading run" size="inline" className="my-3" />
  const outcome = OUTCOME[run.outcome as ManagerFiring['outcome']] ?? { label: run.outcome, tone: 'neutral' }
  const cost = costOf(run)
  return (
    <div className="aw-history-answer" data-testid="manager-run-detail" data-run={run.run_id}>
      <p className="aw-history-meta">
        <span className="aw-history-job">{jobs.find((j) => j.key === run.job)?.title ?? run.job}</span> · {run.run_id} · {subjectLabel?.(run) ?? ''}
      </p>
      <p className="aw-history-meta">
        {triggerLabel(run.trigger)} · {startedBy(run)} · started {formatDateTime(run.started_at, now)} · {run.duration_ms == null ? '—' : formatDuration(run.duration_ms / 1000)} · {outcome.label} · {cost.text}
      </p>
      {run.detail ? <p className="aw-history-meta" data-testid="manager-run-detail-reason">{run.detail}</p> : null}
      {run.answer ? <MarkdownMessage content={run.answer} /> : <p className="aw-empty-line">The model gave no answer.</p>}
      {run.conversation_id && onOpenConversation ? (
        <button type="button" className="aw-history-link" data-testid="manager-run-detail-conversation" onClick={() => onOpenConversation(run.conversation_id!)}>
          Open the thread
        </button>
      ) : null}
      {close}
    </div>
  )
}
