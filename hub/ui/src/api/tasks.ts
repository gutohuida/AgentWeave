import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, patchJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface Task {
  id: string
  project_id: string
  title: string
  description?: string
  status: string
  priority: string
  assignee?: string
  assigner?: string
  assignee_status?: string | null
  assignee_status_msg?: string | null
  assignee_last_seen?: string | null
  requirements?: string[]
  acceptance_criteria?: string[]
  deliverables?: string[]
  notes?: string
  created_at: string
  updated: string
}

export function useTasks() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<Task[]>({
    queryKey: ['project', projectId, 'tasks'],
    queryFn: () => getJson<Task[]>(`/api/v1/projects/${projectId}/tasks`),
    enabled: isConfigured && !!projectId,
  })
}

export function useUpdateTask() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      patchJson<Task>(`/api/v1/projects/${projectId}/tasks/${id}`, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'tasks'] }),
  })
}
