import { useEffect, useRef, useState } from 'react'
import { useCreateAgent } from '@/api/agents'
import { useCharters } from '@/api/charters'
import { useProviderLaunchability, type RunnerLaunchability } from '@/api/runners'
import { useModelCatalog, type ProviderDescriptor } from '@/api/modelCatalog'
import { Button } from '@/components/ui/button'
import { Icon, ProviderMark } from '@/components/common/Icon'
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
 * Replaces a bare `<select>` for provider choice (composer/chrome refinement §4/task
 * 4.4) — a native `<option>` cannot host an SVG mark in any browser, so showing a mark
 * "beside each provider" requires a real listbox rather than the platform control. The
 * provider name stays the primary label; the mark is decoration, not a replacement for it.
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
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const closeOnOutsidePointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', closeOnOutsidePointer)
    return () => document.removeEventListener('mousedown', closeOnOutsidePointer)
  }, [open])

  const current = providers.find((p) => p.provider === value)

  return (
    <div ref={rootRef} className="relative mt-1">
      <button
        type="button"
        aria-label="Provider"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs"
        style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--text)' }}
      >
        {current ? (
          <>
            <ProviderMark provider={current.provider} label={current.label} />
            <span className="flex-1">{current.label}</span>
          </>
        ) : (
          <span className="flex-1" style={{ color: 'var(--text-3)' }}>Select a provider</span>
        )}
        <Icon name="expand_more" size={16} style={{ color: 'var(--text-3)' }} />
      </button>
      {open && (
        <div
          role="listbox"
          aria-label="Provider"
          className="absolute left-0 top-full mt-1 w-full max-h-56 overflow-y-auto p-1 rounded border z-50"
          style={{
            background: 'var(--surface)',
            borderColor: 'var(--border)',
            boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
          }}
        >
          {providers.map((entry) => {
            const verdict = launchability?.[entry.provider]
            const disabled = verdict?.runnable !== true
            return (
              <button
                key={entry.provider}
                type="button"
                role="option"
                aria-selected={entry.provider === value}
                disabled={disabled}
                data-active={entry.provider === value ? 'true' : 'false'}
                onClick={() => {
                  onChange(entry.provider)
                  setOpen(false)
                }}
                className="row-item w-full items-start justify-between gap-3 text-left disabled:pointer-events-none disabled:opacity-50"
                style={{ color: 'var(--text)' }}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <ProviderMark provider={entry.provider} label={entry.label} />
                  <span className="truncate text-xs font-medium">{entry.label}</span>
                </span>
                {verdict && !verdict.runnable && verdict.reason && (
                  <span className="shrink-0 text-[10px] text-right" style={{ color: 'var(--amber)' }}>
                    {verdict.reason}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

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
      <div ref={panelRef} className="lifted-surface w-[min(480px,calc(100vw-32px))] p-5" style={{ background: 'var(--surface)' }}>
        <h2 id="agent-create-title" className="text-sm font-semibold">Create agent</h2>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>Choose a provider and model — the Hub provisions the runner for you.</p>

        <label className="mt-4 block text-xs">
          Agent name
          <input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="codex-reviewer" className="mt-1 block w-full rounded-md px-3 py-2" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }} />
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
