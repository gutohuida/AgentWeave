import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { SSEEvent } from '@/hooks/useSSE'
import { summaryForEvent } from '@/lib/eventSummary'

interface EventRowProps {
  event: SSEEvent & { localId: number }
}

function iconForType(type: string): string {
  if (type.startsWith('message'))  return 'chat'
  if (type.startsWith('task'))     return 'task_alt'
  if (type.startsWith('question')) return 'help'
  return 'bolt'
}

function containerForType(type: string): { bg: string; color: string } {
  if (type.startsWith('message'))  return { bg: 'var(--p-cont)',  color: 'var(--on-p-cont)' }
  if (type.startsWith('task'))     return { bg: 'var(--s-cont)',  color: 'var(--on-s-cont)' }
  if (type.startsWith('question')) return { bg: 'var(--t-cont)',  color: 'var(--on-t-cont)' }
  return { bg: 'var(--surface-highest)', color: 'var(--on-sv)' }
}

const SEVERITY_CHIP: Record<string, { bg: string; color: string }> = {
  error: { bg: 'var(--error-cont)', color: 'var(--on-error-cont)' },
  warn:  { bg: 'var(--t-cont)',     color: 'var(--on-t-cont)' },
  debug: { bg: 'var(--surface-highest)', color: 'var(--on-sv)' },
}

const SEVERITY_BORDER: Record<string, string> = {
  error: 'border-l-2 pl-2',
  warn:  'border-l-2 pl-2',
}

const SEVERITY_BORDER_COLOR: Record<string, string> = {
  error: 'var(--destructive)',
  warn:  'var(--t-cont)',
}

export function EventRow({ event }: EventRowProps) {
  const iconName   = iconForType(event.type)
  const container  = containerForType(event.type)
  const severity   = event.severity ?? 'info'
  const borderCls  = SEVERITY_BORDER[severity] ?? ''
  const borderClr  = SEVERITY_BORDER_COLOR[severity]
  const chip       = SEVERITY_CHIP[severity]

  return (
    <div
      className={`flex items-start gap-3 py-2.5 border-b last:border-b-0 ${borderCls}`}
      style={{
        borderBottomColor: 'var(--outline-variant)',
        borderLeftColor:   borderClr,
      }}
    >
      {/* Icon in tonal container */}
      <div
        className="m3-icon-container shrink-0"
        style={{ width: 36, height: 36, background: container.bg, color: container.color }}
      >
        <Icon name={iconName} size={18} />
      </div>

      {/* Text */}
      <div className="flex-1 min-w-0">
        <span className="m3-label-large" style={{ color: 'var(--foreground)' }}>{event.type}</span>
        <span className="ml-2 m3-body-small" style={{ color: 'var(--on-sv)' }}>
          {summaryForEvent(event.type, event.data as Record<string, unknown>)}
        </span>
      </div>

      {/* Severity chip (only non-info) */}
      {chip && (
        <span
          className="m3-chip m3-label-small capitalize shrink-0"
          style={{ background: chip.bg, color: chip.color }}
        >
          {severity}
        </span>
      )}

      {/* Timestamp */}
      <span className="m3-label-small shrink-0" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
        {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
      </span>
    </div>
  )
}
