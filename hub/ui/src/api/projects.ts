import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
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
