import { formatDistanceToNow } from 'date-fns'
import { Check } from 'lucide-react'
import { Message, useMarkRead } from '@/api/messages'

interface MessageCardProps {
  message: Message
}

export function MessageCard({ message }: MessageCardProps) {
  const markRead = useMarkRead()

  return (
    <div className={`glass-card rounded-xl p-4 transition-all ${
      message.read
        ? 'opacity-50'
        : 'border-l-2 border-primary/50'
    }`}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium text-white/40">
          <span className="text-white/80">{message.from}</span>
          {' → '}
          <span className="text-white/80">{message.to}</span>
        </span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-white/25">
            {formatDistanceToNow(new Date(message.timestamp), { addSuffix: true })}
          </span>
          {!message.read && (
            <button
              onClick={() => markRead.mutate(message.id)}
              className="flex items-center gap-1 rounded-lg bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary hover:bg-primary/20 transition-colors"
            >
              <Check className="h-3 w-3" />
              Mark read
            </button>
          )}
        </div>
      </div>
      <p className="text-sm text-white/80 whitespace-pre-wrap">{message.content}</p>
    </div>
  )
}
