import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import type { BuildDriver, BuildLevel } from './spec'

/** One row of `GET /projects/{id}/project/builds`: a build of any of the project's documents, with
 *  the document's title, its loop, its task counts and the blocking question its work waits on.
 *  Newest build first; the Running tab reads it so it need not open each document. */
export interface ProjectBuildRow {
  id: string
  document_id: string
  document_title: string
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
  stop_reason: string | null
  created_at: string | null
  stopped_at: string | null
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

export function useProjectBuilds() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ProjectBuildRow[]>({
    queryKey: ['project', projectId, 'builds'],
    queryFn: async () =>
      (await getJson<{ builds: ProjectBuildRow[] }>(`/api/v1/projects/${projectId}/project/builds`)).builds,
    enabled: isConfigured && !!projectId,
  })
}
