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

  const { apiKey } = useConfigStore()
  const [message, setMessage] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [selectedSessionId, setSelectedSessionId] = useState<string>('')
  const { data: sessionsData } = useAgentSessions(agent.name)
  const sessions = sessionsData?.sessions || []

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
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--bg)' }}>
      {/* Header bar */}
      <div
        className="flex items-center gap-2 px-4 py-2.5 shrink-0 border-b"
        style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
      >
        <span className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>{agent.name}</span>

        {/* Session ID chip */}
        {sessionId && (
          <button
            onClick={() => copy(sessionId)}
            title="Click to copy full session ID"
            className="flex items-center gap-1 transition-colors cursor-pointer"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              borderRadius: 'var(--radius-sm)',
              padding: '2px 8px',
              fontSize: 11,
              fontWeight: 500,
              background: copied ? 'var(--surface-3)' : 'rgba(168,85,247,0.1)',
              color: copied ? 'var(--text)' : 'var(--purple)',
            }}
          >
            <Icon name={copied ? 'check' : 'content_copy'} size={12} />
            {copied ? 'copied' : `session: ${sessionId.slice(0, 12)}…`}
          </button>
        )}

        {/* Status chip */}
        <span
          className="flex items-center gap-1.5"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            borderRadius: 'var(--radius-sm)',
            padding: '2px 8px',
            fontSize: 11,
            fontWeight: 500,
            background: isRunning ? 'rgba(34,197,94,0.1)' : 'var(--surface-3)',
            color: isRunning ? 'var(--green)' : 'var(--text-3)',
          }}
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
          className="ml-auto transition-colors"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            borderRadius: 'var(--radius-sm)',
            padding: '2px 8px',
            fontSize: 11,
            fontWeight: 500,
            background: 'var(--surface-3)',
            color: 'var(--text-2)',
            cursor: 'pointer',
          }}
        >
          {autoscroll ? 'Pause scroll' : 'Resume scroll'}
        </button>
      </div>

      {/* Output body */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 space-y-0.5"
        style={{ background: 'var(--bg)' }}
      >
        {isLoading ? (
          <p className="font-mono text-xs italic" style={{ color: 'var(--text-3)', fontFamily: "'JetBrains Mono', monospace" }}>Loading output…</p>
        ) : lines.length === 0 ? (
          <p className="font-mono text-xs italic" style={{ color: 'var(--text-3)', fontFamily: "'JetBrains Mono', monospace" }}>Waiting for output…</p>
        ) : (
          lines.map((line, i) => (
            <div
              key={line.id ?? i}
              className="font-mono text-xs leading-5 whitespace-pre-wrap break-all"
              style={{ color: 'var(--text)', fontFamily: "'JetBrains Mono', monospace" }}
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
        style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
      >
        {/* Session selector */}
        <select
          value={selectedSessionId}
          onChange={(e) => setSelectedSessionId(e.target.value)}
          className="w-full px-2 py-1 rounded-lg text-xs border"
          style={{
            background: 'var(--surface)',
            borderColor: 'var(--border)',
            color: 'var(--text-3)',
            outline: 'none',
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
            className="flex-1 px-3 py-2 rounded-lg text-xs resize-none border disabled:opacity-50"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--border)',
              color: 'var(--text-3)',
              minHeight: '36px',
              maxHeight: '96px',
              outline: 'none',
              fontFamily: "'JetBrains Mono', monospace",
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
              background: message.trim() && !isSending && !isRunning ? 'var(--blue)' : 'var(--surface)',
              color: message.trim() && !isSending && !isRunning ? '#fff' : 'var(--text-3)',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            <Icon name="send" size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}
