import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson, putJson } from './client'
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
    queryFn: () => getJson<ProjectSummary[]>('/api/v1/projects'),
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
}

export type ProjectSettingsInput = ProjectSettings

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
      putJson<ProjectSettings>(`/api/v1/projects/${projectId}/settings`, input),
    onSuccess: (settings) => {
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

/** Raw (non-React-Query) fetch of the project collection, for use outside a
 * QueryClientProvider — specifically configStore's bootstrap, which runs
 * before React has mounted anything. Mirrors api/setup.ts's fetchSetupToken. */
export async function fetchProjectSummaries(
  hubUrl: string,
  apiKey: string,
): Promise<ProjectSummary[]> {
  const res = await fetch(`${hubUrl}/api/v1/projects`, {
    headers: { Authorization: `Bearer ${apiKey}` },
  })
  if (!res.ok) return []
  return (await res.json()) as ProjectSummary[]
}
