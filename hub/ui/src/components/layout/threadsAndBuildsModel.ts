import type { AgentConversation } from '@/api/agentChat'

/** What a build needs from the operator, as `GET /builds` is to report it (D2 of
 *  profiles-threads-and-builds-everywhere): "stopped" first, otherwise its first task's need. */
export interface BuildNeed {
  kind: 'stopped' | 'stalled' | 'question' | 'gave-up'
  text: string
}

/** One build as the sidebar lists it: running, or needing the operator and not dismissed. */
export interface SidebarBuild {
  id: string
  document_title: string
  state: 'running' | 'stopped' | 'finished'
  tasks_total: number
  tasks_done: number
  needs_operator: BuildNeed | null
}

/** Where one of the list's two sources stands. A failed route is never shown as an empty list. */
export type ListState = 'loading' | 'error' | 'ready'

/** How many threads show before the rest go behind "Show more", and past which a filter appears. */
export const THREADS_DISPLAY_CAP = 15

export const NEED_WORD: Record<BuildNeed['kind'], string> = {
  stopped: 'Stopped',
  stalled: 'Stalled',
  question: 'Question',
  'gave-up': 'Given up',
}

/** The one-word status a build row shows on its right. */
export function buildStatusWord(build: SidebarBuild): string {
  return build.needs_operator ? NEED_WORD[build.needs_operator.kind] : `${build.tasks_done}/${build.tasks_total}`
}

/** The build row's accessible name: stable words, no ticking time, so drives can find it. */
export function buildAccessibleName(build: SidebarBuild): string {
  const progress = `${build.tasks_done} of ${build.tasks_total} tasks done`
  const state = build.needs_operator ? `${NEED_WORD[build.needs_operator.kind].toLowerCase()}, needs you` : 'running'
  return `Build: ${build.document_title}, ${progress}, ${state}`
}

/** Builds that need the operator first, then running ones; each group keeps the route's order. */
export function orderBuilds(builds: SidebarBuild[]): SidebarBuild[] {
  return [...builds.filter((b) => b.needs_operator), ...builds.filter((b) => !b.needs_operator)]
}

/** Threads waiting on the operator rise; the rest keep the route's order (newest activity first). */
export function orderThreads(threads: AgentConversation[]): AgentConversation[] {
  return [...threads.filter((t) => t.attention === 'waiting'), ...threads.filter((t) => t.attention !== 'waiting')]
}

/** Case-insensitive match on a thread's title or its profile's name. */
export function filterThreads(threads: AgentConversation[], query: string): AgentConversation[] {
  const q = query.trim().toLowerCase()
  if (!q) return threads
  return threads.filter((t) => (t.title ?? '').toLowerCase().includes(q) || t.agent.toLowerCase().includes(q))
}

/**
 * Keeps rows where they were while the pointer is over the list: rows already shown keep their
 * positions, rows that left are dropped, and new rows join at the end. Without it a live update
 * could move the row under a click that is already on its way (vault note P14).
 */
export function holdOrder<T extends { id: string }>(previous: string[], next: T[]): T[] {
  const byId = new Map(next.map((item) => [item.id, item]))
  const kept = previous.filter((id) => byId.has(id)).map((id) => byId.get(id)!)
  const keptIds = new Set(previous)
  return [...kept, ...next.filter((item) => !keptIds.has(item.id))]
}
