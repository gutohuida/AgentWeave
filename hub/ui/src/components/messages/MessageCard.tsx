import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { useMarkRead } from '@/api/messages'

interface MessageCardProps {
  message: {
    id: string
    from: string
    to: string
    subject?: string
    content: string
    timestamp: string
    type: string
    read: boolean
    task_id?: string
  }
}

export function MessageCard({ message }: MessageCardProps) {
  const markRead = useMarkRead()
  const [expanded, setExpanded] = useState(false)

  const isLongContent = message.content.length > 150

  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        overflow: 'hidden',
        ...(!message.read ? { borderLeft: '3px solid var(--blue)' } : {}),
      }}
    >
      {/* Header row */}
      <div
        className="flex items-start gap-3 px-4 pt-4 pb-3 cursor-pointer"
        onClick={() => isLongContent && setExpanded(!expanded)}
      >
        {/* Leading icon */}
        <div
          className="shrink-0 flex items-center justify-center rounded-full"
          style={{
            width: 36,
            height: 36,
            background: 'var(--surface-3)',
            color: 'var(--text-2)',
            marginTop: 2,
          }}
        >
          <Icon name="chat" size={18} fill={message.read ? 0 : 1} />
        </div>

        {/* Text content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>
              {message.from}
              <span className="mx-1.5" style={{ color: 'var(--text-3)', fontWeight: 400 }}>→</span>
              {message.to}
            </span>
            <span className="text-[11px] shrink-0" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
              {formatDistanceToNow(new Date(message.timestamp), { addSuffix: true })}
            </span>
          </div>

          {/* Subject */}
          {message.subject && (
            <p className="text-[11px] mb-1" style={{ color: 'var(--blue)' }}>
              {message.subject}
            </p>
          )}

          {/* Content */}
          <p
            className={`text-xs ${expanded ? '' : 'line-clamp-3'}`}
            style={{ color: 'var(--text)', whiteSpace: 'pre-wrap' }}
          >
            {message.content}
          </p>

          {/* Expand hint */}
          {isLongContent && !expanded && (
            <p className="text-[11px] mt-1" style={{ color: 'var(--blue)' }}>
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
            className="shrink-0 p-1 rounded-full transition-colors"
            style={{ color: 'var(--text-3)' }}
          >
            <Icon name={expanded ? 'expand_less' : 'expand_more'} size={20} />
          </button>
        )}
      </div>

      {/* Footer actions */}
      <div className="px-4 pb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              background: 'var(--surface-3)',
              borderRadius: 'var(--radius-sm)',
              padding: '2px 8px',
              fontSize: 11,
              fontWeight: 500,
              color: 'var(--text-3)',
            }}
          >
            {message.type}
          </span>
          {message.task_id && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                background: 'rgba(168,85,247,0.1)',
                borderRadius: 'var(--radius-sm)',
                padding: '2px 8px',
                fontSize: 11,
                fontWeight: 500,
                color: 'var(--purple)',
              }}
            >
              {message.task_id.slice(0, 12)}…
            </span>
          )}
        </div>

        {!message.read && (
          <button
            onClick={() => markRead.mutate(message.id)}
            className="flex items-center gap-1.5 h-7 px-3 rounded-full text-[11px] font-medium transition-colors"
            style={{ background: 'var(--surface-3)', color: 'var(--text-2)' }}
          >
            <Icon name="check" size={14} />
            Mark read
          </button>
        )}
      </div>
    </div>
  )
}
