import { format } from 'date-fns'
import { ChatMessage } from '@/api/agentChat'

interface AgentPromptMessageProps {
  message: ChatMessage
}

export function AgentPromptMessage({ message }: AgentPromptMessageProps) {
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
          background: isUser ? 'var(--p-cont)' : 'var(--surface-high)',
          color: isUser ? 'var(--on-p-cont)' : 'var(--on-sv)',
        }}
      >
        {/* Header */}
        <div className="flex items-center gap-2 mb-1">
          <span className="m3-label-small font-medium">
            {isUser ? 'You' : 'Agent'}
          </span>
          <span
            className="m3-label-small"
            style={{ opacity: 0.6 }}
          >
            {format(timestamp, 'HH:mm')}
          </span>
        </div>

        {/* Content */}
        <div className="m3-body-medium whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </div>
    </div>
  )
}
