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
    // The queue family. All three carry their only readable detail in a field the default branch
    // does not look at (`reason`, `released_from_depth`), so without a case each rendered as its
    // own event name and nothing else — the same failure `permission_denied` above is a case for.
    // `queue_entry_abandoned` is the one that costs something: it is the durable record that an
    // operator's or an agent's input was dropped, and it was the only record.
    case 'queue_entry_abandoned': return `${data.agent ?? 'an agent'} never received a message — ${String(data.reason ?? `delivery failed ${data.attempts ?? 'several'} times`)}`
    case 'queue_agent_paused': return `${data.agent ?? 'an agent'} is paused: ${String(data.reason ?? 'the workspace is unavailable')}`
    case 'queue_entry_released': return `${data.agent ?? 'an agent'}'s held message was continued from hop ${data.released_from_depth}`
    // A context reading carries its whole meaning in `percent`/`context_tokens`/`limit_tokens`,
    // and the default branch looks at none of them — so the most frequent row in a live timeline
    // rendered as the bare string `context_warning`, with the measurement nowhere. Nothing is
    // invented here either: a sample whose model the catalog does not declare keeps a null
    // `percent` (see `resolve_usage_limit`), and reports the raw count it does have.
    case 'context_warning': {
      const who = String(data.agent ?? 'an agent')
      const model = typeof data.model === 'string' && data.model ? ` (${data.model})` : ''
      if (typeof data.percent === 'number') {
        const of = typeof data.context_tokens === 'number' && typeof data.limit_tokens === 'number'
          ? `, ${data.context_tokens} of ${data.limit_tokens} tokens`
          : ''
        return `${who} is at ${data.percent}% of its context window${of}${model}`
      }
      if (typeof data.context_tokens === 'number') {
        return `${who} has used ${data.context_tokens} context tokens${model}`
      }
      return `${who}: a context reading with no measurement${model}`
    }
    // F105, the failure family. Swept out of the Hub's own `persist_event` call sites rather than
    // found one row at a time — which is how the five families before it were each discovered, and
    // the reason that method is not good enough. Every kind below is written to `event_logs`, so it
    // certainly reaches this timeline, and every one names its detail `reason`, `error_summary` or
    // `run_exit_status` — never `error` or `message`, the only two names the default branch knows.
    // Each rendered as its own event name and nothing else, so an operator scanning a red row
    // learned that a red row existed and had to go elsewhere to learn anything more.
    //
    // Kinds whose payload already carries `error` (`conversation_binding_conflict`) are
    // deliberately NOT here: the default branch renders them correctly as it stands.
    case 'job_run_failed': {
      const job = data.job_name ? `"${data.job_name}"` : String(data.job_id ?? 'a job')
      const who = data.agent ? ` for ${data.agent}` : ''
      return `${job} failed${who}${data.error_summary ? `: ${data.error_summary}` : ''}`
    }
    case 'job_run_skipped': {
      const job = data.job_name ? `"${data.job_name}"` : String(data.job_id ?? 'a job')
      return `${job} skipped${data.reason ? `: ${data.reason}` : ''}`
    }
    case 'agent_action_rejected': {
      const where = String(data.endpoint ?? 'an action')
      const target = data.recipient ? ` (${data.recipient})` : ''
      return `${where} refused${data.reason ? `: ${data.reason}` : ''}${target}`
    }
    // Deliberately not worded like `run_diverged`: that one is about a task nobody moved, this one
    // about a document nobody changed, and an operator reading a timeline should not have to tell
    // two identically-worded rows apart.
    case 'turn_produced_nothing': {
      const status = data.run_exit_status ? ` (${data.run_exit_status})` : ''
      const doc = data.spec_document ? ` ${data.spec_document}` : ' anything'
      return `${data.agent ?? 'an agent'} ended${status} without changing${doc}`
    }
    case 'review_unstaffed':
      return `no agent could review ${data.task_id ?? 'a task'}${data.reason ? `: ${data.reason}` : ''}`
    case 'loop_stopped':
      return `loop ${data.loop_id ?? data.job_id} stopped${data.reason ? `: ${data.reason}` : ''}`
    case 'loop_queue_exhausted':
      return `loop ${data.loop_id ?? data.job_id} has no queued work left`
    // The counts are the whole point: an operator wants to know whether a crash dropped anything,
    // and `abandoned_entry_ids` is the list nothing will ever pick up again.
    case 'run_interrupted': {
      const requeued = Array.isArray(data.returned_entry_ids) ? data.returned_entry_ids.length : 0
      const dropped = Array.isArray(data.abandoned_entry_ids) ? data.abandoned_entry_ids.length : 0
      return `${data.agent ?? 'an agent'}'s run was interrupted — ${requeued} message${requeued === 1 ? '' : 's'} requeued, ${dropped} dropped`
    }
    case 'queue_chain_suspended':
      return `${data.agent ?? 'an agent'}: chain suspended at hop ${data.hop_depth} of a ${data.hop_budget}-hop budget`
    case 'task_worktree_release_failed':
      return `${data.task_id ?? 'a task'}: worktree not released${data.reason ? ` — ${data.reason}` : ''}`
    case 'agent_heartbeat': return `${data.agent} [${data.status}]${data.message ? ` — ${data.message}` : ''}`
    // The wording is the requirement, not a style choice: this row says a write *landed*
    // somewhere else, and the product never calls it an escape, a violation or a breach. It is
    // recorded rather than prevented, and a row that sounded like a refusal would claim a wall
    // the product does not have. `destination_name` is the whole point of the notice for the
    // kinds that have one — "wrote into bob's workspace" is a different fact to "wrote outside".
    case 'agent_wrote_outside_workspace': {
      const named: Record<string, string> = { agent: 'workspace', task: 'task checkout', review: 'review checkout' }
      const kind = String(data.destination_kind ?? '')
      const where = named[kind] && data.destination_name
        ? `${data.destination_name}'s ${named[kind]}`
        : kind === 'project' ? 'the project directory'
        : kind === 'hub' ? "the Hub's own directory"
        : 'outside its workspace'
      return `${data.agent ?? 'an agent'} wrote ${where === 'outside its workspace' ? where : `outside its workspace, into ${where}`}${data.path ? `: ${data.tool ?? 'a tool'} → ${data.path}` : ''}`
    }
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
    // The close to `run_diverged`, and deliberately its own kind rather than a `resolved` flag on
    // that one — a consumer filtering by event kind (this timeline, a future count) would tally a
    // resolution as a new divergence otherwise.
    case 'run_divergence_resolved': return `${data.count} open divergence${data.count === 1 ? '' : 's'} on ${data.task_id} resolved`
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
