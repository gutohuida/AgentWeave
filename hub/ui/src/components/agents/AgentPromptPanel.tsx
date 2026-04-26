import { useState, useEffect, useRef } from 'react'
import { useConfigStore } from '@/store/configStore'
import { useAgentChatHistory, ChatMessage } from '@/api/agentChat'
import { useAgentOutput, useAgentSessions, AgentSummary } from '@/api/agents'
import { AgentPromptMessage } from './AgentPromptMessage'
import { Icon } from '@/components/common/Icon'

interface AgentPromptPanelProps {
  agent: AgentSummary
}

const NEW_SESSION_ID = '__new__'

export function AgentPromptPanel({ agent }: AgentPromptPanelProps) {
  const { apiKey } = useConfigStore()
  const [message, setMessage] = useState('')
  const [sessionMode, setSessionMode] = useState<'new' | 'resume'>('new')
  const [selectedSessionId, setSelectedSessionId] = useState<string>('')
  const [isSending, setIsSending] = useState(false)
  const [localMessages, setLocalMessages] = useState<ChatMessage[]>([])

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const userChoseNewRef = useRef(false)
  const newSessionOutputIndexRef = useRef(0)

  const sessionModeRef = useRef(sessionMode)
  const selectedSessionIdRef = useRef(selectedSessionId)

  const agentName = agent.name
  const isAgentRunning = agent.status === 'running'

  const { lines: outputLines } = useAgentOutput(agentName)

  const { data: chatHistory, refetch: refetchHistory } = useAgentChatHistory(
    agentName,
    sessionMode === 'resume' ? selectedSessionId : null
  )

  const { data: sessionsData, isLoading: isLoadingSessions, refetch: refetchSessions } = useAgentSessions(agentName)
  const sessions = sessionsData?.sessions || []

  useEffect(() => { sessionModeRef.current = sessionMode }, [sessionMode])
  useEffect(() => { selectedSessionIdRef.current = selectedSessionId }, [selectedSessionId])

  useEffect(() => {
    if (sessions.length > 0 && !selectedSessionId && !userChoseNewRef.current) {
      setSelectedSessionId(sessions[0].id)
      setSessionMode('resume')
    }
  }, [sessions, selectedSessionId])

  useEffect(() => {
    if (selectedSessionId === NEW_SESSION_ID) {
      setSessionMode('new')
    }
  }, [selectedSessionId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [localMessages, chatHistory?.messages])

  useEffect(() => {
    if (sessionMode === 'new' && outputLines.length > 0 && selectedSessionId) {
      const linesSinceNew = outputLines.slice(newSessionOutputIndexRef.current)

      const detectedSession = linesSinceNew.find(line => line.session_id)?.session_id
      if (detectedSession && detectedSession !== NEW_SESSION_ID) {
        setSelectedSessionId(detectedSession)
        setSessionMode('resume')
        userChoseNewRef.current = false
        refetchSessions()
        return
      }

      const outputMessages: ChatMessage[] = linesSinceNew
        .filter(line => line.session_id === selectedSessionId || !line.session_id)
        .filter(line =>
          !line.content.startsWith('[watchdog]') &&
          !line.content.startsWith('[stderr]') &&
          !line.content.startsWith('[session:') &&
          !line.content.startsWith('[done] cost:')
        )
        .map(line => ({
          id: line.id,
          role: 'agent',
          content: line.content,
          timestamp: line.timestamp,
        }))

      setLocalMessages(prev => {
        const userMsgs = prev.filter(m => m.role === 'user')
        const merged = [...userMsgs, ...outputMessages]
        merged.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
        return merged
      })
    }
  }, [outputLines, sessionMode, selectedSessionId, refetchSessions])

  useEffect(() => {
    if (
      sessionMode === 'resume' &&
      chatHistory?.messages &&
      chatHistory.messages.length > 0 &&
      chatHistory.session_id === selectedSessionId
    ) {
      const filtered = chatHistory.messages.filter(
        m => m.role !== 'agent' || (
          !m.content.startsWith('[watchdog]') &&
          !m.content.startsWith('[stderr]') &&
          !m.content.startsWith('[session:') &&
          !m.content.startsWith('[done] cost:')
        )
      )
      setLocalMessages(prev => {
        const historyIds = new Set(filtered.map(m => m.id))
        const historyContents = new Set(filtered.map(m => m.content.trim()))
        const toKeep = prev.filter(m => {
          if (historyIds.has(m.id)) return false
          if (m.id.startsWith('temp-') && historyContents.has(m.content.trim())) return false
          return true
        })
        const merged = [...filtered, ...toKeep]
        merged.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
        return merged
      })
    }
  }, [chatHistory, sessionMode, selectedSessionId])

  const handleSend = async () => {
    if (!message.trim() || !apiKey) return

    const trimmedMessage = message.trim()
    setIsSending(true)

    const tempMessage: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: trimmedMessage,
      timestamp: new Date().toISOString(),
    }
    setLocalMessages(prev => [...prev, tempMessage])
    setMessage('')

    const currentMode = sessionModeRef.current
    const currentSessionId = selectedSessionIdRef.current

    try {
      const response = await fetch('/api/v1/agent/trigger', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify({
          agent: agentName,
          message: trimmedMessage,
          session_mode: currentMode,
          session_id: currentMode === 'resume' ? currentSessionId : undefined
        })
      })

      if (!response.ok) {
        const error = await response.json()
        console.error('Failed to send message:', error)
        setLocalMessages(prev => prev.filter(m => m.id !== tempMessage.id))
      } else {
        refetchHistory()
      }
    } catch (err) {
      console.error('Network error:', err)
      setLocalMessages(prev => prev.filter(m => m.id !== tempMessage.id))
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

  const handleNewChat = () => {
    userChoseNewRef.current = true
    setSessionMode('new')
    setSelectedSessionId(NEW_SESSION_ID)
    setLocalMessages([])
    newSessionOutputIndexRef.current = outputLines.length
  }

  const messages = localMessages
  const isInputDisabled = !message.trim() || isSending || isAgentRunning || isLoadingSessions ||
    (sessionMode === 'resume' && !selectedSessionId) || agent.pilot

  const inputStyle: React.CSSProperties = {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    color: 'var(--text-3)',
    padding: '12px 16px',
    minHeight: 48,
    maxHeight: 120,
    outline: 'none',
    fontSize: 14,
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--surface)' }}>
      {/* Header */}
      <div
        className="flex items-center gap-3 px-4 py-3 border-b shrink-0"
        style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
      >
        <Icon name="chat" size={20} style={{ color: 'var(--blue)' }} />
        <span className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>
          Chat with {agentName}
        </span>

        {agent.latest_status_msg && (
          <div className="flex items-center gap-1.5 flex-1 min-w-0 mx-2">
            {isAgentRunning && (
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0 animate-pulse"
                style={{ background: 'var(--blue)' }}
              />
            )}
            <span className="text-xs truncate" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
              {agent.latest_status_msg}
            </span>
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={handleNewChat}
            title="New chat"
            className="p-2 rounded-lg transition-colors"
            style={{ color: 'var(--text-3)' }}
          >
            <Icon name="edit_note" size={20} />
          </button>
        </div>
      </div>

      {/* Session Selection */}
      <div
        className="px-4 py-2 border-b"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        {isLoadingSessions ? (
          <span className="text-xs" style={{ color: 'var(--text-3)' }}>Loading sessions...</span>
        ) : (
          <select
            value={selectedSessionId}
            onChange={(e) => {
              const value = e.target.value
              if (value === NEW_SESSION_ID) {
                handleNewChat()
              } else {
                if (value !== selectedSessionId) {
                  setLocalMessages([])
                }
                setSelectedSessionId(value)
                setSessionMode('resume')
                userChoseNewRef.current = false
              }
            }}
            className="w-full px-3 py-2 rounded-lg text-xs border"
            style={{
              background: 'var(--surface-2)',
              borderColor: 'var(--border)',
              color: 'var(--text-3)',
              outline: 'none',
            }}
          >
            <option value={NEW_SESSION_ID}>New conversation</option>
            {sessions.map((session) => (
              <option key={session.id} value={session.id}>
                {session.id.slice(0, 24)}{session.id.length > 24 ? '…' : ''}
                {session.last_active && ` (${new Date(session.last_active).toLocaleDateString()})`}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full" style={{ color: 'var(--text-3)' }}>
            <Icon name="chat_bubble_outline" size={48} style={{ opacity: 0.5, marginBottom: '1rem' }} />
            <p className="text-sm">Start a conversation</p>
            <p className="text-xs mt-2" style={{ opacity: 0.7 }}>
              {selectedSessionId === NEW_SESSION_ID
                ? 'Type a message to start a new session'
                : 'Select a session from the dropdown above to continue the conversation'}
            </p>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <AgentPromptMessage key={msg.id} message={msg} agentName={agentName} />
            ))}
            {isSending && (
              <div className="flex justify-start mb-4">
                <div
                  className="rounded-2xl rounded-bl-md px-4 py-3"
                  style={{ background: 'var(--surface-2)' }}
                >
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--blue)' }} />
                    <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--blue)', animationDelay: '0.1s' }} />
                    <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--blue)', animationDelay: '0.2s' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input Area */}
      <div
        className="px-4 py-3 border-t"
        style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
      >
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              agent.pilot
                ? `Pilot mode — ${agentName} is manually controlled`
                : isAgentRunning
                  ? `${agentName} is responding…`
                  : `Message ${agentName}...`
            }
            rows={1}
            disabled={isAgentRunning}
            className="flex-1 resize-none disabled:opacity-50"
            style={inputStyle}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement
              target.style.height = 'auto'
              target.style.height = `${Math.min(target.scrollHeight, 120)}px`
            }}
          />
          <button
            onClick={handleSend}
            disabled={isInputDisabled}
            title={
              agent.pilot
                ? 'Pilot mode — agent is manually controlled'
                : isAgentRunning
                  ? 'Agent is responding...'
                  : 'Send message'
            }
            className="px-4 py-3 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: message.trim() && !isSending && !isAgentRunning ? 'var(--blue)' : 'var(--surface)',
              color: message.trim() && !isSending && !isAgentRunning ? '#fff' : 'var(--text-3)',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            <Icon name="send" size={20} />
          </button>
        </div>
        {isAgentRunning ? (
          <p className="mt-2 text-[11px]" style={{ color: 'var(--blue)' }}>
            Agent is responding…
          </p>
        ) : (
          <p className="mt-2 text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.6 }}>
            Press Enter to send, Shift+Enter for new line
          </p>
        )}
      </div>
    </div>
  )
}
