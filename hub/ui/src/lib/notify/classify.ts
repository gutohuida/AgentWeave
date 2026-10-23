/** Which Hub events call the operator, and what each says.
 *
 *  Change `agentweave-calls-you-with-its-own-sound`. The kinds are the brand's notification sounds
 *  (brand/sound/README.md): `ask` when an agent needs the operator, `fail` when work stalled or
 *  failed, `done` when a loop drained its queue. Everything else on the stream stays silent. The
 *  payload shapes are the ones the Hub broadcasts; `project_id` is stamped by hub/hub/sse.py. */
export type NotifyKind = 'ask' | 'fail' | 'done'

export interface Notice {
  kind: NotifyKind
  projectId: string
  text: string
}

/** loop_ending.QUEUE_DRAINED_REASON: the one stop that is finished work, not a failure. */
const QUEUE_DRAINED_REASON = 'loop queue is empty'

type Payload = Record<string, unknown>

function str(d: Payload, key: string): string {
  const v = d[key]
  return typeof v === 'string' ? v : ''
}

function textFor(type: string, d: Payload): { kind: NotifyKind; text: string } | null {
  switch (type) {
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
  return { kind: found.kind, projectId, text }
}
