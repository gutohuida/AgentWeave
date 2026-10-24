import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { MenuSelect } from '@/components/ui/menu'
import { SettingsGroup, SettingsPage, SettingsRow } from '@/components/ui/settings'
import { Switch } from '@/components/ui/switch'
import { MarkdownMessage } from '@/components/agents/MarkdownMessage'
import type { ManagerFiring, ManagerJob, ManagerJobInput } from '@/api/manager'
import type { Runner } from '@/api/runners'
import type { ModelDescriptor } from '@/api/modelCatalog'
import { formatDateTime, formatDuration, formatUsage } from '@/lib/format'
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

/** What a firing was about, in words: "Conversation conv-…" becomes the conversation's title when
 *  the container knows it. */
export type SubjectLabel = (firing: ManagerFiring) => string | null

export function ManagerSettings({
  jobs,
  firings,
  firingsError,
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
  /** Undefined while the history is on its way. */
  firings: ManagerFiring[] | undefined
  /** Why the history could not be read; it is never shown as empty when it was not read. */
  firingsError?: string | null
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
            `${job.title} runs on ${next?.name ?? (job.needs_runner ? 'no runner' : 'each agent’s own runner')}`,
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
                description={job.needs_runner ? 'This job does nothing until a runner is chosen.' : 'None: each conversation’s own agent runner.'}
                control={
                  <MenuSelect
                    label={`${job.title} runner`}
                    value={job.runner_id ?? ''}
                    onChange={(v) => chooseRunner(v || null)}
                    options={runnerChoiceOptions(
                      runners,
                      job.needs_runner
                        ? { label: 'No runner', detail: 'The job does nothing until one is chosen' }
                        : { label: 'The agent’s own runner', detail: 'Each conversation’s own agent runner' },
                      modelPart ?? ((r) => r.model ?? 'Provider default'),
                    )}
                  />
                }
              />
              <SettingsRow
                label="Model"
                inactive={!job.enabled}
                description={runner || job.model ? 'Only for this job, so it need not cost what the runner’s turns cost.' : 'Choose a runner first: with none, the job uses each agent’s runner, whose models are not known here.'}
                control={
                  <MenuSelect
                    label={`${job.title} model`}
                    value={job.model ?? ''}
                    disabled={!runner && !job.model}
                    onChange={(v) => onChange(job.key, { model: v || null }, `${job.title} uses ${modelsFor(runner).find((m) => m.id === v)?.label ?? (v || 'the runner’s model')}`)}
                    options={catalogModelOptions(modelsFor(runner), { unsetLabel: 'The runner’s model', stored: job.model, aliases: false })}
                  />
                }
              />
              {job.key === 'chapters' && job.mode ? (
                <SettingsRow
                  label="Fires"
                  inactive={!job.enabled}
                  description="Automatic: after a document is approved or archived and after its last task is approved, and on the button. Button only: just when you press Weave the thread on the Thread page."
                  control={
                    <MenuSelect
                      label={`${job.title} firing`}
                      value={job.mode}
                      onChange={(v) => onChange(job.key, { mode: v }, `${job.title} fires ${v === 'automatic' ? 'automatically' : 'only on the button'}`)}
                      options={[
                        { value: 'automatic' as const, label: 'Automatic', detail: 'On major events and on the button' },
                        { value: 'button' as const, label: 'Button only', detail: 'Only when you press Weave the thread' },
                      ]}
                    />
                  }
                />
              ) : null}
              {job.usage_total ? (
                <SettingsRow
                  label="Cost so far"
                  description="Everything this job has spent in this project; each firing's own cost is in the history below."
                  control={
                    <span className="tabular" data-testid={`manager-job-${job.key}-total`}>
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

      <SettingsGroup title="History" description="Every time a job called a model.">
        <ManagerHistory firings={firings} error={firingsError} jobs={jobs} runners={runners} subjectLabel={subjectLabel} now={now} />
      </SettingsGroup>
    </SettingsPage>
  )
}

function ManagerHistory({
  firings,
  error,
  jobs,
  runners,
  subjectLabel,
  now,
}: {
  firings: ManagerFiring[] | undefined
  error?: string | null
  jobs: ManagerJob[]
  runners: Runner[]
  subjectLabel?: SubjectLabel
  now: Date
}) {
  const [open, setOpen] = React.useState<string | null>(null)
  const [shown, setShown] = React.useState(8)
  if (error) {
    return (
      <p className="aw-inline-warning" role="alert">
        <Icon name="warning" size={13} /> {error}
      </p>
    )
  }
  if (!firings) return <LoadingThread label="Loading activity" size="inline" className="my-3" />
  if (firings.length === 0) return <p className="aw-empty-line">No job has spawned a model yet.</p>
  return (
    <div className="aw-history" role="table" aria-label="Manager history">
      <div className="aw-history-row aw-history-head" role="row">
        <span role="columnheader">When</span>
        <span role="columnheader">Job</span>
        <span role="columnheader">Result</span>
        <span role="columnheader" className="text-right">Time</span>
        <span role="columnheader" className="text-right">Cost</span>
      </div>
      {firings.slice(0, shown).map((firing, index) => {
        const job = jobs.find((j) => j.key === firing.job)
        const outcome = OUTCOME[firing.outcome] ?? { label: firing.outcome, tone: 'neutral' }
        const expanded = open === firing.id
        const runner = runners.find((r) => r.id === firing.runner_id)
        return (
          <div key={firing.id} className="aw-history-item" data-open={expanded ? 'true' : 'false'} data-testid={`manager-firing-${index}`}>
            <button
              type="button"
              data-slot="history-row"
              className="aw-history-row"
              role="row"
              aria-expanded={expanded}
              onClick={() => setOpen(expanded ? null : firing.id)}
            >
              <span role="cell" className="aw-history-when" title={firing.at}>
                <span className="aw-history-chevron" data-open={expanded ? 'true' : 'false'}>
                  <Icon name="chevron_right" size={12} />
                </span>
                {formatDateTime(firing.at, now)}
              </span>
              <span role="cell" className="min-w-0 truncate">
                <span className="aw-history-job">{job?.title ?? firing.job}</span>
                <span className="aw-history-detail" data-testid={subjectLabel?.(firing) ? `manager-firing-${index}-subject` : undefined}>
                  {subjectLabel?.(firing) ?? firing.detail ?? ''}
                </span>
              </span>
              <span role="cell">
                <span className="aw-state-chip" data-tone={outcome.tone}>
                  <span className="aw-state-dot" />
                  {outcome.label}
                </span>
              </span>
              <span role="cell" className="tabular text-right">{formatDuration(firing.duration_ms / 1000)}</span>
              <span role="cell" className="tabular text-right">{formatUsage(firing.usage)}</span>
            </button>
            {expanded ? (
              <div className="aw-history-answer">
                <p className="aw-history-meta">
                  {runner?.name ?? firing.cli} · {firing.model ?? 'runner’s model'}
                </p>
                {firing.detail && subjectLabel?.(firing) ? <p className="aw-history-meta">{firing.detail}</p> : null}
                {firing.answer ? <MarkdownMessage content={firing.answer} /> : <p className="aw-empty-line">The model gave no answer.</p>}
              </div>
            ) : null}
          </div>
        )
      })}
      {firings.length > shown ? (
        <button type="button" data-slot="history-more" className="aw-history-more" onClick={() => setShown((n) => n + 20)}>
          Show older ({firings.length - shown})
        </button>
      ) : null}
    </div>
  )
}
