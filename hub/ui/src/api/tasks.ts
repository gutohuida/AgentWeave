import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, patchJson, postJson } from './client'
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
  /** What happens when a run bound to this task ends without the task moving. */
  divergence_policy: DivergencePolicy
  escalation_agent?: string | null
  /** A run dropped this task and nothing has moved it since. */
  has_open_divergence: boolean
  /**
   * What a `blocked` task is waiting for, in words. Null on every other status.
   *
   * A blocked task stays in the In Progress column rather than moving to one of its own, so this
   * is most of what tells the operator the card is waiting on *them* rather than merely stalled.
   */
  blocked_reason?: string | null
  /**
   * What a run bound to this task is waiting on *you* to answer, right now — in the same words
   * `blocked_reason` uses on a task that parked.
   *
   * The ordinary wait now moves the status: the task parks the moment the agent asks (F14). This
   * covers the two waits the status cannot — a task that could not park (`under_review`, `pending`,
   * `assigned`), and a batch whose first answer released the task while the run waits on the rest.
   * Derived per request, never stored.
   */
  awaiting_answer_reason?: string | null
  /** The specification document this work is against, and — where a document declared this task —
   *  the key it was declared under. */
  spec_document_id?: string | null
  spec_task_key?: string | null
  /**
   * The requirement identifiers this task serves, in the form they are submitted in.
   *
   * `requirements` is the caller's verbatim prose and can say things no identifier can;
   * these are the checked links the approval gate actually enforces. The board showed only
   * the prose, so a card could not tell you whether it was tied to the specification at all.
   */
  requirement_ids?: string[]
  requirement_links?: RequirementLink[]
  unresolved_requirements?: { reference: string; reason: string }[]
  /** `TaskDependency` read from both ends — enough to render an edge without a second fetch
   *  (`task-dependencies` task 7.1). Absent on a response that never attached dependencies. */
  prerequisites?: TaskDependencyRef[]
  dependents?: TaskDependencyRef[]
  /** `"gated"` | `"gated_on_rejected"` | `"running_on_regressed"` | `null` — derived per request,
   *  never stored (task 7.2, design D1). */
  dependency_state?: string | null
}

/** A prerequisite or dependent named on a `Task` — enough to draw an edge without fetching the
 *  other end of it. `spec_document_id` is null for a hand-made task and is what lets a board draw
 *  a prerequisite outside its own document as an off-board reference naming that document
 *  (`task-dependencies` task 8.7), rather than a bare title with nowhere to point. */
export interface TaskDependencyRef {
  id: string
  title: string
  status: string
  spec_document_id?: string | null
}

/** One checked tie between a task and a requirement. `statement` is null where the document no
 *  longer words the requirement, which is what a retired one is. */
export interface RequirementLink {
  identifier: string
  requirement_id: string
  document_id: string
  state: string
  anchor?: string | null
  key?: string | null
  statement?: string | null
  modal?: string | null
  /** True only for evidence rejected against the requirement's *current* digest. Kept independent
   *  of coverage's `rejected` state: this stays true even after a later acceptance moves coverage
   *  on to `verified` — see `hub/hub/api/v1/tasks.py`. */
  has_rejected_evidence?: boolean
  rejected_evidence_count?: number
  latest_rejection_reason?: string | null
}

export type DivergencePolicy = 'surface' | 'retry' | 'escalate'

export const DIVERGENCE_POLICY_LABELS: Record<DivergencePolicy, string> = {
  surface: 'Tell me',
  retry: 'Try again once',
  escalate: 'Hand to another agent',
}

/**
 * What approving a task did to the repository — including the times it did nothing.
 *
 * A skipped merge with a stated reason is the answer to "my approved work is not on main", so the
 * skips matter as much as the merges and are not filtered out here.
 */
export interface TaskIntegration {
  id: string
  commit_sha: string | null
  source_branch: string | null
  target_branch: string | null
  outcome: 'merged' | 'skipped' | 'failed'
  reason: string
  /** Commits that landed alongside `commit_sha` because a merge brings in a commit's whole
   *  ancestry, not its diff alone (F58). Empty means nothing rode along. */
  rode_along_commits: string[]
  mechanism: string
  actor_kind: string
  actor: string
  created_at: string
}

export function useTaskIntegrations(taskId: string, enabled: boolean) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ integrations: TaskIntegration[] }>({
    queryKey: ['project', projectId, 'task', taskId, 'integrations'],
    queryFn: () =>
      getJson<{ integrations: TaskIntegration[] }>(
        `/api/v1/projects/${projectId}/tasks/${taskId}/integrations`,
      ),
    enabled: isConfigured && !!projectId && enabled,
  })
}

/**
 * What approving this task *would* write, before it is approved (F9).
 *
 * Approval is the only act in the product that changes the operator's own repository — it
 * cherry-picks the commit named by each accepted piece of evidence into the project's main branch.
 * The refusal path already explained itself ("no accepted evidence names a commit"); the
 * *successful* path announced nothing at all, and an operator clicking approve on a task board was
 * writing to their main branch without being told.
 *
 * Read-only and cheap on the server: same source as the merge (`integration_targets` plus
 * `Project.main_branch`), no git subprocess, no conflict probe. This is a sentence, not a gate.
 */
export interface TaskIntegrationPreview {
  task_id: string
  main_branch: string | null
  targets: { commit_sha: string; source_branch: string | null }[]
  will_merge: boolean
  /** Why nothing will be merged. Empty when something will. */
  reason: string
}

export function useTaskIntegrationPreview(taskId: string, enabled: boolean) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<TaskIntegrationPreview>({
    queryKey: ['project', projectId, 'task', taskId, 'integration-preview'],
    queryFn: () =>
      getJson<TaskIntegrationPreview>(
        `/api/v1/projects/${projectId}/tasks/${taskId}/integration-preview`,
      ),
    enabled: isConfigured && !!projectId && enabled,
  })
}

/**
 * Attempt the merge again for an approved task whose work is not in the product.
 *
 * Approving again cannot re-run it — restating a status is a no-op — so without this the reason
 * text on the note asks for a remediation that accomplishes nothing.
 */
export function useRetryTaskIntegration(taskId: string) {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: () =>
      postJson<{ integrations: TaskIntegration[] }>(
        `/api/v1/projects/${projectId}/tasks/${taskId}/integrations/retry`,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['project', projectId, 'task', taskId, 'integrations'],
      })
    },
  })
}

/** `loopId` and `excludeArchivedCompleted` both scope the same query on the Hub (an `elif` chain,
 *  `hub/hub/api/v1/tasks.py`), so passing both is not meaningful — callers pick one. */
export function useTasks(options?: { excludeArchivedCompleted?: boolean; loopId?: string }) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const excludeArchivedCompleted = options?.excludeArchivedCompleted ?? false
  const loopId = options?.loopId
  return useQuery<Task[]>({
    queryKey: ['project', projectId, 'tasks', { excludeArchivedCompleted, loopId }],
    queryFn: () => {
      const params = new URLSearchParams()
      if (loopId) params.set('loop_id', loopId)
      else if (excludeArchivedCompleted) params.set('exclude_archived_completed', 'true')
      const qs = params.toString()
      return getJson<Task[]>(`/api/v1/projects/${projectId}/tasks${qs ? `?${qs}` : ''}`)
    },
    enabled: isConfigured && !!projectId,
  })
}

/** Every task one specification document declared, regardless of status or the document's own
 *  phase — an explicit scope never hides anything. Its own hook rather than `useTasks({
 *  specDocumentId })`: the two exist for different callers (one small link fetching one document's
 *  tasks; the whole board fetching everything it will render). */
export function useDocumentTasks(documentId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<Task[]>({
    queryKey: ['project', projectId, 'tasks', { spec_document_id: documentId }],
    queryFn: () =>
      getJson<Task[]>(
        `/api/v1/projects/${projectId}/tasks?spec_document_id=${encodeURIComponent(documentId ?? '')}`,
      ),
    enabled: isConfigured && !!projectId && !!documentId,
  })
}

/** One edge in a board's graph: `task_id` depends on `depends_on_task_id`. */
export interface TaskBoardEdge {
  task_id: string
  depends_on_task_id: string
}

export interface TaskBoard {
  spec_document_id: string | null
  tasks: Task[]
  edges: TaskBoardEdge[]
}

/**
 * One document's tasks and the edges between them, in one call (`task-dependencies` task 7.3,
 * design D9). `specDocumentId` of `null` is not "nothing selected" — it names the standing
 * "no document" board (every hand-made task, which per design D5 can never have an edge), so this
 * stays enabled for it rather than treating null as disabled the way `useDocumentTasks` does.
 */
export function useTaskBoard(specDocumentId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<TaskBoard>({
    queryKey: ['project', projectId, 'tasks', 'board', specDocumentId],
    queryFn: () => {
      const qs = specDocumentId ? `?spec_document_id=${encodeURIComponent(specDocumentId)}` : ''
      return getJson<TaskBoard>(`/api/v1/projects/${projectId}/tasks/board${qs}`)
    },
    enabled: isConfigured && !!projectId,
  })
}

/** The picker: every board that has tasks, with outstanding counts (task 7.4, design D9). */
export interface TaskBoardSummary {
  spec_document_id: string | null
  title: string | null
  total: number
  outstanding: number
}

export function useTaskBoards() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ boards: TaskBoardSummary[] }>({
    queryKey: ['project', projectId, 'tasks', 'boards'],
    queryFn: () => getJson<{ boards: TaskBoardSummary[] }>(`/api/v1/projects/${projectId}/tasks/boards`),
    enabled: isConfigured && !!projectId,
  })
}

export function useUpdateTask() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    // `blocked_reason` is required by the Hub when the status is `blocked`, and ignored otherwise —
    // so it is sent only when present rather than as a null the validator would still have to
    // reject.
    mutationFn: ({
      id,
      status,
      blocked_reason,
    }: {
      id: string
      status: string
      blocked_reason?: string
    }) =>
      patchJson<Task>(`/api/v1/projects/${projectId}/tasks/${id}`, {
        status,
        ...(blocked_reason ? { blocked_reason } : {}),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'tasks'] }),
  })
}

/**
 * How this task's neglect should be answered.
 *
 * Separate from `useUpdateTask` because it is a different kind of act: that one moves the task
 * through its lifecycle and can be refused by the transition machine, this one records a standing
 * instruction and cannot. Sharing a mutation would put both under one pending state, so setting a
 * policy would look like a status change in flight.
 */
export function useSetDivergenceHandling() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({
      id,
      ...fields
    }: {
      id: string
      divergence_policy?: DivergencePolicy
      escalation_agent?: string | null
    }) => patchJson<Task>(`/api/v1/projects/${projectId}/tasks/${id}`, fields),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'tasks'] }),
  })
}

export interface RunDivergence {
  id: string
  run_id: string
  agent: string
  task_id: string
  task_status_at_end: string
  run_exit_status: string
  policy_applied: DivergencePolicy
  outcome: 'surfaced' | 'retried' | 'escalated'
  response_run_id?: string | null
  previous_assignee?: string | null
  created_at: string
  resolved_at?: string | null
}

/** Runs that ended holding work nobody moved — including ones since picked up. */
export function useDivergences(openOnly = false) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<RunDivergence[]>({
    queryKey: ['project', projectId, 'divergences', openOnly],
    queryFn: () =>
      getJson<RunDivergence[]>(
        `/api/v1/projects/${projectId}/tasks/divergences/recent?open_only=${openOnly}`,
      ),
    enabled: isConfigured && !!projectId,
  })
}

/**
 * Start a run bound to a task.
 *
 * The binding is what makes the run answerable at its boundary, and it is the Hub that sets it —
 * so this is a trigger carrying `task_id`, not a task update. The task moves to in_progress by
 * itself, without the agent being asked.
 */
export function useStartWorkOnTask() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ taskId, agent, title }: { taskId: string; agent: string; title: string }) =>
      postJson<{ run_id?: string; conversation_id: string }>(
        `/api/v1/projects/${projectId}/agent/trigger`,
        {
          agent,
          message: `Work on task ${taskId}: ${title}`,
          task_id: taskId,
        },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'tasks'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agents'] })
    },
  })
}

/** `{ from_status: [reachable...] }` for the operator, as the Hub declares it. */
export type AllowedTransitions = Record<string, string[]>

/**
 * The transition map, fetched once for the operator rather than per task.
 *
 * The legal set depends on who is asking, so it deliberately does not ride on the task response —
 * a resource that varies by asker breaks what every cache assumes about it, this query key
 * included. And it is not per-task: forty cards in the same status have one answer, not forty.
 * See design D13 of `openspec/changes/2026-08-10-task-transition-machine`.
 *
 * Serving it from the same declaration the Hub enforces is the point. A copy of the map here would
 * drift, and the first symptom would be the card offering a move that is then refused.
 */
export function useAllowedTransitions() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ actor_kind: string; transitions: AllowedTransitions }>({
    queryKey: ['project', projectId, 'task-transitions'],
    queryFn: () =>
      getJson<{ actor_kind: string; transitions: AllowedTransitions }>(
        `/api/v1/projects/${projectId}/tasks/transitions/allowed`,
      ),
    enabled: isConfigured && !!projectId,
    // The map changes only when the Hub is redeployed, so refetching it per window focus is noise.
    staleTime: Infinity,
  })
}
