import { useState } from 'react'
import { format } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { useCopy } from '@/hooks/useCopy'
import { EventLogEntry } from '@/api/logs'
import { summaryForEvent } from '@/lib/eventSummary'

interface LogLineProps {
  entry: EventLogEntry
}

const SEVERITY_CHIP: Record<string, { bg: string; color: string }> = {
  error: { bg: 'var(--error-cont)',      color: 'var(--on-error-cont)' },
  warn:  { bg: 'var(--t-cont)',          color: 'var(--on-t-cont)' },
  info:  { bg: 'var(--p-cont)',          color: 'var(--on-p-cont)' },
  debug: { bg: 'var(--surface-highest)', color: 'var(--on-sv)' },
}

const SEVERITY_BORDER_COLOR: Record<string, string> = {
  error: 'var(--destructive)',
  warn:  'var(--t-cont)',
}

const EVENT_TYPE_COLOR: Record<string, string> = {
  message_created:       'var(--primary)',
  message_read:          'var(--primary)',
  task_created:          'var(--s-cont)',
  task_updated:          'var(--s-cont)',
  task_status:           'var(--s-cont)',
  question_asked:        'var(--t-cont)',
  question_answered:     'var(--t-cont)',
  agent_heartbeat:       'var(--on-sv)',
  transport_error:       'var(--destructive)',
  watchdog_spawn_failed: 'var(--destructive)',
  watchdog_agent_exit:   'var(--on-t-cont)',
}

export function LogLine({ entry }: LogLineProps) {
  const [expanded, setExpanded] = useState(false)
  const { copied, copy } = useCopy()

  const severity  = entry.severity ?? 'info'
  const ts        = format(new Date(entry.timestamp), 'MMM dd HH:mm:ss.SSS')
  const summary   = summaryForEvent(entry.event_type, (entry.data ?? {}) as Record<string, unknown>)
  const hasData   = entry.data && Object.keys(entry.data).length > 0
  const chip      = SEVERITY_CHIP[severity] ?? SEVERITY_CHIP.info
  const borderClr = SEVERITY_BORDER_COLOR[severity]
  const typeColor = EVENT_TYPE_COLOR[entry.event_type]

  function handleCopy(e: React.MouseEvent) {
    e.stopPropagation()
    copy(JSON.stringify({ ...entry, data: entry.data }, null, 2))
  }

  return (
    <div
      className="group font-mono text-xs"
      style={{ borderLeft: borderClr ? `2px solid ${borderClr}` : '2px solid transparent' }}
    >
      <div
        className="flex items-center gap-2 px-2 py-[3px] row-hover select-none transition-colors"
        onClick={() => hasData && setExpanded(!expanded)}
      >
        <span className="w-3 shrink-0" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
          {hasData && (
            <Icon name={expanded ? 'expand_more' : 'chevron_right'} size={12} />
          )}
        </span>
        <span className="shrink-0 w-[156px]" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>{ts}</span>
        <span
          className="shrink-0 w-12 text-center rounded px-1 m3-label-small uppercase"
          style={{ background: chip.bg, color: chip.color }}
        >
          {severity}
        </span>
        <span className="shrink-0 w-44 truncate" style={{ color: typeColor ?? 'var(--foreground)' }}>
          {entry.event_type}
        </span>
        <span className="shrink-0 w-20 truncate" style={{ color: 'var(--on-sv)' }}>
          {entry.agent ?? ''}
        </span>
        <span className="flex-1 truncate" style={{ color: 'var(--foreground)' }}>
          {summary}
        </span>
        <button
          onClick={handleCopy}
          className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity p-0.5"
          style={{ color: 'var(--on-sv)' }}
          title="Copy entry"
        >
          <Icon name={copied ? 'check' : 'content_copy'} size={12} style={{ color: copied ? 'var(--primary)' : undefined }} />
        </button>
      </div>

      {expanded && hasData && (
        <div
          className="ml-7 mr-2 mb-1 rounded-xl overflow-x-auto"
          style={{ background: 'var(--surface-highest)', border: '1px solid var(--outline-variant)' }}
        >
          <pre className="p-3 text-[11px] leading-relaxed whitespace-pre" style={{ color: 'var(--foreground)' }}>
            {JSON.stringify(entry.data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
