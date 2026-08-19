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
  /** The Hub's own lifecycle phase for this path, when a document record exists for it. Archiving
   *  is a phase transition and does not relocate the file, so a document can be `archived` here
   *  while its path still sits outside `spec/changes/archive/` — the tree has to check both. */
  phase?: string | null
  /** The durable id the panel shell keys a `spec:` tab by (design D4, `2026-08-18-one-shell-three-panels`),
   *  present only for documents the Hub tracks a record for — `null` for a document discovery
   *  found on disk that was never created through the Hub. */
  document_id?: string | null
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
    | 'rejected'
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
      // An accepted/rejected proposal, or a fresh one from a gated submission, changes what this
      // document's pending list looks like — the same broadcast covers all three (accept/reject
      // routes and submit_spec_document all emit `spec_updated`).
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specProposals'] })
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
  phase: 'exploring' | 'proposed' | 'approved' | 'archived' | 'current'
  /** What happens to work that ignores this document. **Not phase.** Phase asks whether the
   *  operator agreed to it; rigor asks what the system does about work that does not satisfy it.
   *  A `gate` document can still be exploring, and an approved one can still be a sketch. */
  rigor: 'sketch' | 'contract' | 'gate'
  /** The document as the Hub last wrote it. Sent back on a rigor change so it cannot land on a
   *  document edited underneath the operator who read it. */
  content_digest: string | null
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
/** Raise or lower how strictly a document is enforced.
 *
 *  There is deliberately no agent-facing equivalent anywhere in this codebase. An agent blocked by
 *  a gate that could lower the document has not been gated. */
export function useSetSpecRigor() {
  return useSpecMutation<
    { path: string; rigor: string; reason?: string; expectedDigest?: string | null },
    SpecDocumentRecord
  >((projectId, { path, rigor, reason, expectedDigest }) =>
    postJson(`/api/v1/projects/${projectId}/project/documents/${path}/rigor`, {
      rigor,
      reason: reason ?? '',
      expected_digest: expectedDigest ?? null,
    }),
  )
}

export function useSetSpecPhase() {
  return useSpecMutation<{ path: string; to: string; reason?: string }, SpecDocumentRecord>(
    (projectId, { path, to, reason }) =>
      postJson(
        `/api/v1/projects/${projectId}/project/documents/phase?path=${encodeURIComponent(path)}&to=${encodeURIComponent(to)}`,
        { reason: reason ?? '' },
      ),
  )
}

// ---------------------------------------------------------------------------
// Edit proposals — `contract`/`gate` rigor gates a submission behind one of
// these instead of writing it (openspec/changes/2026-08-17-authoring-rigor-and-scope).
// ---------------------------------------------------------------------------

export interface SpecEditProposal {
  id: string
  unit_kind: 'requirement' | 'metadata'
  unit_key: string
  change_kind: 'add' | 'modify' | 'remove'
  /** `add` proposals only — the key of the requirement it was submitted immediately after, or
   *  null for "first". The in-position anchor a brand-new requirement has no existing row to
   *  carry otherwise. */
  position_after_key: string | null
  proposed_payload: Record<string, unknown>
  previous_payload: Record<string, unknown> | null
  status: 'pending' | 'accepted' | 'rejected' | 'stale'
  proposer_actor_kind: string | null
  proposer_actor_name: string | null
  created_at: string
  resolved_at: string | null
  resolved_by_actor_name: string | null
  resolution_reason: string
}

export function useSpecProposals(path: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ proposals: SpecEditProposal[] }>({
    queryKey: ['project', projectId, 'specProposals', path],
    queryFn: () =>
      getJson<{ proposals: SpecEditProposal[] }>(
        `/api/v1/projects/${projectId}/project/documents/${path}/proposals`,
      ),
    enabled: isConfigured && !!projectId && !!path,
  })
}

export function useAcceptSpecProposal() {
  return useSpecMutation<
    { path: string; proposalId: string; expectedDigest?: string | null },
    SpecDocumentRecord
  >((projectId, { path, proposalId, expectedDigest }) =>
    postJson(
      `/api/v1/projects/${projectId}/project/documents/${path}/proposals/${proposalId}/accept`,
      { expected_digest: expectedDigest ?? null },
    ),
  )
}

export function useRejectSpecProposal() {
  return useSpecMutation<{ path: string; proposalId: string; reason?: string }, unknown>(
    (projectId, { path, proposalId, reason }) =>
      postJson(
        `/api/v1/projects/${projectId}/project/documents/${path}/proposals/${proposalId}/reject`,
        { reason: reason ?? '' },
      ),
  )
}
