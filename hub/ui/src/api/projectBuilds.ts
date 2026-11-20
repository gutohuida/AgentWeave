import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'
import type { BuildDriver, BuildLevel } from './spec'
import type { BuildNeedsRead } from '@/components/builds/buildViewModel'
import { sidebarBuilds } from '@/components/layout/threadsAndBuildsModel'

/** One row of `GET /projects/{id}/project/builds`: a build of any of the project's documents, with
 *  the document's title, its loop, its task counts and the blocking question its work waits on.
 *  Newest build first; the Running tab reads it so it need not open each document. */
export interface ProjectBuildRow {
  id: string
  document_id: string
  document_title: string
  /** The document's path, so a row can open it (the Spec home's Recently built). */
  document_path?: string
  /** When a finished build finished; null while running or for a stopped build. */
  finished_at?: string | null
  /** The roadmap slice the document builds, or null. */
  roadmap?: {
    path: string
    title: string
    slice: { key: string; title: string }
  } | null
  /** The capabilities the document names it changes, resolved to titles. */
  capabilities?: { path: string; title: string }[]
  state: 'running' | 'stopped' | 'finished'
  driver: BuildDriver
  level: BuildLevel
  lead: string | null
  loop_id: string | null
  loop: { id: string; name: string; enabled: boolean } | null
  tasks_total: number
  /** Tasks done: approved and landed on main (or merged as a pull request, or approved in a build
   *  that lands nowhere). An approved task not landed yet is not done. */
  tasks_done: number
  /** Approved tasks whose work has not landed yet. */
  tasks_landing: number
  /** Each of the build's tasks on its way to main, or sent back by its landing, in the order the
   *  build's tasks were created. */
  landings: ProjectBuildLanding[]
  spent_usd: number | null
  /** Turns of the build that carry no price; above zero, spent_usd is not a cost, so show "unpriced". */
  unpriced_turns?: number
  stop_reason: string | null
  created_at: string | null
  stopped_at: string | null
  /** What the build needs from the operator, the build read's own (`hub/hub/build_needs.py`):
   *  "stopped" first, otherwise its first task's need; null when it needs nothing. */
  needs_operator: BuildNeedsRead | null
  /** The operator dismissed it from the sidebar and its needs are still the ones dismissed. */
  attention_dismissed: boolean
  open_questions: number
  question: {
    id: string
    question: string
    from_agent: string
    conversation_id: string | null
    created_at: string | null
  } | null
}

/** One task of a build whose work is not on main yet, as `GET /project/builds` reports it. */
export interface ProjectBuildLanding {
  task_id: string
  display_id: string
  title: string
  /** The task's status: `approved` while its landing runs; another once landing sent it back. */
  status: string
  /** Its latest landing's state: queued, checking, landing, held, pushed, not_landed, sent_back. */
  landing_state: string
  /** Why the landing is where it is (a send-back's or a hold's reason); may be empty. */
  reason: string
}

const readProjectBuilds = async (projectId: string) =>
  (await getJson<{ builds: ProjectBuildRow[] }>(`/api/v1/projects/${projectId}/project/builds`)).builds

export function useProjectBuilds(refetchMs?: number) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ProjectBuildRow[]>({
    queryKey: ['project', projectId, 'builds'],
    queryFn: () => readProjectBuilds(projectId as string),
    enabled: isConfigured && !!projectId,
    refetchInterval: refetchMs,
  })
}

/** The same rows for a project named explicitly: the sidebar draws every registered project, not
 *  only the selected one. One cache entry with `useProjectBuilds` for the selected project. */
export function useBuildsOfProject(projectId: string, enabled = true) {
  const { isConfigured } = useConfigStore()
  return useQuery<ProjectBuildRow[]>({
    queryKey: ['project', projectId, 'builds'],
    queryFn: () => readProjectBuilds(projectId),
    enabled: isConfigured && enabled,
  })
}

/** The titles of a project's builds that need the operator and were not dismissed: the collapsed
 *  rail's mark (FR-14), read from the same rows as the sidebar's expanded list. */
export function useBuildsNeedingYouOf(projectId: string): string[] {
  const { data } = useBuildsOfProject(projectId)
  return sidebarBuilds(data ?? [])
    .filter((build) => build.needs_operator !== null)
    .map((build) => build.document_title)
}

/** Dismiss a listed build of any project from the sidebar (D3); the Hub refuses a running one. */
export function useDismissProjectBuild() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, buildId }: { projectId: string; buildId: string }) =>
      postJson<ProjectBuildRow>(`/api/v1/projects/${projectId}/project/builds/${buildId}/attention/dismiss`, {}),
    onSuccess: (_row, { projectId }) => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'builds'] }),
  })
}
