import { formatDistanceToNow } from 'date-fns'
import { MessageSquare, CheckSquare, HelpCircle, Zap } from 'lucide-react'
import { SSEEvent } from '@/hooks/useSSE'

interface EventRowProps {
  event: SSEEvent & { localId: number }
}

function iconForType(type: string) {
  if (type.startsWith('message')) return MessageSquare
  if (type.startsWith('task')) return CheckSquare
  if (type.startsWith('question')) return HelpCircle
  return Zap
}

function summaryForEvent(event: SSEEvent): string {
  const d = event.data as Record<string, unknown>
  switch (event.type) {
    case 'message_created': return `New message from ${d.from} to ${d.to}`
    case 'message_read': return `Message ${d.id} marked as read`
    case 'task_created': return `Task created: ${d.title}`
    case 'task_updated': return `Task ${d.id} → ${d.status}`
    case 'question_asked': return `Question from ${d.from_agent}${d.blocking ? ' (blocking)' : ''}`
    case 'question_answered': return `Question ${d.id} answered`
    default: return event.type
  }
}

export function EventRow({ event }: EventRowProps) {
  const Icon = iconForType(event.type)
  return (
    <div className="flex items-start gap-3 py-2 border-b last:border-b-0">
      <Icon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
      <div className="flex-1 min-w-0">
        <span className="text-xs font-medium">{event.type}</span>
        <span className="ml-2 text-xs text-muted-foreground">{summaryForEvent(event)}</span>
      </div>
      <span className="text-xs text-muted-foreground whitespace-nowrap">
        {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
      </span>
    </div>
  )
}
