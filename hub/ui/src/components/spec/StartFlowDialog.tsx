import { useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import { useDialogFocus } from '@/hooks/useDialogFocus'
import { useAgents } from '@/api/agents'
import { useCreateFlow } from '@/api/loops'
import { readableApiError } from '@/api/client'
import { cronDayAmbiguity, describeCron } from '@/lib/cron'

/** `create_flow`'s default (`mcp_server.py`): a firing whose agent is busy is refused before it
 *  claims anything, so five minutes costs a query and no rows. */
const FLOW_DEFAULT_CRON = '*/5 * * * *'
const NAME_MAX = 256

/**
 * Starts a flow on an approved document — `POST /jobs` with a `spec_document_id`
 * (`a-flow-is-configured-from-its-own-tab`, design D5).
 *
 * Not `JobForm`: that sends `work_needs_evidence` whenever its loop section is open, and a flow's
 * work is always evidence-governed. It takes the document and an `onClose` and no host props, so a
 * later report can open the same dialog.
 */
export function StartFlowDialog({
  document,
  onClose,
}: {
  document: { id: string; title: string }
  onClose: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  useDialogFocus(true, panelRef, onClose)
  const { data: agents, isError: agentsFailed } = useAgents()
  const createFlow = useCreateFlow()

  const [name, setName] = useState(document.title.slice(0, NAME_MAX))
  const [agent, setAgent] = useState('')
  const [message, setMessage] = useState(`Work the next task of "${document.title}".`)
  const [cron, setCron] = useState(FLOW_DEFAULT_CRON)
  const [stopWhenQueueEmpties, setStopWhenQueueEmpties] = useState(true)
  const [stopAt, setStopAt] = useState('')
  const [error, setError] = useState<string | null>(null)

  const open = useMemo(() => agents ?? [], [agents])
  // With a single open agent there is nothing to choose between; with more, no preselection.
  const chosen = agent || (open.length === 1 ? open[0].name : '')
  const cronPlain = describeCron(cron)
  const cronAmbiguity = cronDayAmbiguity(cron)

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    if (!name.trim()) return setError('Name is required')
    if (!chosen) return setError('Choose the agent that works this flow.')
    if (!message.trim()) return setError('Message is required')
    if (!cron.trim()) return setError('Cron expression is required')
    // `create_flow` refuses the same way: a flow with no stop never ends.
    if (!stopWhenQueueEmpties && !stopAt) {
      return setError('A flow needs a stop condition: keep “when the queue empties”, or set a stop time.')
    }
    createFlow.mutate(
      {
        name: name.trim().slice(0, NAME_MAX),
        agent: chosen,
        message: message.trim(),
        cron: cron.trim(),
        enabled: true,
        source: 'hub',
        spec_document_id: document.id,
        purpose: '',
        stop_when_queue_empties: stopWhenQueueEmpties,
        /* `new Date`, not `hubDate`: `stopAt` is wall-clock time typed into a `datetime-local`
         * input in the operator's zone, not a Hub timestamp. */
        ...(stopAt ? { stop_at: new Date(stopAt).toISOString() } : {}),
      },
      {
        onSuccess: onClose,
        onError: (e: unknown) =>
          setError(readableApiError(e, 'The Hub refused to start this flow.')),
      },
    )
  }

  const label = 'mb-1.5 block text-[11px] font-medium'
  const field: React.CSSProperties = { padding: '8px 12px', width: '100%', fontSize: 13 }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'var(--scrim)' }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="start-flow-title"
    >
      <div
        ref={panelRef}
        className="lifted-surface max-h-[90vh] w-full max-w-md overflow-y-auto p-5"
        style={{ background: 'var(--surface)' }}
      >
        <h2 id="start-flow-title" className="text-sm font-semibold">
          Start a flow on “{document.title}”
        </h2>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
          The first firing is on the next schedule tick; nothing runs when you press Start.
        </p>

        <form onSubmit={submit} className="mt-4 space-y-3">
          <div>
            <label className={label} style={{ color: 'var(--text-3)' }} htmlFor="flow-name">
              Name
            </label>
            <input
              id="flow-name"
              className="control-field"
              style={field}
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={createFlow.isPending}
            />
          </div>
          <div>
            <label className={label} style={{ color: 'var(--text-3)' }} htmlFor="flow-agent">
              Default agent
            </label>
            <div className="control-select-wrap">
              <select
                id="flow-agent"
                data-dialog-initial-focus
                className="control-field"
                style={field}
                value={chosen}
                onChange={(e) => setAgent(e.target.value)}
                disabled={createFlow.isPending}
              >
                <option value="">Select an agent…</option>
                {open.map((a) => (
                  <option key={a.name} value={a.name}>
                    @{a.name}
                  </option>
                ))}
              </select>
              <Icon name="expand_more" size={15} className="control-select-icon" />
            </div>
          </div>
          <div>
            <label className={label} style={{ color: 'var(--text-3)' }} htmlFor="flow-message">
              Message
            </label>
            <textarea
              id="flow-message"
              rows={2}
              className="control-field resize-none"
              style={field}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              disabled={createFlow.isPending}
            />
          </div>
          <div>
            <label className={label} style={{ color: 'var(--text-3)' }} htmlFor="flow-cron">
              Schedule (cron)
            </label>
            <input
              id="flow-cron"
              className="control-field font-mono"
              style={field}
              value={cron}
              onChange={(e) => setCron(e.target.value)}
              disabled={createFlow.isPending}
            />
            {cronPlain && (
              <p className="cron-preview" data-testid="cron-preview">
                {cronPlain}
              </p>
            )}
            {cronAmbiguity && (
              <p className="next-run-preview" style={{ color: 'var(--amber)' }}>
                {cronAmbiguity}
              </p>
            )}
          </div>
          <fieldset className="space-y-2">
            <legend className={label} style={{ color: 'var(--text-3)' }}>
              Stop
            </legend>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                className="control-choice"
                checked={stopWhenQueueEmpties}
                onChange={(e) => setStopWhenQueueEmpties(e.target.checked)}
                disabled={createFlow.isPending}
              />
              When the queue empties
            </label>
            <div>
              <label className={label} style={{ color: 'var(--text-3)' }} htmlFor="flow-stop-at">
                Stop at (optional)
              </label>
              <input
                id="flow-stop-at"
                type="datetime-local"
                className="control-field"
                style={field}
                value={stopAt}
                onChange={(e) => setStopAt(e.target.value)}
                disabled={createFlow.isPending}
              />
            </div>
          </fieldset>

          {agentsFailed && (
            <p role="alert" className="text-xs" style={{ color: 'var(--amber)' }}>
              Could not load the agent list.
            </p>
          )}
          {error && (
            <p role="alert" className="text-xs" style={{ color: 'var(--amber)' }}>
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={createFlow.isPending}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={createFlow.isPending}>
              {createFlow.isPending ? 'Starting…' : 'Start flow'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
