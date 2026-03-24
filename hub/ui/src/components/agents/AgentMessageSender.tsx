import { useState, useEffect } from 'react'
import { useConfigStore } from '@/store/configStore'

interface AgentMessageSenderProps {
  agent: string
  existingSessionId?: string
}

interface Session {
  id: string
  type: string
  path: string
}

export function AgentMessageSender({ agent, existingSessionId }: AgentMessageSenderProps) {
  const { apiKey } = useConfigStore()
  const [message, setMessage] = useState('')
  const [sessionMode, setSessionMode] = useState<'new' | 'resume'>('new')
  const [selectedSessionId, setSelectedSessionId] = useState('')
  const [sessions, setSessions] = useState<Session[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [result, setResult] = useState<{success: boolean; message: string} | null>(null)

  // Fetch available sessions when component mounts or agent changes
  useEffect(() => {
    fetchSessions()
  }, [agent])

  // Update selected session when existingSessionId changes
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

  return (
    <div className="p-4 space-y-4" style={{ background: 'var(--surface-low)' }}>
      <h3 className="m3-title-medium" style={{ color: 'var(--on-sv)' }}>
        Send Message to {agent}
      </h3>

      {/* Session Mode Selection */}
      <div className="space-y-2">
        <label className="m3-label-medium" style={{ color: 'var(--on-sv)' }}>
          Session Mode
        </label>
        <div className="flex gap-2">
          <button
            onClick={() => setSessionMode('new')}
            className={`px-4 py-2 rounded-lg m3-label-large transition-colors ${
              sessionMode === 'new'
                ? 'bg-primary text-primary-foreground'
                : 'bg-surface-high text-on-sv hover:bg-surface-highest'
            }`}
            style={sessionMode === 'new' ? { background: 'var(--primary)', color: 'var(--primary-foreground)' } : {}}
          >
            New Session
          </button>
          <button
            onClick={() => setSessionMode('resume')}
            disabled={!hasSessions}
            className={`px-4 py-2 rounded-lg m3-label-large transition-colors ${
              sessionMode === 'resume'
                ? 'bg-primary text-primary-foreground'
                : 'bg-surface-high text-on-sv hover:bg-surface-highest'
            } ${!hasSessions ? 'opacity-50 cursor-not-allowed' : ''}`}
            style={sessionMode === 'resume' ? { background: 'var(--primary)', color: 'var(--primary-foreground)' } : {}}
          >
            Resume Session
          </button>
        </div>
      </div>

      {/* Session Selection (only for resume mode) */}
      {sessionMode === 'resume' && (
        <div className="space-y-2">
          <label className="m3-label-medium" style={{ color: 'var(--on-sv)' }}>
            Select Session
          </label>
          {isLoading ? (
            <div className="text-sm" style={{ color: 'var(--on-sv)' }}>Loading sessions...</div>
          ) : hasSessions ? (
            <select
              value={selectedSessionId}
              onChange={(e) => setSelectedSessionId(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-surface-high border m3-body-medium"
              style={{ 
                background: 'var(--surface-high)', 
                borderColor: 'var(--outline-variant)',
                color: 'var(--on-sv)'
              }}
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
            <div className="text-sm" style={{ color: 'var(--error)' }}>
              No available sessions. Start a new session first.
            </div>
          )}
        </div>
      )}

      {/* Message Input */}
      <div className="space-y-2">
        <label className="m3-label-medium" style={{ color: 'var(--on-sv)' }}>
          Message
        </label>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={`Enter message for ${agent}...`}
          rows={4}
          className="w-full px-3 py-2 rounded-lg bg-surface-high border m3-body-medium resize-none"
          style={{ 
            background: 'var(--surface-high)', 
            borderColor: 'var(--outline-variant)',
            color: 'var(--on-sv)'
          }}
        />
      </div>

      {/* Send Button */}
      <button
        onClick={handleSend}
        disabled={!message.trim() || isSending || (sessionMode === 'resume' && !selectedSessionId)}
        className="w-full px-4 py-3 rounded-lg m3-label-large transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ 
          background: message.trim() && !isSending ? 'var(--primary)' : 'var(--surface-high)',
          color: message.trim() && !isSending ? 'var(--primary-foreground)' : 'var(--on-sv)'
        }}
      >
        {isSending ? 'Starting Agent...' : `Send to ${agent}`}
      </button>

      {/* Result */}
      {result && (
        <div
          className="p-3 rounded-lg m3-body-medium"
          style={
            result.success
              ? { background: 'var(--s-cont)', color: 'var(--on-s-cont)' }
              : { background: 'var(--error-cont)', color: 'var(--on-error-cont)' }
          }
        >
          {result.message}
        </div>
      )}

      {/* Instructions */}
      <div className="text-xs p-3 rounded-lg" style={{ background: 'var(--surface-high)', color: 'var(--on-sv)' }}>
        <p className="m3-label-medium mb-1">How it works:</p>
        <ul className="list-disc list-inside space-y-1 opacity-80">
          <li>New Session: Starts the agent with a fresh context</li>
          <li>Resume Session: Continues from the selected session ID</li>
          <li>Output will appear in the agent's output panel above</li>
        </ul>
      </div>
    </div>
  )
}
