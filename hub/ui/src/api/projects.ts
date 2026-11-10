import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, fetchWithAuth, getJson, postJson, putJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface ProjectAgentSummary {
  id: string
  name: string
  color_index: number | null
  status: string
  last_seen: string | null
}

export interface ProjectSummary {
  id: string
  name: string
  working_directory: string | null
  path_display: string | null
  directory_state: string
  last_opened_at: string | null
  last_seen_at: string | null
  hop_budget: number
  turn_delivery_cap: number
  agent_budget: number
  token_budget: number | null
  allow_agent_jobs: boolean
  agents: ProjectAgentSummary[]
}

/** The project collection itself — instance-scoped, not project-scoped, so
 * its query key deliberately carries no project ID. Powers the rail
 * (phase 5) and configStore's own project auto-selection. */
export function useProjects() {
  const { isConfigured } = useConfigStore()
  return useQuery<ProjectSummary[]>({
    queryKey: ['projects'],
    queryFn: () => {
      const { hubUrl, apiKey } = useConfigStore.getState()
      return readProjectCollection(hubUrl, apiKey, () => getJson<ProjectSummary[]>('/api/v1/projects'))
    },
    enabled: isConfigured,
  })
}

export interface ProjectPathInput {
  path: string
  name?: string
  register_copy_as_new?: boolean
}

function useProjectPathMutation(action: 'open' | 'create') {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: ProjectPathInput) =>
      postJson<ProjectSummary>(`/api/v1/projects/${action}`, input),
    onSuccess: (project) => {
      queryClient.setQueryData<ProjectSummary[]>(['projects'], (current = []) => [
        project,
        ...current.filter((item) => item.id !== project.id),
      ])
    },
  })
}

export function useOpenProject() {
  return useProjectPathMutation('open')
}

export function useCreateProject() {
  return useProjectPathMutation('create')
}

/**
 * The whole settings representation, not a slice of `ProjectSummary`.
 *
 * It used to be `Pick<ProjectSummary, …>` of six fields, and `ProjectSummary` carries neither the
 * conversation-title fields nor the checkpoint ones. The panel sends the whole object, so any field
 * it could not see was silently reset — observed clearing a whole checkpoint configuration with a
 * 200. Holding the entire object is what makes a field added server-side survive a client that has
 * never heard of it.
 *
 * The server now merges rather than replaces, so a partial body is safe there too; this type stays
 * whole because the panel's problem was never the verb, it was not knowing the field existed.
 */
export interface ProjectSettings {
  name: string
  hop_budget: number
  turn_delivery_cap: number
  agent_budget: number
  token_budget: number | null
  allow_agent_jobs: boolean
  conversation_title_mode: 'truncate' | 'generate'
  conversation_title_runner_id: string | null
  checkpoint_mode: 'off' | 'offered' | 'automatic'
  checkpoint_threshold_mode: 'percent' | 'tokens' | null
  /** Canonical units: 0-100 under `percent`, an actual token count under `tokens`. The form
   *  collects thousands and converts, because that is the unit an operator thinks in. */
  checkpoint_threshold_value: number | null
  checkpoint_notes_value: number | null
  checkpoint_runner_id: string | null
  checkpoint_model: string | null
  /** Whether a successor starts working the moment it is handed its checkpoint. */
  checkpoint_auto_continue: boolean
  /** The branch approving a task merges into. Null means "not chosen", and nothing merges — which
   *  is why the integration note tells the operator to come here. */
  main_branch: string | null
  /** Commands the Hub runs on the work a task's approval would merge; approval is refused until
   *  they pass. Null means no checks, and approval is unchanged. Only the operator sets these. */
  checks: ProjectCheck[] | null
  /** Whether every process a check run starts runs below normal priority, so the operator's own
   *  work on the machine comes first (`checks-know-their-phase-and-give-way-to-the-user`). Off by
   *  default; absent from a Hub older than that change. */
  checks_give_way?: boolean
  /** The files a command rebuilds from other files, which landing rebuilds instead of sending a
   *  conflict back (`generated-files-are-rebuilt-when-work-lands-instead-of-sending-it-back`).
   *  Null means none. Only the operator sets this; absent from a Hub older than that change. */
  generated_files?: GeneratedFiles | null
  /** Whether a build may land as one GitHub pull request; off until turned on. */
  pr_landing?: boolean
  /** With PR landing on, one commit holding the whole build rather than one per task. */
  pr_single_commit?: boolean
  /** The PR's own CI is the full check: a PR build pushes without landing-phase checks locally
   *  (`the-pr-s-ci-is-the-full-check`). Refused while PR landing is off; turned off with it. */
  pr_ci_full_check?: boolean
  /** The checks that count where GitHub marks none required. */
  pr_ci_check_names?: string[]
  /** Whole minutes between asks while CI is pending, 1 to 60; 2 by default. */
  pr_ci_interval_minutes?: number
  /** Whole minutes after a push when interval asking stops, 5 to 1440; 60 by default. */
  pr_ci_cutoff_minutes?: number
  /** The posture every agent's run gets when neither its conversation nor the agent states one
   *  (reach-1019). Null is the runner's built-in posture; an agent's own default wins either way. */
  default_permission_mode?: string | null
  /** Roots and hosts the workspace judge allows beyond the workspace; an agent's own replace them. */
  reach_grants?: ReachGrants | null
}

/** One root granted beyond the workspace: an absolute path, `{temp}` or `{project}`. */
export interface ReachRoot {
  path: string
  access: 'read' | 'readwrite'
}

/** What an agent may reach beyond its workspace under Workspace only (reach-1019). */
export interface ReachGrants {
  roots: ReachRoot[]
  hosts: string[]
}

/** What a settings save answers: the stored settings, plus what the operator should know about
 *  them (an agent budget below the open agents, a token threshold an agent can never reach).
 *  Answer-only; never sent back. */
export interface ProjectSettingsSaved extends ProjectSettings {
  warnings?: string[]
}

/** One of a project's checks (`approval-runs-the-projects-checks`). */
/** The generated files setting: globs over repository-relative paths, the command that rebuilds
 *  them, and its timeout (1 to 3600 seconds, 600 by default). */
export interface GeneratedFiles {
  paths: string[]
  command: string
  timeout_seconds: number
}

export interface ProjectCheck {
  name: string
  command: string
  timeout_seconds: number
  /** Globs over repository paths (`hub/**`). Empty or absent: it runs for every task. Otherwise it
   *  is skipped, and passes, when the work changes no file matching one. */
  paths?: string[]
  /** Run when an agent completes its task, which is refused with the check's output when it fails
   *  (`checks-run-before-anyone-reviews`). At most 120 s. Absent on a check saved before it. */
  fast?: boolean
  /** When it runs: in a task's run before review, in a landing batch's run, or both
   *  (`checks-know-their-phase-and-give-way-to-the-user`). A check saved before it reads `both`. */
  phase?: CheckPhase
  /** The JUnit XML file the check writes, relative to the directory it runs in
   *  (`checks-report-which-tests-failed-in-any-language`, FR-1). Absent: judged as a whole. */
  report_path?: string | null
  /** Re-runs named tests: `{tests}` is replaced by their ids, `classname::name`, one argument each.
   *  The Hub refuses one without `{tests}`. */
  rerun_command?: string | null
  /** What runs in a task's pre-review run in place of `command`, where the files the task changed
   *  are known: `{changed_files}` is replaced by the path of a file listing them. The Hub refuses
   *  one without `{changed_files}`. Landings and main runs keep running `command`. */
  change_command?: string | null
}

export type CheckPhase = 'review' | 'landing' | 'both'

/** The server merges a partial body onto what is stored (`projects.py`), so a caller sends only
 *  what it changes: the Overview's switch sends `allow_agent_jobs` alone, and the panel never sends
 *  `token_budget`, whose one editor is Budgets. */
export type ProjectSettingsInput = Partial<ProjectSettings>

/** How long a check usually takes in this project: the median and longest of its last 20 passing
 *  results (`checks-know-their-phase-and-give-way-to-the-user`, FR-11). */
export interface CheckUsualDuration {
  median_seconds: number
  longest_seconds: number
  passes: number
}

/** Each configured check's usual duration by name; null for a check with no passing run yet. */
export type CheckUsualDurations = Record<string, CheckUsualDuration | null>

export function useCheckUsualDurations(projectId: string | null) {
  const { isConfigured } = useConfigStore()
  return useQuery<CheckUsualDurations>({
    queryKey: ['project', projectId, 'checks', 'usual-durations'],
    queryFn: () => getJson<CheckUsualDurations>(`/api/v1/projects/${projectId}/checks/usual-durations`),
    enabled: isConfigured && !!projectId,
  })
}

/** The stored settings, which is what the panel edits. `useProjects()` cannot serve this: its
 *  summary omits every field added since it was written. */
export function useProjectSettings(projectId: string | null) {
  const { isConfigured } = useConfigStore()
  return useQuery<ProjectSettings>({
    queryKey: ['project', projectId, 'settings'],
    queryFn: () => getJson<ProjectSettings>(`/api/v1/projects/${projectId}/settings`),
    enabled: isConfigured && !!projectId,
  })
}

/**
 * A branch the operator might mean, and the one they have chosen.
 *
 * A suggestion, never an assignment: detecting a branch is safe for a report and unsafe for a
 * write, so nothing merges until the operator submits one.
 */
export interface MainBranchSuggestion {
  suggestion: string | null
  chosen: string | null
  is_repository: boolean
}

export function useMainBranchSuggestion(projectId: string | null) {
  const { isConfigured } = useConfigStore()
  return useQuery<MainBranchSuggestion>({
    queryKey: ['project', projectId, 'main-branch-suggestion'],
    queryFn: () =>
      getJson<MainBranchSuggestion>(`/api/v1/projects/${projectId}/main-branch-suggestion`),
    enabled: isConfigured && !!projectId,
  })
}

export function useUpdateProjectSettings(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: ProjectSettingsInput) =>
      putJson<ProjectSettingsSaved>(`/api/v1/projects/${projectId}/settings`, input),
    onSuccess: (saved) => {
      // `warnings` is answer-only: the cached settings are what is stored, without it.
      const settings: ProjectSettings & { warnings?: string[] } = { ...saved }
      delete settings.warnings
      queryClient.setQueryData<ProjectSettings>(['project', projectId, 'settings'], settings)
      queryClient.setQueryData<ProjectSummary[]>(['projects'], (current = []) =>
        current.map((project) => project.id === projectId ? { ...project, ...settings } : project),
      )
    },
  })
}

export function useRelocateProject(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { path: string }) =>
      postJson<ProjectSummary>(`/api/v1/projects/${projectId}/relocate`, input),
    onSuccess: (updated) => {
      queryClient.setQueryData<ProjectSummary[]>(['projects'], (current = []) =>
        current.map((project) => project.id === projectId ? updated : project),
      )
    },
  })
}

/**
 * DELETE /api/v1/projects/{id} returns 204 with no body, so this bypasses `deleteJson` (which
 * always calls `res.json()` and would throw a `SyntaxError` on an empty response) and drops the
 * response entirely — the caller learns of success or failure only through the promise settling.
 *
 * `onSuccess` mirrors `useRelocateProject`'s direct-cache-write pattern, then resolves the next
 * selection the same way `configStore.bootstrap()` does when a persisted selection stops existing
 * (`design.md` D6) — reusing that fallback rather than a second one, so the two paths that can make
 * the selected project disappear (deletion, and a stale selection at load) never disagree.
 */
export function useDeleteProject(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    // *removePrivate*: also delete this project's private vault entries, held outside its folder
    // (fix-D1). The folder itself is never touched.
    mutationFn: (removePrivate: boolean = false) =>
      fetchWithAuth(`/api/v1/projects/${projectId}?remove_private=${removePrivate}`, {
        method: 'DELETE',
      }).then(() => undefined),
    onSuccess: () => {
      // Only the collection changes here. Navigation owns the selection: with the project gone
      // from `['projects']` it resolves a fallback destination, and App writes that to the store.
      // Writing the store here as well (F729) raced App's destination->store effect, which, still
      // holding the deleted destination for one commit, wrote the deleted id straight back, and
      // every query keyed on the selected project re-ran against a project that no longer exists.
      queryClient.setQueryData<ProjectSummary[]>(['projects'], (current = []) =>
        current.filter((project) => project.id !== projectId),
      )
      void queryClient.cancelQueries({ queryKey: ['project', projectId] })
    },
  })
}

/** Raw (non-React-Query) fetch of the project collection, for use outside a
 * QueryClientProvider — specifically configStore's bootstrap, which runs
 * before React has mounted anything. Mirrors api/setup.ts's fetchSetupToken. */
export async function fetchProjectSummaries(
  hubUrl: string,
  apiKey: string,
): Promise<ProjectSummary[]> {
  try {
    return await readProjectCollection(hubUrl, apiKey, async () => {
      const res = await fetch(`${hubUrl}/api/v1/projects`, {
        headers: { Authorization: `Bearer ${apiKey}` },
      })
      if (!res.ok) throw new ApiError(res.status, await res.text())
      return (await res.json()) as ProjectSummary[]
    })
  } catch {
    return []
  }
}

let projectCollectionRead: { key: string; read: Promise<ProjectSummary[]> } | null = null

/** The project collection, joining a read of it that is already under way with the same
 *  credential. Bootstrap's auto-selection and `useProjects` both read it as the app opens, and
 *  they used to send two requests for one answer. Only an in-flight read is shared: once it
 *  settles, the next read goes to the Hub, so nothing is served stale. */
function readProjectCollection(
  hubUrl: string,
  apiKey: string,
  read: () => Promise<ProjectSummary[]>,
): Promise<ProjectSummary[]> {
  const key = `${hubUrl}
${apiKey}`
  if (projectCollectionRead && projectCollectionRead.key === key) return projectCollectionRead.read
  const pending = read()
  const entry = { key, read: pending }
  projectCollectionRead = entry
  const clear = () => {
    if (projectCollectionRead === entry) projectCollectionRead = null
  }
  pending.then(clear, clear)
  return pending
}
