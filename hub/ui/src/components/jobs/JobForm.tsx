import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { useAgents } from '@/api/agents'
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
    })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0, 0, 0, 0.5)' }}
      onClick={onCancel}
    >
      <div
        className="m3-dialog w-full max-w-lg max-h-[90vh] overflow-y-auto p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <h2 className="m3-headline-small" style={{ color: 'var(--foreground)' }}>
            Create New Job
          </h2>
          <button
            onClick={onCancel}
            className="p-1 rounded-full transition-colors hover:bg-black/5"
            style={{ color: 'var(--on-sv)' }}
          >
            <Icon name="close" size={24} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div>
            <label className="m3-label-small block mb-1.5" style={{ color: 'var(--on-sv)' }}>
              Job Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Daily Standup Report"
              className="m3-input w-full"
              disabled={isPending}
            />
          </div>

          {/* Agent */}
          <div>
            <label className="m3-label-small block mb-1.5" style={{ color: 'var(--on-sv)' }}>
              Target Agent
            </label>
            <select
              value={agent}
              onChange={(e) => setAgent(e.target.value)}
              className="m3-input w-full"
              disabled={isPending}
            >
              <option value="">Select an agent…</option>
              {agents?.map((a) => (
                <option key={a.name} value={a.name}>
                  @{a.name}
                </option>
              ))}
            </select>
          </div>

          {/* Message */}
          <div>
            <label className="m3-label-small block mb-1.5" style={{ color: 'var(--on-sv)' }}>
              Message / Task
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="The message to send to the agent when this job runs…"
              className="m3-input w-full h-24 resize-none"
              disabled={isPending}
            />
          </div>

          {/* Cron */}
          <div>
            <label className="m3-label-small block mb-1.5" style={{ color: 'var(--on-sv)' }}>
              Schedule (Cron Expression)
            </label>
            <input
              type="text"
              value={cron}
              onChange={(e) => setCron(e.target.value)}
              placeholder="0 9 * * *"
              className="m3-input w-full font-mono"
              disabled={isPending}
            />
            <div className="flex flex-wrap gap-2 mt-2">
              {CRON_EXAMPLES.map((example) => (
                <button
                  key={example.value}
                  type="button"
                  onClick={() => setCron(example.value)}
                  className="m3-chip"
                  style={{
                    background: cron === example.value ? 'var(--p-cont)' : 'var(--surface-high)',
                    color: cron === example.value ? 'var(--on-p-cont)' : 'var(--foreground)'
                  }}
                >
                  {example.label}
                </button>
              ))}
            </div>
          </div>

          {/* Session Mode */}
          <div>
            <label className="m3-label-small block mb-1.5" style={{ color: 'var(--on-sv)' }}>
              Session Mode
            </label>
            <div className="flex gap-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="sessionMode"
                  value="new"
                  checked={sessionMode === 'new'}
                  onChange={() => setSessionMode('new')}
                  className="m3-radio"
                />
                <span className="m3-body-small" style={{ color: 'var(--foreground)' }}>
                  New session each run
                </span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="sessionMode"
                  value="resume"
                  checked={sessionMode === 'resume'}
                  onChange={() => setSessionMode('resume')}
                  className="m3-radio"
                />
                <span className="m3-body-small" style={{ color: 'var(--foreground)' }}>
                  Resume last session
                </span>
              </label>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg" style={{ background: 'var(--error-cont)' }}>
              <Icon name="error" size={18} style={{ color: 'var(--destructive)' }} />
              <span className="m3-body-small" style={{ color: 'var(--destructive)' }}>{error}</span>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-4" style={{ borderTop: '1px solid var(--outline-variant)' }}>
            <button
              type="button"
              onClick={onCancel}
              disabled={isPending}
              className="m3-btn m3-btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="m3-btn m3-btn-primary flex items-center gap-2"
            >
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
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
