import * as React from 'react'
import { Icon, ProviderMark } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { MenuSelect, type SelectOption } from '@/components/ui/menu'
import { SettingsGroup, SettingsRow } from '@/components/ui/settings'
import type { AgentPoolEntry, PoolModelChoice } from '@/api/agentPool'
import type { ModelCatalogResponse } from '@/api/modelCatalog'
import type { RunnerCli } from '@/api/runners'
import { defaultModel, modelOptions, providerOptions } from './catalogOptions'
import { addRefusal, cliLabel, effortsFor, entryLabel, removeRefusal } from './poolModel'
import '@/styles/profile-pool.css'

const NO_EFFORT = '__cli__'

/**
 * The models a profile may run on, on its Running page (FR-1, FR-3): its pool, one entry the
 * default, with an entry added from the model catalog (`a-profile-s-pool-and-a-new-chat-can-use-
 * any-model-of-any-provider`, FR-1): any provider, any of its models, at an effort that provider
 * offers. A model no runner of the project uses yet is added all the same; the Hub makes its runner
 * (FR-2). Presentational: the Hub applies each change and may refuse it; `error` is its refusal,
 * shown where the change was asked for.
 */
export function PoolEditor({
  agentName,
  pool,
  catalog,
  error = null,
  pending = false,
  onAdd,
  onRemove,
  onMakeDefault,
}: {
  agentName: string
  pool: AgentPoolEntry[]
  catalog: ModelCatalogResponse | undefined
  /** The Hub's refusal of the last change, in its own words. */
  error?: string | null
  pending?: boolean
  onAdd: (choice: PoolModelChoice) => void
  onRemove: (entry: AgentPoolEntry) => void
  onMakeDefault: (entry: AgentPoolEntry) => void
}) {
  const providers = catalog?.providers ?? []
  const [providerId, setProviderId] = React.useState('')
  const [modelId, setModelId] = React.useState('')
  const [effort, setEffort] = React.useState(NO_EFFORT)
  const provider = providers.find((p) => p.provider === providerId)
  const efforts = provider ? effortsFor(catalog, provider.provider) : []
  const chosenEffort = effort === NO_EFFORT ? null : effort
  const choice = provider && modelId ? { provider: provider.provider, model: modelId } : null
  const refusal = choice ? addRefusal(catalog, pool, choice, chosenEffort) : null

  function chooseProvider(id: string) {
    setProviderId(id)
    setModelId(defaultModel(providers.find((p) => p.provider === id)))
    // An effort the newly chosen provider does not offer is not carried over to it.
    if (effort !== NO_EFFORT && !effortsFor(catalog, id).some((v) => v.id === effort)) setEffort(NO_EFFORT)
  }

  const effortOptions: SelectOption<string>[] = [
    { value: NO_EFFORT, label: 'Its usual effort', detail: provider ? `Whatever ${cliLabel(provider.provider)} uses` : undefined },
    ...efforts.map((v) => ({ value: v.id, label: v.label })),
  ]

  function add() {
    if (!choice || refusal) return
    onAdd({ provider: choice.provider as RunnerCli, model: choice.model, effort: chosenEffort })
    setModelId(defaultModel(provider))
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
        description="Any model of any provider, at the effort you choose. The same model at two efforts is two entries."
        stacked
        control={
          providers.length === 0 ? (
            <p className="aw-pool-note">The model catalog has not loaded, so there is nothing to add yet.</p>
          ) : (
            <div className="aw-pool-block">
              <div className="aw-pool-add-controls">
                <MenuSelect<string> label="Provider" value={providerId} onChange={chooseProvider} options={providerOptions(providers)} placeholder="Choose a provider" maxWidth={200} />
                <MenuSelect<string> label={`Model to add to ${agentName}`} value={modelId} onChange={setModelId} options={modelOptions(provider)} disabled={!provider} placeholder="Choose a model" maxWidth={240} />
                <MenuSelect<string> label="Effort" value={effort} onChange={setEffort} options={effortOptions} disabled={!provider || efforts.length === 0} maxWidth={180} />
                <Button variant="outline" size="sm" disabled={!choice || Boolean(refusal) || pending} onClick={add}>
                  <Icon name="add" size={13} /> Add
                </Button>
              </div>
              {refusal ? <p className="aw-pool-refusal">{refusal}</p> : null}
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
        {/* The CLI once: the label names the model and effort, and a runner's name only repeats them. */}
        <span className="aw-pool-entry-detail">{cliLabel(entry.cli)}</span>
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
