import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Icon } from '@/components/common/Icon'
import { fetchWithAuth } from '@/api/client'
import { useAgentOutput, useAgentSessions } from '@/api/agents'
import { SharedStreamRenderer } from '@/components/stream/SharedStreamRenderer'

interface ChatAgent {
  name: string
  status?: string
}

interface TriggerResponse {
  message?: string
  execution_confidence?: string
}

const QUEUED_START_TIMEOUT_MS = 15_000

interface SpecChatPaneProps {
  agents: ChatAgent[] | undefined
  selectedAgent: string
  onSelectedAgentChange: (name: string) => void
  /** Owned by SpecPage because manifest repair shares the same one-shot flag. */
  startNewSession: boolean
  onStartNewSessionChange: (value: boolean) => void
  apiKey: string | null
}

export function SpecChatPane({
  agents,
  selectedAgent,
  onSelectedAgentChange,
  startNewSession,
  onStartNewSessionChange,
  apiKey,
}: SpecChatPaneProps) {
  const queryClient = useQueryClient()
  const agent = agents?.find((a) => a.name === selectedAgent)
  const isRunning = agent?.status === 'running'

  // Only used to tell the user whether the next message continues something.
  // The session id itself is never sent — the watchdog resolves it.
  const { data: sessionData } = useAgentSessions(selectedAgent || null)
  const hasSavedSession = (sessionData?.sessions?.length ?? 0) > 0

  const { lines } = useAgentOutput(selectedAgent || null)
  const filteredLines = lines

  const bottomRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [filteredLines.length])

  const [message, setMessage] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [triggerState, setTriggerState] = useState<'idle' | 'queued' | 'running'>('idle')
  const [sendError, setSendError] = useState<string | null>(null)
  const [sendWarning, setSendWarning] = useState<string | null>(null)

  useEffect(() => {
    if (triggerState === 'queued' && isRunning) setTriggerState('running')
    if (triggerState === 'running' && !isRunning) setTriggerState('idle')
  }, [triggerState, isRunning])

  useEffect(() => {
    if (triggerState !== 'queued') return
    const timeoutId = window.setTimeout(() => {
      setTriggerState((current) => (current === 'queued' ? 'idle' : current))
      setSendWarning(
        'Message is queued, but the agent did not start within 15 seconds. Check the watchdog.'
      )
    }, QUEUED_START_TIMEOUT_MS)
    return () => window.clearTimeout(timeoutId)
  }, [triggerState])

  useEffect(() => {
    setTriggerState('idle')
    setSendError(null)
    setSendWarning(null)
  }, [selectedAgent])

  const inputDisabled = !selectedAgent || isRunning || isSending || triggerState !== 'idle'

  const handleSend = async () => {
    if (!message.trim() || !apiKey || !selectedAgent) return
    setIsSending(true)
    setSendError(null)
    setSendWarning(null)
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 15000)
    try {
      // Use the configured Hub URL. A relative URL targets the Vite dev
      // server when the UI runs on port 5173, causing the request to hang.
      const res = await fetchWithAuth('/api/v1/agent/trigger', {
        method: 'POST',
        // `resume` with no session_id makes the trigger endpoint emit no
        // session tag, so the watchdog falls back to the agent's last saved
        // session (or starts a new one if there is none). Resolving the id
        // here would duplicate that rule in a second place.
        body: JSON.stringify({
          agent: selectedAgent,
          message: message.trim(),
          session_mode: startNewSession ? 'new' : 'resume',
        }),
        signal: controller.signal,
      })
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }
      const triggerResponse = (await res.json()) as TriggerResponse
      // The trigger response confirms queueing, but the status/output stream
      // may arrive later. Refresh immediately so the running state is not
      // dependent on an agent_heartbeat SSE event.
      if (
        triggerResponse.execution_confidence &&
        triggerResponse.execution_confidence !== 'queued_watchdog_healthy'
      ) {
        setTriggerState('idle')
        setSendWarning(
          triggerResponse.message ||
            'Message queued, but automatic execution could not be confirmed.'
        )
      } else {
        setTriggerState('queued')
      }
      // Consumed — the next message resumes the session this one creates.
      onStartNewSessionChange(false)
      await queryClient.invalidateQueries({ queryKey: ['agents'] })
      await queryClient.refetchQueries({ queryKey: ['agents'], type: 'active' })
      setMessage('')
    } catch (err) {
      console.error('Failed to send message:', err)
      setSendError(
        err instanceof DOMException && err.name === 'AbortError'
          ? 'Request timed out; check the watchdog and try again'
          : 'Failed to send message'
      )
    } finally {
      window.clearTimeout(timeoutId)
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
    <div className="flex flex-col h-full min-h-0" style={{ background: 'var(--bg)' }}>
      {/* Agent selector header */}
      <div
        className="flex items-center gap-2 px-3 py-2.5 shrink-0 border-b"
        style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
      >
        <select
          value={selectedAgent}
          onChange={(e) => onSelectedAgentChange(e.target.value)}
          disabled={!agents || agents.length === 0}
          className="flex-1 px-2 py-1 rounded-lg text-xs border"
          style={{
            background: 'var(--surface)',
            borderColor: 'var(--border)',
            color: 'var(--text-3)',
            outline: 'none',
          }}
        >
          {(!agents || agents.length === 0) && <option value="">No agents</option>}
          {agents?.map((a) => (
            <option key={a.name} value={a.name}>
              {a.name}
            </option>
          ))}
        </select>
        <button
          onClick={() => onStartNewSessionChange(!startNewSession)}
          disabled={!selectedAgent}
          title={
            startNewSession
              ? 'Next message starts a new session — click to keep the current one'
              : 'Start a new session with the next message'
          }
          aria-pressed={startNewSession}
          aria-label="Start a new session"
          className="px-1.5 py-1 rounded-md transition-colors disabled:opacity-50"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            background: startNewSession ? 'var(--blue)' : 'var(--surface)',
            border: '1px solid var(--border)',
            color: startNewSession ? '#fff' : 'var(--text-3)',
            cursor: selectedAgent ? 'pointer' : 'not-allowed',
            borderRadius: 'var(--radius-sm)',
          }}
        >
          <Icon name="restart_alt" size={14} />
        </button>
        {agent && (
          <span
            className="flex items-center gap-1.5"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              borderRadius: 'var(--radius-sm)',
              padding: '2px 8px',
              fontSize: 11,
              fontWeight: 500,
              background: isRunning ? 'rgba(34,197,94,0.1)' : 'var(--surface-3)',
              color: isRunning ? 'var(--green)' : 'var(--text-3)',
            }}
          >
            {isRunning && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />}
            {agent.status}
          </span>
        )}
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-3 space-y-0.5" style={{ background: 'var(--bg)' }}>
        {filteredLines.length === 0 ? (
          <p
            className="font-mono text-xs italic"
            style={{ color: 'var(--text-3)', fontFamily: "'JetBrains Mono', monospace" }}
          >
            Waiting for output…
          </p>
        ) : (
          <SharedStreamRenderer lines={filteredLines} showDiagnostics={false} />
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input footer */}
      <div
        className="shrink-0 border-t px-3 py-2 flex flex-col gap-2"
        style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
      >
        {sendError && <span style={{ fontSize: 11, color: 'var(--red)' }}>{sendError}</span>}
        {sendWarning && (
          <span role="status" style={{ fontSize: 11, color: 'var(--amber)' }}>
            {sendWarning}
          </span>
        )}
        {selectedAgent && (
          <span
            data-testid="session-continuity"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              fontSize: 11,
              color: startNewSession ? 'var(--blue)' : 'var(--text-3)',
            }}
          >
            <Icon name={startNewSession ? 'restart_alt' : hasSavedSession ? 'link' : 'add'} size={12} />
            {startNewSession
              ? 'Next message starts a new session'
              : hasSavedSession
                ? `Continuing ${selectedAgent}'s most recent session`
                : 'No session yet — the next message starts one'}
          </span>
        )}
        <div className="flex gap-2">
          {triggerState !== 'idle' && (
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
              {triggerState === 'queued' ? 'Message queued…' : `${selectedAgent} is responding…`}
            </span>
          )}
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              !selectedAgent
                ? 'Select an agent…'
                : isRunning
                  ? `${selectedAgent} is responding…`
                  : `Message ${selectedAgent}…`
            }
            rows={1}
            disabled={inputDisabled}
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
            disabled={!message.trim() || inputDisabled}
            className="px-3 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: message.trim() && !inputDisabled ? 'var(--blue)' : 'var(--surface)',
              color: message.trim() && !inputDisabled ? '#fff' : 'var(--text-3)',
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
