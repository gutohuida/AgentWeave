import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** A check whose latest run ended 'could not run' (`project_checks.could_not_run_notices`): landing
 *  is waiting on it. Nothing dismisses it; the check's next run, passing or failing, clears it. */
export interface CheckNotice {
  check: string
  /** The program the check lacked (`eslint`), or why its command could not start. */
  program: string | null
  dependency_link_failures: { name: string; reason: string }[]
  source: 'task' | 'landing' | 'main'
  at: string
  message: string
}

/** The project's open could-not-run notices. SSE `task_checks_finished` invalidates it. */
export function useCheckNotices() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<CheckNotice[]>({
    queryKey: ['project', projectId, 'checkNotices'],
    queryFn: async () =>
      (await getJson<{ notices: CheckNotice[] }>(`/api/v1/projects/${projectId}/check-notices`)).notices,
    enabled: isConfigured && !!projectId,
  })
}
