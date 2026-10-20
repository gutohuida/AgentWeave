import { useRef, useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Input, Select } from '@/components/ui/input'
import { useDialogFocus } from '@/hooks/useDialogFocus'
import type { Runner, RunnerCli, ProviderConfigInput } from '@/api/runners'
import {
  useModelCatalog,
  catalogModelLabel,
  catalogSourceLine,
  resolveCatalogModel,
} from '@/api/modelCatalog'
import { readableApiError } from '@/api/client'
import { PROVIDER_RUNNER_CATALOG } from '@/lib/runnerProvider'

/** The runner dialog: create or edit one runner (name, CLI, model, and a Copilot runner's model
 *  provider). Shared by Project settings → Runners; the mutation and its error are the caller's. */

const CLI_OPTIONS: RunnerCli[] = ['claude', 'codex', 'copilot']

// Only a Copilot runner can send its runs to a model provider (design D7), and Anthropic is the
// only provider offered (OpenAI and Azure deferred, 2026-09-28).
export const PROVIDER_CLI: RunnerCli = 'copilot'
const DEFAULT_PROVIDER_BASE_URL = 'https://api.anthropic.com'

/** Runner management states that the provider takes an API key and that a subscription cannot back
 * it (runner-registry: "A subscription cannot back a provider runner"). */
export const PROVIDER_KEY_SENTENCE =
  'The provider is reached with an Anthropic API key, sent on every request. A Claude Max ' +
  "subscription cannot be used: it signs in to Claude, it is not a key. Put the key in the Hub's " +
  'environment and name that variable here; the key itself is never stored.'

export interface RunnerFormValues {
  name: string
  cli: RunnerCli
  model?: string
  provider_config?: ProviderConfigInput
}

export function RunnerForm({
  title,
  initial,
  isPending,
  error,
  onCancel,
  onSubmit,
}: {
  title: string
  initial: Runner | null
  isPending: boolean
  /** The save mutation's error, owned by `RunnersPage` — the dialog stays open on failure and
   * this is where the Hub's own sentence is read. */
  error: unknown
  onCancel: () => void
  onSubmit: (values: RunnerFormValues) => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [cli, setCli] = useState<RunnerCli>(initial?.cli ?? 'claude')
  // '' is the unset model — the "Provider default" choice, a valid runner state, not a placeholder.
  const [model, setModel] = useState(initial?.model ?? '')
  const initialProvider = initial?.provider_config ?? null
  const [providerOn, setProviderOn] = useState(!!initialProvider)
  const [baseUrl, setBaseUrl] = useState(initialProvider?.base_url ?? '')
  const [apiKeyVar, setApiKeyVar] = useState(initialProvider?.api_key_var ?? '')
  const { data: catalog } = useModelCatalog()
  const withProvider = cli === PROVIDER_CLI && providerOn

  // Loading and failed both land here. An empty select would read as "this provider declares no
  // models" rather than "we do not know yet", so the control is disabled and says which it is.
  const catalogAvailable = !!catalog
  // A provider runner's model is sent to the provider's API as is, so it is offered the Claude API
  // ids alone: no alias (an alias is a Claude Code choice, not an API model) and no unset choice
  // (the provider needs a model). The Hub refuses anything else (review 2026-09-28, finding 9).
  const providerEntry = catalog?.providers.find(
    (p) => p.provider === (withProvider ? PROVIDER_RUNNER_CATALOG : cli),
  )
  const declaredModels = providerEntry?.models ?? []
  const aliasModels = withProvider
    ? []
    : declaredModels.flatMap((model) => model.aliases.map((alias) => ({ alias, model })))

  // The runner's own stored model, kept as an offered and selected option when the catalog does not
  // list it — without it, opening a legacy runner would silently re-point it at whatever option came
  // first, and Save would destroy a working configuration. A declared alias counts as declared too
  // (`resolveCatalogModel` — a-model-alias-is-a-model-choice): a runner stored as `opus` must not
  // show as unrecognised.
  // Only while the provider is off and as stored: toggling it clears the model and changes the list,
  // and a provider runner's list is the declared ids and nothing else.
  const storedModel =
    !withProvider && providerOn === !!initialProvider ? (initial?.model ?? null) : null
  const storedIsDeclared = !!resolveCatalogModel(providerEntry, storedModel)
  const storedOption = storedModel && !storedIsDeclared ? storedModel : null

  // The refusal is the Hub's own sentence. With a provider set it is read beside the key field,
  // where the likeliest mistake (a pasted key) is made; the route checks the provider first.
  const refusal = error ? readableApiError(error, 'The runner could not be saved.') : null

  const toggleProvider = (on: boolean) => {
    setProviderOn(on)
    // The two lists share no valid value, so the operator chooses again from the right one.
    setModel('')
  }

  const submit = () => {
    const providerConfig: ProviderConfigInput | undefined = withProvider
      ? {
          type: 'anthropic',
          api_key_var: apiKeyVar.trim(),
          ...(baseUrl.trim() ? { base_url: baseUrl.trim() } : {}),
        }
      : undefined
    onSubmit({ name, cli, model: model || undefined, provider_config: providerConfig })
  }

  // Only Codex publishes its own catalog today (design D2) — Claude's models are a literal with
  // no cache to name, so this line is Codex-only rather than showing "Built-in list" for every
  // provider and implying Claude might one day drift the same way.
  const sourceLine = cli === 'codex' ? catalogSourceLine(providerEntry?.source) : null

  const panelRef = useRef<HTMLDivElement>(null)
  useDialogFocus(true, panelRef, onCancel)

  return (
    <div
      className="fixed inset-0 flex items-center justify-center z-50"
      style={{ background: 'var(--scrim)' }}
      onClick={onCancel}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="runner-form-title"
        className="lifted-surface surface-enter w-[min(448px,calc(100vw-32px))] p-5"
        style={{ background: 'var(--surface)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="runner-form-title" className="text-base font-medium mb-4" style={{ color: 'var(--text)' }}>
          {title}
        </h2>
        <div className="space-y-3">
          <div>
            <label htmlFor="runner-name" className="block text-xs mb-1" style={{ color: 'var(--text-3)' }}>
              Name
            </label>
            <Input
              id="runner-name"
              data-dialog-initial-focus
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="px-3 py-2 text-sm"
              placeholder="e.g. Claude Opus"
            />
          </div>
          <div>
            <label htmlFor="runner-cli" className="block text-xs mb-1" style={{ color: 'var(--text-3)' }}>
              CLI
            </label>
            <Select
              id="runner-cli"
              value={cli}
              disabled={!!initial}
              onChange={(e) => {
                setCli(e.target.value as RunnerCli)
                setProviderOn(false)
                // Back to unset, not to the new provider's default model: unset is a valid runner
                // state, and choosing a model on the operator's behalf is the same class of mistake
                // as silently re-pointing a legacy runner. AgentCreateDialog resets to a concrete
                // model id because an agent must have one; a runner must not.
                setModel('')
              }}
              className="px-3 py-2 text-sm capitalize"
            >
              {CLI_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </Select>
          </div>
          {cli === PROVIDER_CLI && (
            <ProviderFields
              on={providerOn}
              onToggle={toggleProvider}
              baseUrl={baseUrl}
              onBaseUrl={setBaseUrl}
              apiKeyVar={apiKeyVar}
              onApiKeyVar={setApiKeyVar}
              refusal={withProvider ? refusal : null}
            />
          )}
          <div>
            <label htmlFor="runner-model" className="block text-xs mb-1" style={{ color: 'var(--text-3)' }}>
              Model
            </label>
            <Select
              id="runner-model"
              value={model}
              disabled={!catalogAvailable}
              onChange={(e) => setModel(e.target.value)}
              className="px-3 py-2 text-sm"
            >
              {withProvider ? (
                <option value="" disabled hidden>
                  Choose a Claude API model
                </option>
              ) : (
                <option value="">Provider default</option>
              )}
              {storedOption && (
                <option value={storedOption}>
                  {initial?.model_unrecognised ? `${storedOption} — unrecognised` : storedOption}
                </option>
              )}
              {declaredModels.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
              {aliasModels.length > 0 && (
                <optgroup label="Latest">
                  {aliasModels.map(({ alias, model: target }) => (
                    <option key={alias} value={alias}>
                      {catalogModelLabel(target, alias)}
                    </option>
                  ))}
                </optgroup>
              )}
            </Select>
            {!catalogAvailable && (
              <p className="text-xs mt-1" style={{ color: 'var(--text-3)' }}>
                The model catalog is unavailable — this runner will use the provider's default.
              </p>
            )}
            {catalogAvailable && sourceLine && (
              <p className="text-xs mt-1" style={{ color: 'var(--text-3)' }}>
                {sourceLine}
              </p>
            )}
          </div>
        </div>
        {refusal && !withProvider && <RefusalNote>{refusal}</RefusalNote>}
        <div className="flex items-center justify-end gap-2 mt-5">
          <Button variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
          <Button
            variant="primary"
            size="sm"
            onClick={submit}
            disabled={isPending || !name.trim() || (withProvider && (!apiKeyVar.trim() || !model))}
          >
            {isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  )
}

const REFUSAL_ID = 'runner-form-refusal'

function RefusalNote({ children }: { children: ReactNode }) {
  return (
    <div
      id={REFUSAL_ID}
      role="alert"
      className="mt-3 rounded-md px-3 py-2 text-xs"
      style={{ background: 'var(--error-cont)', color: 'var(--red)' }}
    >
      {children}
    </div>
  )
}

/** A Copilot runner's model provider (design D7): the type, the address, and the *name* of the
 * Hub environment variable holding the key, never the key. */
function ProviderFields({
  on,
  onToggle,
  baseUrl,
  onBaseUrl,
  apiKeyVar,
  onApiKeyVar,
  refusal,
}: {
  on: boolean
  onToggle: (on: boolean) => void
  baseUrl: string
  onBaseUrl: (value: string) => void
  apiKeyVar: string
  onApiKeyVar: (value: string) => void
  refusal: string | null
}) {
  const labelClass = 'block text-xs mb-1'
  const labelStyle = { color: 'var(--text-3)' }
  return (
    <div className="space-y-3 rounded-md border p-3" style={{ borderColor: 'var(--border)' }}>
      <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-2)' }}>
        <input type="checkbox" checked={on} onChange={(e) => onToggle(e.target.checked)} />
        Send runs to a model provider with your own API key
      </label>
      {on && (
        <>
          <div>
            <label htmlFor="runner-provider-type" className={labelClass} style={labelStyle}>
              Provider
            </label>
            {/* One provider offered, so nothing to choose yet; the field says which it is. */}
            <Select id="runner-provider-type" value="anthropic" disabled className="px-3 py-2 text-sm">
              <option value="anthropic">Anthropic</option>
            </Select>
          </div>
          <div>
            <label htmlFor="runner-provider-base-url" className={labelClass} style={labelStyle}>
              Base URL
            </label>
            <Input
              id="runner-provider-base-url"
              value={baseUrl}
              onChange={(e) => onBaseUrl(e.target.value)}
              className="px-3 py-2 text-sm"
              placeholder={DEFAULT_PROVIDER_BASE_URL}
            />
          </div>
          <div>
            <label htmlFor="runner-provider-key-var" className={labelClass} style={labelStyle}>
              Key variable name
            </label>
            <Input
              id="runner-provider-key-var"
              value={apiKeyVar}
              onChange={(e) => onApiKeyVar(e.target.value)}
              className="px-3 py-2 text-sm font-mono"
              placeholder="MY_ANTHROPIC_KEY"
              autoComplete="off"
              spellCheck={false}
              aria-describedby={refusal ? `runner-provider-key-note ${REFUSAL_ID}` : 'runner-provider-key-note'}
            />
            <p id="runner-provider-key-note" className="text-xs mt-1" style={{ color: 'var(--text-3)' }}>
              {PROVIDER_KEY_SENTENCE}
            </p>
            {refusal && <RefusalNote>{refusal}</RefusalNote>}
          </div>
        </>
      )}
    </div>
  )
}
