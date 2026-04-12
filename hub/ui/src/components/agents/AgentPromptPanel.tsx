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
  
  // Refs to track current state values (avoid stale closures in handleSend)
  const sessionModeRef = useRef(sessionMode)
  const selectedSessionIdRef = useRef(selectedSessionId)
  
  const agentName = agent.name
  const isAgentRunning = agent.status === 'running'
  
  // Fetch agent output for real-time updates
  const { lines: outputLines } = useAgentOutput(agentName)
  
  // Fetch chat history when session is selected
  const { data: chatHistory, refetch: refetchHistory } = useAgentChatHistory(
    agentName,
    sessionMode === 'resume' ? selectedSessionId : null
  )

  // Fetch available sessions using React Query hook
  const { data: sessionsData, isLoading: isLoadingSessions, refetch: refetchSessions } = useAgentSessions(agentName)
  const sessions = sessionsData?.sessions || []

  // Sync refs with state values to avoid stale closures
  useEffect(() => { sessionModeRef.current = sessionMode }, [sessionMode])
  useEffect(() => { selectedSessionIdRef.current = selectedSessionId }, [selectedSessionId])

  // Auto-select most recent session on mount (if user hasn't chosen new)
  // Note: userChoseNewRef is intentionally not in deps - we want to read its current value
  // without re-triggering the effect when it changes
  useEffect(() => {
    if (sessions.length > 0 && !selectedSessionId && !userChoseNewRef.current) {
      setSelectedSessionId(sessions[0].id)
      setSessionMode('resume')
    }
  }, [sessions, selectedSessionId])

  // When sessions update and we're in new mode, ensure we stay in new mode
  useEffect(() => {
    if (selectedSessionId === NEW_SESSION_ID) {
      setSessionMode('new')
    }
  }, [selectedSessionId])

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [localMessages, chatHistory?.messages])

  // Convert agent output to chat messages when in "new" mode
  useEffect(() => {
    if (sessionMode === 'new' && outputLines.length > 0 && selectedSessionId) {
      // Only look at output lines that arrived after entering new mode so we
      // don't instantly switch back to a previous session from cached lines.
      const linesSinceNew = outputLines.slice(newSessionOutputIndexRef.current)

      // Detect real session ID from new output lines and auto-switch to resume mode
      const detectedSession = linesSinceNew.find(line => line.session_id)?.session_id
      if (detectedSession && detectedSession !== NEW_SESSION_ID) {
        setSelectedSessionId(detectedSession)
        setSessionMode('resume')
        userChoseNewRef.current = false
        refetchSessions()
        return
      }

      const outputMessages: ChatMessage[] = linesSinceNew
        // In new mode before detection, show lines with no session_id or matching __new__
        .filter(line => line.session_id === selectedSessionId || !line.session_id)
        // Fix C: Filter system messages from chat bubbles
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

  // When session is selected in resume mode, use chat history
  useEffect(() => {
    if (
      sessionMode === 'resume' &&
      chatHistory?.messages &&
      chatHistory.messages.length > 0 &&
      chatHistory.session_id === selectedSessionId
    ) {
      // Fix A: Filter out system messages from chat history
      const filtered = chatHistory.messages.filter(
        m => m.role !== 'agent' || (
          !m.content.startsWith('[watchdog]') &&
          !m.content.startsWith('[stderr]') &&
          !m.content.startsWith('[session:') &&
          !m.content.startsWith('[done] cost:')
        )
      )
      // Merge with existing local messages to preserve optimistic temp messages
      // and agent outputs that arrived before the history was fetched
      setLocalMessages(prev => {
        const historyIds = new Set(filtered.map(m => m.id))
        const historyContents = new Set(filtered.map(m => m.content.trim()))
        const toKeep = prev.filter(m => {
          if (historyIds.has(m.id)) return false
          // Deduplicate optimistic temp messages by content
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
    
    // Add message to local state immediately (optimistic update)
    const tempMessage: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: trimmedMessage,
      timestamp: new Date().toISOString(),
    }
    setLocalMessages(prev => [...prev, tempMessage])
    setMessage('')

    // Read current values from refs to avoid stale closures
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
        // Remove temp message on error
        setLocalMessages(prev => prev.filter(m => m.id !== tempMessage.id))
      } else {
        // Refresh chat history
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

  // handleNewChat - sets mode to new with special ID so selector stays visible
  const handleNewChat = () => {
    userChoseNewRef.current = true
    setSessionMode('new')
    setSelectedSessionId(NEW_SESSION_ID)
    setLocalMessages([])
    // Only consider output lines that arrive after this point for session detection
    newSessionOutputIndexRef.current = outputLines.length
  }

  const messages = localMessages
  const isInputDisabled = !message.trim() || isSending || isAgentRunning || isLoadingSessions ||
    (sessionMode === 'resume' && !selectedSessionId) || agent.pilot

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--surface-low)' }}>
      {/* Header */}
      <div
        className="flex items-center gap-3 px-4 py-3 border-b shrink-0"
        style={{ background: 'var(--surface-high)', borderColor: 'var(--outline-variant)' }}
      >
        <Icon name="chat" size={20} style={{ color: 'var(--primary)' }} />
        <span className="m3-title-small" style={{ color: 'var(--foreground)' }}>
          Chat with {agentName}
        </span>
        
        {/* Fix C: Inline status message */}
        {agent.latest_status_msg && (
          <div className="flex items-center gap-1.5 flex-1 min-w-0 mx-2">
            {isAgentRunning && (
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0 animate-pulse"
                style={{ background: 'var(--primary)' }}
              />
            )}
            <span className="m3-body-small truncate" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
              {agent.latest_status_msg}
            </span>
          </div>
        )}
        
        <div className="ml-auto flex items-center gap-2">
          {/* New chat icon button */}
          <button
            onClick={handleNewChat}
            title="New chat"
            className="p-2 rounded-lg transition-colors hover:bg-surface"
            style={{ color: 'var(--on-sv)' }}
          >
            <Icon name="edit_note" size={20} />
          </button>
        </div>
      </div>

      {/* Session Selection Dropdown (always visible) */}
      <div
        className="px-4 py-2 border-b"
        style={{ background: 'var(--surface)', borderColor: 'var(--outline-variant)' }}
      >
        {isLoadingSessions ? (
          <span className="m3-body-small" style={{ color: 'var(--on-sv)' }}>Loading sessions...</span>
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
            className="w-full px-3 py-2 rounded-lg m3-body-medium border"
            style={{
              background: 'var(--surface-high)',
              borderColor: 'var(--outline-variant)',
              color: 'var(--on-sv)',
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
          <div className="flex flex-col items-center justify-center h-full" style={{ color: 'var(--on-sv)' }}>
            <Icon name="chat_bubble_outline" size={48} style={{ opacity: 0.5, marginBottom: '1rem' }} />
            <p className="m3-body-large">Start a conversation</p>
            <p className="m3-body-small mt-2" style={{ opacity: 0.7 }}>
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
                  style={{ background: 'var(--surface-high)' }}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2 h-2 rounded-full animate-bounce"
                      style={{ background: 'var(--primary)' }}
                    />
                    <span
                      className="w-2 h-2 rounded-full animate-bounce"
                      style={{ background: 'var(--primary)', animationDelay: '0.1s' }}
                    />
                    <span
                      className="w-2 h-2 rounded-full animate-bounce"
                      style={{ background: 'var(--primary)', animationDelay: '0.2s' }}
                    />
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
        style={{ background: 'var(--surface-high)', borderColor: 'var(--outline-variant)' }}
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
            className="flex-1 px-4 py-3 rounded-xl m3-body-medium resize-none border disabled:opacity-50"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--outline-variant)',
              color: 'var(--on-sv)',
              minHeight: '48px',
              maxHeight: '120px',
            }}
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
              background: message.trim() && !isSending && !isAgentRunning ? 'var(--primary)' : 'var(--surface)',
              color: message.trim() && !isSending && !isAgentRunning ? 'var(--primary-foreground)' : 'var(--on-sv)',
            }}
          >
            <Icon name="send" size={20} />
          </button>
        </div>
        {isAgentRunning ? (
          <p className="mt-2 m3-label-small" style={{ color: 'var(--primary)' }}>
            Agent is responding…
          </p>
        ) : (
          <p className="mt-2 m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
            Press Enter to send, Shift+Enter for new line
          </p>
        )}
      </div>
    </div>
  )
}
