import type { AgentOutputLine, StreamEventKind } from '@/api/agents'

const KINDS = new Set<StreamEventKind>([
  'text', 'thinking', 'tool_use', 'tool_result', 'status', 'diagnostic', 'error',
])

export interface SemanticStreamEvent extends AgentOutputLine {
  kind: StreamEventKind
  legacy: boolean
  callId?: string
}

export function normalizeStreamEvent(line: AgentOutputLine): SemanticStreamEvent {
  let kind = line.kind && KINDS.has(line.kind) ? line.kind : undefined
  if (!kind) {
    const text = line.content.toLowerCase()
    if (text.startsWith('[thinking]')) kind = 'thinking'
    else if (text.startsWith('[tool]') || text.startsWith('[tool_use]')) kind = 'tool_use'
    else if (text.startsWith('[tool_result]')) kind = 'tool_result'
    else if (text.startsWith('[stderr]') || text.startsWith('[watchdog]') || text.startsWith('[session:')) kind = 'diagnostic'
    else if (text.startsWith('[error]') || text.includes('❌')) kind = 'error'
    else if (text.startsWith('[done]') || text.startsWith('[status]')) kind = 'status'
    else kind = 'text'
  }
  const callId = typeof line.payload?.call_id === 'string' ? line.payload.call_id : undefined
  return { ...line, kind, legacy: !line.kind, callId }
}

export function streamActivityEvents(lines: AgentOutputLine[]): SemanticStreamEvent[] {
  return lines.map(normalizeStreamEvent).filter((event) =>
    event.kind === 'status' || event.kind === 'diagnostic' || event.kind === 'error' ||
    event.kind === 'tool_use' || event.kind === 'tool_result',
  )
}

export function formatStreamDuration(start: string, end: string): string {
  const seconds = Math.max(0, (Date.parse(end) - Date.parse(start)) / 1000)
  return seconds < 1 ? '<1s' : `${Math.round(seconds)}s`
}
