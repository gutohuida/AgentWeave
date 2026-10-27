import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** The work tally (`GET /projects/{id}/stats`, `project-stats-come-from-the-same-records`): where the
 *  project's work went. Every figure is a *row* of the same shape, whether it is a build, a spec, an
 *  agent, a model or a level, and the spec page's build card reads the same rows. Money is micros of
 *  an API-equivalent dollar; a figure no record reports is `null` and is shown as unknown, never 0. */
export const ROLES = ['building', 'reviewing', 'leading', 'mending', 'other'] as const
export type Role = (typeof ROLES)[number]
export const WALL_PARTS = ['building', 'reviewing', 'checks', 'held', 'review', 'waiting'] as const
export type WallPart = (typeof WALL_PARTS)[number]

export interface WorkRow {
  runs: Record<Role | 'total', number>
  cost_micros: Record<Role | 'total', number | null>
  run_seconds: Record<Role | 'total', number>
  unpriced: number
  turns: number
  tokens: number | null
  ai_nano_aiu: number | null
  premium_requests: number | null
  wall: Record<WallPart | 'total', number>
  checks: { runs: number; passed: number; failed: number; seconds: number }
  send_backs: { made: number; received: number }
  pieces: { accepted: number; rejected: number; held: number; awaiting: number }
  beside_failing: { count: number; cost_micros: number | null; run_seconds: number }
}

export interface WorkBuild {
  id: string
  state: string
  level: string
  driver: string
  created_at: string | null
  row: WorkRow
}

export interface WorkGroup {
  /** The document id, agent, model or level; null is the entry for what has none. */
  key: string | null
  label: string
  path?: string | null
  row: WorkRow
  /** On a spec entry only: its builds, and the work done before any build was recorded. */
  builds?: WorkBuild[]
  before_builds?: WorkRow | null
}

export type Grouping = 'spec' | 'agent' | 'model' | 'level'

export interface WorkTally {
  since: string | null
  total: WorkRow
  workers: WorkRow
  project: WorkRow
  builds: Record<string, WorkRow>
  groups: Record<Grouping, WorkGroup[]>
}

/** The tally from `since` (a date-time, or none for the whole history). */
export function useProjectStats(since: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<WorkTally>({
    queryKey: ['project', projectId, 'stats', since],
    queryFn: () =>
      getJson<WorkTally>(`/api/v1/projects/${projectId}/stats${since ? `?since=${encodeURIComponent(since)}` : ''}`),
    enabled: isConfigured && !!projectId,
  })
}
