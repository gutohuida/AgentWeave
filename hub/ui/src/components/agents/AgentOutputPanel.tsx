import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { useCopy } from '@/hooks/useCopy'
import { AgentSummary, useAgentOutput, useAgentSessions } from '@/api/agents'
import { useConfigStore } from '@/store/configStore'

interface AgentOutputPanelProps {
  agent: AgentSummary
}

const NEW_SESSION_VALUE = '__new__'

export function AgentOutputPanel({ agent }: AgentOutputPanelProps) {
  const { lines, isLoading } = useAgentOutput(agent.name)
  const bottomRef    = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoscroll, setAutoscroll] = useState(true)
  const { copied, copy } = useCopy(2000)

  // Send message state
  const { apiKey } = useConfigStore()
  const [message, setMessage] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [selectedSessionId, setSelectedSessionId] = useState<string>('')
  const { data: sessionsData } = useAgentSessions(agent.name)
  const sessions = sessionsData?.sessions || []

  // Auto-select most recent session
  useEffect(() => {
    if (sessions.length > 0 && !selectedSessionId) {
      setSelectedSessionId(sessions[0].id)
    }
  }, [sessions, selectedSessionId])

  useEffect(() => {
    if (autoscroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [lines, autoscroll])

  function handleScroll() {
    const el = containerRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    setAutoscroll(atBottom)
  }

  const sessionId = [...lines].reverse().find((l) => l.session_id)?.session_id
  const isRunning = agent.status === 'running'

  const handleSend = async () => {
    if (!message.trim() || !apiKey) return
    setIsSending(true)
    try {
      const isNew = !selectedSessionId || selectedSessionId === NEW_SESSION_VALUE
      await fetch('/api/v1/agent/trigger', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          agent: agent.name,
          message: message.trim(),
          session_mode: isNew ? 'new' : 'resume',
          session_id: isNew ? undefined : selectedSessionId,
        }),
      })
      setMessage('')
    } catch (err) {
      console.error('Failed to send message:', err)
    } finally {
      setIsSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--background)' }}>
      {/* Header bar */}
      <div
        className="flex items-center gap-2 px-4 py-2.5 shrink-0 border-b"
        style={{ background: 'var(--surface-high)', borderColor: 'var(--outline-variant)' }}
      >
        <span className="m3-title-small" style={{ color: 'var(--foreground)' }}>{agent.name}</span>

        {/* Session ID chip */}
        {sessionId && (
          <button
            onClick={() => copy(sessionId)}
            title="Click to copy full session ID"
            className="m3-chip m3-label-small flex items-center gap-1 transition-colors cursor-pointer"
            style={copied
              ? { background: 'var(--p-cont)', color: 'var(--on-p-cont)' }
              : { background: 'var(--s-cont)', color: 'var(--on-s-cont)' }
            }
          >
            <Icon name={copied ? 'check' : 'content_copy'} size={12} />
            {copied ? 'copied' : `session: ${sessionId.slice(0, 12)}…`}
          </button>
        )}

        {/* Status chip */}
        <span
          className="m3-chip m3-label-small flex items-center gap-1.5"
          style={isRunning
            ? { background: 'var(--p-cont)', color: 'var(--on-p-cont)' }
            : { background: 'var(--surface-highest)', color: 'var(--on-sv)' }
          }
        >
          {isRunning && (
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
          )}
          {agent.status}
        </span>

        {/* Autoscroll toggle */}
        <button
          onClick={() => {
            setAutoscroll((v) => {
              if (!v && bottomRef.current) {
                bottomRef.current.scrollIntoView({ behavior: 'smooth' })
              }
              return !v
            })
          }}
          className="ml-auto m3-chip m3-label-small transition-colors"
          style={{ background: 'var(--s-cont)', color: 'var(--on-s-cont)', cursor: 'pointer' }}
        >
          {autoscroll ? 'Pause scroll' : 'Resume scroll'}
        </button>
      </div>

      {/* Output body — darkest surface for terminal feel */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 space-y-0.5"
        style={{ background: 'var(--surface-lowest)' }}
      >
        {isLoading ? (
          <p className="font-mono m3-body-small italic" style={{ color: 'var(--on-sv)' }}>Loading output…</p>
        ) : lines.length === 0 ? (
          <p className="font-mono m3-body-small italic" style={{ color: 'var(--on-sv)' }}>Waiting for output…</p>
        ) : (
          lines.map((line, i) => (
            <div
              key={line.id ?? i}
              className="font-mono m3-body-small leading-5 whitespace-pre-wrap break-all"
              style={{ color: 'var(--foreground)' }}
            >
              {line.content}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Send message footer */}
      <div
        className="shrink-0 border-t px-3 py-2 flex flex-col gap-2"
        style={{ background: 'var(--surface-high)', borderColor: 'var(--outline-variant)' }}
      >
        {/* Session selector */}
        <select
          value={selectedSessionId}
          onChange={(e) => setSelectedSessionId(e.target.value)}
          className="w-full px-2 py-1 rounded-lg m3-body-small border"
          style={{
            background: 'var(--surface)',
            borderColor: 'var(--outline-variant)',
            color: 'var(--on-sv)',
          }}
        >
          <option value={NEW_SESSION_VALUE}>New session</option>
          {sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.id.slice(0, 28)}{s.id.length > 28 ? '…' : ''}
              {s.last_active && ` (${new Date(s.last_active).toLocaleDateString()})`}
            </option>
          ))}
        </select>

        {/* Input row */}
        <div className="flex gap-2">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isRunning ? `${agent.name} is responding…` : `Message ${agent.name}…`}
            rows={1}
            disabled={isRunning || isSending}
            className="flex-1 px-3 py-2 rounded-lg m3-body-small resize-none border disabled:opacity-50"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--outline-variant)',
              color: 'var(--on-sv)',
              minHeight: '36px',
              maxHeight: '96px',
            }}
            onInput={(e) => {
              const t = e.target as HTMLTextAreaElement
              t.style.height = 'auto'
              t.style.height = `${Math.min(t.scrollHeight, 96)}px`
            }}
          />
          <button
            onClick={handleSend}
            disabled={!message.trim() || isSending || isRunning}
            className="px-3 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: message.trim() && !isSending && !isRunning ? 'var(--primary)' : 'var(--surface)',
              color: message.trim() && !isSending && !isRunning ? 'var(--primary-foreground)' : 'var(--on-sv)',
            }}
          >
            <Icon name="send" size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}
