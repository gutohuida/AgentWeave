/** Which Hub events call the operator, and what each says.
 *
 *  Change `agentweave-calls-you-with-its-own-sound`. The kinds are the brand's notification sounds
 *  (brand/sound/README.md): `ask` when an agent needs the operator, `fail` when work stalled or
 *  failed, `done` when a loop drained its queue, `reply` when an agent finished a turn the operator
 *  started in a conversation (operator, 2026-10-23). Everything else on the stream stays silent. The
 *  payload shapes are the ones the Hub broadcasts; `project_id` is stamped by hub/hub/sse.py. */
export type NotifyKind = 'ask' | 'fail' | 'done' | 'reply'

export interface Notice {
  kind: NotifyKind
  projectId: string
  text: string
  /** A reply's conversation, so its toast opens it and the app can tell it is already in view. */
  conversationId?: string
  agent?: string
}

/** loop_ending.QUEUE_DRAINED_REASON: the one stop that is finished work, not a failure. */
const QUEUE_DRAINED_REASON = 'loop queue is empty'

type Payload = Record<string, unknown>

function str(d: Payload, key: string): string {
  const v = d[key]
  return typeof v === 'string' ? v : ''
}

function textFor(type: string, d: Payload): { kind: NotifyKind; text: string; conversationId?: string; agent?: string } | null {
  switch (type) {
    case 'run_completed': {
      // Only a turn the operator started: `initiator` is the run's own ("operator" when the
      // operator's message controlled the turn, "autonomous" for a flow's, a job's or a peer's).
      // Every other completed run is everyday traffic.
      const conversationId = str(d, 'conversation_id')
      if (str(d, 'initiator') !== 'operator' || !conversationId) return null
      const agent = str(d, 'agent') || 'An agent'
      return { kind: 'reply', text: `${agent} replied`, conversationId, agent }
    }
    case 'question_asked':
      return { kind: 'ask', text: `${str(d, 'from_agent') || 'An agent'} asked you a question` }
    case 'permission_requested': {
      const tool = str(d, 'tool_name')
      return { kind: 'ask', text: `${str(d, 'agent') || 'An agent'} wants permission${tool ? ` for ${tool}` : ''}` }
    }
    case 'stall_recorded':
      return { kind: 'fail', text: str(d, 'reason') ? `Work stalled: ${str(d, 'reason')}` : 'Work stalled' }
    case 'run_failed':
      return { kind: 'fail', text: `${str(d, 'agent') || 'An agent'}'s run failed` }
    case 'queue_chain_suspended':
      return { kind: 'fail', text: `A message chain to ${str(d, 'agent') || 'an agent'} was suspended` }
    case 'loop_stopped': {
      const reason = str(d, 'reason')
      if (reason === QUEUE_DRAINED_REASON) return { kind: 'done', text: 'A loop finished its queue' }
      return { kind: 'fail', text: reason ? `A loop stopped: ${reason}` : 'A loop stopped' }
    }
    default:
      return null
  }
}

export function classify(type: string, data: unknown): Notice | null {
  if (!data || typeof data !== 'object') return null
  const d = data as Payload
  const projectId = str(d, 'project_id')
  if (!projectId) return null
  const found = textFor(type, d)
  if (!found) return null
  const text = found.text.length > 140 ? `${found.text.slice(0, 139)}…` : found.text
  const notice: Notice = { kind: found.kind, projectId, text }
  if (found.conversationId) notice.conversationId = found.conversationId
  if (found.agent) notice.agent = found.agent
  return notice
}
