import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, getJson, postJson } from './client'
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

/** Whether the delivery a change-spec document declares can actually be honoured, computed fresh
 *  on every `GET /spec` read rather than stored in the file (design D5,
 *  `a-document-says-how-it-will-be-built-and-approval-starts-it`). Present only for a change-spec
 *  document at `exploring` or `proposed`; absent for every other document, kind or phase, and
 *  absent entirely from a Hub that predates this change (the `:8000` skew). */
export interface SpecDeliveryStatus {
  state: 'ok' | 'stale' | 'none' | 'absent'
  agent?: string
  reason?: 'archived' | 'unknown'
}

/** One task the board created for this approval. */
export interface ApprovalCreatedTask {
  id: string
  key: string
  title: string
}

/** A declared entry the board skipped because a hand-made task already served every requirement
 *  it named. */
export interface ApprovalServedEntry {
  key: string
  requirements: string[]
}

/** A dependency this approval's tasks could not honour. */
export interface ApprovalDependencyProblem {
  task_id: string
  task_key: string
  reference: string
  reason: string
}

/** What approval did about the document's delivery (design D6/D7). `state` is `not_applicable`
 *  for a document that is not a change-spec (only a change declares a delivery), `none` when the
 *  document declared no flow, `not_created` when a flow was declared but could not be made,
 *  `existing` when an unarchived flow already declared the document, and `created` for a new one.
 *  `messages` carries the Hub's own sentences, in the order it returns them. */
export interface ApprovalFlowOutcome {
  state: 'created' | 'existing' | 'not_created' | 'none' | 'not_applicable'
  job_id?: string
  name?: string
  agent?: string
  flow_state?: 'running' | 'disabled' | 'ended'
  messages: string[]
}

/** The newest approval's report (design D7) — present on `GET /spec` only for an approved
 *  document that has one. Every field is read as possibly absent: an older Hub returns neither
 *  this nor `delivery_status` at all (the `:8000` skew). Problems are rendered in the order the
 *  Hub returns them: created, then already_served, then failed, then dependencies_not_honoured,
 *  then the flow's own messages. */
export interface SpecApprovalOutcome {
  created: ApprovalCreatedTask[]
  already_served: ApprovalServedEntry[]
  failed: string | null
  dependencies_not_honoured: ApprovalDependencyProblem[]
  flow: ApprovalFlowOutcome
  delivery_agent?: string | null
}

/** The roadmap slice a change document specifies (`a-spec-is-written-one-slice-at-a-time`, D7).
 *  Present on `GET /spec` only for a document that names one; an older Hub never returns it. */
export interface SpecRoadmapSlice {
  document: string
  slice: string
}

/** What an approval asked with `draft_next_slice` did about the next slice (D4, D4a). `waiting` means
 *  the turn is queued once the slice's `open_tasks` close; `queued` means it was queued now (no
 *  linked task was open); the other states say why nothing will be queued. */
export interface SpecNextSliceOutcome {
  state:
    | 'waiting'
    | 'queued'
    | 'last_slice'
    | 'no_author'
    | 'no_conversation'
    | 'not_a_slice'
    | 'not_queued'
  slice: string | null
  agent: string | null
  open_tasks?: number
}

export interface SpecDocument {
  path: string
  content: string
  updated_at?: string
  delivery_status?: SpecDeliveryStatus
  approval_outcome?: SpecApprovalOutcome
  roadmap_slice?: SpecRoadmapSlice
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
    // Reported only for a retired requirement nothing serves any more (F214), which only
    // `GET /spec/requirements/{identifier}` reads — document coverage leaves retired rows out.
    | 'retired'
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

/** A requirement with no work linked to it. An object rather than a bare identifier because
 *  identifiers are minted per document, so `FR-1` names one requirement only when one document
 *  in the project declares it (F212). */
export interface UnservedRequirement {
  identifier: string
  document_id: string
  requirement_id: string
}

export interface CoverageResponse {
  requirements: CoverageEntry[]
  diagnostics: CoverageDiagnostic[]
  totals: Record<string, number>
  integration: Record<string, number>
  unserved: UnservedRequirement[]
}

/** One piece of evidence, as the Hub's `_evidence_view` reports it. `recording_run_live` is absent
 *  from a Hub that predates the change that added it, and reads as `false` there. */
export interface EvidencePiece {
  id: string
  summary: string
  kind: string
  locator: string | null
  actor_kind: string
  actor: string
  run_id: string | null
  task_id: string | null
  review_state: string
  recording_run_live?: boolean
  latest_review: { decision: string; reason: string; actor_kind: string; actor: string } | null
  produced_at: string
  footprint: {
    kind: string
    branch: string | null
    commit_sha: string | null
    outside_workspace_writes: string[] | null
  } | null
}

/** Oldest first — the order the route returns (`requirement_evidence.for_requirement`). */
export function useSpecEvidence(path: string, identifier: string, enabled: boolean) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ evidence: EvidencePiece[] }>({
    queryKey: ['project', projectId, 'specEvidence', path, identifier],
    queryFn: () =>
      getJson<{ evidence: EvidencePiece[] }>(
        `/api/v1/projects/${projectId}/project/spec/evidence?identifier=${encodeURIComponent(
          identifier,
        )}&document=${encodeURIComponent(path)}`,
      ),
    enabled: isConfigured && !!projectId && enabled,
  })
}

export function useDecideEvidence(path: string, identifier: string) {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({
      id,
      decision,
      reason,
    }: {
      id: string
      decision: 'accepted' | 'rejected'
      reason: string
    }) =>
      postJson<EvidencePiece>(`/api/v1/projects/${projectId}/project/spec/evidence/${id}/decision`, {
        decision,
        reason,
      }),
    onSuccess: () => {
      // Accepting can merge a commit for a waiting task, so the task-scoped keys move too
      // (`task` covers integrations/transitions/preview, `tasks` the lists and boards).
      for (const key of [
        ['specCoverage'],
        ['specEvidence', path, identifier],
        ['task'],
        ['tasks'],
      ]) {
        queryClient.invalidateQueries({ queryKey: ['project', projectId, ...key] })
      }
    },
  })
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

/** Coverage for several documents at once, one query per path, sharing `useSpecCoverage`'s own
 *  query key — so a card reading several documents' coverage can never disagree with the cache
 *  the document view itself reads, and both invalidate on the same `spec_updated`/evidence-decision
 *  events (`useSpecEvents`, `useDecideEvidence`). Order matches `paths`. */
export function useSpecCoverageMany(paths: string[]) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQueries({
    queries: paths.map((path) => ({
      queryKey: ['project', projectId, 'specCoverage', path],
      queryFn: () =>
        getJson<CoverageResponse>(
          `/api/v1/projects/${projectId}/project/spec/coverage?document=${encodeURIComponent(path)}`,
        ),
      enabled: isConfigured && !!projectId,
    })),
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
      // A piece an agent records while a row is open, and a recording run's end (`{run_ended}`,
      // which un-greys a piece held as still being recorded), both arrive here with no path.
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specEvidence'] })
      // An accepted/rejected proposal, or a fresh one from a gated submission, changes what this
      // document's pending list looks like — the same broadcast covers all three (accept/reject
      // routes and submit_spec_document all emit `spec_updated`).
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specProposals'] })
      // A rigor change arrives here (`set_document_rigor` broadcasts `{path, rigor}`), and so does
      // a save that retires a requirement — the history, the requirement list and an open
      // requirement's detail all move with them.
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specRigorHistory'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specRequirements'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specRequirement'] })
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
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({
      path,
      rigor,
      reason,
      expectedDigest,
    }: {
      path: string
      rigor: string
      reason?: string
      expectedDigest?: string | null
    }) =>
      postJson<SpecDocumentRecord>(`/api/v1/projects/${projectId}/project/documents/${path}/rigor`, {
        rigor,
        reason: reason ?? '',
        expected_digest: expectedDigest ?? null,
      }),
    // What `useSpecMutation` invalidates, plus the history of the path just changed — so the tab
    // that pressed Confirm does not wait for the `spec_updated` round-trip to see its own change.
    // Its own `onSuccess`, the way `useSetSpecPhase` has one, so the shared helper and every other
    // mutation built on it are unchanged.
    onSuccess: (_record, { path }) => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specDocuments'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specs'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specRigorHistory', path] })
    },
  })
}

/** One recorded rigor change. `reason` is `''` where none was given — every change the app made
 *  before it asked for one (F429). */
export interface SpecRigorEvent {
  id: string
  from: SpecDocumentRecord['rigor']
  to: SpecDocumentRecord['rigor']
  actor_kind: string
  actor: string
  reason: string
  created_at: string
}

/** Oldest first — the order the route returns (`spec_rigor.history_for`: `created_at, id`). */
export function useSpecRigorHistory(path: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ events: SpecRigorEvent[] }>({
    queryKey: ['project', projectId, 'specRigorHistory', path],
    queryFn: () =>
      getJson<{ events: SpecRigorEvent[] }>(
        `/api/v1/projects/${projectId}/project/documents/${path}/rigor-history`,
      ),
    enabled: isConfigured && !!projectId && !!path,
  })
}

/** A requirement as the index holds it. A removed requirement is retired, not deleted, so its
 *  links and evidence survive; `state` says which. */
export interface SpecRequirementRow {
  id: string
  identifier: string
  key: string
  document_id: string
  state: 'active' | 'retired'
  digest: string
  anchor: string | null
}

/** Every requirement of one document, **retired ones included** (the route's default) — the only
 *  read that returns them. Ordered by identifier as a *string*, so `FR-10` comes before `FR-2`. */
export function useSpecRequirements(path: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ requirements: SpecRequirementRow[] }>({
    queryKey: ['project', projectId, 'specRequirements', path],
    queryFn: () =>
      getJson<{ requirements: SpecRequirementRow[] }>(
        `/api/v1/projects/${projectId}/project/spec/requirements?document=${encodeURIComponent(
          path ?? '',
        )}`,
      ),
    enabled: isConfigured && !!projectId && !!path,
  })
}

export interface SpecRequirementDetail {
  requirement: SpecRequirementRow
  /** In `Task.created_at` order (`requirement_links.tasks_for_requirement`). */
  tasks: Array<{ id: string; title: string; status: string; assignee: string | null }>
  /** Oldest first (`requirement_evidence.for_requirement`). */
  evidence: EvidencePiece[]
  coverage: CoverageEntry | null
}

/** One requirement and everything still pointing at it. `document` is always sent: identifiers
 *  are minted per document, and without it an identifier two documents declare is a 422. */
export function useSpecRequirement(identifier: string, path: string) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<SpecRequirementDetail>({
    queryKey: ['project', projectId, 'specRequirement', path, identifier],
    queryFn: () =>
      getJson<SpecRequirementDetail>(
        `/api/v1/projects/${projectId}/project/spec/requirements/${encodeURIComponent(
          identifier,
        )}?document=${encodeURIComponent(path)}`,
      ),
    enabled: isConfigured && !!projectId,
  })
}

/** Approving (or reopening). Approving a change-spec document with a flow delivery may create the
 *  flow (design D6, `a-document-says-how-it-will-be-built-and-approval-starts-it`), so this
 *  invalidates the loops and jobs keys on success too — not just `useSpecMutation`'s
 *  `specDocuments`/`specs` — or the phase bar would keep offering "Start a flow…" beside the flow
 *  approval just made. */
export function useSetSpecPhase() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({
      path,
      to,
      reason,
      delivery_agent,
      draft_next_slice,
    }: {
      path: string
      to: string
      reason?: string
      /** Sent only for a document whose `GET /spec` named a `roadmap_slice`: a Hub that returns
       *  that field also accepts this one, and no other Hub is ever sent it (it would 422). */
      draft_next_slice?: boolean
      /** Sent only when the operator chose one from the stale-delivery strip (design D5b): an
       *  agent name, or `''` for "No flow". Omitted otherwise — a bundle with no `delivery_status`
       *  (the strip never appears without it) must never send this to a Hub that predates it,
       *  which would 422 an unknown field. */
      delivery_agent?: string
    }) =>
      postJson<
        SpecDocumentRecord & {
          approval_outcome?: SpecApprovalOutcome
          next_slice?: SpecNextSliceOutcome
        }
      >(
        `/api/v1/projects/${projectId}/project/documents/phase?path=${encodeURIComponent(path)}&to=${encodeURIComponent(to)}`,
        {
          reason: reason ?? '',
          ...(delivery_agent !== undefined ? { delivery_agent } : {}),
          ...(draft_next_slice !== undefined ? { draft_next_slice } : {}),
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specDocuments'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specs'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'loops'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'jobs'] })
    },
  })
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
  status: 'pending' | 'accepted' | 'rejected' | 'stale' | 'withdrawn' | 'superseded'
  /** The document version this was made against. Two identical proposals on different versions
   *  are not duplicates: the older is refused as stale on accept (`a-pending-proposal-can-be-
   *  withdrawn`, D4). Absent from a Hub older than the field. */
  expected_digest?: string | null
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

/** A decision on one proposal. Invalidates the document's proposals **on settled**, not only on
 *  success: an accept refused as stale still moves the row out of `pending`, and the pressing tab
 *  must not wait for the broadcast to drop it (F428, F431; `a-pending-proposal-can-be-withdrawn`
 *  D5). Everything else `useSpecMutation` invalidates, on success, as before. */
function useProposalDecision<TArgs extends { path: string }, TResult>(
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
    onSettled: (_data, _error, args) => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specProposals', args.path] })
    },
  })
}

export function useAcceptSpecProposal() {
  return useProposalDecision<
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
  return useProposalDecision<{ path: string; proposalId: string; reason?: string }, unknown>(
    (projectId, { path, proposalId, reason }) =>
      postJson(
        `/api/v1/projects/${projectId}/project/documents/${path}/proposals/${proposalId}/reject`,
        { reason: reason ?? '' },
      ),
  )
}

/** Take a pending proposal off the list without judging it (D3): for duplicates and proposals
 *  nobody is pursuing. The document is untouched. */
export function useWithdrawSpecProposal() {
  return useProposalDecision<{ path: string; proposalId: string; note?: string }, unknown>(
    (projectId, { path, proposalId, note }) =>
      postJson(
        `/api/v1/projects/${projectId}/project/documents/${path}/proposals/${proposalId}/withdraw`,
        { note: note ?? '' },
      ),
  )
}

// --------------------------------------------------------------------------- the corpus, from the app
// `the-corpus-is-indexed-arranged-and-adopted-from-the-app` (F206): reindex, adopt one, adopt all,
// and arrange had no caller here. Each reads the route's own answer; nothing is computed in the UI.

export interface ReindexDocumentCounts {
  created: string[]
  reworded: string[]
  retired: string[]
  restored: string[]
  unchanged: string[]
}

export interface CorpusSkip {
  path: string
  /** `file_missing`, `no_readable_payload`, or `write_failed` (F434), with the OS reason. */
  reason: string
  message?: string
}

export interface ReindexResult {
  documents: Record<string, ReindexDocumentCounts | null>
  index: {
    written: { path: string; documents: number; home: string | null } | null
    diagnostics: SpecDiagnostic[]
  }
  corpus: { rerendered: string[]; skipped: CorpusSkip[] }
}

export interface AdoptionDifference {
  field: string
  file: string | null
  row: string | null
}

/** One path's outcome in an adopt-all sweep, in the route's own shape. */
export interface CorpusAdoptOutcome {
  adopted: boolean
  path: string
  code?: string
  message?: string
  differences?: AdoptionDifference[]
}

export interface CorpusAdoptResult {
  documents: Record<string, CorpusAdoptOutcome>
  adopted: string[]
  skipped: string[]
  diagnostics: SpecDiagnostic[]
}

export interface ArrangeResult {
  path: string
  parent: string | null
  corpus: { rerendered: string[]; skipped: CorpusSkip[] }
}

/** Like `useSpecMutation`, and also drops every open document's content: reindex and arrange
 *  re-render files, so a page already loaded would show the navigation it had before. */
function useCorpusMutation<TArgs, TResult>(
  call: (projectId: string, args: TArgs) => Promise<TResult>,
) {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (args: TArgs) => call(projectId ?? '', args),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specDocuments'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specs'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'spec'] })
    },
  })
}

/** Rebuild the requirement index and `spec/index.json`. With no `home`, the Hub answers
 *  `index_home_required` when it will not guess one; the strip then asks the operator. */
export function useReindexSpec() {
  return useCorpusMutation<{ home?: string }, ReindexResult>((projectId, { home }) =>
    postJson(`/api/v1/projects/${projectId}/project/spec/reindex`, home ? { home } : {}),
  )
}

/** Place a document under another in the corpus hierarchy, or at the top with `parent: null`. */
export function useArrangeSpecDocument() {
  return useCorpusMutation<{ path: string; parent: string | null }, ArrangeResult>(
    (projectId, body) =>
      postJson(`/api/v1/projects/${projectId}/project/spec/documents/arrange`, body),
  )
}

/** Adopt one document found on disk that the Hub has no record of. */
export function useAdoptSpecDocument() {
  return useSpecMutation<{ path: string }, SpecDocumentRecord>((projectId, { path }) =>
    postJson(`/api/v1/projects/${projectId}/project/documents/adopt`, { path }),
  )
}

/** Adopt every adoptable document beneath `spec/`. Never fails as a whole. */
export function useAdoptSpecCorpus() {
  return useSpecMutation<void, CorpusAdoptResult>((projectId) =>
    postJson(`/api/v1/projects/${projectId}/project/spec/adopt`),
  )
}

/** The body of a refused corpus call, as the Hub sent it: `{detail: {message, code, ...}}` or a
 *  plain `{detail: "..."}`. Null when the error is not an API error with a JSON body. */
export function corpusRefusal(error: unknown): {
  status: number
  message: string
  code?: string
  differences?: AdoptionDifference[]
  diagnostics?: SpecDiagnostic[]
} | null {
  if (!(error instanceof ApiError)) return null
  try {
    const body = JSON.parse(error.message) as { detail?: unknown }
    const detail = body.detail
    if (typeof detail === 'string') return { status: error.status, message: detail }
    if (detail && typeof detail === 'object') {
      const d = detail as Record<string, unknown>
      return {
        status: error.status,
        message: typeof d.message === 'string' ? d.message : error.message,
        code: typeof d.code === 'string' ? d.code : undefined,
        differences: Array.isArray(d.differences) ? (d.differences as AdoptionDifference[]) : undefined,
        diagnostics: Array.isArray(d.diagnostics) ? (d.diagnostics as SpecDiagnostic[]) : undefined,
      }
    }
  } catch {
    // Not JSON: fall through to the raw text.
  }
  return { status: error.status, message: error.message }
}
