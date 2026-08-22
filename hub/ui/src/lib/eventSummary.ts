export function summaryForEvent(type: string, data: Record<string, unknown>): string {
  switch (type) {
    // Hub-side events
    case 'message_created': {
      const route = data.from && data.to ? `${data.from} → ${data.to}` : ''
      const subject = data.subject ? `"${data.subject}"` : ''
      return [route, subject].filter(Boolean).join(': ')
    }
    case 'message_read': return `msg ${data.id} read`
    case 'task_created': return `"${data.title}" assigned to ${data.assignee ?? 'unassigned'}`
    case 'task_updated': {
      const task = data.title ?? data.id ?? data.task_id
      return `${task ? `${task} → ` : ''}${data.status ?? 'updated'}`
    }
    case 'question_asked': {
      const source = data.from_agent ? `from ${data.from_agent}${data.blocking ? ' (blocking)' : ''}: ` : ''
      return `${source}${String(data.question ?? 'waiting for an operator answer').slice(0, 80)}`
    }
    case 'question_answered': return `question ${data.id} answered`
    case 'agent_heartbeat': return `${data.agent} [${data.status}]${data.message ? ` — ${data.message}` : ''}`
    // Both of these carry the only detail worth reading in a field the default branch does not
    // look at, so without a case they render as their own event name twice over.
    case 'permission_denied': return `${data.agent ?? ''} refused ${data.tool_name ?? 'an action'}${data.reason ? `: ${data.reason}` : ''}`
    // Retired: nothing emits `question_not_asked` any more (the unasked-question backstop was
    // removed and its table dropped in 0082). Kept because `event_logs` rows written before then
    // still exist, and the alternative is an old timeline rendering its own event name twice.
    case 'question_not_asked': return `${data.agent} ended a turn on a question it never asked: ${String(data.question ?? '').slice(0, 80)}`
    // CLI-pushed events
    case 'msg_sent': return `${data.from} → ${data.to}${data.subject ? `: "${data.subject}"` : ''} (${data.msg_id})`
    case 'msg_read': return `${data.agent} read ${data.msg_id} from ${data.from}`
    case 'msg_detected': return `${data.from} → ${data.to}: "${data.subject ?? ''}"`
    case 'msg_stale': return `${data.msg_id} unread ${data.minutes_unread}m — re-pinging ${data.to}`
    case 'msg_send_failed': return `FAILED ${data.from} → ${data.to}: "${data.subject ?? ''}" (${data.msg_id})`
    // No second `task_created` here. It duplicated the Hub-side case above, so it was unreachable —
    // esbuild flagged it on every build — and the richer wording it carried never once rendered.
    case 'task_status': return `${data.task_id}: ${data.prev} → ${data.status}`
    case 'task_save_failed': return `FAILED to save task ${data.task_id}: "${data.title}"`
    // A run ended holding work nobody moved. The outcome is what the operator actually needs —
    // whether the Hub did something about it, or is telling them so they can.
    case 'run_diverged': return data.outcome === 'retried'
      ? `${data.agent} ended without moving ${data.task_id} — trying again once`
      : data.outcome === 'escalated'
        ? `${data.agent} ended without moving ${data.task_id} — handed to ${data.response_agent}`
        : `${data.agent} ended without moving ${data.task_id} (${data.task_status})`
    // The opposite of the above, and worded so it cannot be mistaken for it: the agent asked
    // rather than guessed, and the work is waiting on the operator, not on nobody.
    case 'task_blocked': return `${data.agent} is waiting on you before continuing "${data.task_title ?? data.task_id}"`
    case 'task_unblocked': return `your answer released "${data.task_title ?? data.task_id}"`
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
    case 'log_event': return `${(data as Record<string, unknown>).event_type ?? ''}: ${(data as Record<string, unknown>).agent ?? ''}`
    default: {
      // Best-effort: pick any short string field from data
      const val = data.error ?? data.message ?? data.summary ?? data.title ?? ''
      return val ? String(val).slice(0, 120) : type
    }
  }
}
