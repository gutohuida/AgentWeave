import { format } from 'date-fns'
import { ChatMessage } from '@/api/agentChat'

interface AgentPromptMessageProps {
  message: ChatMessage
  agentName?: string
}

export function AgentPromptMessage({ message, agentName }: AgentPromptMessageProps) {
  const isUser = message.role === 'user'
  const timestamp = new Date(message.timestamp)

  return (
    <div
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}
    >
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 ${
          isUser
            ? 'rounded-br-md'
            : 'rounded-bl-md'
        }`}
        style={{
          background: isUser ? 'var(--surface-3)' : 'var(--surface-2)',
          color: isUser ? 'var(--text)' : 'var(--text-3)',
        }}
      >
        {/* Header */}
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[11px] font-medium">
            {isUser ? 'You' : (agentName || 'Agent')}
          </span>
          <span
            className="text-[11px]"
            style={{ opacity: 0.6 }}
          >
            {format(timestamp, 'HH:mm')}
          </span>
        </div>

        {/* Content */}
        <div className="text-sm whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </div>
    </div>
  )
}
