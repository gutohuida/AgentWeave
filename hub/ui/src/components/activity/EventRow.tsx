import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { summaryForEvent } from '@/lib/eventSummary'

interface EventRowProps {
  event: {
    type: string
    data: unknown
    timestamp: string
    severity?: string
    localId: number
  }
}

function iconForType(type: string): string {
  if (type.startsWith('message'))  return 'chat'
  if (type.startsWith('task'))     return 'task_alt'
  if (type.startsWith('question')) return 'help'
  return 'bolt'
}

function containerForType(type: string): { bg: string; color: string } {
  if (type.startsWith('message'))  return { bg: 'var(--surface-3)',  color: 'var(--text-2)' }
  if (type.startsWith('task'))     return { bg: 'rgba(168,85,247,0.1)',  color: 'var(--purple)' }
  if (type.startsWith('question')) return { bg: 'rgba(245,158,11,0.1)',  color: 'var(--amber)' }
  return { bg: 'var(--surface-3)', color: 'var(--text-3)' }
}

const SEVERITY_CHIP: Record<string, { bg: string; color: string }> = {
  error: { bg: 'rgba(239,68,68,0.1)', color: 'var(--red)' },
  warn:  { bg: 'rgba(245,158,11,0.1)', color: 'var(--amber)' },
  debug: { bg: 'var(--surface-3)', color: 'var(--text-3)' },
}

const SEVERITY_BORDER: Record<string, string> = {
  error: 'var(--red)',
  warn:  'var(--amber)',
}

export function EventRow({ event }: EventRowProps) {
  const iconName   = iconForType(event.type)
  const container  = containerForType(event.type)
  const severity   = event.severity ?? 'info'
  const borderClr  = SEVERITY_BORDER[severity]
  const chip       = SEVERITY_CHIP[severity]

  return (
    <div
      className="flex items-start gap-3 py-2.5 border-b last:border-b-0"
      style={{
        borderBottomColor: 'var(--border)',
        ...(borderClr ? { borderLeft: `2px solid ${borderClr}`, paddingLeft: 10 } : {}),
      }}
    >
      {/* Icon */}
      <div
        className="shrink-0 flex items-center justify-center rounded-full"
        style={{ width: 36, height: 36, background: container.bg, color: container.color }}
      >
        <Icon name={iconName} size={18} />
      </div>

      {/* Text */}
      <div className="flex-1 min-w-0">
        <span className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>{event.type}</span>
        <span className="ml-2 text-xs" style={{ color: 'var(--text-3)' }}>
          {summaryForEvent(event.type, event.data as Record<string, unknown>)}
        </span>
      </div>

      {/* Severity chip */}
      {chip && (
        <span
          className="text-[10px] font-medium capitalize shrink-0 rounded px-1.5 py-0.5"
          style={{ background: chip.bg, color: chip.color }}
        >
          {severity}
        </span>
      )}

      {/* Timestamp */}
      <span className="text-[11px] shrink-0" style={{ color: 'var(--text-3)', opacity: 0.6 }}>
        {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
      </span>
    </div>
  )
}
