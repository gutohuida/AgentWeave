import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** Main moved outside the Hub's own integration (`hub/hub/main_watch.py`): one open notice per
 *  project gathers every such move until the operator marks it seen. Nothing was blocked. */
export interface MainNotice {
  id: string
  project_id: string
  branch: string
  old_tip: string
  new_tip: string
  /** Any gathered move rewrote history (the old tip is no longer an ancestor). */
  rewrite: boolean
  /** Newest first: each commit's short sha, subject and author. */
  commits: { sha: string; subject: string; author: string }[]
  created_at: string
  updated_at: string
  seen_at: string | null
  seen_by: string | null
}

/** The project's open main notice, if any. SSE (`main_moved`, `main_notice_seen`) invalidates it. */
export function useOpenMainNotices() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<MainNotice[]>({
    queryKey: ['project', projectId, 'mainNotices', 'open'],
    queryFn: async () =>
      (await getJson<{ notices: MainNotice[] }>(`/api/v1/projects/${projectId}/main-notices`)).notices,
    enabled: isConfigured && !!projectId,
  })
}

/** Mark a main notice seen: it closes, and the next move opens a new one. */
export function useMarkMainNoticeSeen() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (noticeId: string) =>
      postJson<MainNotice>(`/api/v1/projects/${projectId}/main-notices/${noticeId}/seen`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'mainNotices'] }),
  })
}

/** The commits a notice names, as one line: `abc1234 subject (author)`, the first few. */
export function describeMainNotice(notice: MainNotice, shown = 3): string {
  const listed = notice.commits
    .slice(0, shown)
    .map((c) => `${c.sha.slice(0, 7)} ${c.subject} (${c.author})`)
    .join('; ')
  const more = notice.commits.length > shown ? `; and ${notice.commits.length - shown} more` : ''
  const tips = `${notice.branch} moved from ${notice.old_tip.slice(0, 7)} to ${notice.new_tip.slice(0, 7)}`
  return `${tips}${notice.rewrite ? ', rewriting its history' : ''}${listed ? `: ${listed}${more}` : ''}.`
}
