import { formatDistanceToNow } from 'date-fns'
import { MessageSquare, CheckSquare, HelpCircle, Zap } from 'lucide-react'
import { SSEEvent } from '@/hooks/useSSE'
import { summaryForEvent } from '@/lib/eventSummary'

interface EventRowProps {
  event: SSEEvent & { localId: number }
}

function iconForType(type: string) {
  if (type.startsWith('message')) return MessageSquare
  if (type.startsWith('task')) return CheckSquare
  if (type.startsWith('question')) return HelpCircle
  return Zap
}

const SEVERITY_BADGE: Record<string, string> = {
  error: 'bg-red-500/15 text-red-400 ring-1 ring-red-500/20',
  warn:  'bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/20',
  info:  'bg-primary/15 text-primary ring-1 ring-primary/20',
  debug: 'bg-zinc-700/50 text-zinc-400 ring-1 ring-zinc-600/30',
}

const SEVERITY_ROW: Record<string, string> = {
  error: 'border-l-2 border-l-red-500 bg-red-500/[0.03] pl-2',
  warn:  'border-l-2 border-l-amber-500 bg-amber-500/[0.03] pl-2',
}

export function EventRow({ event }: EventRowProps) {
  const Icon = iconForType(event.type)
  const severity = event.severity ?? 'info'
  const rowClass = SEVERITY_ROW[severity] ?? ''
  const badgeClass = SEVERITY_BADGE[severity] ?? SEVERITY_BADGE.info

  return (
    <div className={`flex items-start gap-3 py-2 border-b border-zinc-800/60 last:border-b-0 ${rowClass}`}>
      <Icon className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-zinc-500" />
      <div className="flex-1 min-w-0">
        <span className="text-xs font-medium text-zinc-300">{event.type}</span>
        <span className="ml-2 text-xs text-zinc-500">{summaryForEvent(event.type, event.data as Record<string, unknown>)}</span>
      </div>
      {severity !== 'info' && (
        <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium capitalize ${badgeClass}`}>
          {severity}
        </span>
      )}
      <span className="text-xs text-zinc-600 whitespace-nowrap">
        {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
      </span>
    </div>
  )
}
