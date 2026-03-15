import { useState } from 'react'
import { format } from 'date-fns'
import { ChevronRight, ChevronDown, Copy, Check } from 'lucide-react'
import { EventLogEntry } from '@/api/logs'
import { summaryForEvent } from '@/lib/eventSummary'

interface LogLineProps {
  entry: EventLogEntry
}

const SEVERITY_BADGE: Record<string, string> = {
  error: 'bg-red-500/20 text-red-400 border border-red-500/40 font-bold',
  warn:  'bg-amber-500/20 text-amber-400 border border-amber-500/40 font-bold',
  info:  'bg-sky-500/20 text-sky-400 border border-sky-500/40',
  debug: 'bg-gray-500/20 text-gray-500 border border-gray-600/40',
}

const SEVERITY_BORDER: Record<string, string> = {
  error: 'border-l-2 border-l-red-500',
  warn:  'border-l-2 border-l-amber-500',
  info:  'border-l-transparent border-l-2',
  debug: 'border-l-2 border-l-gray-700',
}

const EVENT_TYPE_COLOR: Record<string, string> = {
  message_created: 'text-violet-400',
  message_read:    'text-violet-300',
  task_created:    'text-cyan-400',
  task_updated:    'text-cyan-300',
  task_status:     'text-cyan-300',
  question_asked:  'text-orange-400',
  question_answered: 'text-orange-300',
  agent_heartbeat: 'text-teal-400',
  transport_error: 'text-red-400',
  watchdog_spawn_failed: 'text-red-400',
  watchdog_agent_exit: 'text-amber-400',
}

export function LogLine({ entry }: LogLineProps) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  const severity = entry.severity ?? 'info'
  const ts = format(new Date(entry.timestamp), 'MMM dd HH:mm:ss.SSS')
  const summary = summaryForEvent(entry.event_type, (entry.data ?? {}) as Record<string, unknown>)
  const hasData = entry.data && Object.keys(entry.data).length > 0
  const typeColor = EVENT_TYPE_COLOR[entry.event_type] ?? 'text-gray-300'

  function handleCopy(e: React.MouseEvent) {
    e.stopPropagation()
    const text = JSON.stringify({ ...entry, data: entry.data }, null, 2)
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div className={`group font-mono text-xs ${SEVERITY_BORDER[severity] ?? SEVERITY_BORDER.info}`}>
      {/* Main row */}
      <div
        className={`flex items-center gap-2 px-2 py-[3px] hover:bg-white/5 cursor-pointer select-none`}
        onClick={() => hasData && setExpanded(!expanded)}
      >
        {/* Expand toggle */}
        <span className="w-3 shrink-0 text-gray-600">
          {hasData
            ? expanded
              ? <ChevronDown className="h-3 w-3" />
              : <ChevronRight className="h-3 w-3" />
            : null}
        </span>

        {/* Timestamp */}
        <span className="text-gray-500 shrink-0 w-[156px]">{ts}</span>

        {/* Severity badge */}
        <span className={`shrink-0 w-12 text-center rounded px-1 text-[10px] uppercase tracking-wide ${SEVERITY_BADGE[severity] ?? SEVERITY_BADGE.info}`}>
          {severity}
        </span>

        {/* Event type */}
        <span className={`shrink-0 w-44 truncate ${typeColor}`}>
          {entry.event_type}
        </span>

        {/* Agent */}
        <span className="shrink-0 w-20 truncate text-emerald-400">
          {entry.agent ?? ''}
        </span>

        {/* Summary */}
        <span className="flex-1 truncate text-gray-300">
          {summary}
        </span>

        {/* Copy button (hover) */}
        <button
          onClick={handleCopy}
          className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-gray-600 hover:text-gray-300 p-0.5"
          title="Copy entry"
        >
          {copied
            ? <Check className="h-3 w-3 text-green-400" />
            : <Copy className="h-3 w-3" />}
        </button>
      </div>

      {/* Expanded JSON */}
      {expanded && hasData && (
        <div className="ml-7 mr-2 mb-1 rounded bg-black/40 border border-white/5 overflow-x-auto">
          <pre className="p-3 text-[11px] leading-relaxed text-gray-300 whitespace-pre">
            {JSON.stringify(entry.data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
