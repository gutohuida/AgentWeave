import { formatDistanceToNow } from 'date-fns'
import { Check } from 'lucide-react'
import { Message, useMarkRead } from '@/api/messages'

interface MessageCardProps {
  message: Message
}

export function MessageCard({ message }: MessageCardProps) {
  const markRead = useMarkRead()

  return (
    <div className={`rounded-lg border p-4 ${message.read ? 'opacity-60' : 'border-primary/30 bg-primary/5'}`}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">
          <span className="text-foreground">{message.from}</span>
          {' → '}
          <span className="text-foreground">{message.to}</span>
        </span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {formatDistanceToNow(new Date(message.timestamp), { addSuffix: true })}
          </span>
          {!message.read && (
            <button
              onClick={() => markRead.mutate(message.id)}
              className="flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary hover:bg-primary/20"
            >
              <Check className="h-3 w-3" />
              Mark read
            </button>
          )}
        </div>
      </div>
      <p className="text-sm whitespace-pre-wrap">{message.content}</p>
    </div>
  )
}
