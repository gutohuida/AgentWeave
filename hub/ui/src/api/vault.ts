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
  /** The text's first lines, cut at 300 characters; null when the text is not here. For a fact,
   *  its claim. */
  opening: string | null
  /** Absent on a Hub that predates facts, whose entries are all sources. */
  kind?: 'source' | 'fact'
  /** A fact's: the sources it cites. */
  sources?: string[]
  /** A source's: the day it was said, `YYYY-MM-DD`, when the operator gave one. */
  dated?: string | null
  /** A fact's, derived by the Hub from its contradictions: an open one cites it. Absent on a Hub
   *  that predates contradictions. */
  disputed?: boolean
  /** A fact's: the later-dated side of an open contradiction, which the Hub presumes holds. */
  presumed?: boolean
  /** A fact's: the `decision` source of a resolved contradiction that set it aside, or the
   *  corrected fact (`fct-`) a report replaced it with. */
  superseded_by?: string | null
}

/** Where a fact's quote sits in its source, 1-based lines found by the Hub, not the model. */
export interface VaultCitation {
  source: string
  quote: string
  line_start: number
  line_end: number
}

/** One page of an entry's text (`GET /vault/entries/{id}?offset=`). */
export interface VaultEntryPage extends VaultEntry {
  content: string | null
  /** Where the next page starts; null when this page reaches the end. */
  next_offset: number | null
  /** Why there is no text, for an entry held elsewhere. */
  note: string | null
  /** A fact's claim and citations, when its record is on this machine. */
  claim?: string
  citations?: VaultCitation[]
}

export function isFact(entry: VaultEntry): boolean {
  return entry.kind === 'fact'
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
  /** When it was said, `YYYY-MM-DD`; left out when unknown. */
  dated?: string
}

/** One side of a contradiction, with the claim and date the Hub found for it. */
export interface ContradictionSide {
  id: string
  /** Null when the fact's record is held on another machine. */
  claim: string | null
  source: string | null
  date: string | null
  presumed: boolean
}

/** One contradiction as `GET /vault/contradictions` lists it, open ones first. */
export interface VaultContradiction {
  id: string
  facts: [string, string]
  presumed: string | null
  explanation?: string
  /** Null for a private contradiction held on another machine, which cannot be resolved here. */
  status: 'open' | 'resolved' | null
  visibility?: VaultVisibility
  holder?: string | null
  resolution: { stands: string | null; note: string; decision: string; resolved_at: string } | null
  sides: ContradictionSide[]
}

export interface ContradictionResolution {
  /** The fact that stands, or null for neither. */
  stands: string | null
  note: string
}

/** True when the Hub predates the vault. A committed bundle reaches the operator's app before its
 *  server restarts, so this is a state the tab has to read, not an error. */
export function isNoVault(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

/** `refetchMs`: poll while a distillation may still be writing facts; false otherwise. */
export function useVaultMap(refetchMs: number | false = false) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<VaultEntry[]>({
    queryKey: ['project', projectId, 'vault', 'map'],
    queryFn: async () => (await getJson<{ entries: VaultEntry[] }>(`/api/v1/projects/${projectId}/vault/map`)).entries,
    enabled: isConfigured && !!projectId,
    retry: (count, error) => !isNoVault(error) && count < 2,
    refetchInterval: refetchMs,
  })
}

/** Ask the manager to distil one source again. 202: it runs in the background, and its facts
 *  reach the map when it finishes. 409 carries the reason it cannot run (the job is off, has no
 *  runner, or the text is on another machine). */
export function useDistilVaultSource() {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  return useMutation({
    mutationFn: (sourceId: string) =>
      postJson<{ source: string; queued: boolean }>(`/api/v1/projects/${projectId}/vault/sources/${sourceId}/distil`, {}),
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

/** The contradictions the distillation's check recorded. A 404 is a Hub that predates them, which
 *  the tab reads as no section. `refetchMs` polls while a check may still be running. */
export function useVaultContradictions(refetchMs: number | false = false) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<VaultContradiction[]>({
    queryKey: ['project', projectId, 'vault', 'contradictions'],
    queryFn: async () =>
      (await getJson<{ contradictions: VaultContradiction[] }>(`/api/v1/projects/${projectId}/vault/contradictions`))
        .contradictions,
    enabled: isConfigured && !!projectId,
    retry: (count, error) => !isNoVault(error) && count < 2,
    refetchInterval: refetchMs,
  })
}

export function useResolveContradiction() {
  const queryClient = useQueryClient()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  return useMutation({
    mutationFn: ({ id, ...body }: ContradictionResolution & { id: string }) =>
      postJson<VaultContradiction>(`/api/v1/projects/${projectId}/vault/contradictions/${id}/resolve`, body),
    onSuccess: () => {
      // The decision is a new source, and the facts' marks follow from the resolution.
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'vault', 'contradictions'] })
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'vault', 'map'] })
    },
  })
}

/** One report as `GET /vault/reports` lists it, open ones first: a working agent's message that an
 *  entry is wrong, and what the manager did with it (`a-working-agent-tells-the-manager-an-entry-is-wrong`). */
export interface VaultReport {
  id: string
  entry: string
  entry_kind: 'source' | 'fact'
  entry_name: string
  message: string
  reporter: { agent: string; run_id: string | null }
  /** `referred` is the one waiting for the operator. */
  status: 'pending' | 'corrected' | 'answered' | 'referred' | 'closed'
  answer: string | null
  /** The corrected fact a `corrected` report wrote, with its claim. */
  replaced_by: string | null
  replaced_by_claim: string | null
  close: { note: string; closed_at: string } | null
}

/** The reports agents filed. A 404 is a Hub that predates them, which the tab reads as no section.
 *  `refetchMs` polls while a manager job may still be answering one. */
export function useVaultReports(refetchMs: number | false = false) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<VaultReport[]>({
    queryKey: ['project', projectId, 'vault', 'reports'],
    queryFn: async () =>
      (await getJson<{ reports: VaultReport[] }>(`/api/v1/projects/${projectId}/vault/reports`)).reports,
    enabled: isConfigured && !!projectId,
    retry: (count, error) => !isNoVault(error) && count < 2,
    refetchInterval: refetchMs,
  })
}

export function useCloseVaultReport() {
  const queryClient = useQueryClient()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      postJson<VaultReport>(`/api/v1/projects/${projectId}/vault/reports/${id}/close`, { note }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'vault', 'reports'] })
      // A closed report no longer marks its entry disputed.
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'vault', 'map'] })
    },
  })
}
