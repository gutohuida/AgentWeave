import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { useSSE } from '@/hooks/useSSE'

export interface SpecEntry {
  path: string
  updated_at?: string
  // Additive — present only for documents the index covers ("filed"); absent
  // for "unindexed" (no usable index to be filed against) and "unfiled" (the
  // index is valid and does not list this document). There is no "stale":
  // that state meant a cached row no active sync source claimed, and neither
  // the cache nor the sources exist.
  title?: string
  kind?: 'baseline' | 'system-map' | 'roadmap' | 'change-spec'
  status?: string
  parent?: string | null
  order?: number
  state?: 'filed' | 'unindexed' | 'unfiled'
}

export interface SpecDocument {
  path: string
  content: string
  updated_at?: string
}

// `source_id` and `updated_at` are gone with the push model: a source was a
// machine syncing this project's documents, and there are no longer any. The
// index is a file the Hub reads, so its state is the only thing to report.
export interface SpecManifestSummary {
  state: 'valid' | 'absent' | 'unreadable' | 'invalid'
  version: number | null
}

export interface SpecDiagnostic {
  code: string
  path?: string | null
  field?: string | null
  expected?: string | null
  actual?: string | null
  source_ids?: string[] | null
}

export interface SpecMissingEntry {
  path: string
  title: string
  kind: string
  status: string
  parent: string | null
  order: number
}

export interface SpecListResponse {
  specs: SpecEntry[]
  home: string | null
  manifest: SpecManifestSummary | null
  missing: SpecMissingEntry[]
  diagnostics: SpecDiagnostic[]
}

export function useSpecList() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<SpecListResponse>({
    queryKey: ['project', projectId, 'specs'],
    queryFn: () => getJson<SpecListResponse>(`/api/v1/projects/${projectId}/project/specs`),
    enabled: isConfigured && !!projectId,
  })
}

export function useSpec(path: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<SpecDocument>({
    queryKey: ['project', projectId, 'spec', path],
    queryFn: () =>
      getJson<SpecDocument>(
        `/api/v1/projects/${projectId}/project/spec?path=${encodeURIComponent(path ?? '')}`,
      ),
    enabled: isConfigured && !!projectId && !!path,
  })
}

/** One requirement's coverage. `integration` is never optional: a state shown without it
 *  would be true of a branch and false of the product. */
export interface CoverageEntry {
  identifier: string
  requirement_id: string
  document_id: string
  state:
    | 'drifting'
    | 'stale'
    | 'evidence_awaiting_review'
    | 'verified'
    | 'in_progress'
    | 'not_started'
    | 'unserved'
  integration: 'integrated' | 'not_integrated' | 'unknown' | 'not_applicable'
  evidence_count: number
  accepted_count: number
  linked_task_ids: string[]
}

/** A requirement that could not be given a state at all — broken, not unserved. */
export interface CoverageDiagnostic {
  requirement_id: string
  identifier: string
  document_id: string
  problem: string
}

export interface CoverageResponse {
  requirements: CoverageEntry[]
  diagnostics: CoverageDiagnostic[]
  totals: Record<string, number>
  integration: Record<string, number>
  unserved: string[]
}

export function useSpecCoverage(path: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<CoverageResponse>({
    queryKey: ['project', projectId, 'specCoverage', path],
    queryFn: () =>
      getJson<CoverageResponse>(
        `/api/v1/projects/${projectId}/project/spec/coverage${
          path ? `?document=${encodeURIComponent(path)}` : ''
        }`,
      ),
    enabled: isConfigured && !!projectId,
  })
}

export function useSpecEvents() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()

  // Invalidate spec queries when the Hub broadcasts a spec_updated SSE event
  useSSE((event) => {
    const d = event.data as { path?: string; previous_path?: string; project_id?: string }
    if (event.type === 'spec_updated' && d.project_id === projectId) {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specs'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specDocuments'] })
      // Coverage moves on a save (a rewording makes evidence stale) and on evidence arriving,
      // and both arrive as `spec_updated`.
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specCoverage'] })
      if (d?.path) {
        queryClient.invalidateQueries({ queryKey: ['project', projectId, 'spec', d.path] })
      }
      // A rename leaves a cache entry under a path that no longer resolves. Dropping it matters
      // more than the usual invalidation: nothing will ever refetch that key again.
      if (d?.previous_path && d.previous_path !== d.path) {
        queryClient.removeQueries({ queryKey: ['project', projectId, 'spec', d.previous_path] })
      }
    }
  })
}

/** Follow the open document when the agent renames it.
 *
 *  A document's identity in this frontend is its path — the query key, the URL
 *  and the panel's prop all hold it — so the one operation that changes a path
 *  has to be told to the screen showing it, or the operator is left looking at
 *  a document that no longer exists. `onMoved` is the screen's own navigation,
 *  because whether this is a push or a replace is the screen's business. */
export function useSpecDocumentRename(
  openPath: string | null,
  onMoved: (path: string) => void,
): void {
  const { selectedProjectId: projectId } = useConfigStore()

  useSSE((event) => {
    const d = event.data as { path?: string; previous_path?: string; project_id?: string }
    if (event.type !== 'spec_updated' || d.project_id !== projectId) return
    if (!d.path || !d.previous_path || d.previous_path === d.path) return
    if (openPath !== d.previous_path) return
    onMoved(d.path)
  })
}

// ---------------------------------------------------------------------------
// Documents — phase, and the operator decisions that move it
// ---------------------------------------------------------------------------

export interface SpecDocumentRecord {
  id: string
  path: string
  title: string
  kind: string
  /** The authority on where the document stands. The `aw-spec-status` metadata
   *  inside the file is a copy for whoever reads it, never the source. */
  phase: 'exploring' | 'proposed' | 'approved'
  explore_closed: boolean
  updated_at: string
}

/** One reason a document cannot be proposed yet, and where to look. */
export interface SpecBlockingFinding {
  code: string
  where: string
  message: string
}

export function useSpecDocuments() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ documents: SpecDocumentRecord[] }>({
    queryKey: ['project', projectId, 'specDocuments'],
    queryFn: () =>
      getJson<{ documents: SpecDocumentRecord[] }>(
        `/api/v1/projects/${projectId}/project/documents`,
      ),
    enabled: isConfigured && !!projectId,
  })
}

function useSpecMutation<TArgs, TResult>(
  call: (projectId: string, args: TArgs) => Promise<TResult>,
) {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (args: TArgs) => call(projectId ?? '', args),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specDocuments'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specs'] })
    },
  })
}

/** Start an exploration. The document exists from this moment, which is what
 *  gives "propose" and "approve" something to refer to.
 *
 *  `path` is optional and normally omitted: the Hub mints a placeholder, because
 *  a document is created before anyone knows what it is about and a path derived
 *  from the operator's opening sentence records the guess that preceded the
 *  interview. Read the created path off the record rather than predicting it. */
export function useCreateSpecDocument() {
  return useSpecMutation<{ path?: string; title?: string; kind?: string }, SpecDocumentRecord>(
    (projectId, body) => postJson(`/api/v1/projects/${projectId}/project/documents`, body),
  )
}

/** The operator declaring exploration finished. Not a computation — whether an
 *  exploration is complete enough to propose from is a judgement, and putting a
 *  model in that path would make the gate theatre. */
export function useCloseExploration() {
  return useSpecMutation<{ path: string }, SpecDocumentRecord>((projectId, { path }) =>
    postJson(
      `/api/v1/projects/${projectId}/project/documents/close-exploration?path=${encodeURIComponent(path)}`,
    ),
  )
}

export function useProposeSpecDocument() {
  return useSpecMutation<
    { path: string },
    SpecDocumentRecord & { blocking: SpecBlockingFinding[] }
  >((projectId, { path }) =>
    postJson(
      `/api/v1/projects/${projectId}/project/documents/propose?path=${encodeURIComponent(path)}`,
    ),
  )
}

/** Approving, or reopening. There is no agent-facing equivalent of this call. */
export function useSetSpecPhase() {
  return useSpecMutation<{ path: string; to: string; reason?: string }, SpecDocumentRecord>(
    (projectId, { path, to, reason }) =>
      postJson(
        `/api/v1/projects/${projectId}/project/documents/phase?path=${encodeURIComponent(path)}&to=${encodeURIComponent(to)}`,
        { reason: reason ?? '' },
      ),
  )
}
