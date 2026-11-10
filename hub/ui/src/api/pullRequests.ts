import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** One counted check on the head commit (`hub/hub/pull_requests.py` `read_ci`). */
export interface CiCheck {
  name: string
  state: 'pending' | 'passed' | 'failed'
  /** Its page on GitHub; null where GitHub gave none. */
  url: string | null
  /** For a failing check: what the same check did on main's latest commit. */
  main_result?: 'failed' | 'passed' | 'none'
}

/** CI's result on a PR's head commit (`the-pr-s-ci-is-the-full-check`). */
export interface CiRead {
  state:
    | 'pending'
    | 'passed'
    | 'failed'
    | 'failing_on_main'
    | 'superseded'
    | 'not_finished'
    | null
  head_sha: string | null
  checks: CiCheck[]
  /** When the Hub last asked GitHub. */
  last_asked_at?: string | null
  /** GitHub's own words from a failed ask. */
  error: string | null
}

/** A build's pull request as the build reads it (`hub/hub/builds.py` `pull_request_view`). */
export interface BuildPullRequest {
  /** Null until a push with the project's CI setting on. */
  ci?: CiRead | null
  number: number | null
  url: string | null
  /** `draft`, `ready`, `merged` or `closed`; null before the first push opens it. */
  state: 'draft' | 'ready' | 'merged' | 'closed' | null
  last_asked_at: string | null
  /** GitHub's own words from the last failed push or ask. */
  error: string | null
}

/** The project's local main against GitHub's (`hub/hub/pull_requests.py` `MainState`). */
export interface MainAgainstGitHub {
  branch: string
  local: string | null
  github: string | null
  /** GitHub's main holds commits the local main does not: the project shows 'main is behind GitHub'. */
  behind: boolean
  /** Moved forward by this call (Update). */
  updated: boolean
  /** Update would bring it forward now. */
  can_update: boolean
  /** Why Update cannot bring it forward yet, where it is behind. */
  reason: string | null
}

export interface PullRequestCheck {
  pull_request: BuildPullRequest | null
  main: MainAgainstGitHub | null
}

/** Ask GitHub about a build's PR. `wait` is 'check now'; without it, the build being opened, which
 *  asks in the background and answers at once. */
export function useCheckBuildPullRequest() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ buildId, wait = true }: { buildId: string; wait?: boolean }) =>
      postJson<PullRequestCheck>(
        `/api/v1/projects/${projectId}/project/builds/${buildId}/pull-request/check?wait=${wait}`,
        {},
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId] }),
  })
}

/** Whether the project's local main is behind GitHub's; `null` where PR landing does not apply.
 *  SSE `main_behind_github` invalidates it. */
export function useMainAgainstGitHub() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<MainAgainstGitHub | null>({
    queryKey: ['project', projectId, 'mainAgainstGitHub'],
    queryFn: async () =>
      (await getJson<{ main: MainAgainstGitHub | null }>(`/api/v1/projects/${projectId}/main/github`))
        .main,
    enabled: isConfigured && !!projectId,
  })
}

/** Update: fast-forward the local main to GitHub's when that is safe; `reason` says why not. */
export function useUpdateMainFromGitHub() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: async () =>
      (await postJson<{ main: MainAgainstGitHub }>(`/api/v1/projects/${projectId}/main/update`, {}))
        .main,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'mainAgainstGitHub'] }),
  })
}
