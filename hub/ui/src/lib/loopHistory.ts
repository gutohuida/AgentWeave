import type { LoopDetail } from '@/api/loops'

export type LoopEvent = LoopDetail['events'][number]

interface Actor {
  kind?: string
  agent?: string | null
  run_id?: string | null
}

/** Who did it: the operator, or the agent with the run it acted in. Events written before the actor
 *  was recorded (and every other event type) carry only the `agent` column. */
function who(event: LoopEvent): string {
  const by = (event.data.by ?? null) as Actor | null
  if (by?.kind === 'operator') return 'The operator'
  if (by?.kind === 'agent' && by.agent) {
    return by.run_id ? `${by.agent} (run ${by.run_id})` : by.agent
  }
  return event.agent ? event.agent : 'The Hub'
}

const SOURCE_PHRASE: Record<string, string> = {
  initial_tasks: 'as its first tasks',
  create_task: 'to its queue',
  document: "from the loop's document",
  flow_built: 'when its flow was built',
}

/** One event as a sentence naming who did what; the caller adds when. */
export function loopEventSentence(event: LoopEvent): string {
  const data = event.data
  if (event.event_type === 'loop_created') {
    const door = data.door === 'approval' ? 'by approving a document' : 'from the jobs page'
    const document = typeof data.document_path === 'string' ? ` from ${data.document_path}` : ''
    const purpose = typeof data.purpose === 'string' && data.purpose ? `, to ${data.purpose}` : ''
    return `${who(event)} created this loop ${door}, for ${String(data.agent ?? 'an agent')}${document}${purpose}.`
  }
  if (event.event_type === 'loop_tasks_added') {
    const tasks = (Array.isArray(data.tasks) ? data.tasks : []) as Array<{ title?: string }>
    const titles = tasks.map((task) => `"${task.title ?? ''}"`).join(', ')
    const phrase = SOURCE_PHRASE[String(data.source)] ?? 'to its queue'
    return `${who(event)} added ${tasks.length === 1 ? '1 task' : `${tasks.length} tasks`} ${phrase}: ${titles}.`
  }
  const label = event.event_type.replace(/_/g, ' ')
  return event.agent ? `${label} (${event.agent}).` : `${label}.`
}
