import { readableApiError } from '@/api/client'
import {
  isNoManager,
  useManagerActivity,
  useManagerJobs,
  useUpdateManagerJob,
  type ManagerFiring,
  type ManagerJob,
  type ManagerJobInput,
} from '@/api/manager'
import { useModelCatalog, type ModelCatalogResponse } from '@/api/modelCatalog'
import { useRunners, type Runner } from '@/api/runners'
import { useVaultMap } from '@/api/vault'
import { Badge } from '@/components/common/Badge'
import type { BadgeVariant } from '@/components/common/badgeVariants'
import { SettingsRow, SettingsSection } from '@/components/environment/SettingsSection'
import { Select } from '@/components/ui/input'
import { hubDate } from '@/lib/hubTime'
import { runnerOptionLabel } from '@/lib/runnerLabel'

/**
 * Environment > Manager (`the-hubs-background-jobs-are-configured-on-a-manager-page`).
 *
 * The Hub's background jobs — model work no operator or agent started, conversation titles first —
 * each with its own switch, runner and model, and below them every time one of them spawned a model.
 * Each control saves on change, sending only what it changed; the jobs are configuration, not a form.
 *
 * A Hub that predates the manager answers its routes 404. The bundle reaches the operator's app on
 * reload, possibly before their server restarts, so that reads as a state rather than an error.
 */
export function ManagerPanel() {
  const jobs = useManagerJobs()
  const activity = useManagerActivity()
  const { data: runners = [], error: runnersError } = useRunners()
  const { data: catalog, error: catalogError } = useModelCatalog()
  const update = useUpdateManagerJob()
  // Names for the vault entries a firing worked on (F719); ids alone when the map is unavailable.
  const { data: vaultEntries } = useVaultMap()
  const entryNames = new Map((vaultEntries ?? []).map((entry) => [entry.id, entry.name]))

  const noManager = isNoManager(jobs.error) || isNoManager(activity.error)
  const save = (key: string, input: ManagerJobInput) => update.mutate({ key, input })
  // Without the runners a select cannot show the stored runner and falls back to its first option,
  // "The agent's own runner" -- a false statement of what the job uses. Without the catalog the
  // model choices are missing. Either way the controls are withheld rather than shown wrong.
  const choicesError = runnersError ?? catalogError

  return (
    <SettingsSection
      title="Manager"
      description="Work the Hub does in the background with a model. Choose which jobs run, on which runner and model, and see every time one ran."
    >
      {noManager ? (
        <p className="py-4 text-xs" style={{ color: 'var(--text-3)' }}>
          This Hub has no manager yet. It arrives when the Hub is restarted on a version that has one.
        </p>
      ) : jobs.error ? (
        <p className="py-4 text-xs" style={{ color: 'var(--amber)' }} role="alert">
          {readableApiError(jobs.error, "Could not read this project's background jobs.")}
        </p>
      ) : !jobs.data ? (
        <div aria-label="Loading background jobs" className="skeleton my-3 h-[58px] w-full" />
      ) : (
        <>
          {choicesError ? (
            <p className="py-4 text-xs" style={{ color: 'var(--amber)' }} role="alert">
              {readableApiError(
                choicesError,
                runnersError
                  ? "Could not read this project's runners, so the jobs' choices cannot be shown."
                  : "Could not read the model catalog, so the jobs' choices cannot be shown.",
              )}
            </p>
          ) : (
            jobs.data.map((job) => (
              <JobRow key={job.key} job={job} runners={runners} catalog={catalog} onSave={save} />
            ))
          )}
          {update.error && (
            <p className="py-2 text-xs" style={{ color: 'var(--amber)' }} role="alert">
              {readableApiError(update.error, 'Could not save that change.')}
            </p>
          )}
          <h3 className="settings-group-heading">Activity</h3>
          <Activity
            firings={activity.data}
            error={activity.error}
            jobs={jobs.data}
            runners={runners}
            catalog={catalog}
            entryNames={entryNames}
          />
        </>
      )}
    </SettingsSection>
  )
}

function JobRow({
  job,
  runners,
  catalog,
  onSave,
}: {
  job: ManagerJob
  runners: Runner[]
  catalog: ModelCatalogResponse | undefined
  onSave: (key: string, input: ManagerJobInput) => void
}) {
  const runner = runners.find((item) => item.id === job.runner_id)
  // Models are offered for the chosen runner's CLI. With no runner chosen the job uses each
  // conversation's own agent's runner, whose CLI is not known here, so only "the runner's model"
  // can be offered honestly.
  const provider = catalog?.providers.find((item) => item.provider === runner?.cli)
  const models = provider?.models ?? []
  const storedUnlisted = job.model && !models.some((model) => model.id === job.model)

  const chooseRunner = (runnerId: string | null) => {
    const next = runners.find((item) => item.id === runnerId)
    // A model belongs to a CLI: one chosen for another CLI's runner is cleared, not carried over.
    const keepsModel = !job.model || (next && runner && next.cli === runner.cli)
    onSave(job.key, keepsModel ? { runner_id: runnerId } : { runner_id: runnerId, model: null })
  }

  return (
    <div data-testid={`manager-job-${job.key}`}>
      <SettingsRow label={job.title} description={job.description}>
        <input
          className="control-choice"
          type="checkbox"
          aria-label={`${job.title} enabled`}
          data-testid={`manager-job-${job.key}-enabled`}
          checked={job.enabled}
          onChange={(event) => onSave(job.key, { enabled: event.target.checked })}
        />
      </SettingsRow>
      <SettingsRow
        label="Runner"
        description={
          job.needs_runner
            ? 'Which runner does this job. It does nothing until a runner is chosen.'
            : "Which runner does this job. None uses each conversation's own agent's runner."
        }
      >
        <Select
          aria-label={`${job.title} runner`}
          data-testid={`manager-job-${job.key}-runner`}
          value={job.runner_id ?? ''}
          onChange={(event) => chooseRunner(event.target.value || null)}
          wrapperClassName="w-56"
          className="px-2 py-1.5 text-xs"
        >
          <option value="">
            {job.needs_runner ? 'No runner (the job does nothing)' : "The agent's own runner"}
          </option>
          {runners.map((item) => (
            <option key={item.id} value={item.id}>{runnerOptionLabel(item, catalog)}</option>
          ))}
        </Select>
      </SettingsRow>
      <SettingsRow
        label="Model"
        description="Overrides the runner's model for this job only, so it need not cost what the runner's turns cost."
      >
        <Select
          aria-label={`${job.title} model`}
          data-testid={`manager-job-${job.key}-model`}
          value={job.model ?? ''}
          disabled={!runner && !job.model}
          onChange={(event) => onSave(job.key, { model: event.target.value || null })}
          wrapperClassName="w-56"
          className="px-2 py-1.5 text-xs"
        >
          <option value="">The runner's model</option>
          {models.map((model) => (
            <option key={model.id} value={model.id}>{model.label}</option>
          ))}
          {storedUnlisted && <option value={job.model ?? ''}>{job.model}</option>}
        </Select>
      </SettingsRow>
    </div>
  )
}

const OUTCOME_VARIANT: Record<ManagerFiring['outcome'], BadgeVariant> = {
  written: 'success',
  // A verdict, not a failure and not nothing: the report was answered and its entry stands (F641).
  answered: 'success',
  empty: 'default',
  failed: 'danger',
}

/** What a firing worked on, in words (F719): every job's subject, not only a title's conversation.
 *  A vault entry is named when the map knows it, its id kept so two of one name stay apart. */
function firingSubject(
  subject: Record<string, string> | null | undefined,
  entryNames: Map<string, string>,
): string | null {
  if (!subject) return null
  const entry = (id: string) => {
    const name = entryNames.get(id)
    return name ? `"${name}" (${id})` : id
  }
  const parts: string[] = []
  if (subject.source) parts.push(`source ${entry(subject.source)}`)
  if (subject.document) parts.push(`document ${subject.document}`)
  if (subject.report) parts.push(`report ${subject.report}`)
  if (subject.entry) parts.push(`on ${entry(subject.entry)}`)
  if (subject.conversation_id) parts.push(`conversation ${subject.conversation_id}`)
  return parts.length ? parts.join(' ') : null
}

function Activity({
  firings,
  error,
  jobs,
  runners,
  catalog,
  entryNames,
}: {
  firings: ManagerFiring[] | undefined
  error: unknown
  jobs: ManagerJob[]
  runners: Runner[]
  catalog: ModelCatalogResponse | undefined
  entryNames: Map<string, string>
}) {
  if (error) {
    return (
      <p className="py-4 text-xs" style={{ color: 'var(--amber)' }} role="alert">
        {readableApiError(error, "Could not read the manager's activity.")}
      </p>
    )
  }
  if (!firings) return <div aria-label="Loading activity" className="skeleton my-3 h-[40px] w-full" />
  if (firings.length === 0) {
    return (
      <p className="py-4 text-xs" style={{ color: 'var(--text-3)' }}>
        No job has spawned a model yet.
      </p>
    )
  }
  return (
    <ol className="divide-y" style={{ borderColor: 'var(--border)' }}>
      {firings.map((firing, index) => {
        const runner = runners.find((item) => item.id === firing.runner_id)
        const provider = catalog?.providers.find((item) => item.provider === firing.cli)
        const model = provider?.models.find((item) => item.id === firing.model)
        return (
          <li
            key={firing.id}
            data-testid={`manager-firing-${index}`}
            className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2.5 text-xs"
          >
            <time dateTime={firing.at} style={{ color: 'var(--text-3)' }}>
              {hubDate(firing.at).toLocaleString()}
            </time>
            <span className="font-medium" style={{ color: 'var(--text)' }}>
              {jobs.find((job) => job.key === firing.job)?.title ?? firing.job}
            </span>
            <Badge variant={OUTCOME_VARIANT[firing.outcome] ?? 'default'}>{firing.outcome}</Badge>
            <span style={{ color: 'var(--text-2)' }}>
              {runner?.name ?? firing.runner_id} · {model?.label ?? firing.model ?? 'runner default'}
              {' · '}
              {(firing.duration_ms / 1000).toFixed(1)} s
            </span>
            {firingSubject(firing.subject, entryNames) && (
              <span data-testid={`manager-firing-${index}-subject`} style={{ color: 'var(--text-3)' }}>
                {firingSubject(firing.subject, entryNames)}
              </span>
            )}
            {firing.detail && (
              <span className="basis-full" style={{ color: 'var(--text)' }}>{firing.detail}</span>
            )}
            {firing.answer && (
              // Kept so a judgement can be read afterwards (F581); closed, since it runs long.
              <details className="basis-full">
                <summary className="cursor-pointer" style={{ color: 'var(--text-3)' }}>
                  What the model answered
                </summary>
                <pre
                  className="mt-1 whitespace-pre-wrap break-words rounded px-2 py-1 font-mono text-[11px]"
                  style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}
                >
                  {firing.answer}
                </pre>
              </details>
            )}
          </li>
        )
      })}
    </ol>
  )
}
