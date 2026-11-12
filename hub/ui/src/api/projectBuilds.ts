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
  tasks_done: number
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

export function useProjectBuilds() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ProjectBuildRow[]>({
    queryKey: ['project', projectId, 'builds'],
    queryFn: async () =>
      (await getJson<{ builds: ProjectBuildRow[] }>(`/api/v1/projects/${projectId}/project/builds`)).builds,
    enabled: isConfigured && !!projectId,
  })
}
