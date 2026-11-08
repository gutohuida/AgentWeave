/** The notice the Hub publishes for an event that calls the operator.
 *
 *  Change `windows-notifications-for-what-calls-the-operator`: which Hub events call the operator,
 *  and what each says, is decided once, in hub/hub/operator_notices.py, and published as an
 *  `operator_notice` event beside the event itself. The page draws its toast from that notice, so
 *  the in-app toast and a Windows notification cannot drift apart. The kinds are the brand's
 *  notification sounds (brand/sound/README.md): `ask` when an agent needs the operator, `fail` when
 *  work stalled or failed, `done` when something finished, `reply` when an agent finished a turn the
 *  operator started in a conversation. `project_id` is stamped by hub/hub/sse.py. */
export type NotifyKind = 'ask' | 'fail' | 'done' | 'reply'

export interface Notice {
  /** Stable per event; what the page and the Windows notifier de-duplicate by. */
  id?: string
  kind: NotifyKind
  projectId: string
  text: string
  /** The conversation the notice belongs to, so its toast opens it. */
  conversationId?: string
  agent?: string
}

export const NOTICE_EVENT = 'operator_notice'

const KINDS: readonly string[] = ['ask', 'fail', 'done', 'reply']

type Payload = Record<string, unknown>

function str(d: Payload, key: string): string {
  const v = d[key]
  return typeof v === 'string' ? v : ''
}

/** The notice an `operator_notice` event carries, or null for any other event. */
export function noticeFrom(type: string, data: unknown): Notice | null {
  if (type !== NOTICE_EVENT || !data || typeof data !== 'object') return null
  const d = data as Payload
  const kind = str(d, 'kind')
  const projectId = str(d, 'project_id')
  const text = str(d, 'text')
  if (!KINDS.includes(kind) || !projectId || !text) return null
  const notice: Notice = { kind: kind as NotifyKind, projectId, text }
  if (str(d, 'id')) notice.id = str(d, 'id')
  if (str(d, 'conversation_id')) notice.conversationId = str(d, 'conversation_id')
  if (str(d, 'agent')) notice.agent = str(d, 'agent')
  return notice
}
