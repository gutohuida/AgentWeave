import { useEffect, useRef, useState } from 'react'
import { useCreateAgent } from '@/api/agents'
import { useCharters } from '@/api/charters'
import { useProviderLaunchability, type RunnerLaunchability } from '@/api/runners'
import { useModelCatalog, catalogModelLabel, type ProviderDescriptor } from '@/api/modelCatalog'
import { Button } from '@/components/ui/button'
import { ProviderMark } from '@/components/common/Icon'
import { MenuSelect } from '@/components/ui/menu'
import { useDialogFocus } from '@/hooks/useDialogFocus'

function errorDetail(error: unknown): string {
  if (!(error instanceof Error)) return 'The agent could not be created.'
  try {
    const parsed = JSON.parse(error.message) as { detail?: string }
    return parsed.detail ?? error.message
  } catch {
    return error.message
  }
}

/**
 * Provider choice. A native `<option>` cannot host an SVG mark in any browser, so the list is a
 * themed menu (`MenuSelect`) whose rows carry the mark. The provider name stays the primary label;
 * the mark is decoration. Being a menu, it takes the arrow keys and Enter, and Escape closes only
 * the list, not the dialog under it (F1027).
 */
function ProviderPicker({
  providers,
  launchability,
  value,
  onChange,
}: {
  providers: ProviderDescriptor[]
  launchability: Record<string, RunnerLaunchability> | undefined
  value: string
  onChange: (provider: string) => void
}) {
  return (
    <div className="mt-1 [&_.aw-select-trigger]:w-full">
      <MenuSelect
        label="Provider"
        value={value}
        onChange={onChange}
        maxWidth={9999}
        placeholder="Select a provider"
        options={providers.map((entry) => {
          const verdict = launchability?.[entry.provider]
          return {
            value: entry.provider,
            label: entry.label,
            icon: <ProviderMark provider={entry.provider} label={entry.label} />,
            disabled: verdict?.runnable !== true,
            detail: verdict && !verdict.runnable && verdict.reason ? verdict.reason : undefined,
          }
        })}
      />
    </div>
  )
}

/**
 * Creating an agent.
 *
 * **Before adding a field here, apply the rule:** a setting is offered at creation only if the
 * agent's *first turn* would be materially different without it. Everything else belongs on the
 * agent's configuration page, where it can be changed before it ever matters.
 *
 * The four that qualify: **name** (how it is addressed, by you and by peers), **provider** and
 * **model** (what actually runs), and **charter** (the behaviour contract injected into that first
 * turn's context). Charter is offered but never required — `operator-agent-creation` defines a
 * no-charter contract, and tightening that here would break it.
 *
 * Thresholds, timeouts and access grants deliberately do **not** qualify. They all have workable
 * defaults, and lengthening creation is friction at exactly the wrong moment: the operator is
 * trying to get an agent, not to configure one.
 */
export function AgentCreateDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (name: string) => void
}) {
  const [name, setName] = useState('')
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [charterId, setCharterId] = useState('')
  const panelRef = useRef<HTMLDivElement>(null)
  const { data: catalog } = useModelCatalog()
  const { data: launchability } = useProviderLaunchability()
  const { data: charters = [], isLoading: chartersLoading } = useCharters()
  const createAgent = useCreateAgent()

  useEffect(() => {
    if (!open) return
    setName('')
    setProvider('')
    setModel('')
    setCharterId('')
    createAgent.reset()
    // The mutation object changes identity as its state changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])
  useDialogFocus(open, panelRef, onClose)

  if (!open) return null

  const providers = catalog?.providers ?? []
  const selectedProvider = providers.find((p) => p.provider === provider)
  const models = selectedProvider?.models ?? []
  const aliasModels = models.flatMap((model) => model.aliases.map((alias) => ({ alias, model })))
  const selectedVerdict = launchability?.providers[provider]
  const canSubmit = /^[a-zA-Z0-9_-]{1,32}$/.test(name.trim())
    && !!provider
    && !!model
    && selectedVerdict?.runnable === true

  const handleProviderChange = (nextProvider: string) => {
    setProvider(nextProvider)
    const entry = providers.find((p) => p.provider === nextProvider)
    setModel(entry?.models.find((m) => m.default)?.id ?? entry?.models[0]?.id ?? '')
  }

  const submit = () => {
    if (!canSubmit) return
    createAgent.mutate(
      {
        name: name.trim(),
        provider,
        model,
        ...(charterId ? { charter_id: charterId } : {}),
      },
      { onSuccess: (agent) => onCreated(agent.name) },
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'var(--scrim)' }} role="dialog" aria-modal="true" aria-labelledby="agent-create-title">
      <div ref={panelRef} tabIndex={-1} className="lifted-surface w-[min(480px,calc(100vw-32px))] p-5" style={{ background: 'var(--surface)' }}>
        <h2 id="agent-create-title" className="text-sm font-semibold">Create agent</h2>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>Choose a provider and model — the Hub provisions the runner for you.</p>

        <label className="mt-4 block text-xs">
          Agent name
          <input data-dialog-initial-focus value={name} onChange={(event) => setName(event.target.value)} placeholder="codex-reviewer" className="mt-1 block w-full rounded-md px-3 py-2" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }} />
        </label>
        {name && !/^[a-zA-Z0-9_-]{1,32}$/.test(name.trim()) && <p className="mt-1 text-[11px]" style={{ color: 'var(--red)' }}>Use 1–32 letters, numbers, hyphens, or underscores.</p>}

        <div className="mt-3 text-xs">
          Provider
          <ProviderPicker
            providers={providers}
            launchability={launchability?.providers}
            value={provider}
            onChange={handleProviderChange}
          />
        </div>

        {provider && (
          <label className="mt-3 block text-xs">
            Model
            <select aria-label="Model" value={model} onChange={(event) => setModel(event.target.value)} className="mt-1 block w-full rounded-md px-3 py-2" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
              {models.map((entry) => <option key={entry.id} value={entry.id}>{entry.label}</option>)}
              {aliasModels.length > 0 && (
                <optgroup label="Latest">
                  {aliasModels.map(({ alias, model: target }) => (
                    <option key={alias} value={alias}>{catalogModelLabel(target, alias)}</option>
                  ))}
                </optgroup>
              )}
            </select>
          </label>
        )}

        <label className="mt-3 block text-xs">
          Charter <span style={{ color: 'var(--text-3)' }}>(optional)</span>
          <select aria-label="Charter" value={charterId} onChange={(event) => setCharterId(event.target.value)} disabled={chartersLoading} className="mt-1 block w-full rounded-md px-3 py-2" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
            <option value="">No charter</option>
            {charters.map((charter) => <option key={charter.id} value={charter.id}>{charter.name}</option>)}
          </select>
        </label>

        {createAgent.error && <div role="alert" className="mt-3 rounded-md px-3 py-2 text-xs" style={{ background: 'var(--error-cont)', color: 'var(--red)' }}>{errorDetail(createAgent.error)}</div>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button variant="primary" size="sm" onClick={submit} disabled={!canSubmit || createAgent.isPending}>{createAgent.isPending ? 'Creating…' : 'Create agent'}</Button>
        </div>
      </div>
    </div>
  )
}
