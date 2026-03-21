import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { Message, useMarkRead } from '@/api/messages'

interface MessageCardProps {
  message: Message
}

export function MessageCard({ message }: MessageCardProps) {
  const markRead = useMarkRead()
  const [expanded, setExpanded] = useState(false)

  const isLongContent = message.content.length > 150

  return (
    <div
      className="m3-card-elevated overflow-hidden"
      style={!message.read ? { borderLeft: '3px solid var(--primary)' } : undefined}
    >
      {/* Header row — 2-line list item style */}
      <div 
        className="flex items-start gap-3 px-4 pt-4 pb-3 cursor-pointer"
        onClick={() => isLongContent && setExpanded(!expanded)}
      >
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
          
          {/* Subject */}
          {message.subject && (
            <p className="m3-label-small mb-1" style={{ color: 'var(--primary)' }}>
              {message.subject}
            </p>
          )}
          
          {/* Content - truncated or full */}
          <p 
            className={`m3-body-small ${expanded ? '' : 'line-clamp-3'}`} 
            style={{ color: 'var(--foreground)', whiteSpace: 'pre-wrap' }}
          >
            {message.content}
          </p>
          
          {/* Expand hint */}
          {isLongContent && !expanded && (
            <p className="m3-label-small mt-1" style={{ color: 'var(--primary)' }}>
              Click to expand…
            </p>
          )}
        </div>

        {/* Expand/collapse icon */}
        {isLongContent && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              setExpanded(!expanded)
            }}
            className="shrink-0 p-1 rounded-full transition-colors hover:bg-black/5"
            style={{ color: 'var(--on-sv)' }}
          >
            <Icon name={expanded ? 'expand_less' : 'expand_more'} size={20} />
          </button>
        )}
      </div>

      {/* Footer actions */}
      <div className="px-4 pb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span 
            className="m3-chip m3-label-small"
            style={{ background: 'var(--surface-highest)', color: 'var(--on-sv)' }}
          >
            {message.type}
          </span>
          {message.task_id && (
            <span 
              className="m3-chip m3-label-small"
              style={{ background: 'var(--s-cont)', color: 'var(--on-s-cont)' }}
            >
              {message.task_id.slice(0, 12)}…
            </span>
          )}
        </div>

        {!message.read && (
          <button
            onClick={() => markRead.mutate(message.id)}
            className="flex items-center gap-1.5 h-7 px-3 rounded-full m3-label-small transition-colors"
            style={{ background: 'var(--p-cont)', color: 'var(--on-p-cont)' }}
          >
            <Icon name="check" size={14} />
            Mark read
          </button>
        )}
      </div>
    </div>
  )
}
