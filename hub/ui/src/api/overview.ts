import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** The one Overview read (`GET /api/v1/projects/{id}/overview`, design D1 and its contract): every
 *  figure both tabs show, assembled and ranked by the Hub, so the two tabs cannot drift. */

export type OverviewNeedKind =
  | 'main'
  | 'merge'
  | 'stall'
  | 'question'
  | 'review'
  | 'permission'
  | 'check'
  | 'offer'
  | 'reopening'
  | 'main_moved'

export type OverviewTargetType = 'thread' | 'task' | 'build' | 'permission' | 'check' | 'setting' | 'spec'

/** What an item opens: the thread, task, build, request, check or setting it is about. */
export interface OverviewItemTarget {
  type: OverviewTargetType
  id: string | null
  conversation_id?: string | null
  path?: string | null
}

export interface OverviewNeed {
  id: string
  kind: OverviewNeedKind
  rank: number
  agent: string | null
  title: string
  waiting_since: string
  /** The verb the row offers: "Answer", "Review", "Try again". */
  action: string
  target: OverviewItemTarget
}

export interface OverviewRunning {
  run_id: string
  agent: string
  conversation_id: string
  task_id: string | null
  what: string
  /** `Run.started_at`, never the thread's last event (design D7). */
  started_at: string
}

export type OverviewOutcome = 'landed' | 'sent_back' | 'failed' | 'stopped'

export interface OverviewFinished {
  id: string
  task_id: string | null
  run_id: string | null
  agent: string | null
  title: string
  outcome: OverviewOutcome
  at: string
  usd: number | null
  tokens: number | null
  credits: number | null
}

export interface OverviewSpendDay {
  /** The day's start, bucketed from the client's `day_start` (design D6). */
  day: string
  /** Null when the day's turns could not be priced. */
  usd: number | null
  tokens: number
  /** Copilot premium requests; null when none. */
  credits: number | null
  unpriced_turns: number
}

export interface OverviewSpend {
  /** Oldest first. */
  days: OverviewSpendDay[]
  token_budget: { limit: number; used: number } | null
}

export interface OverviewMain {
  state: 'green' | 'failing' | 'held' | 'unknown'
  branch: string | null
  held_landings: number
  /** Counts of known-failing entries by kind; null when the list has never been checked. */
  fails_on_main: number | null
  flaky: number | null
  detail: string | null
}

export interface OverviewBuild {
  build_id: string
  document_path: string | null
  title: string
  tasks_done: number
  tasks_total: number
  stage_words: string
  needs_operator: boolean
}

export interface OverviewNote {
  id: string
  written_at: string
  trigger: string
  text: string
  cites: { type: string; id: string; label: string }[]
}

export interface OverviewBody {
  generated_at: string
  visit: { previous_at: string | null; last_at: string | null } | null
  needs: OverviewNeed[]
  running: OverviewRunning[]
  finished: OverviewFinished[]
  spend: OverviewSpend
  main: OverviewMain
  builds: OverviewBuild[]
  note: OverviewNote | null
  note_writing: boolean
  note_last_attempt: { at: string; trigger: string; outcome: string; reason: string | null } | null
}

/** The operator's local midnight as ISO with its offset, so "today" is their day (design D6). */
export function localDayStart(now: Date = new Date()): string {
  const midnight = new Date()
  midnight.setTime(now.getTime())
  midnight.setHours(0, 0, 0, 0)
  const offset = -midnight.getTimezoneOffset()
  const sign = offset >= 0 ? '+' : '-'
  const abs = Math.abs(offset)
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${midnight.getFullYear()}-${pad(midnight.getMonth() + 1)}-${pad(midnight.getDate())}T00:00:00` +
    `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`
  )
}

/** The Overview read. `data` is null when the Hub predates the route (404): the screen then says to
 *  restart the Hub and falls back to the old needs list, rather than failing (design, hazards). */
export function useOverview() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const dayStart = localDayStart()
  return useQuery<OverviewBody | null>({
    queryKey: ['project', projectId, 'overview', dayStart],
    queryFn: () =>
      getJson<OverviewBody>(
        `/api/v1/projects/${projectId}/overview?day_start=${encodeURIComponent(dayStart)}&days=7`,
      ).then(
        (body) => body,
        (error: unknown) => {
          if ((error as { status?: number })?.status === 404) return null
          throw error
        },
      ),
    enabled: isConfigured && !!projectId,
  })
}
