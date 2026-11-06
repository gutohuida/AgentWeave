/** What closing the app window found running, as the launcher hands it to the page (the Hub's
 *  `GET /api/v1/work/running`, or `{ unknown: true }` when the Hub was up but did not answer).
 *  Change `agentweave-is-its-own-app-on-windows`, D4. */
export interface WorkRunning {
  unknown?: boolean
  running?: boolean
  turns?: number
  check_runs?: number
  landings?: number
  builds?: number
  turn_agents?: Array<{ agent: string; project: string }>
  build_list?: Array<{ id: string; title: string; project: string }>
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

/** "1 agent turn is running", "2 agent turns, 1 check run and the build X are running": the same
 *  words the launcher's native fallback uses (`desktop_window.describe_work`). */
export function describeWork(work: WorkRunning): string {
  if (work.unknown) return 'AgentWeave could not say what is running'
  const parts: string[] = []
  if (work.turns) parts.push(plural(work.turns, 'agent turn', 'agent turns'))
  if (work.check_runs) parts.push(plural(work.check_runs, 'check run', 'check runs'))
  if (work.landings) parts.push(plural(work.landings, 'landing', 'landings'))
  const builds = (work.build_list ?? []).map((b) => b.title).filter(Boolean)
  if (builds.length) parts.push(`${builds.length === 1 ? 'the build' : 'the builds'} ${builds.join(', ')}`)
  else if (work.builds) parts.push(plural(work.builds, 'build', 'builds'))
  if (!parts.length) return 'Work is running'
  const text = parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`
  return `${text[0].toUpperCase()}${text.slice(1)} ${parts.length === 1 ? 'is' : 'are'} running`
}

export type CloseChoice = 'stop' | 'keep' | 'cancel'
