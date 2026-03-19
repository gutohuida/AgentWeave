import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { Message, useMarkRead } from '@/api/messages'

interface MessageCardProps {
  message: Message
}

export function MessageCard({ message }: MessageCardProps) {
  const markRead = useMarkRead()

  return (
    <div
      className="m3-card-elevated"
      style={!message.read ? { borderLeft: '3px solid var(--primary)' } : undefined}
    >
      {/* Header row — 2-line list item style */}
      <div className="flex items-start gap-3 px-4 pt-4 pb-3">
        {/* Leading icon in tonal container */}
        <div
          className="m3-icon-container shrink-0"
          style={{ background: 'var(--p-cont)', color: 'var(--on-p-cont)', marginTop: 2 }}
        >
          <Icon name="chat" size={18} fill={message.read ? 0 : 1} />
        </div>

        {/* Text content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-0.5">
            <span className="m3-title-small" style={{ color: 'var(--foreground)' }}>
              {message.from}
              <span className="mx-1.5" style={{ color: 'var(--on-sv)', fontWeight: 400 }}>→</span>
              {message.to}
            </span>
            <span className="m3-label-small shrink-0" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
              {formatDistanceToNow(new Date(message.timestamp), { addSuffix: true })}
            </span>
          </div>
          <p className="m3-body-small line-clamp-3" style={{ color: 'var(--foreground)', whiteSpace: 'pre-wrap' }}>
            {message.content}
          </p>
        </div>
      </div>

      {/* Mark read button */}
      {!message.read && (
        <div className="px-4 pb-3 flex justify-end">
          <button
            onClick={() => markRead.mutate(message.id)}
            className="flex items-center gap-1.5 h-7 px-3 rounded-full m3-label-small transition-colors"
            style={{ background: 'var(--p-cont)', color: 'var(--on-p-cont)' }}
          >
            <Icon name="check" size={14} />
            Mark read
          </button>
        </div>
      )}
    </div>
  )
}
