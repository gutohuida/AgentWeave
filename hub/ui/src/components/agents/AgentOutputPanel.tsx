import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { useCopy } from '@/hooks/useCopy'
import { AgentSummary, useAgentOutput, useAgentSessions } from '@/api/agents'
import { useConfigStore } from '@/store/configStore'
import { SharedStreamRenderer } from '@/components/stream/SharedStreamRenderer'

interface AgentOutputPanelProps {
  agent: AgentSummary
}

const NEW_SESSION_VALUE = '__new__'
const HANDOFF_PROMPT = `Prepare a durable AgentWeave handoff before ending this session.

Invoke your aw-checkpoint skill with reason pre_handoff. Save the current intent, files modified,
decisions and rationale, blockers, exact next steps, and verification commands under
.agentweave/shared/checkpoints/. Stop after confirming the checkpoint path.`

const RESUME_HANDOFF_PREFIX = `Resume from the latest durable AgentWeave handoff.

Before doing anything else, find and read the newest checkpoint for your agent under
.agentweave/shared/checkpoints/, then read .agentweave/shared/context.md. Treat the checkpoint
as authoritative and continue from its Next Steps.

User request:`

type HandoffState = 'idle' | 'preparing' | 'ready'

interface PendingNewSession {
  knownSessionIds: Set<string>
  outputStartIndex: number
}

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
  const [handoffState, setHandoffState] = useState<HandoffState>('idle')
  const [sessionNotice, setSessionNotice] = useState<string | null>(null)
  const handoffOutputStartRef = useRef<number | null>(null)
  const handoffSawRunningRef = useRef(false)
  const pendingNewSessionRef = useRef<PendingNewSession | null>(null)
  const { data: sessionsData } = useAgentSessions(agent.name)
  const sessions = sessionsData?.sessions || []

  useEffect(() => {
    setSelectedSessionId('')
    setHandoffState('idle')
    setSessionNotice(null)
    handoffOutputStartRef.current = null
    handoffSawRunningRef.current = false
    pendingNewSessionRef.current = null
  }, [agent.name])

  useEffect(() => {
    if (sessions.length > 0 && !selectedSessionId) {
      setSelectedSessionId(sessions[0].id)
    }
  }, [sessions, selectedSessionId])

  useEffect(() => {
    const outputStart = handoffOutputStartRef.current
    if (handoffState !== 'preparing' || outputStart === null) return
    if (agent.status === 'running') {
      handoffSawRunningRef.current = true
      return
    }

    const completed = lines.slice(outputStart).some(
      (line) => line.kind === 'status' && line.payload?.phase === 'completed',
    )
    if (completed || handoffSawRunningRef.current) {
      handoffOutputStartRef.current = null
      handoffSawRunningRef.current = false
      setHandoffState('ready')
      setSessionNotice('Handoff ready — your next message starts fresh and resumes it')
    }
  }, [agent.status, handoffState, lines.length])

  useEffect(() => {
    const pending = pendingNewSessionRef.current
    if (!pending) return

    const outputSessionId = lines
      .slice(pending.outputStartIndex)
      .map((line) => line.session_id)
      .find((id): id is string => Boolean(id) && !pending.knownSessionIds.has(id as string))
    const listedSessionId = sessions.find((session) => !pending.knownSessionIds.has(session.id))?.id
    const newSessionId = outputSessionId || listedSessionId
    if (!newSessionId) return

    pendingNewSessionRef.current = null
    setSelectedSessionId(newSessionId)
    setSessionNotice(`Continuing new conversation ${newSessionId.slice(0, 12)}…`)
  }, [lines, sessions])

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
  const isBindingNewSession = pendingNewSessionRef.current !== null
  const handoffUnavailable = agent.pilot || agent.runner === 'manual'
  const interactionLocked =
    isRunning || isSending || handoffState === 'preparing' || isBindingNewSession
  const currentSessionId =
    selectedSessionId && selectedSessionId !== NEW_SESSION_VALUE
      ? selectedSessionId
      : undefined

  const postTrigger = async (
    triggerMessage: string,
    sessionMode: 'new' | 'resume',
    triggerSessionId?: string,
  ) => {
    const response = await fetch('/api/v1/agent/trigger', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        agent: agent.name,
        message: triggerMessage,
        session_mode: sessionMode,
        session_id: sessionMode === 'resume' ? triggerSessionId : undefined,
      }),
    })
    if (!response.ok) {
      throw new Error(`Trigger failed with status ${response.status}`)
    }
  }

  const handleHandoff = async () => {
    if (!apiKey || !currentSessionId || isRunning || isSending) return
    setIsSending(true)
    setHandoffState('preparing')
    setSessionNotice('Preparing durable handoff…')
    handoffOutputStartRef.current = lines.length
    handoffSawRunningRef.current = false
    try {
      await postTrigger(HANDOFF_PROMPT, 'resume', currentSessionId)
      setSelectedSessionId(NEW_SESSION_VALUE)
    } catch (err) {
      console.error('Failed to prepare handoff:', err)
      handoffOutputStartRef.current = null
      handoffSawRunningRef.current = false
      setHandoffState('idle')
      setSelectedSessionId(currentSessionId)
      setSessionNotice('Failed to prepare handoff')
    } finally {
      setIsSending(false)
    }
  }

  const handleSend = async () => {
    if (!message.trim() || !apiKey) return
    setIsSending(true)
    const isNew = !selectedSessionId || selectedSessionId === NEW_SESSION_VALUE
    const outgoingMessage =
      isNew && handoffState === 'ready'
        ? `${RESUME_HANDOFF_PREFIX}\n\n${message.trim()}`
        : message.trim()
    if (isNew) {
      pendingNewSessionRef.current = {
        knownSessionIds: new Set(sessions.map((session) => session.id)),
        outputStartIndex: lines.length,
      }
      setSessionNotice('Starting new conversation…')
    }
    try {
      await postTrigger(outgoingMessage, isNew ? 'new' : 'resume', selectedSessionId)
      setMessage('')
      if (isNew) setHandoffState('idle')
    } catch (err) {
      console.error('Failed to send message:', err)
      if (isNew) pendingNewSessionRef.current = null
      setSessionNotice('Failed to send message')
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
          <SharedStreamRenderer lines={lines} />
        )}
        <div ref={bottomRef} />
      </div>

      {/* Send message footer */}
      <div
        className="shrink-0 border-t px-3 py-2 flex flex-col gap-2"
        style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
      >
        {/* Session selector + durable handoff */}
        <div className="flex gap-2">
          <select
            value={selectedSessionId}
            aria-label="Conversation"
            disabled={interactionLocked}
            onChange={(e) => {
              setSelectedSessionId(e.target.value)
              setHandoffState('idle')
              setSessionNotice(null)
              handoffOutputStartRef.current = null
              handoffSawRunningRef.current = false
              pendingNewSessionRef.current = null
            }}
            className="flex-1 min-w-0 px-2 py-1 rounded-lg text-xs border"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--border)',
              color: 'var(--text-3)',
              outline: 'none',
            }}
          >
            <option value={NEW_SESSION_VALUE}>New conversation (start fresh)</option>
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.id.slice(0, 28)}{s.id.length > 28 ? '…' : ''}
                {s.last_active && ` (${new Date(s.last_active).toLocaleDateString()})`}
              </option>
            ))}
          </select>
          <button
            onClick={handleHandoff}
            disabled={
              !currentSessionId
              || interactionLocked
              || handoffState !== 'idle'
              || handoffUnavailable
            }
            title={
              handoffUnavailable
                ? 'Handoff requires an automatically managed runner'
                : 'Save a durable checkpoint, then resume it in a fresh conversation'
            }
            className="shrink-0 px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--border)',
              color: 'var(--text-2)',
            }}
          >
            {handoffState === 'preparing'
              ? 'Preparing…'
              : handoffState === 'ready'
                ? 'Ready'
                : 'Handoff'}
          </button>
        </div>

        <span
          data-testid="session-continuity"
          className="flex items-center gap-1"
          style={{
            fontSize: 11,
            color:
              handoffState === 'ready' || selectedSessionId === NEW_SESSION_VALUE
                ? 'var(--blue)'
                : 'var(--text-3)',
          }}
        >
          <Icon
            name={
              handoffState === 'preparing'
                ? 'hourglass_top'
                : selectedSessionId === NEW_SESSION_VALUE
                  ? 'move_up'
                  : 'link'
            }
            size={12}
          />
          {sessionNotice
            || (selectedSessionId === NEW_SESSION_VALUE
              ? 'Next message starts a fresh conversation'
              : currentSessionId
                ? `Continuing ${currentSessionId.slice(0, 12)}…`
                : 'No conversation yet')}
        </span>

        {/* Input row */}
        <div className="flex gap-2">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isRunning ? `${agent.name} is responding…` : `Message ${agent.name}…`}
            rows={1}
            disabled={interactionLocked}
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
            aria-label="Send message"
            disabled={!message.trim() || interactionLocked}
            className="px-3 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: message.trim() && !interactionLocked ? 'var(--blue)' : 'var(--surface)',
              color: message.trim() && !interactionLocked ? '#fff' : 'var(--text-3)',
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
