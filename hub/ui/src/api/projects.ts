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

export type ProjectSettingsInput = Pick<
  ProjectSummary,
  'name' | 'hop_budget' | 'turn_delivery_cap' | 'agent_budget' | 'token_budget' | 'allow_agent_jobs'
>

export function useUpdateProjectSettings(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: ProjectSettingsInput) =>
      putJson<ProjectSettingsInput>(`/api/v1/projects/${projectId}/settings`, input),
    onSuccess: (settings) => {
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
