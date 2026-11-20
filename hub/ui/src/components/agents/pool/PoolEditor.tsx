import * as React from 'react'
import { Icon, ProviderMark } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { MenuSelect, type SelectOption } from '@/components/ui/menu'
import { SettingsGroup, SettingsRow } from '@/components/ui/settings'
import type { AgentPoolEntry, PoolEntryChoice } from '@/api/agentPool'
import type { ModelCatalogResponse } from '@/api/modelCatalog'
import type { Runner } from '@/api/runners'
import { addRefusal, cliLabel, effortsFor, entryLabel, modelLabel, removeRefusal } from './poolModel'
import '@/styles/profile-pool.css'

const NO_EFFORT = '__cli__'

/**
 * The models a profile may run on, on its Running page (FR-1, FR-3): its pool, one entry the
 * default, with an entry added from the project's runners and an effort the catalog offers for
 * it. Replaces the single Model choice. Presentational: the Hub applies each change and may
 * refuse it; `error` is its refusal, shown where the change was asked for.
 */
export function PoolEditor({
  agentName,
  pool,
  runners,
  catalog,
  error = null,
  pending = false,
  onAdd,
  onRemove,
  onMakeDefault,
  onOpenRunners,
}: {
  agentName: string
  pool: AgentPoolEntry[]
  /** The project's runners, as Settings → Runners lists them. */
  runners: Runner[]
  catalog: ModelCatalogResponse | undefined
  /** The Hub's refusal of the last change, in its own words. */
  error?: string | null
  pending?: boolean
  onAdd: (choice: PoolEntryChoice) => void
  onRemove: (entry: AgentPoolEntry) => void
  onMakeDefault: (entry: AgentPoolEntry) => void
  onOpenRunners?: () => void
}) {
  const [runnerId, setRunnerId] = React.useState('')
  const [effort, setEffort] = React.useState(NO_EFFORT)
  const runner = runners.find((r) => r.id === runnerId)
  const efforts = runner ? effortsFor(catalog, runner.cli) : []
  const chosenEffort = effort === NO_EFFORT ? null : effort
  const refusal = runner ? addRefusal(catalog, pool, runner, chosenEffort) : null

  function chooseRunner(id: string) {
    setRunnerId(id)
    // An effort the newly chosen runner's CLI does not offer is not carried over to it.
    const next = runners.find((r) => r.id === id)
    if (next && effort !== NO_EFFORT && !effortsFor(catalog, next.cli).some((v) => v.id === effort)) setEffort(NO_EFFORT)
  }

  const runnerOptions: SelectOption<string>[] = runners.map((r) => ({
    value: r.id,
    label: modelLabel(catalog, r.cli, r.model ?? null),
    detail: `${r.name} · ${cliLabel(r.cli)}`,
    icon: <ProviderMark provider={r.cli} label={cliLabel(r.cli)} />,
  }))
  const effortOptions: SelectOption<string>[] = [
    { value: NO_EFFORT, label: 'Its usual effort', detail: runner ? `Whatever ${cliLabel(runner.cli)} uses` : undefined },
    ...efforts.map((v) => ({ value: v.id, label: v.label })),
  ]

  function add() {
    if (!runner || refusal) return
    onAdd({ runner_id: runner.id, effort: chosenEffort })
    setRunnerId('')
    setEffort(NO_EFFORT)
  }

  return (
    <SettingsGroup title="Models it may run on">
      <SettingsRow
        label="Its models"
        description={`Every task, review and chat of ${agentName} runs on one of these. Build can choose one for each task; anything it does not choose for runs on the default.`}
        stacked
        control={
          <div className="aw-pool-block">
            {pool.length === 0 ? (
              <p className="aw-pool-empty" role="status">
                <Icon name="warning" size={13} /> {agentName} cannot run until it has a model. Add one below.
              </p>
            ) : (
              <ul className="aw-pool-list" aria-label={`Models ${agentName} may run on`}>
                {pool.map((entry) => (
                  <PoolRow key={entry.id} entry={entry} label={entryLabel(catalog, entry)} blocked={removeRefusal(pool, entry)} pending={pending} onRemove={onRemove} onMakeDefault={onMakeDefault} />
                ))}
              </ul>
            )}
            {error ? (
              <p className="aw-pool-refusal" role="alert">
                <Icon name="warning" size={13} /> {error}
              </p>
            ) : null}
          </div>
        }
      />
      <SettingsRow
        label="Add a model"
        description="A runner of the project, at the effort you choose. The same model at two efforts is two entries."
        stacked
        control={
          runners.length === 0 ? (
            <p className="aw-pool-note">
              The project has no runners to add.{' '}
              {onOpenRunners ? (
                <button data-slot="link" type="button" className="aw-pool-link" onClick={onOpenRunners}>
                  Add a runner
                </button>
              ) : null}
            </p>
          ) : (
            <div className="aw-pool-block">
              <div className="aw-pool-add-controls">
                <MenuSelect<string> label={`Runner to add to ${agentName}`} value={runnerId} onChange={chooseRunner} options={runnerOptions} placeholder="Choose a runner" maxWidth={260} />
                <MenuSelect<string> label="Effort" value={effort} onChange={setEffort} options={effortOptions} disabled={!runner || efforts.length === 0} maxWidth={180} />
                <Button variant="outline" size="sm" disabled={!runner || Boolean(refusal) || pending} onClick={add}>
                  <Icon name="add" size={13} /> Add
                </Button>
              </div>
              {refusal ? (
                <p className="aw-pool-refusal">{refusal}</p>
              ) : onOpenRunners ? (
                <p className="aw-pool-note">
                  A runner is a coding agent with its model and settings.{' '}
                  <button data-slot="link" type="button" className="aw-pool-link" onClick={onOpenRunners}>
                    Manage runners
                  </button>
                </p>
              ) : null}
            </div>
          )
        }
      />
    </SettingsGroup>
  )
}

function PoolRow({
  entry,
  label,
  blocked,
  pending,
  onRemove,
  onMakeDefault,
}: {
  entry: AgentPoolEntry
  label: string
  blocked: string | null
  pending: boolean
  onRemove: (entry: AgentPoolEntry) => void
  onMakeDefault: (entry: AgentPoolEntry) => void
}) {
  return (
    <li className="aw-pool-entry" data-default={entry.default ? 'true' : undefined}>
      <ProviderMark provider={entry.cli} label={cliLabel(entry.cli)} size={16} />
      <span className="aw-pool-entry-text">
        <span className="aw-pool-entry-label">{label}</span>
        <span className="aw-pool-entry-detail">
          {entry.runner_name} · {cliLabel(entry.cli)}
        </span>
      </span>
      {entry.default ? (
        <span className="aw-pool-default">
          <Icon name="check" size={12} /> Default
        </span>
      ) : (
        <Button variant="ghost" size="xs" disabled={pending} onClick={() => onMakeDefault(entry)} aria-label={`Make ${label} the default`}>
          Make default
        </Button>
      )}
      <button
        data-slot="icon-button"
        type="button"
        className="aw-icon-button"
        aria-label={`Remove ${label}`}
        title={blocked ?? `Remove ${label}`}
        aria-disabled={blocked || pending ? 'true' : undefined}
        onClick={() => {
          if (!blocked && !pending) onRemove(entry)
        }}
      >
        <Icon name="close" size={13} />
      </button>
    </li>
  )
}
