import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, deleteJson, getJson, patchJson, postJson, putJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { useSSE } from '@/hooks/useSSE'
import type { KeptWork } from '@/store/specDeletionStore'

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
 *  document at `exploring` or `approved` (where Build reads it); absent for every other document,
 *  kind or phase, and absent entirely from a Hub that predates this change (the `:8000` skew). */
export interface SpecDeliveryStatus {
  state: 'ok' | 'stale' | 'none' | 'absent'
  agent?: string
  reason?: 'archived' | 'unknown'
  /** `delivery.reviewer`, the default reviewer of every task naming none (F508). Absent when the
   *  document names none: any free agent reviews. */
  reviewer?: string
  /** Whether `reviewer` is an open agent. A review never moves from a stale default to someone
   *  else; it comes to the operator. */
  reviewer_state?: 'ok' | 'archived' | 'unknown'
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

/** An open task re-approval brought up to date (F535): which fields changed, and the identifiers of
 *  this document's requirements it was linked to and unlinked from. */
export interface ApprovalRefreshedTask {
  id: string
  key: string
  title: string
  fields: string[]
  linked: string[]
  unlinked: string[]
}

/** A closed task, left as delivered, that still links a requirement the document retired. */
export interface ApprovalClosedLinkingRetired {
  id: string
  key: string
  status: string
  requirements: string[]
}

/** A task the document created under a key it no longer declares. Reported, never changed. */
export interface ApprovalUndeclaredTask {
  id: string
  key: string
  status: string
}

/** A dependency this approval's tasks could not honour. */
export interface ApprovalDependencyProblem {
  task_id: string
  task_key: string
  reference: string
  reason: string
}

/** What a build did about the document's delivery (design D6/D7; Build since
 *  `exploring-ends-at-an-approved-plan`). `state` is `not_applicable` for a document that is not a
 *  change-spec (only a change declares a delivery), `none` when the document declared no flow,
 *  `not_created` when a flow was declared but could not be made, `existing` when an unarchived flow
 *  already declared the document, `created` for a new one, and `already_built` when Approve and
 *  build built nothing because intake recorded the work as built. `messages` carries the Hub's own
 *  sentences, in the order it returns them. */
export interface ApprovalFlowOutcome {
  state: 'created' | 'existing' | 'not_created' | 'none' | 'not_applicable' | 'already_built'
  job_id?: string
  name?: string
  agent?: string
  flow_state?: 'running' | 'disabled' | 'ended'
  messages: string[]
}

/** The newest approval's report (design D7) — present on `GET /spec` only for an approved
 *  document that has one. Every field is read as possibly absent: an older Hub returns neither
 *  this nor `delivery_status` at all (the `:8000` skew). Problems are rendered in the order the
 *  Hub returns them: created, then already_served, then failed, then refreshed,
 *  closed_linking_retired and no_longer_declared (F535; absent from an older Hub), then
 *  dependencies_not_honoured, then the flow's own messages. */
export interface SpecApprovalOutcome {
  created: ApprovalCreatedTask[]
  already_served: ApprovalServedEntry[]
  failed: string | null
  refreshed?: ApprovalRefreshedTask[]
  closed_linking_retired?: ApprovalClosedLinkingRetired[]
  no_longer_declared?: ApprovalUndeclaredTask[]
  dependencies_not_honoured: ApprovalDependencyProblem[]
  /** Only on a report written before approval stopped starting the flow: Build reports it now. */
  flow?: ApprovalFlowOutcome
  delivery_agent?: string | null
  /** Intake recorded the work as already built (`already-built-at-intake`): close its tasks as
   *  built at these commits instead of building them. */
  already_built?: SpecAlreadyBuiltOffer
}

export interface SpecAlreadyBuiltOffer {
  commits: string[]
  route: string
  message: string
}

/** What the newest Build (or Approve and build) did (`build-is-separate`). */
export interface SpecBuildOutcome {
  flow: ApprovalFlowOutcome
  delivery_agent?: string | null
  reviewer?: string | null
  /** The build it recorded (`a-build-has-a-driver-a-level-and-its-people`); absent from an older
   *  Hub. `unresolved_builders` names each declared builder that is no open agent. */
  build?: SpecBuild & {
    unresolved_builders?: Array<{ task: string; builder: string }>
    joined?: boolean
    message?: string
  }
}

export type BuildDriver = 'flow' | 'lead' | 'hand'
export type BuildLevel = 'fast' | 'reviewed' | 'gated'
export type BuildLanding = 'main' | 'nowhere'

/** One build of a document, as `GET /project/spec` lists them (`builds`, newest first). */
export interface SpecBuild {
  id: string
  state: 'running' | 'stopped' | 'finished'
  driver: BuildDriver
  level: BuildLevel
  builders: string[]
  reviewers: string[]
  lead: string | null
  budget_cap_usd: number | null
  spent_usd: number | null
  unpriced_turns: number
  window_start: string | null
  window_end: string | null
  landing: BuildLanding
  loop_id: string | null
  stop_reason: string | null
  created_at: string | null
  stopped_at: string | null
}

/** What the operator chooses when they press Build: each left out takes the recommendation. */
export interface BuildChoices {
  delivery_agent?: string
  driver?: BuildDriver
  level?: BuildLevel
  builders?: string[]
  reviewers?: string[]
  lead?: string
  budget_cap_usd?: number
  window_start?: string
  window_end?: string
  landing?: BuildLanding
  task_builders?: Record<string, string>
}

/** The build the document recommends, with a reason per choice (`recommend-a-build`): what Build
 *  and Approve and build open with. Absent on a document that declares no delivery. The build's
 *  settings (driver to task_builders) are absent from an older Hub. */
export interface SpecRecommendedBuild {
  mode: 'flow' | 'none'
  agent: string | null
  reviewer: string | null
  tester: string | false | null
  cron: string
  stop_when_queue_empties: boolean
  stop_at: string | null
  driver?: BuildDriver
  level?: BuildLevel
  builders?: string[]
  reviewers?: string[]
  lead?: string | null
  budget_cap_usd?: number | null
  landing?: BuildLanding
  /** Each declared task's builder by key, as the document names it (F1046). */
  task_builders?: Record<string, string | null>
  reasons: Partial<
    Record<
      | 'mode'
      | 'agent'
      | 'reviewer'
      | 'tester'
      | 'stop'
      | 'cron'
      | 'driver'
      | 'level'
      | 'builders'
      | 'reviewers'
      | 'lead'
      | 'cap'
      | 'landing',
      string
    >
  >
}

/** The roadmap slice a change document specifies (`a-spec-is-written-one-slice-at-a-time`, D7).
 *  Present on `GET /spec` only for a document that names one; an older Hub never returns it. */
export interface SpecRoadmapSlice {
  document: string
  slice: string
}

/** Where an approved or archived change stands on its way into the corpus, computed per read
 *  (`a-finished-change-is-folded-into-its-capability`). `ready`: every task is approved or
 *  rejected and no merge names it yet. Absent for other kinds and phases, and from a Hub that
 *  predates the change. */
export interface SpecFoldState {
  state: 'tasks_open' | 'ready' | 'folded'
  open_tasks: string[]
  capabilities: string[]
  /** The change's latest reconcile result (`a-change-is-reconciled-with-its-code-before-it-is-
   *  folded`). Absent from a Hub that predates it. */
  reconcile?: SpecReconcileResult
}

export type SpecReconcileClass = 'missing' | 'partial' | 'contradicts' | 'unrequested'

export interface SpecReconcileGap {
  class: SpecReconcileClass
  requirement: string | null
  where: string
  summary: string
}

export type SpecReconcileResult =
  | { state: 'none' }
  | {
      state: 'recorded'
      id: string
      author: string
      run_id: string | null
      at: string | null
      summary: string
      counts: Record<SpecReconcileClass, number>
      gaps: SpecReconcileGap[]
    }

/** One defect of a change and the step that caught it, derived by the Hub from its own records. */
export interface SpecDefect {
  source: 'amendment' | 'cannot_satisfy' | 'review' | 'reconcile' | 'operator'
  caught_by: string
  summary: string
  at: string | null
  by: string
}

export interface SpecDefectsChange {
  document_id: string
  path: string
  title: string
  phase: string
  defects: SpecDefect[]
  by_step: Record<string, number>
}

/** Defects per change, by the step that caught them. Oldest first within a change. */
export function useSpecDefects() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ changes: SpecDefectsChange[] }>({
    // Under `specs`, so `spec_updated` and every spec mutation refresh it.
    queryKey: ['project', projectId, 'specs', 'defects'],
    queryFn: () =>
      getJson<{ changes: SpecDefectsChange[] }>(`/api/v1/projects/${projectId}/project/spec/defects`),
    enabled: isConfigured && !!projectId,
  })
}

/** The stages after approval a defect can be caught at, after the project's journey steps. Restates
 *  `spec_defects.POST_APPROVAL_STEPS`; the Hub refuses anything else with 422 naming `caught_by`. */
export const POST_APPROVAL_STEPS = ['build', 'review', 'test', 'reconcile', 'after-fold'] as const

/** Record a defect against a change, and the step that caught it. */
export function useRecordDefect() {
  return useSpecMutation<{ path: string; summary: string; caught_by: string }, SpecDefect>(
    (projectId, { path, ...body }) =>
      postJson(`/api/v1/projects/${projectId}/project/documents/${path}/defects`, body),
  )
}

/** Ask an agent to reconcile an approved change with its code; the Hub writes the brief. */
export function useAskReconcile() {
  return useSpecMutation<{ path: string; agent: string }, { agent: string; status: string }>(
    (projectId, { path, agent }) =>
      postJson(`/api/v1/projects/${projectId}/project/documents/${path}/reconcile`, { agent }),
  )
}

/** One task closed as already built: where it was, where it is now, and the evidence recorded. */
export interface AlreadyBuiltTask {
  id: string
  title: string
  from_status: string
  status: string
  evidence: string[]
}

export interface AlreadyBuiltResult {
  document: string
  commits: string[]
  tasks: AlreadyBuiltTask[]
}

/** Close every open task of an approved change as already built, against commits on the main
 *  branch (`every-task-can-always-be-moved-on` FR-5/FR-6). Each task moves to under review with
 *  evidence awaiting a decision, and is approved once that evidence is accepted. */
export function useCloseAlreadyBuilt() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ path, commits }: { path: string; commits: string[] }) =>
      postJson<AlreadyBuiltResult>(
        `/api/v1/projects/${projectId}/project/documents/${path}/close-already-built`,
        { commits },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specDocuments'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specs'] })
      for (const key of [['specCoverage'], ['specEvidence'], ['task'], ['tasks']]) {
        queryClient.invalidateQueries({ queryKey: ['project', projectId, ...key] })
      }
    },
  })
}

export interface SpecDocument {
  path: string
  content: string
  updated_at?: string
  delivery_status?: SpecDeliveryStatus
  fold_state?: SpecFoldState
  approval_outcome?: SpecApprovalOutcome
  build_outcome?: SpecBuildOutcome
  recommended_build?: SpecRecommendedBuild
  /** Every build of this document, newest first (absent from an older Hub). */
  builds?: SpecBuild[]
  /** The version of the content this read shows. An approval names it, and is refused when the
   *  document changed since (`approve-what-was-seen`). */
  content_version?: string
  roadmap_slice?: SpecRoadmapSlice
  /** On a roadmap: the change document that specifies each slice, by slice key. */
  slice_documents?: Record<string, string>
  /** Set only on a retired (archived) capability: why, and the capability that absorbed it (F536). */
  retired?: SpecRetirement
}

export interface SpecRetirement {
  reason: string
  absorbed_by: string | null
  at: string | null
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
  /** The Hub's own sentence for it (`spec_manifest.describe_diagnostic`); absent on an older Hub. */
  message?: string | null
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
    // A tester changed or removed one of its criteria and the operator has not reviewed it yet
    // (tester-amends): its evidence cannot count until they do.
    | 'amendment_unreviewed'
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
  /** The folded change requirement whose verification this one carries (F593), or null. */
  served_by?: {
    requirement_id: string
    identifier: string
    document_id: string
    document_path?: string | null
  } | null
  /** Why the state is what it is, where the state alone does not say (F706: "partial evidence only"). */
  reason?: string | null
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
  /** What it takes to judge the piece (vis-D5): absent from a Hub before migration 0130, null where
   *  the recorder gave none. `output` is the tail, led by "[earlier output cut]" when it was cut. */
  command?: string | null
  output?: string | null
  covers?: 'full' | 'partial' | null
  /** The durable requirement this piece is about; `FR-n` alone repeats in every document. */
  requirement_id?: string
  /** The requirement in the document's own words; the statement is null when it cannot be read.
   *  `document` names which document's `FR-n` it is. */
  requirement?: {
    identifier: string
    statement: string | null
    document?: { path: string; title: string } | null
  } | null
  /** The newest later piece for the same requirement and task, when one replaced this. */
  superseded_by?: string | null
  /** False when it was recorded for an earlier wording of the requirement (coverage's `stale`
   *  for this piece): its review state is about words the requirement no longer says, so it does
   *  not count as the requirement's evidence (F691). Null or absent when the Hub could not tell. */
  for_current_wording?: boolean | null
}

/** A decision's answer: the piece, plus what it did to an approved task (F730 item 8) and, for an
 *  overturn, the decision it reversed (F692). */
export interface EvidenceDecisionResult extends EvidencePiece {
  task_reopen?: { task: string; reopened: boolean; reason?: string }
  overturned?: { from: string }
}

/** A piece recorded for words the requirement no longer says (F691). */
export function forEarlierWording(piece: Pick<EvidencePiece, 'for_current_wording'>): boolean {
  return piece.for_current_wording === false
}

/** Every piece of evidence in the project, oldest first (`GET /spec/evidence`, the order the route
 *  returns). Under `specEvidence`, so `spec_updated` refreshes it with every other evidence read. */
export function useProjectEvidence(enabled = true) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ evidence: EvidencePiece[] }>({
    queryKey: ['project', projectId, 'specEvidence', '__all__'],
    queryFn: () =>
      getJson<{ evidence: EvidencePiece[] }>(`/api/v1/projects/${projectId}/project/spec/evidence`),
    enabled: isConfigured && !!projectId && enabled,
  })
}

export interface EvidenceReviewRow {
  id: string
  decision: 'accepted' | 'rejected'
  actor_kind: string
  actor: string
  run_id: string | null
  reason: string | null
  created_at: string
}

/** Every review of one piece, oldest first (`GET /spec/evidence/{id}/reviews`); read when opened. */
export function useEvidenceReviews(evidenceId: string, enabled: boolean) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ reviews: EvidenceReviewRow[] }>({
    queryKey: ['project', projectId, 'specEvidence', 'reviews', evidenceId],
    queryFn: () =>
      getJson<{ reviews: EvidenceReviewRow[] }>(
        `/api/v1/projects/${projectId}/project/spec/evidence/${encodeURIComponent(evidenceId)}/reviews`,
      ),
    enabled: isConfigured && !!projectId && enabled,
  })
}

export interface EvidenceDiff {
  files: { path: string; status: string; patch: string }[]
  base: string | null
  commit: string | null
  truncated: boolean
  reason: string | null
}

/** The work a piece's commit carries on its line of work (`GET /spec/evidence/{id}/diff`). Fetched
 *  only when its proof is opened; a commit's diff never changes, so it is cached for the session. */
export function useEvidenceDiff(evidenceId: string, enabled: boolean) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<EvidenceDiff>({
    queryKey: ['project', projectId, 'evidenceDiff', evidenceId],
    queryFn: () =>
      getJson<EvidenceDiff>(
        `/api/v1/projects/${projectId}/project/spec/evidence/${encodeURIComponent(evidenceId)}/diff`,
      ),
    enabled: isConfigured && !!projectId && enabled,
    staleTime: Infinity,
    retry: false,
  })
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
      postJson<EvidenceDecisionResult>(
        `/api/v1/projects/${projectId}/project/spec/evidence/${id}/decision`,
        { decision, reason },
      ),
    onSuccess: () => invalidateAfterDecision(queryClient, projectId, path, identifier),
  })
}

function invalidateAfterDecision(
  queryClient: ReturnType<typeof useQueryClient>,
  projectId: string | null,
  path: string,
  identifier: string,
) {
  // Accepting can merge a commit for a waiting task, and rejecting can reopen an approved one, so
  // the task-scoped keys move too (`task` covers integrations/transitions/preview, `tasks` the
  // lists and boards).
  for (const key of [['specCoverage'], ['specEvidence', path, identifier], ['task'], ['tasks']]) {
    queryClient.invalidateQueries({ queryKey: ['project', projectId, ...key] })
  }
}

/** The operator reversing a decided piece, with a required reason (F692). */
export function useOverturnEvidence(path: string, identifier: string) {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      postJson<EvidenceDecisionResult>(
        `/api/v1/projects/${projectId}/project/spec/evidence/${id}/overturn`,
        { reason },
      ),
    onSuccess: () => invalidateAfterDecision(queryClient, projectId, path, identifier),
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
      // A save that retires a requirement arrives here: the requirement list and an open
      // requirement's detail move with it.
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specRequirements'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specRequirement'] })
      // A scan or an answer (`{path: null, drift: true}`) moves this document's drift strip.
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specDrift'] })
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
  phase: 'exploring' | 'approved' | 'archived' | 'current'
  /** The document as the Hub last wrote it. */
  content_digest: string | null
  explore_closed: boolean
  /** Where a change being explored stands on its journey, and how big the work is
   *  (`a-spec-is-written-one-step-at-a-time`). Null on every other document; `journey` is the
   *  ordered steps the size gives (no size is briefed as large). Absent from a Hub before 0122. */
  step?: string | null
  size?: SpecSize | null
  journey?: string[] | null
  /** The gaps the latest approval overrode with `approve_anyway`, while the document stays approved
   *  (`approve-lists-what-is-missing-and-can-approve-anyway` FR-5). Absent otherwise, and from a Hub
   *  that predates it. */
  approval_warnings_overridden?: SpecBlockingFinding[]
  /** A tester's amendments to the approved document, and how many the operator has not reviewed
   *  (`a-tester-drives-the-built-product-and-keeps-the-spec-true`), and how many proposals wait
   *  for the operator (`proposed`, absent from an older Hub). Absent when there are none. */
  amendments?: { total: number; unreviewed: number; proposed?: number }
  /** Present while a build of this document is running: how many of the tasks it covers are
   *  approved (`the-spec-page-redesigned`: the list's 'building now' mark and the picker's progress). */
  build?: { id: string; done: number; total: number }
  updated_at: string
}

export type SpecSize = 'fix' | 'small' | 'large'

/** One reason a document cannot be approved yet, and where to look. */
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
 *  gives "check" and "approve" something to refer to.
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

/** The operator moving a change to any step of its journey, or changing its size. Takes effect
 *  from the next turn on the document (FR-10). */
export function useSetSpecJourney() {
  return useSpecMutation<{ path: string; step?: string; size?: SpecSize }, SpecDocumentRecord>(
    (projectId, { path, ...body }) =>
      postJson(
        `/api/v1/projects/${projectId}/project/documents/journey?path=${encodeURIComponent(path)}`,
        body,
      ),
  )
}

/** One step of the project's own journey (`a-project-orders-its-own-spec-steps`). A built-in step is
 *  its `key` alone, plus an optional `append`; a custom one also carries `title`, `instructions`
 *  (the pasted Markdown) and the `sizes` whose journey it joins. */
export interface JourneyStep {
  key: string
  title?: string
  instructions?: string
  sizes?: SpecSize[]
  append?: string
}

/** `GET /project/journey`: the steps in file order, and what the Hub found wrong with the file
 *  (it briefs with the built-in steps while `diagnostics` is non-empty). */
export interface ProjectJourney {
  steps: JourneyStep[]
  diagnostics: { code: string; message: string }[]
}

export function useProjectJourney() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ProjectJourney>({
    queryKey: ['project', projectId, 'specJourney'],
    queryFn: () => getJson<ProjectJourney>(`/api/v1/projects/${projectId}/project/journey`),
    enabled: isConfigured && !!projectId,
  })
}

/** Replace the project's steps. The Hub validates every rule (and the 2,000-character cap) before
 *  it writes `spec/journey.json`; a refusal names the step. */
export function useSaveProjectJourney() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ steps }: { steps: JourneyStep[] }) =>
      putJson<ProjectJourney>(`/api/v1/projects/${projectId}/project/journey`, { steps }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specJourney'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specDocuments'] })
    },
  })
}

/** Check a document's readiness and move nothing (`check-never-moves`): the blocking findings and
 *  warnings the agent's own save returns, so the agent keeps writing while the operator looks. */
export function useCheckSpecDocument() {
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ path }: { path: string }) =>
      postJson<
        SpecDocumentRecord & {
          blocking: SpecBlockingFinding[]
          warnings: SpecBlockingFinding[]
          ready: boolean
          content_version: string
        }
      >(`/api/v1/projects/${projectId}/project/documents/check?path=${encodeURIComponent(path)}`),
  })
}

/** What a build route answers: the document, and what the build did. */
export type SpecBuildResult = SpecDocumentRecord & { build_outcome: SpecBuildOutcome }

/** Build an approved document as its recommended build says (`build-is-separate`), at any time
 *  after approval. `delivery_agent` replaces a flow delivery's agent for this build (`''`: no flow). */
export function useBuildSpecDocument() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ path, ...choices }: { path: string } & BuildChoices) =>
      postJson<SpecBuildResult>(
        `/api/v1/projects/${projectId}/project/documents/build?path=${encodeURIComponent(path)}`,
        choices,
      ),
    onSuccess: () => invalidateAfterPhase(queryClient, projectId),
  })
}

/** Raise a build's cap or move its window; a build its cap or window stopped resumes. */
export function useUpdateBuild() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({
      id,
      ...change
    }: {
      id: string
      budget_cap_usd?: number
      window_start?: string
      window_end?: string
    }) => patchJson<SpecBuild>(`/api/v1/projects/${projectId}/project/builds/${id}`, change),
    onSuccess: () => invalidateAfterPhase(queryClient, projectId),
  })
}

/** Stop a running build: nothing new is handed out, running turns finish. */
export function useStopBuild() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ id }: { id: string }) =>
      postJson<SpecBuild>(`/api/v1/projects/${projectId}/project/builds/${id}/stop`),
    onSuccess: () => invalidateAfterPhase(queryClient, projectId),
  })
}

/** Approve and build in one action (`approve-and-build`), refused exactly as approving alone is. */
export function useApproveAndBuildSpecDocument() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({
      path,
      content_version,
      delivery_agent,
      approve_anyway,
      ...choices
    }: {
      path: string
      content_version: string
      approve_anyway?: boolean
    } & BuildChoices) =>
      postJson<
        SpecDocumentRecord & {
          approval_outcome?: SpecApprovalOutcome
          build_outcome: SpecBuildOutcome
          approval_notes?: SpecBlockingFinding[]
        }
      >(
        `/api/v1/projects/${projectId}/project/documents/approve-and-build?path=${encodeURIComponent(path)}`,
        {
          reason: '',
          content_version,
          ...(delivery_agent !== undefined ? { delivery_agent } : {}),
          ...(approve_anyway ? { approve_anyway } : {}),
          ...choices,
        },
      ),
    onSuccess: () => invalidateAfterPhase(queryClient, projectId),
  })
}

/** A phase move or a build may create tasks and a flow, so the loops and jobs keys are refreshed
 *  with the documents — or the header would keep offering Build beside the flow just made. */
function invalidateAfterPhase(queryClient: ReturnType<typeof useQueryClient>, projectId: string | null) {
  queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specDocuments'] })
  queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specs'] })
  queryClient.invalidateQueries({ queryKey: ['project', projectId, 'loops'] })
  queryClient.invalidateQueries({ queryKey: ['project', projectId, 'jobs'] })
}

/** One amendment to an approved document, oldest first from the route: a tester's, applied at
 *  once, or an author's or the lead's proposal, which the operator accepts or declines. */
export interface SpecAmendment {
  id: string
  op:
    | 'add_task'
    | 'add_requirement'
    | 'add_criterion'
    | 'change_criterion'
    | 'remove_criterion'
    | 'cannot_satisfy'
  target: string
  requirement: string | null
  identifier: string | null
  reason: string
  how_to_check: string
  author: string
  run_id: string | null
  created_at: string
  reviewed: boolean
  reviewed_at: string | null
  reviewed_by: string | null
  /** A change or removal of a criterion, or a cannot-satisfy report: its requirement cannot be
   *  verified until the operator reviews it. */
  relaxing: boolean
  change: Record<string, unknown> | null
  before: Record<string, unknown> | null
  /** F700: how a cannot-satisfy report was answered, why, and the amendment an `amended` answer
   *  produced. Absent from a Hub before F700. */
  response?: 'amended' | 'accepted' | 'rejected' | null
  response_reason?: string | null
  answered_by?: string | null
  /** The report an operator's amendment answers. */
  responds_to?: string | null
  /** `applied` at once (a tester's), `proposed` and waiting for the operator, `accepted`,
   *  `declined`, or `stale` (no longer applied when accepted). Absent from an older Hub. */
  state?: 'applied' | 'proposed' | 'accepted' | 'declined' | 'stale'
  decided_by?: string | null
  decided_at?: string | null
  decided_reason?: string | null
}

/** The operator accepts a proposed amendment: applied to the document as it stands, or refused
 *  409 `amendment_stale` naming why. The proposer is told either way. */
export function useAcceptSpecAmendment() {
  return useSpecMutation<{ path: string; id: string }, { state: string; task_created: string | null }>(
    (projectId, { path, id }) =>
      postJson(`/api/v1/projects/${projectId}/project/documents/${path}/amendments/${id}/accept`, {}),
  )
}

/** The operator declines a proposed amendment with a reason the proposer reads. */
export function useDeclineSpecAmendment() {
  return useSpecMutation<{ path: string; id: string; reason: string }, { state: string }>(
    (projectId, { path, id, reason }) =>
      postJson(`/api/v1/projects/${projectId}/project/documents/${path}/amendments/${id}/decline`, {
        reason,
      }),
  )
}

export function useSpecAmendments(path: string | null, enabled = true) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ amendments: SpecAmendment[] }>({
    // Under `specs`, so every mutation and `spec_updated` that refreshes the document refreshes this.
    queryKey: ['project', projectId, 'specs', 'amendments', path],
    queryFn: () =>
      getJson<{ amendments: SpecAmendment[] }>(
        `/api/v1/projects/${projectId}/project/documents/${path}/amendments`,
      ),
    enabled: isConfigured && !!projectId && !!path && enabled,
  })
}

/** Mark amendments reviewed: the ids given, or every one not reviewed when `ids` is omitted. */
export function useReviewSpecAmendments() {
  return useSpecMutation<{ path: string; ids?: string[] }, { marked: string[] }>(
    (projectId, { path, ids }) =>
      postJson(
        `/api/v1/projects/${projectId}/project/documents/${path}/amendments/review`,
        ids ? { ids } : {},
      ),
  )
}

/** The operator's answer to a cannot-satisfy report (F700): amend the criterion, accept the
 *  report (the task resumes), or reject it with a reason (the task stays blocked). */
export function useRespondToReport() {
  return useSpecMutation<
    {
      path: string
      id: string
      response: 'amend' | 'accept' | 'reject'
      reason: string
      change?: Record<string, string>
    },
    { response: string; task_unblocked: boolean }
  >((projectId, { path, id, response, reason, change }) =>
    postJson(`/api/v1/projects/${projectId}/project/documents/${path}/amendments/${id}/respond`, {
      response,
      reason,
      ...(change ? { change } : {}),
    }),
  )
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

/** One revision of a requirement (slice requirement-story), oldest first as the route returns.
 *  `statement` is null on a retirement and on every revision recorded before migration 0131. */
export interface RequirementRevision {
  id: string
  classification: 'created' | 'reworded' | 'retired' | 'restored'
  /** What the revision left unchanged: `criteria` is a `reworded` revision whose statement stood
   *  (F833). Absent from a Hub that predates it. */
  change?: 'created' | 'reworded' | 'retired' | 'restored' | 'criteria'
  source: string
  actor_kind: string
  actor: string
  run_id: string | null
  statement: string | null
  digest: string
  previous_digest: string | null
  created_at: string | null
  /** The change this revision was folded in from, when a fold wrote it. */
  folded_from?: { path: string; title: string; at: string } | null
}

export interface RequirementDriftRow {
  id: string
  evidence_id: string
  state: 'candidate' | 'resolved' | 'superseded'
  observed: unknown
  resolution: string | null
  resolved_by: string | null
  resolved_at: string | null
  created_at: string | null
}

export interface SpecRequirementDetail {
  /** `statement` and `document` are absent from a Hub before slice requirement-story. */
  requirement: SpecRequirementRow & {
    statement?: string | null
    document?: { path: string; title: string } | null
  }
  revisions?: RequirementRevision[]
  drift?: RequirementDriftRow[]
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

/** Approving, reopening or archiving. Approval lays the tasks out and starts nothing
 *  (`approval-is-a-plan`); it names the `content_version` the operator loaded and is refused when
 *  the document changed since (`approve-what-was-seen`). */
export function useSetSpecPhase() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({
      path,
      to,
      reason,
      content_version,
      no_capability_change,
      absorbed_by,
      approve_anyway,
    }: {
      path: string
      to: string
      reason?: string
      /** Archiving an approved change folded into no capability; `reason` says why. Sent only when
       *  true, so a Hub without the archive guard never receives it. */
      no_capability_change?: boolean
      /** Retiring a capability (to `archived`): the current capability that absorbed it. Sent only
       *  when chosen, so a Hub without retirement never receives it (F536). */
      absorbed_by?: string
      /** With `to: 'approved'` only: the version of the document read the operator approved. */
      content_version?: string
      /** Approve over the gaps a refused approval listed (409 `approval_warnings`). Sent only on
       *  that resend: a Hub that answers `approval_warnings` is the one that accepts it. */
      approve_anyway?: boolean
    }) =>
      postJson<
        SpecDocumentRecord & {
          approval_outcome?: SpecApprovalOutcome
          /** F704: what approval told and did not gate on (an unclaimed roadmap slice). */
          approval_notes?: SpecBlockingFinding[]
        }
      >(
        `/api/v1/projects/${projectId}/project/documents/phase?path=${encodeURIComponent(path)}&to=${encodeURIComponent(to)}`,
        {
          reason: reason ?? '',
          ...(content_version !== undefined ? { content_version } : {}),
          ...(no_capability_change ? { no_capability_change } : {}),
          ...(absorbed_by ? { absorbed_by } : {}),
          ...(approve_anyway ? { approve_anyway } : {}),
        },
      ),
    onSuccess: () => invalidateAfterPhase(queryClient, projectId),
  })
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

/** One change requirement as a fold would write it: `from` is the change's key, `key` the
 *  capability's (`<change-slug>-<key>` unless edited). */
export interface SpecFoldDraftRequirement {
  from: string
  key: string
  statement: string
  modal: string | null
  replaces: string | null
}

export interface SpecFoldDraft {
  into: string
  requirements: SpecFoldDraftRequirement[]
  /** Draft keys the capability already holds; folding them as they are is refused. */
  collisions: string[]
  /** What the capability holds before the fold, in its order, to choose what to retire (F533).
   *  Absent from a Hub that predates retirement. */
  capability_requirements?: { key: string; statement: string }[]
  capability_criteria?: { key: string; requirement: string | null; then: string }[]
}

/** What folding `path` into the capability `into` would write. Writes nothing. */
export function useFoldDraft(path: string, into: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<SpecFoldDraft>({
    queryKey: ['project', projectId, 'foldDraft', path, into],
    queryFn: () =>
      getJson<SpecFoldDraft>(
        `/api/v1/projects/${projectId}/project/documents/${path}/fold-draft?into=${encodeURIComponent(into ?? '')}`,
      ),
    enabled: isConfigured && !!projectId && !!into,
  })
}

export interface SpecFoldItem {
  key: string
  as_key?: string
  statement?: string
}

/** Fold an approved change into a capability through the merge and, unless `archive` is false,
 *  archive it — the operator's close-out of a finished change. Re-renders both documents. */
export function useFoldDocument() {
  return useCorpusMutation(
    (
      projectId,
      {
        path,
        ...body
      }: {
        path: string
        into: string
        requirements: SpecFoldItem[]
        archive: boolean
        note?: string
        /** Capability requirements (with their criteria) and single criteria to remove in the same
         *  merge. Sent only when non-empty, so a Hub without retirement never receives them. */
        retire?: string[]
        retire_criteria?: string[]
      },
    ) =>
      postJson<SpecDocumentRecord & { archived: boolean; merged: number }>(
        `/api/v1/projects/${projectId}/project/documents/${path}/fold`,
        body,
      ),
  )
}

/** Delete a specification document and what it produced (F532). The Hub refuses a capability, an
 *  archived or folded document, and one with a running flow or a run on its tasks. */
export function useDeleteSpecDocument() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ path }: { path: string }) =>
      deleteJson<{ path: string; deleted: boolean; tasks: string[]; kept_work?: KeptWork[] }>(
        `/api/v1/projects/${projectId}/project/documents/${path}`,
      ),
    onSuccess: (_result, { path }) => {
      // F829: the document is gone, so nothing may ask for it again. The corpus invalidation
      // refetched the dead path's own queries while its panel was still mounted (404 after 404).
      // Its keys are left alone, not removed -- a mounted observer rebuilds a removed query -- and
      // are collected once the panel lets go. It leaves the cached lists with the 200.
      queryClient.setQueriesData<{ specs?: { path: string }[] }>(
        { queryKey: ['project', projectId, 'specs'], exact: true },
        (list) =>
          list && Array.isArray(list.specs)
            ? { ...list, specs: list.specs.filter((s) => s.path !== path) }
            : list,
      )
      queryClient.setQueriesData<{ documents?: { path: string }[] }>(
        { queryKey: ['project', projectId, 'specDocuments'], exact: true },
        (list) =>
          list && Array.isArray(list.documents)
            ? { ...list, documents: list.documents.filter((d) => d.path !== path) }
            : list,
      )
      for (const key of ['specDocuments', 'specs', 'spec']) {
        queryClient.invalidateQueries({
          queryKey: ['project', projectId, key],
          predicate: (q) => !q.queryKey.includes(path),
        })
      }
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

// --------------------------------------------------------------------------- drift, on the document
// `drift-is-scanned-and-answered-on-the-document` (F129): detect and resolve had no caller here.

export interface DriftCandidate {
  id: string
  requirement_id: string
  evidence_id: string
  /** `superseded`: its requirement was reworded or retired while it was open (F435). */
  state: 'candidate' | 'resolved' | 'superseded'
  /** `{path: {was, now}}`; `now: null` means the file was removed. */
  observed: Record<string, { was: string | null; now: string | null }>
  resolution: string | null
  created_at: string | null
  requirement: { identifier: string; document: string | null } | null
  /** The asked-for document's requirement this drift reaches through a fold (F690): the
   *  candidate is on the change requirement whose evidence serves it. Absent or null otherwise. */
  serves?: { identifier: string; document: string | null } | null
  evidence: { summary: string; locator: string | null; actor: string; actor_kind: string } | null
}

export interface UnwatchedEvidence {
  evidence_id: string
  requirement: { identifier: string; document: string | null }
  summary: string
  actor: string
  reason: 'names_no_file' | 'recorded_before_watching' | 'no_footprint'
}

export interface DriftListResponse {
  /** In the route's order: oldest first, ties by id. The panel does not re-sort (F190). */
  drift: DriftCandidate[]
  unwatched: UnwatchedEvidence[]
}

export type DriftResolution = 'specification_updated' | 'implementation_corrected' | 'no_change_required'

/** This document's open candidates and its unwatched evidence. */
export function useSpecDrift(path: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<DriftListResponse>({
    queryKey: ['project', projectId, 'specDrift', path],
    queryFn: () =>
      getJson<DriftListResponse>(
        `/api/v1/projects/${projectId}/project/spec/drift?state=candidate${
          path ? `&document=${encodeURIComponent(path)}` : ''
        }`,
      ),
    enabled: isConfigured && !!projectId && !!path,
  })
}

/** A drift write moves the strip and the coverage bar; both are dropped on success so the pressing
 *  tab does not wait for the SSE round-trip. */
function useDriftMutation<TArgs, TResult>(call: (projectId: string, args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (args: TArgs) => call(projectId ?? '', args),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specDrift'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'specCoverage'] })
    },
  })
}

/** Scan the whole project for drift (the route is project-wide). Answers the ids it raised. */
export function useDetectDrift() {
  return useDriftMutation<void, { raised: string[]; rebuilt?: number }>((projectId) =>
    postJson(`/api/v1/projects/${projectId}/project/spec/drift/detect`),
  )
}

/** The operator's answer to one candidate. A candidate is answered once (409 `drift_not_open`). */
export function useResolveDrift() {
  return useDriftMutation<{ id: string; resolution: DriftResolution }, DriftCandidate>(
    (projectId, { id, resolution }) =>
      postJson(`/api/v1/projects/${projectId}/project/spec/drift/${id}/resolve`, { resolution }),
  )
}
