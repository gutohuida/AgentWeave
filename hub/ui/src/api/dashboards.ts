import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchWithAuth, getJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** The chart kinds a panel can name (`hub/hub/api/v1/dashboards.py` CHART_KINDS, FR-10). */
export const CHART_KINDS = ['number', 'table', 'bar', 'stacked_bar', 'line'] as const
export type ChartKind = (typeof CHART_KINDS)[number]

/** One row of the list: a dashboard without its panels. */
export interface DashboardSummary {
  id: string
  name: string
  description: string
  author: string
  created_at: string | null
  updated_at: string | null
  panel_count: number
}

export type CellValue = string | number | boolean | null

/** A panel's refusal: the query service's own error, shown as it came. */
export interface PanelError {
  code?: string
  message: string
}

/** One panel as `GET .../run` answers it. A failed query carries `error`; a result that cannot be
 *  drawn as its kind carries `warning`; neither stops the other panels. */
export interface PanelRun {
  id: string
  title: string
  kind: string
  query: string
  columns: string[]
  rows: CellValue[][]
  row_count: number
  truncated: boolean
  elapsed_ms: number | null
  error: PanelError | null
  warning: string | null
}

export interface DashboardRun {
  id: string
  name: string
  description: string
  author: string
  updated_at: string | null
  fetched_at: string
  panels: PanelRun[]
}

const base = (projectId: string | null) => `/api/v1/projects/${projectId}/dashboards`

export function useDashboards() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<DashboardSummary[]>({
    queryKey: ['project', projectId, 'dashboards'],
    queryFn: async () => (await getJson<{ dashboards: DashboardSummary[] }>(base(projectId))).dashboards,
    enabled: isConfigured && !!projectId,
  })
}

/** Runs every query of one dashboard. Never cached as fresh: opening a dashboard, and every
 *  Refresh, is a new fetch, and `fetched_at` says when. */
export function useDashboardRun(dashboardId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<DashboardRun>({
    queryKey: ['project', projectId, 'dashboards', dashboardId, 'run'],
    queryFn: () => getJson<DashboardRun>(`${base(projectId)}/${dashboardId}/run`),
    enabled: isConfigured && !!projectId && !!dashboardId,
    staleTime: 0,
    gcTime: 0,
  })
}

export function useDeleteDashboard() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    // The route answers 204 with no body, so this does not read JSON back.
    mutationFn: async (id: string) => {
      await fetchWithAuth(`${base(projectId)}/${id}`, { method: 'DELETE' })
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'dashboards'] }),
  })
}
