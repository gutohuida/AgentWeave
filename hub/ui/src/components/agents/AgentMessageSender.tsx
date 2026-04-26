import { useState, useEffect } from 'react'
import { useConfigStore } from '@/store/configStore'
import { Icon } from '@/components/common/Icon'

interface AgentMessageSenderProps {
  agent: string
  existingSessionId?: string
  runner?: string
}

interface Session {
  id: string
  type: string
  path: string
}

export function AgentMessageSender({ agent, existingSessionId, runner }: AgentMessageSenderProps) {
  const { apiKey } = useConfigStore()
  const [message, setMessage] = useState('')
  const [sessionMode, setSessionMode] = useState<'new' | 'resume'>('new')
  const [selectedSessionId, setSelectedSessionId] = useState('')
  const [sessions, setSessions] = useState<Session[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [result, setResult] = useState<{success: boolean; message: string} | null>(null)

  useEffect(() => {
    fetchSessions()
  }, [agent])

  useEffect(() => {
    if (existingSessionId) {
      setSelectedSessionId(existingSessionId)
      setSessionMode('resume')
    }
  }, [existingSessionId])

  const fetchSessions = async () => {
    if (!apiKey) return

    setIsLoading(true)
    try {
      const response = await fetch(`/api/v1/agent/sessions/${agent}`, {
        headers: {
          'Authorization': `Bearer ${apiKey}`
        }
      })

      if (response.ok) {
        const data = await response.json()
        setSessions(data.sessions || [])
      }
    } catch (err) {
      console.error('Failed to fetch sessions:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSend = async () => {
    if (!message.trim() || !apiKey) return

    setIsSending(true)
    setResult(null)

    try {
      const response = await fetch('/api/v1/agent/trigger', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify({
          agent,
          message: message.trim(),
          session_mode: sessionMode,
          session_id: sessionMode === 'resume' ? selectedSessionId : undefined
        })
      })

      const data = await response.json()

      if (response.ok) {
        setResult({ success: true, message: data.message || 'Message queued for agent' })
        setMessage('')
      } else {
        setResult({ success: false, message: data.detail || 'Failed to start agent' })
      }
    } catch (err) {
      setResult({ success: false, message: 'Network error' })
    } finally {
      setIsSending(false)
    }
  }

  const hasSessions = sessions.length > 0 || existingSessionId

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
    <div className="p-4 space-y-4" style={{ background: 'var(--surface)' }}>
      <h3 className="text-sm font-medium" style={{ color: 'var(--text-3)' }}>
        Send Message to {agent}
      </h3>

      {/* Manual agent info */}
      {runner === 'manual' && (
        <div
          className="p-3 rounded-lg text-xs"
          style={{
            background: 'rgba(161,161,170,0.08)',
            color: 'var(--text-3)',
            border: '1px solid var(--border)',
          }}
        >
          <Icon name="info" size={16} className="inline-block mr-1" />
          This is a manual agent (human-operated). The message will be queued but no automation
          will run it — open the agent manually and check its AgentWeave inbox.
        </div>
      )}

      {/* Proxy agent warning */}
      {runner === 'claude_proxy' && (
        <div
          className="p-3 rounded-lg text-xs"
          style={{
            background: 'rgba(245,158,11,0.06)',
            color: 'var(--amber)',
            border: '1px solid rgba(245,158,11,0.2)',
          }}
        >
          <Icon name="warning" size={16} className="inline-block mr-1" />
          This is a proxy agent (runs via Claude CLI with custom env vars).
          Triggering it requires your watchdog to be running with the appropriate API key exported
          (e.g., <code>export MINIMAX_API_KEY=...</code> before <code>agentweave start</code>).
        </div>
      )}

      {/* Session Mode Selection */}
      <div className="space-y-2">
        <label className="text-xs font-medium" style={{ color: 'var(--text-3)' }}>
          Session Mode
        </label>
        <div className="flex gap-2">
          <button
            onClick={() => setSessionMode('new')}
            className="px-4 py-2 rounded-lg text-[13px] font-medium transition-colors"
            style={sessionMode === 'new'
              ? { background: 'var(--blue)', color: '#fff' }
              : { background: 'var(--surface-2)', color: 'var(--text-3)' }
            }
          >
            New Session
          </button>
          <button
            onClick={() => setSessionMode('resume')}
            disabled={!hasSessions}
            className="px-4 py-2 rounded-lg text-[13px] font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={sessionMode === 'resume'
              ? { background: 'var(--blue)', color: '#fff' }
              : { background: 'var(--surface-2)', color: 'var(--text-3)' }
            }
          >
            Resume Session
          </button>
        </div>
      </div>

      {/* Session Selection */}
      {sessionMode === 'resume' && (
        <div className="space-y-2">
          <label className="text-xs font-medium" style={{ color: 'var(--text-3)' }}>
            Select Session
          </label>
          {isLoading ? (
            <div className="text-sm" style={{ color: 'var(--text-3)' }}>Loading sessions...</div>
          ) : hasSessions ? (
            <select
              value={selectedSessionId}
              onChange={(e) => setSelectedSessionId(e.target.value)}
              style={inputStyle}
            >
              {existingSessionId && (
                <option value={existingSessionId}>
                  Current: {existingSessionId.slice(0, 16)}…
                </option>
              )}
              {sessions.map((session) => (
                <option key={session.id} value={session.id}>
                  {session.id.slice(0, 32)}{session.id.length > 32 ? '…' : ''}
                </option>
              ))}
            </select>
          ) : (
            <div className="text-sm" style={{ color: 'var(--red)' }}>
              No available sessions. Start a new session first.
            </div>
          )}
        </div>
      )}

      {/* Message Input */}
      <div className="space-y-2">
        <label className="text-xs font-medium" style={{ color: 'var(--text-3)' }}>
          Message
        </label>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={`Enter message for ${agent}...`}
          rows={4}
          className="resize-none"
          style={inputStyle}
        />
      </div>

      {/* Send Button */}
      <button
        onClick={handleSend}
        disabled={!message.trim() || isSending || (sessionMode === 'resume' && !selectedSessionId)}
        className="w-full px-4 py-3 rounded-lg text-[13px] font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        style={{
          background: message.trim() && !isSending ? 'var(--blue)' : 'var(--surface-2)',
          color: message.trim() && !isSending ? '#fff' : 'var(--text-3)',
        }}
      >
        {isSending ? 'Starting Agent...' : `Send to ${agent}`}
      </button>

      {/* Result */}
      {result && (
        <div
          className="p-3 rounded-lg text-sm"
          style={{
            background: result.success ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
            color: result.success ? 'var(--green)' : 'var(--red)',
          }}
        >
          {result.message}
        </div>
      )}

      {/* Instructions */}
      <div className="text-xs p-3 rounded-lg" style={{ background: 'var(--surface-2)', color: 'var(--text-3)' }}>
        <p className="text-xs font-medium mb-1">How it works:</p>
        <ul className="list-disc list-inside space-y-1 opacity-80">
          <li>New Session: Starts the agent with a fresh context</li>
          <li>Resume Session: Continues from the selected session ID</li>
          <li>Output will appear in the agent's output panel above</li>
        </ul>
      </div>
    </div>
  )
}
