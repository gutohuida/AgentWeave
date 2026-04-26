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

  const inputStyle: React.CSSProperties = {
    background: 'var(--surface-2)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm)',
    color: 'var(--text)',
    padding: '8px 12px',
    width: '100%',
    fontSize: 13,
    outline: 'none',
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'var(--scrim)' }}
      onClick={onCancel}
    >
      <div
        className="w-full max-w-lg max-h-[90vh] overflow-y-auto p-6"
        style={{
          background: 'var(--surface)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-normal" style={{ color: 'var(--text)' }}>
            Create New Job
          </h2>
          <button
            onClick={onCancel}
            className="p-1 rounded-full transition-colors"
            style={{ color: 'var(--text-3)' }}
          >
            <Icon name="close" size={24} />
          </button>
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
              style={inputStyle}
              disabled={isPending}
            />
          </div>

          {/* Agent */}
          <div>
            <label className="block mb-1.5 text-[11px] font-medium" style={{ color: 'var(--text-3)' }}>
              Target Agent
            </label>
            <select
              value={agent}
              onChange={(e) => setAgent(e.target.value)}
              style={inputStyle}
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
            <label className="block mb-1.5 text-[11px] font-medium" style={{ color: 'var(--text-3)' }}>
              Message / Task
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="The message to send to the agent when this job runs…"
              rows={3}
              className="h-24 resize-none"
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
              className="font-mono"
              style={{ ...inputStyle, fontFamily: "'JetBrains Mono', monospace" }}
              disabled={isPending}
            />
            <div className="flex flex-wrap gap-2 mt-2">
              {CRON_EXAMPLES.map((example) => (
                <button
                  key={example.value}
                  type="button"
                  onClick={() => setCron(example.value)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    borderRadius: 'var(--radius-sm)',
                    padding: '3px 10px',
                    fontSize: 11,
                    fontWeight: 500,
                    background: cron === example.value ? 'var(--surface-3)' : 'var(--surface-2)',
                    color: cron === example.value ? 'var(--text)' : 'var(--text-2)',
                    border: '1px solid var(--border)',
                    cursor: 'pointer',
                  }}
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
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="sessionMode"
                  value="new"
                  checked={sessionMode === 'new'}
                  onChange={() => setSessionMode('new')}
                  disabled={isPending}
                />
                <span className="text-xs" style={{ color: 'var(--text)' }}>
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
                  disabled={isPending}
                />
                <span className="text-xs" style={{ color: 'var(--text)' }}>
                  Resume last session
                </span>
              </label>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg" style={{ background: 'rgba(239,68,68,0.08)' }}>
              <Icon name="error" size={18} style={{ color: 'var(--red)' }} />
              <span className="text-xs" style={{ color: 'var(--red)' }}>{error}</span>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
            <button
              type="button"
              onClick={onCancel}
              disabled={isPending}
              style={{
                ...inputStyle,
                width: 'auto',
                padding: '0 16px',
                height: 36,
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="flex items-center gap-2"
              style={{
                ...inputStyle,
                width: 'auto',
                padding: '0 16px',
                height: 36,
                background: 'var(--blue)',
                color: '#fff',
                borderColor: 'transparent',
                cursor: 'pointer',
              }}
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
