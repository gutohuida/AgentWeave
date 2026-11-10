import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { deleteJson, getJson, postJson } from './client'
import type { SpecDocumentRecord } from './spec'

/** `an-agent-the-operator-trusts-can-tidy-the-specs`: what the operator sees of an agent's tidying. */

export interface SupersededMark {
  at: string
  by: string
  reason: string
  /** The document that took over, when the agent named one. */
  successor: string | null
}

export interface HeldMark {
  at: string
  note: string | null
}

/** A rewritten or retired requirement the code contradicted (FR-13). */
export interface CodeWins {
  requirement: string
  before: string | null
  after: string | null
  /** The file or test the agent read to decide. */
  cited: string
}

export interface TidyAct {
  id: string
  act: string
  path: string
  agent: string
  run_id: string | null
  at: string
  reason: string
  code_wins: CodeWins | null
  reviewed: boolean
}

export type TidyDocument = SpecDocumentRecord & {
  superseded?: SupersededMark | null
  held?: HeldMark | null
}

function usePrefix() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return { enabled: isConfigured && !!projectId, projectId, base: `/api/v1/projects/${projectId}/project` }
}

function useRefreshSpecs() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return () => {
    for (const key of ['specDocuments', 'specs', 'spec', 'tidyActs', 'supersededDocuments']) {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, key] })
    }
  }
}

/** The documents marked superseded, for the operator's filter and batch archive (FR-10). */
export function useSupersededDocuments() {
  const { enabled, projectId, base } = usePrefix()
  return useQuery<{ documents: TidyDocument[] }>({
    queryKey: ['project', projectId, 'supersededDocuments'],
    queryFn: () => getJson<{ documents: TidyDocument[] }>(`${base}/documents?superseded=true`),
    enabled,
  })
}

export interface ArchiveBatchResult {
  archived: string[]
  refused: { path: string; code: string; reason: string }[]
}

export function useArchiveBatch() {
  const { base } = usePrefix()
  const refresh = useRefreshSpecs()
  return useMutation({
    mutationFn: (args: { paths: string[]; reason?: string }) =>
      postJson<ArchiveBatchResult>(`${base}/documents/archive-batch`, args),
    onSuccess: refresh,
  })
}

export function useHoldDocument() {
  const { base } = usePrefix()
  const refresh = useRefreshSpecs()
  return useMutation({
    mutationFn: ({ path, note }: { path: string; note: string }) =>
      postJson<TidyDocument>(`${base}/documents/${encodeURI(path)}/hold`, { note }),
    onSuccess: refresh,
  })
}

export function useReleaseHold() {
  const { base } = usePrefix()
  const refresh = useRefreshSpecs()
  return useMutation({
    mutationFn: (path: string) => deleteJson<TidyDocument>(`${base}/documents/${encodeURI(path)}/hold`),
    onSuccess: refresh,
  })
}

/** Every tidy act not yet reviewed (FR-6). The route answers a bare list. */
export function useTidyActs() {
  const { enabled, projectId, base } = usePrefix()
  return useQuery<TidyAct[]>({
    queryKey: ['project', projectId, 'tidyActs'],
    queryFn: () => getJson<TidyAct[]>(`${base}/tidy-acts?reviewed=false`),
    enabled,
  })
}

export function useMarkTidyReviewed() {
  const { base } = usePrefix()
  const refresh = useRefreshSpecs()
  return useMutation({
    mutationFn: (args: { ids: string[] } | { all: true }) =>
      postJson<{ marked: number; unreviewed: number }>(`${base}/tidy-acts/reviewed`, args),
    onSuccess: refresh,
  })
}
