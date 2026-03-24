export function summaryForEvent(type: string, data: Record<string, unknown>): string {
  switch (type) {
    // Hub-side events
    case 'message_created': return `${data.from} → ${data.to}${data.subject ? `: "${data.subject}"` : ''}`
    case 'message_read': return `msg ${data.id} read`
    case 'task_created': return `"${data.title}" assigned to ${data.assignee ?? 'unassigned'}`
    case 'task_updated': return `${data.id} → ${data.status}`
    case 'question_asked': return `from ${data.from_agent}${data.blocking ? ' (blocking)' : ''}: ${String(data.question ?? '').slice(0, 80)}`
    case 'question_answered': return `question ${data.id} answered`
    case 'agent_heartbeat': return `${data.agent} [${data.status}]${data.message ? ` — ${data.message}` : ''}`
    // CLI-pushed events
    case 'msg_sent': return `${data.from} → ${data.to}${data.subject ? `: "${data.subject}"` : ''} (${data.msg_id})`
    case 'msg_read': return `${data.agent} read ${data.msg_id} from ${data.from}`
    case 'msg_detected': return `${data.from} → ${data.to}: "${data.subject ?? ''}"`
    case 'msg_stale': return `${data.msg_id} unread ${data.minutes_unread}m — re-pinging ${data.to}`
    case 'msg_send_failed': return `FAILED ${data.from} → ${data.to}: "${data.subject ?? ''}" (${data.msg_id})`
    case 'task_created': return `"${data.title}" → ${data.assignee ?? 'unassigned'} [${data.priority}]`
    case 'task_status': return `${data.task_id}: ${data.prev} → ${data.status}`
    case 'task_save_failed': return `FAILED to save task ${data.task_id}: "${data.title}"`
    case 'watchdog_started': return `transport=${data.transport}`
    case 'watchdog_stopped': return 'watchdog stopped'
    case 'watchdog_ping': return `→ ${data.agent} for msg ${data.msg_id}`
    case 'watchdog_poll_error': return String(data.error ?? '')
    case 'watchdog_spawn_failed': return `cannot launch ${data.agent}: ${data.error}`
    case 'watchdog_subprocess_error': return `${data.agent}: ${data.error}`
    case 'watchdog_agent_exit': return `${data.agent} exited with code ${data.exit_code}`
    case 'watchdog_heartbeat_failed': return `heartbeat for ${data.agent} failed: ${data.error}`
    case 'watchdog_output_post_failed': return `output post for ${data.agent} failed: ${data.error}`
    case 'watchdog_stderr_drain_failed': return `stderr drain for ${data.agent} failed: ${data.error}`
    case 'ping_skipped': return `${data.agent}: ${data.reason}`
    case 'transport_error': return `${data.method}: ${data.error}`
    case 'log_event': {
      const eventType = (data as Record<string, unknown>).event_type ?? ''
      const agent = (data as Record<string, unknown>).agent ?? ''
      if (eventType === 'yolo_enabled') return `🚀 ${agent} YOLO mode ENABLED`
      if (eventType === 'yolo_disabled') return `🛑 ${agent} YOLO mode disabled`
      return `${eventType}: ${agent}`
    }
    default: {
      // Best-effort: pick any short string field from data
      const val = data.error ?? data.message ?? data.summary ?? data.title ?? ''
      return val ? String(val).slice(0, 120) : type
    }
  }
}
