import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { useAgents } from '@/api/agents'
import { Button } from '@/components/ui/button'
import { JobCreate } from '@/api/jobs'

interface JobFormProps {
  onSubmit: (job: JobCreate) => void
  onCancel: () => void
  isPending: boolean
}

const CRON_EXAMPLES = [
  { label: 'Daily at 9am', value: '0 9 * * *' },
  { label: 'Weekdays at 9am', value: '0 9 * * 1-5' },
  { label: 'Every 6 hours', value: '0 */6 * * *' },
  { label: 'Weekly (Sundays)', value: '0 0 * * 0' },
  { label: 'Monthly (1st)', value: '0 0 1 * *' },
]

export function JobForm({ onSubmit, onCancel, isPending }: JobFormProps) {
  const { data: agents } = useAgents()
  const [name, setName] = useState('')
  const [agent, setAgent] = useState('')
  const [message, setMessage] = useState('')
  const [cron, setCron] = useState('0 9 * * *')
  const [sessionMode, setSessionMode] = useState<'new' | 'resume'>('new')
  const [error, setError] = useState('')

  // "Make this a loop" — collapsed by default. `loopEnabled` tracks whether the operator ever
  // opened the section, which is what decides whether the loop fields are sent at all (task 5.1):
  // a controlled textarea that always renders `purpose=""` must not, by that fact alone, opt every
  // job into being a loop the server's `purpose is not None` rule would then honor.
  const [loopEnabled, setLoopEnabled] = useState(false)
  const [purpose, setPurpose] = useState('')
  const [stopAt, setStopAt] = useState('')
  const [stopWhenQueueEmpties, setStopWhenQueueEmpties] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!name.trim()) {
      setError('Name is required')
      return
    }
    if (!agent) {
      setError('Agent is required')
      return
    }
    if (!message.trim()) {
      setError('Message is required')
      return
    }
    if (!cron.trim()) {
      setError('Cron expression is required')
      return
    }

    onSubmit({
      name: name.trim(),
      agent,
      message: message.trim(),
      cron: cron.trim(),
      session_mode: sessionMode,
      enabled: true,
      source: 'hub',
      ...(loopEnabled
        ? {
            purpose: purpose.trim(),
            /* Deliberately `new Date`, not `hubDate`: `stopAt` is what the operator typed into a
             * `datetime-local` input, which is wall-clock time in *their* zone, not a Hub
             * timestamp. Reading it as UTC would move the stop condition by the machine's offset. */
            ...(stopAt ? { stop_at: new Date(stopAt).toISOString() } : {}),
            stop_when_queue_empties: stopWhenQueueEmpties,
          }
        : {}),
    })
  }

  const inputStyle: React.CSSProperties = {
    padding: '8px 12px',
    width: '100%',
    fontSize: 13,
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'var(--scrim)' }}
      onClick={onCancel}
    >
      <div
        className="elevation-overlay w-full max-w-lg max-h-[90vh] overflow-y-auto p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-job-title"
        style={{
          borderRadius: 'var(--radius-lg)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <h2 id="create-job-title" className="text-lg font-normal" style={{ color: 'var(--text)' }}>
            Create New Job
          </h2>
          <Button variant="ghost" size="icon-xs" onClick={onCancel} className="rounded-full" aria-label="Close">
            <Icon name="close" size={24} />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div>
            <label className="block mb-1.5 text-[11px] font-medium" style={{ color: 'var(--text-3)' }}>
              Job Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Daily Standup Report"
              className="control-field"
              style={inputStyle}
              disabled={isPending}
            />
          </div>

          {/* Agent */}
          <div>
            <label className="block mb-1.5 text-[11px] font-medium" style={{ color: 'var(--text-3)' }}>
              Target Agent
            </label>
            <div className="control-select-wrap">
              <select className="control-field" value={agent} onChange={(e) => setAgent(e.target.value)} style={inputStyle} disabled={isPending}>
                <option value="">Select an agent…</option>
                {agents?.map((a) => <option key={a.name} value={a.name}>@{a.name}</option>)}
              </select>
              <Icon name="expand_more" size={15} className="control-select-icon" />
            </div>
          </div>

          {/* Message */}
          <div>
            <label className="block mb-1.5 text-[11px] font-medium" style={{ color: 'var(--text-3)' }}>
              Message / Task
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="The message to send to the agent when this job runs…"
              rows={3}
              className="control-field h-24 resize-none"
              style={inputStyle}
              disabled={isPending}
            />
          </div>

          {/* Cron */}
          <div>
            <label className="block mb-1.5 text-[11px] font-medium" style={{ color: 'var(--text-3)' }}>
              Schedule (Cron Expression)
            </label>
            <input
              type="text"
              value={cron}
              onChange={(e) => setCron(e.target.value)}
              placeholder="0 9 * * *"
              className="control-field font-mono"
              style={{ ...inputStyle, fontFamily: "'JetBrains Mono', monospace" }}
              disabled={isPending}
            />
            <div className="flex flex-wrap gap-2 mt-2">
              {CRON_EXAMPLES.map((example) => (
                <button
                  key={example.value}
                  type="button"
                  onClick={() => setCron(example.value)}
                  data-active={cron === example.value ? 'true' : 'false'}
                  className="row-item aw-chip w-auto px-2.5 py-0.5 text-[11px] font-medium"
                  style={{ border: '1px solid var(--border)' }}
                >
                  {example.label}
                </button>
              ))}
            </div>
          </div>

          {/* Session Mode */}
          <div>
            <label className="block mb-1.5 text-[11px] font-medium" style={{ color: 'var(--text-3)' }}>
              Session Mode
            </label>
            <div className="flex gap-3">
              <label className="flex items-center gap-2 cursor-pointer rounded-md px-2 py-1.5" style={{ background: sessionMode === 'new' ? 'var(--row-selected)' : undefined }}>
                <input
                  type="radio"
                  name="sessionMode"
                  value="new"
                  checked={sessionMode === 'new'}
                  onChange={() => setSessionMode('new')}
                  disabled={isPending}
                  className="control-choice"
                />
                <span className="text-xs" style={{ color: 'var(--text)' }}>
                  New session each run
                </span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer rounded-md px-2 py-1.5" style={{ background: sessionMode === 'resume' ? 'var(--row-selected)' : undefined }}>
                <input
                  type="radio"
                  name="sessionMode"
                  value="resume"
                  checked={sessionMode === 'resume'}
                  onChange={() => setSessionMode('resume')}
                  disabled={isPending}
                  className="control-choice"
                />
                <span className="text-xs" style={{ color: 'var(--text)' }}>
                  Resume last session
                </span>
              </label>
            </div>
          </div>

          {/* Loop section — collapsed by default */}
          <div className="rounded-lg p-3" style={{ border: '1px solid var(--border)', background: loopEnabled ? 'var(--surface-2)' : undefined }}>
            <button
              type="button"
              onClick={() => setLoopEnabled(!loopEnabled)}
              className="flex items-center gap-1.5 text-[11px] font-medium"
              style={{ color: 'var(--text-3)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
              aria-expanded={loopEnabled}
            >
              <span style={{ display: 'flex', transform: loopEnabled ? 'rotate(180deg)' : undefined, transition: 'transform var(--dur-fast) var(--ease)' }}><Icon name="expand_more" size={16} /></span>
              Make this a loop
            </button>

            {loopEnabled && (
              <div className="space-y-3 mt-3">
                <div>
                  <label className="block mb-1.5 text-[11px] font-medium" style={{ color: 'var(--text-3)' }}>
                    Purpose
                  </label>
                  <textarea
                    value={purpose}
                    onChange={(e) => setPurpose(e.target.value)}
                    placeholder="What is this loop for?"
                    rows={2}
                    className="control-field resize-none"
                    style={inputStyle}
                    disabled={isPending}
                  />
                </div>

                <div>
                  <label className="block mb-1.5 text-[11px] font-medium" style={{ color: 'var(--text-3)' }}>
                    Stop at (optional)
                  </label>
                  <input
                    type="datetime-local"
                    value={stopAt}
                    onChange={(e) => setStopAt(e.target.value)}
                    className="control-field"
                    style={inputStyle}
                    disabled={isPending}
                  />
                </div>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={stopWhenQueueEmpties}
                    onChange={(e) => setStopWhenQueueEmpties(e.target.checked)}
                    disabled={isPending}
                    className="control-choice"
                  />
                  <span className="text-xs" style={{ color: 'var(--text)' }}>
                    Stop when the queue is empty
                  </span>
                </label>
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg" style={{ background: 'color-mix(in srgb, var(--red) 8%, transparent)' }}>
              <Icon name="error" size={18} style={{ color: 'var(--red)' }} />
              <span className="text-xs" style={{ color: 'var(--red)' }}>{error}</span>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
            <Button variant="outline" size="md" type="button" onClick={onCancel} disabled={isPending}>
              Cancel
            </Button>
            <Button variant="primary" size="md" type="submit" disabled={isPending}>
              {isPending ? (
                <>
                  <Icon name="sync" size={18} className="animate-spin" />
                  Creating…
                </>
              ) : (
                <>
                  <Icon name="add" size={18} />
                  Create Job
                </>
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
