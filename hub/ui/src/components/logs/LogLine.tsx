import { useState } from 'react'
import { format } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { useCopy } from '@/hooks/useCopy'
import { summaryForEvent } from '@/lib/eventSummary'
import { tint } from '@/lib/colorTint'
import { hubDate } from '@/lib/hubTime'

interface LogLineProps {
  entry: {
    id: string
    event_type: string
    severity?: string
    timestamp: string
    agent?: string
    data?: Record<string, unknown>
  }
  /** True only for the render that follows this row's arrival — see LogsView's arrival tracking. */
  isNew?: boolean
}

const SEVERITY_CHIP: Record<string, { bg: string; color: string }> = {
  error: { bg: tint('var(--red)'), color: 'var(--red)' },
  warn:  { bg: tint('var(--amber)'), color: 'var(--amber)' },
  info:  { bg: 'var(--surface-3)', color: 'var(--text-2)' },
  debug: { bg: 'var(--surface-3)', color: 'var(--text-3)' },
}

const SEVERITY_BORDER_COLOR: Record<string, string> = {
  error: 'var(--red)',
  warn:  'var(--amber)',
}

const EVENT_TYPE_COLOR: Record<string, string> = {
  message_created:       'var(--blue)',
  message_read:          'var(--blue)',
  task_created:          'var(--purple)',
  task_updated:          'var(--purple)',
  task_status:           'var(--purple)',
  question_asked:        'var(--amber)',
  question_answered:     'var(--amber)',
  agent_heartbeat:       'var(--text-3)',
  transport_error:       'var(--red)',
  watchdog_spawn_failed: 'var(--red)',
  watchdog_agent_exit:   'var(--amber)',
}

export function LogLine({ entry, isNew = false }: LogLineProps) {
  const [expanded, setExpanded] = useState(false)
  const { copied, copy } = useCopy()

  const severity  = entry.severity ?? 'info'
  const ts        = format(hubDate(entry.timestamp), 'MMM dd HH:mm:ss.SSS')
  const summary   = summaryForEvent(entry.event_type, (entry.data ?? {}) as Record<string, unknown>)
  const hasData   = entry.data && Object.keys(entry.data).length > 0
  const chip      = SEVERITY_CHIP[severity] ?? SEVERITY_CHIP.info
  const borderClr = SEVERITY_BORDER_COLOR[severity]
  const typeColor = EVENT_TYPE_COLOR[entry.event_type]

  function handleCopy(e: React.MouseEvent) {
    e.stopPropagation()
    copy(JSON.stringify({ ...entry, data: entry.data }, null, 2))
  }

  function toggleExpanded() {
    if (hasData) setExpanded((value) => !value)
  }

  return (
    <div
      className="group font-mono text-xs"
      style={{
        borderLeft: borderClr ? `2px solid ${borderClr}` : '2px solid transparent',
        fontFamily: "'JetBrains Mono', monospace",
      }}
    >
      <div
        // Hover and focus live in CSS (`.log-row-main`), not in a mouse handler: the handler this
        // replaced could not fire for a keyboard user, so a focused row got a ring and no fill.
        className={`log-row-main flex items-center gap-2 px-2 py-[3px] select-none cursor-pointer${isNew ? ' is-new' : ''}`}
        style={{ color: 'var(--text)' }}
        onClick={toggleExpanded}
        onKeyDown={(event) => {
          if (!hasData || (event.key !== 'Enter' && event.key !== ' ')) return
          event.preventDefault()
          toggleExpanded()
        }}
        role={hasData ? 'button' : undefined}
        tabIndex={hasData ? 0 : undefined}
        aria-expanded={hasData ? expanded : undefined}
        aria-label={hasData ? `${expanded ? 'Collapse' : 'Expand'} ${entry.event_type} log entry` : undefined}
      >
        <span className="w-3 shrink-0" style={{ color: 'var(--text-3)', opacity: 0.6 }}>
          {hasData && (
            <span style={{ display: 'flex', transform: expanded ? 'rotate(90deg)' : undefined, transition: 'transform var(--dur-fast) var(--ease)' }}><Icon name="chevron_right" size={14} /></span>
          )}
        </span>
        <span className="shrink-0 w-[156px]" style={{ color: 'var(--text-3)', opacity: 0.7 }}>{ts}</span>
        <span
          className="shrink-0 w-12 text-center rounded px-1 text-[10px] uppercase"
          style={{ background: chip.bg, color: chip.color }}
        >
          {severity}
        </span>
        <span className="shrink-0 w-44 truncate" style={{ color: typeColor ?? 'var(--text)' }}>
          {entry.event_type}
        </span>
        <span className="shrink-0 w-20 truncate" style={{ color: 'var(--text-3)' }}>
          {entry.agent ?? ''}
        </span>
        <span className="flex-1 truncate" style={{ color: 'var(--text)' }}>
          {summary}
        </span>
        <button
          onClick={handleCopy}
          className="shrink-0 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity p-0.5"
          style={{ color: 'var(--text-3)' }}
          title="Copy entry"
        >
          {/* Green, matching EventRow's identical confirmation: --blue is focus/selection, and a
              copy succeeding is a state, not a selection. */}
          <Icon name={copied ? 'check' : 'content_copy'} size={14} style={{ color: copied ? 'var(--green)' : undefined }} />
        </button>
      </div>

      {expanded && hasData && (
        <div
          className="ml-7 mr-2 mb-1 rounded-lg overflow-x-auto"
          style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
        >
          <pre className="p-3 text-[11px] leading-relaxed whitespace-pre" style={{ color: 'var(--text)', fontFamily: "'JetBrains Mono', monospace" }}>
            {JSON.stringify(entry.data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
