import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, getJson, postJson, putJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** `a-vault-the-operator-fills-with-text-and-agents-can-read`: the project's knowledge vault. The
 *  records are files the Hub reads on every request (`hub/hub/vault.py`), so the map is always
 *  what is on disk, a colleague's pulled entries included. */

export const VAULT_TYPES = ['transcript', 'document', 'rules', 'example', 'note'] as const
export type VaultType = (typeof VAULT_TYPES)[number]
export type VaultVisibility = 'tracked' | 'private'

/** One entry as `GET /vault/map` lists it, newest first. */
export interface VaultEntry {
  id: string
  name: string
  /** One of `VAULT_TYPES` for entries this Hub wrote; a colleague's newer Hub may write others. */
  type: string
  visibility: VaultVisibility
  created_at: string
  /** The machine holding a private entry's text; null for a tracked one. */
  holder: string | null
  /** False for a private entry whose text is on another machine. */
  available: boolean
  /** The text's first lines, cut at 300 characters; null when the text is not here. */
  opening: string | null
}

/** One page of an entry's text (`GET /vault/entries/{id}?offset=`). */
export interface VaultEntryPage extends VaultEntry {
  content: string | null
  /** Where the next page starts; null when this page reaches the end. */
  next_offset: number | null
  /** Why there is no text, for an entry held elsewhere. */
  note: string | null
}

export interface VaultSettings {
  /** Null: the Hub's own folder, `effective_private_location`. */
  private_location: string | null
  effective_private_location: string
  default_visibility: VaultVisibility
}

export interface VaultSourceInput {
  name: string
  type: VaultType
  content: string
  visibility: VaultVisibility
}

/** True when the Hub predates the vault. A committed bundle reaches the operator's app before its
 *  server restarts, so this is a state the tab has to read, not an error. */
export function isNoVault(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

export function useVaultMap() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<VaultEntry[]>({
    queryKey: ['project', projectId, 'vault', 'map'],
    queryFn: async () => (await getJson<{ entries: VaultEntry[] }>(`/api/v1/projects/${projectId}/vault/map`)).entries,
    enabled: isConfigured && !!projectId,
    retry: (count, error) => !isNoVault(error) && count < 2,
  })
}

export function useVaultSettings() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<VaultSettings>({
    queryKey: ['project', projectId, 'vault', 'settings'],
    queryFn: () => getJson<VaultSettings>(`/api/v1/projects/${projectId}/vault/settings`),
    enabled: isConfigured && !!projectId,
    retry: (count, error) => !isNoVault(error) && count < 2,
  })
}

/** An entry's text, a page at a time: `fetchNextPage` reads from the last page's `next_offset`. */
export function useVaultEntry(entryId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useInfiniteQuery<VaultEntryPage>({
    queryKey: ['project', projectId, 'vault', 'entry', entryId],
    queryFn: ({ pageParam }) =>
      getJson<VaultEntryPage>(`/api/v1/projects/${projectId}/vault/entries/${entryId}?offset=${pageParam as number}`),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
    enabled: isConfigured && !!projectId && !!entryId,
  })
}

export function useUploadVaultSource() {
  const queryClient = useQueryClient()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  return useMutation({
    mutationFn: (input: VaultSourceInput) => postJson<VaultEntry>(`/api/v1/projects/${projectId}/vault/sources`, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'vault', 'map'] })
    },
  })
}

export function useUpdateVaultSettings() {
  const queryClient = useQueryClient()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  return useMutation({
    mutationFn: (input: Partial<Pick<VaultSettings, 'private_location' | 'default_visibility'>>) =>
      putJson<VaultSettings>(`/api/v1/projects/${projectId}/vault/settings`, input),
    onSuccess: (settings) => {
      queryClient.setQueryData(['project', projectId, 'vault', 'settings'], settings)
      // Which private entries are readable here depends on the location.
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'vault', 'map'] })
    },
  })
}
