import { useQuery } from '@tanstack/react-query'
import { ApiError, getJson, postJson, readableApiError } from './client'
import { useConfigStore } from '@/store/configStore'
import type { CheckState } from '@/lib/checkState'

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
  /** A turn on a task: that task's stage and check state, as the task list derives them (FR-11). */
  stage?: string | null
  check_state?: CheckState | null
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
    // While a note is being written the Briefing says so, and picks the note up when it lands.
    refetchInterval: (query) => (query.state.data?.note_writing ? NOTE_POLL_MS : false),
  })
}

const NOTE_POLL_MS = 3000

/** The operator opened the Overview (`POST /overview/visit`): the Hub records it and, on a new visit
 *  with something changed, starts a note. Best effort: a failed record only leaves "last looked" as
 *  it was. */
export function recordOverviewVisit(projectId: string): Promise<{ previous_at: string | null; note_started: boolean } | null> {
  return postJson<{ previous_at: string | null; note_started: boolean }>(`/api/v1/projects/${projectId}/overview/visit`).catch(() => null)
}

/** "Refresh note": the overview-note job writes one now. Resolves to why it could not, or null. */
export function refreshOverviewNote(projectId: string): Promise<string | null> {
  return postJson<unknown>(`/api/v1/projects/${projectId}/manager/jobs/overview-note/run`).then(
    () => null,
    (error: unknown) => {
      // The refusal is `{detail: {code, reason}}`: the reason is the sentence to show.
      if (error instanceof ApiError) {
        try {
          const reason = (JSON.parse(error.message) as { detail?: { reason?: unknown } })?.detail?.reason
          if (typeof reason === 'string' && reason.trim()) return reason
        } catch {
          // not JSON: fall through to the generic reading
        }
      }
      return readableApiError(error, 'The note could not be written.')
    },
  )
}
