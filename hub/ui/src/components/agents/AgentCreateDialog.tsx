import { useEffect, useRef, useState } from 'react'
import { useCreateAgent } from '@/api/agents'
import { useCharters } from '@/api/charters'
import { useRunners, useRunnerLaunchability } from '@/api/runners'
import { Button } from '@/components/ui/button'
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
  const [runnerId, setRunnerId] = useState('')
  const [charterId, setCharterId] = useState('')
  const panelRef = useRef<HTMLDivElement>(null)
  const { data: runners = [], isLoading: runnersLoading } = useRunners()
  const { data: launchability } = useRunnerLaunchability()
  const { data: charters = [], isLoading: chartersLoading } = useCharters()
  const createAgent = useCreateAgent()

  useEffect(() => {
    if (!open) return
    setName('')
    setRunnerId('')
    setCharterId('')
    createAgent.reset()
    // The mutation object changes identity as its state changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])
  useDialogFocus(open, panelRef, onClose)

  if (!open) return null

  const selectedVerdict = launchability?.runners[runnerId]
  const canSubmit = /^[a-zA-Z0-9_-]{1,32}$/.test(name.trim())
    && !!runnerId
    && selectedVerdict?.runnable === true

  const submit = () => {
    if (!canSubmit) return
    createAgent.mutate(
      {
        name: name.trim(),
        runner_id: runnerId,
        ...(charterId ? { charter_id: charterId } : {}),
      },
      { onSuccess: (agent) => onCreated(agent.name) },
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'var(--scrim)' }} role="dialog" aria-modal="true" aria-labelledby="agent-create-title">
      <div ref={panelRef} className="lifted-surface w-[min(480px,calc(100vw-32px))] p-5" style={{ background: 'var(--surface)' }}>
        <h2 id="agent-create-title" className="text-sm font-semibold">Create agent</h2>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>Create an addressable agent from a runner already configured for this project.</p>

        <label className="mt-4 block text-xs">
          Agent name
          <input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="codex-reviewer" className="mt-1 block w-full rounded-md px-3 py-2" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }} />
        </label>
        {name && !/^[a-zA-Z0-9_-]{1,32}$/.test(name.trim()) && <p className="mt-1 text-[11px]" style={{ color: 'var(--red)' }}>Use 1–32 letters, numbers, hyphens, or underscores.</p>}

        <label className="mt-3 block text-xs">
          Runner
          <select aria-label="Runner" value={runnerId} onChange={(event) => setRunnerId(event.target.value)} disabled={runnersLoading} className="mt-1 block w-full rounded-md px-3 py-2" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
            <option value="">Select a runner</option>
            {runners.map((runner) => {
              const verdict = launchability?.runners[runner.id]
              return <option key={runner.id} value={runner.id} disabled={verdict?.runnable !== true}>{runner.name} · {runner.cli}{runner.model ? ` · ${runner.model}` : ''}</option>
            })}
          </select>
        </label>
        {runners.map((runner) => {
          const verdict = launchability?.runners[runner.id]
          return verdict && !verdict.runnable && verdict.reason ? <p key={runner.id} className="mt-1 text-[11px]" style={{ color: 'var(--amber)' }}>{runner.name}: {verdict.reason}</p> : null
        })}

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
