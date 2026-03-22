import { useState, useEffect, useRef } from 'react'
import { useConfigStore } from '@/store/configStore'
import { useAgentChatHistory, useAgentRecentChat, ChatMessage } from '@/api/agentChat'
import { useAgentOutput } from '@/api/agents'
import { AgentPromptMessage } from './AgentPromptMessage'
import { Icon } from '@/components/common/Icon'

interface AgentPromptPanelProps {
  agent: string
}

interface Session {
  id: string
  type: string
  path: string
  last_active?: string
}

export function AgentPromptPanel({ agent }: AgentPromptPanelProps) {
  const { apiKey } = useConfigStore()
  const [message, setMessage] = useState('')
  const [sessionMode, setSessionMode] = useState<'new' | 'resume'>('new')
  const [selectedSessionId, setSelectedSessionId] = useState<string>('')
  const [sessions, setSessions] = useState<Session[]>([])
  const [isLoadingSessions, setIsLoadingSessions] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [localMessages, setLocalMessages] = useState<ChatMessage[]>([])
  
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  
  // Fetch agent output for real-time updates
  const { lines: outputLines } = useAgentOutput(agent)
  
  // Fetch chat history when session is selected
  const { data: chatHistory, refetch: refetchHistory } = useAgentChatHistory(
    agent,
    sessionMode === 'resume' ? selectedSessionId : null
  )
  
  // Fetch recent chat for "new" mode context
  const { data: recentChat } = useAgentRecentChat(agent, 10)

  // Fetch available sessions
  useEffect(() => {
    fetchSessions()
  }, [agent])

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [localMessages, chatHistory?.messages])

  // Convert agent output to chat messages when in "new" mode
  useEffect(() => {
    if (sessionMode === 'new' && outputLines.length > 0) {
      const outputMessages: ChatMessage[] = outputLines
        .filter(line => line.session_id === selectedSessionId || !selectedSessionId)
        .map(line => ({
          id: line.id,
          role: 'agent',
          content: line.content,
          timestamp: line.timestamp,
        }))
      
      // Merge with user messages from recent chat
      if (recentChat) {
        const userMessages = recentChat.filter(m => m.role === 'user')
        const merged = [...userMessages, ...outputMessages]
        merged.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
        setLocalMessages(merged)
      } else {
        setLocalMessages(outputMessages)
      }
    }
  }, [outputLines, sessionMode, recentChat, selectedSessionId])

  // When session is selected in resume mode, use chat history
  useEffect(() => {
    if (sessionMode === 'resume' && chatHistory?.messages) {
      setLocalMessages(chatHistory.messages)
    }
  }, [chatHistory, sessionMode])

  const fetchSessions = async () => {
    if (!apiKey) return
    
    setIsLoadingSessions(true)
    try {
      const response = await fetch(`/api/v1/agent/sessions/${agent}`, {
        headers: { 'Authorization': `Bearer ${apiKey}` }
      })
      
      if (response.ok) {
        const data = await response.json()
        setSessions(data.sessions || [])
        // Auto-select most recent session if available
        if (data.sessions?.length > 0 && !selectedSessionId) {
          setSelectedSessionId(data.sessions[0].id)
          setSessionMode('resume')
        }
      }
    } catch (err) {
      console.error('Failed to fetch sessions:', err)
    } finally {
      setIsLoadingSessions(false)
    }
  }

  const handleSend = async () => {
    if (!message.trim() || !apiKey) return

    const trimmedMessage = message.trim()
    setIsSending(true)
    
    // Add message to local state immediately
    const tempMessage: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: trimmedMessage,
      timestamp: new Date().toISOString(),
    }
    setLocalMessages(prev => [...prev, tempMessage])
    setMessage('')

    try {
      const response = await fetch('/api/v1/agent/trigger', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify({
          agent,
          message: trimmedMessage,
          session_mode: sessionMode,
          session_id: sessionMode === 'resume' ? selectedSessionId : undefined
        })
      })

      if (!response.ok) {
        const error = await response.json()
        console.error('Failed to send message:', error)
        // Remove temp message on error
        setLocalMessages(prev => prev.filter(m => m.id !== tempMessage.id))
      } else {
        const data = await response.json()
        // If new session, update selected session
        if (sessionMode === 'new' && data.session_id) {
          setSelectedSessionId(data.session_id)
          // Refresh sessions list
          fetchSessions()
        }
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

  const hasSessions = sessions.length > 0
  const messages = localMessages

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--surface-low)' }}>
      {/* Header with Session Selector */}
      <div
        className="flex items-center gap-3 px-4 py-3 border-b shrink-0"
        style={{ background: 'var(--surface-high)', borderColor: 'var(--outline-variant)' }}
      >
        <Icon name="chat" size={20} style={{ color: 'var(--primary)' }} />
        <span className="m3-title-small" style={{ color: 'var(--foreground)' }}>
          Chat with {agent}
        </span>
        
        <div className="ml-auto flex items-center gap-2">
          {/* Session Mode Toggle */}
          <button
            onClick={() => setSessionMode('new')}
            className={`px-3 py-1.5 rounded-lg m3-label-small transition-colors ${
              sessionMode === 'new'
                ? 'bg-primary text-primary-foreground'
                : 'hover:bg-surface-highest'
            }`}
            style={sessionMode === 'new' ? { background: 'var(--primary)', color: 'var(--primary-foreground)' } : {}}
          >
            New Session
          </button>
          <button
            onClick={() => setSessionMode('resume')}
            disabled={!hasSessions}
            className={`px-3 py-1.5 rounded-lg m3-label-small transition-colors ${
              sessionMode === 'resume'
                ? 'bg-primary text-primary-foreground'
                : 'hover:bg-surface-highest'
            } ${!hasSessions ? 'opacity-50 cursor-not-allowed' : ''}`}
            style={sessionMode === 'resume' ? { background: 'var(--primary)', color: 'var(--primary-foreground)' } : {}}
          >
            Resume
          </button>
        </div>
      </div>

      {/* Session Selection Dropdown */}
      {sessionMode === 'resume' && (
        <div
          className="px-4 py-2 border-b"
          style={{ background: 'var(--surface)', borderColor: 'var(--outline-variant)' }}
        >
          {isLoadingSessions ? (
            <span className="m3-body-small" style={{ color: 'var(--on-sv)' }}>Loading sessions...</span>
          ) : hasSessions ? (
            <select
              value={selectedSessionId}
              onChange={(e) => setSelectedSessionId(e.target.value)}
              className="w-full px-3 py-2 rounded-lg m3-body-medium border"
              style={{
                background: 'var(--surface-high)',
                borderColor: 'var(--outline-variant)',
                color: 'var(--on-sv)',
              }}
            >
              {sessions.map((session) => (
                <option key={session.id} value={session.id}>
                  {session.id.slice(0, 24)}{session.id.length > 24 ? '…' : ''}
                  {session.last_active && ` (${new Date(session.last_active).toLocaleDateString()})`}
                </option>
              ))}
            </select>
          ) : (
            <span className="m3-body-small" style={{ color: 'var(--error)' }}>
              No sessions available. Start a new conversation.
            </span>
          )}
        </div>
      )}

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full" style={{ color: 'var(--on-sv)' }}>
            <Icon name="chat_bubble_outline" size={48} style={{ opacity: 0.5, marginBottom: '1rem' }} />
            <p className="m3-body-large">Start a conversation</p>
            <p className="m3-body-small mt-2" style={{ opacity: 0.7 }}>
              {sessionMode === 'new' 
                ? 'Type a message to start a new session'
                : 'Select a session to continue the conversation'}
            </p>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <AgentPromptMessage key={msg.id} message={msg} />
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
            placeholder={`Message ${agent}...`}
            rows={1}
            className="flex-1 px-4 py-3 rounded-xl m3-body-medium resize-none border"
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
            disabled={!message.trim() || isSending || (sessionMode === 'resume' && !selectedSessionId)}
            className="px-4 py-3 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: message.trim() && !isSending ? 'var(--primary)' : 'var(--surface)',
              color: message.trim() && !isSending ? 'var(--primary-foreground)' : 'var(--on-sv)',
            }}
          >
            <Icon name="send" size={20} />
          </button>
        </div>
        <p className="mt-2 m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
          Press Enter to send, Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}
