import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { summaryForEvent } from '@/lib/eventSummary'
import { agentColorVars } from '@/lib/agentColors'
import { tint } from '@/lib/colorTint'
import { hubDate } from '@/lib/hubTime'
import { useCopy } from '@/hooks/useCopy'

interface EventRowProps {
  event: {
    type: string
    data: unknown
    timestamp: string
    severity?: string
    localId: number
  }
  actorName?: string | null
  actorColorIndex?: number | null
}

function iconForType(type: string): string {
  if (type.startsWith('message'))  return 'chat'
  if (type.startsWith('task'))     return 'task_alt'
  if (type.startsWith('question')) return 'help'
  return 'bolt'
}

function containerForType(type: string): { bg: string; color: string } {
  if (type.startsWith('message'))  return { bg: 'var(--surface-3)',  color: 'var(--text-2)' }
  if (type.startsWith('task'))     return { bg: tint('var(--purple)'),  color: 'var(--purple)' }
  if (type.startsWith('question')) return { bg: tint('var(--amber)'),  color: 'var(--amber)' }
  return { bg: 'var(--surface-3)', color: 'var(--text-3)' }
}

const SEVERITY_CHIP: Record<string, { bg: string; color: string }> = {
  error: { bg: tint('var(--red)'), color: 'var(--red)' },
  warn:  { bg: tint('var(--amber)'), color: 'var(--amber)' },
  info:  { bg: 'var(--surface-3)', color: 'var(--text-2)' },
  debug: { bg: 'var(--surface-3)', color: 'var(--text-3)' },
}

const SEVERITY_BORDER: Record<string, string> = {
  error: 'var(--red)',
  warn:  'var(--amber)',
}

export function EventRow({ event, actorName, actorColorIndex }: EventRowProps) {
  const { copied, copy } = useCopy()
  const iconName   = iconForType(event.type)
  const container  = containerForType(event.type)
  const severity   = event.severity ?? 'info'
  const borderClr  = SEVERITY_BORDER[severity]
  const chip       = SEVERITY_CHIP[severity]

  return (
    <div
      className="group flex items-start gap-3 py-2.5 border-b last:border-b-0"
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
        {actorName && (
          <span className="mr-2 inline-flex items-center gap-1 text-xs font-medium">
            <span data-testid={`activity-actor-color-${actorName}`} className="h-1.5 w-1.5 rounded-full" style={{ background: agentColorVars(actorColorIndex).accent }} />
            {actorName}
          </span>
        )}
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

      <button
        type="button"
        className="shrink-0 p-1 opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100"
        onClick={() => copy(JSON.stringify(event, null, 2))}
        aria-label="Copy activity entry"
        title="Copy activity entry"
      >
        <Icon name={copied ? 'check' : 'content_copy'} size={13} style={{ color: copied ? 'var(--green)' : 'var(--text-3)' }} />
      </button>

      {/* Timestamp */}
      <span className="text-[11px] shrink-0" style={{ color: 'var(--text-3)', opacity: 0.6 }}>
        {formatDistanceToNow(hubDate(event.timestamp), { addSuffix: true })}
      </span>
    </div>
  )
}
