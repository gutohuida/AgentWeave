import { useMutation, useQuery } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface DialogAvailability {
  available: boolean
  reason?: string | null
}

export interface DialogOpenResult {
  outcome: 'chosen' | 'cancelled' | 'timeout' | 'unavailable' | 'failed'
  path?: string | null
  detail?: string | null
}

/** Instance-scoped, not project-scoped — mirrors `useDirectoryListing`: it backs choosing
 * a project directory before a project exists (composer/chrome refinement §7/§8). */
export function useNativeDialogAvailability() {
  const { isConfigured } = useConfigStore()
  return useQuery<DialogAvailability>({
    queryKey: ['native-dialog-availability'],
    queryFn: () => getJson<DialogAvailability>('/api/v1/fs/native-dialog/availability'),
    enabled: isConfigured,
    staleTime: 60_000,
  })
}

export function useOpenNativeDialog() {
  return useMutation<DialogOpenResult, unknown, void>({
    mutationFn: () => postJson<DialogOpenResult>('/api/v1/fs/native-dialog/open'),
  })
}
