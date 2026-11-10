import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, putJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface Instructions {
  content: string
  /** The most characters the Hub will store (F686): instructions ride every agent turn. */
  max_chars?: number
  /** Where they live: the Hub's own record, or the project's AGENTS.md (absent from an older Hub,
   *  which only has the first). */
  source?: 'hub' | 'agents_md'
  /** The folder holds an AGENTS.md the operator may switch on as the instructions. */
  agents_md_offered?: boolean
  main_branch?: string | null
  /** After a save to AGENTS.md: whether it was committed on the main branch, and if not, why. */
  committed?: boolean
  notice?: string | null
}

export function useInstructions() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<Instructions>({
    queryKey: ['project', projectId, 'instructions'],
    queryFn: () => getJson<Instructions>(`/api/v1/projects/${projectId}/project/instructions`),
    enabled: isConfigured && !!projectId,
  })
}

export function useSaveInstructions() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (content: string) =>
      putJson<Instructions>(`/api/v1/projects/${projectId}/project/instructions`, { content }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'instructions'] })
    },
  })
}

/** Switch "Use AGENTS.md as this project's instructions" on (moving the Hub's instructions into
 *  the file once) or off (back to the Hub's own, kept unchanged). */
export function useInstructionsSource() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (agentsMd: boolean) =>
      putJson<Instructions>(`/api/v1/projects/${projectId}/project/instructions/source`, {
        agents_md: agentsMd,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'instructions'] })
    },
  })
}
