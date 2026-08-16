# Design — The board scoped by document

## D1. Two independent query parameters on `GET /tasks`, `elif`-ordered so scope always wins

`hub/hub/api/v1/tasks.py`'s `list_tasks` gains:

```python
spec_document_id: Optional[str] = Query(None)
exclude_archived_completed: bool = Query(False)
```

alongside the existing `agent`, `status`, `offset`, `limit`. Applied as:

```python
if spec_document_id:
    q = q.where(Task.spec_document_id == spec_document_id)
elif exclude_archived_completed:
    archived_ids = select(SpecDocument.id).where(
        SpecDocument.project_id == project_id,
        SpecDocument.phase == spec_lifecycle.ARCHIVED,
    )
    q = q.where(
        ~(Task.spec_document_id.in_(archived_ids) & Task.status.in_(TERMINAL_FOR_BINDING))
    )
```

**Why `elif`, not two independent `if`s that could both apply.** If both were applied together, a
caller who scopes to a document that is itself archived would have their own terminal tasks
filtered back out of a request that named them explicitly — exactly the outcome proposal.md rules
out ("an explicit scope is never allowed to hide anything"). Both parameters are exposed because
they serve two different callers (the document-tasks affordance always sends `spec_document_id`
alone; the board's default fetch always sends `exclude_archived_completed` alone), not because a
caller is expected to combine them — `elif` makes the combination well-defined anyway, rather than
leaving it to whichever clause happens to run last.

**Why a subquery (`Task.spec_document_id.in_(archived_ids)`) rather than a join.** `list_tasks`
already runs three more queries after the initial `select(Task)` — heartbeats, divergence, and
integrations, all keyed off the tasks already fetched (`hub/hub/api/v1/tasks.py:421-429`). Adding a
`JOIN spec_documents` to the primary query would require `Task.spec_document_id` to be non-null for
the row to survive an inner join, silently dropping every task with no document at all (`nullable
=True`, the common case per N1 §4 — "most tasks today are unlinked"). An `IN` subquery has no such
hazard: a task with a null `spec_document_id` simply never matches `.in_(archived_ids)`, so the
`~(...)` leaves it in the result, which is the correct outcome (an unlinked task has no declaring
document to be excluded on behalf of).

**Why `TERMINAL_FOR_BINDING` and not a new list.** `hub/hub/run_task_binding.py:272` already names
exactly `("approved", "rejected")` as the pair a run's binding to a task considers finished, for the
identical underlying idea this exclusion needs — "this task is not going anywhere else." Reusing it
is one import, not a new constant that could drift from the existing one the moment either changes.
`task_transitions.py`'s own module docstring calls these two "not terminal, but their only exits
belong to the operator" — true for the transition machine, and beside the point here:
`TERMINAL_FOR_BINDING`'s name and existing use already describe "no further binding-relevant work is
expected," which is precisely this exclusion's condition, regardless of what the transition machine
would technically still permit an operator to do next.

**Why `SpecDocument.phase == spec_lifecycle.ARCHIVED`, imported from `spec_lifecycle`, not a bare
string.** `spec_lifecycle.ARCHIVED` is the constant N2 introduced for exactly this phase value
(`spec_lifecycle.py`, task 3.1 of `2026-08-16-the-corpus-keeps-what-shipped`); importing it keeps
this file from carrying its own copy of a string that already has a canonical name.

## D2. The board's own fetch chooses the parameter, not the API's default

The API defaults `exclude_archived_completed` to `false` — every existing caller of `GET /tasks`
(the MCP `list_tasks` tool, `App.tsx`, `OverviewPage.tsx`, `QualityHealthPanel.tsx`) keeps seeing
every task, unchanged, with no code change on their part. Only `TasksBoard.tsx`'s own fetch opts in,
and only when it is showing the default, unscoped board:

```ts
const activeTaskIds = useTaskFilterStore((state) => state.activeTaskIds)
const { data: tasks, isLoading } = useTasks({ excludeArchivedCompleted: activeTaskIds === null })
```

`useTasks()` (`hub/ui/src/api/tasks.ts`) gains an optional options argument:

```ts
export function useTasks(options?: { excludeArchivedCompleted?: boolean }) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const excludeArchivedCompleted = options?.excludeArchivedCompleted ?? false
  return useQuery<Task[]>({
    queryKey: ['project', projectId, 'tasks', { excludeArchivedCompleted }],
    queryFn: () =>
      getJson<Task[]>(
        `/api/v1/projects/${projectId}/tasks${
          excludeArchivedCompleted ? '?exclude_archived_completed=true' : ''
        }`,
      ),
    enabled: isConfigured && !!projectId,
  })
}
```

**Why the query key includes the options object.** React Query treats a different key as a
different cache entry; toggling `activeTaskIds` between `null` and a real array (clicking a
coverage-bar or document-tasks link, or clearing it) now switches which of two cached queries the
board reads, rather than one query whose filter silently changed underneath an in-flight
subscriber. The three existing mutations that call `invalidateQueries({ queryKey: ['project',
projectId, 'tasks'] })` (`hub/ui/src/api/tasks.ts:160,184,237`) still invalidate both variants —
React Query's default `invalidateQueries` match is a prefix match, not exact, so a key ending in
`['tasks']` matches a cached key that continues `['tasks', { excludeArchivedCompleted: true }]`
without any change to those call sites.

**Why this lives in the query layer and not as a client-side filter over an unfiltered fetch.** The
alternative — fetch every task always, filter archived-and-terminal ones out in `TasksBoard.tsx`
itself — would need the board to also fetch every spec document (`useSpecDocuments()`) just to know
which ones are archived, and recompute that join on every render for a board that, at the scale N1
is written for (hundreds of archived changes), is exactly the case this proposal exists to keep
cheap. Pushing the exclusion into the query means the unwanted rows are never sent to the client at
all.

## D3. The document-tasks affordance

New component, `hub/ui/src/components/spec/SpecDocumentTasksLink.tsx`:

```tsx
interface SpecDocumentTasksLinkProps {
  path: string
  onOpenTasks?: (taskIds: string[]) => void
}

export function SpecDocumentTasksLink({ path, onOpenTasks }: SpecDocumentTasksLinkProps) {
  const { data } = useSpecDocuments()
  const document = data?.documents.find((entry) => entry.path === path)
  const { data: tasks } = useDocumentTasks(document?.id ?? null)

  if (!document || !tasks || tasks.length === 0) return null

  return (
    <div className="flex shrink-0 items-center gap-1.5 px-3 py-1.5 text-xs" data-testid="spec-document-tasks-link" ...>
      <Icon name="task_alt" size={14} />
      {onOpenTasks ? (
        <button type="button" onClick={() => onOpenTasks(tasks.map((t) => t.id))} ...>
          {tasks.length} task{tasks.length === 1 ? '' : 's'} declared by this document
        </button>
      ) : (
        <span>{tasks.length} task{tasks.length === 1 ? '' : 's'} declared by this document</span>
      )}
    </div>
  )
}
```

rendered in `SpecDocumentPanel.tsx` beside `SpecCoverageBar`, receiving the same `onOpenTasks` prop
it is already threaded (`hub/ui/src/components/spec/SpecDocumentPanel.tsx:238`) — no new prop drilling
from `App.tsx`.

**Why a new component rather than folding this into `SpecCoverageBar`.** `SpecCoverageBar` returns
`null` when a document has no requirements and no diagnostics
(`SpecCoverageBar.tsx:87`), which is unrelated to whether it has declared tasks — a document can
declare tasks whose declared work does not (yet, or ever) cite a requirement. Folding the new
affordance inside that early return would hide it exactly when a document's tasks are least
discoverable any other way. A second, independent component with its own null-guard avoids
coupling two facts (coverage exists; tasks exist) that are not actually related.

**Why it resolves the document by path via `useSpecDocuments()`, the same lookup
`SpecPhaseBar.tsx:30` already performs.** `useSpecDocuments()` is a single project-scoped query
(`queryKey: ['project', projectId, 'specDocuments']`); React Query dedupes identical keys across
components automatically, so this is a second *reader* of an already-cached query, not a second
network request.

**New hook**, `hub/ui/src/api/tasks.ts`:

```ts
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
```

Deliberately its own hook, not `useTasks({ specDocumentId })` — the two exist for different callers
(one small link fetching one document's tasks; the whole board fetching everything it will render)
and giving them separate names keeps a reader of either call site from having to check which
argument shape applies.

## D4. What this leaves undone, on purpose

No UI renders anywhere for a task whose declaring document is a `kind="capability"` document — N2
never causes such a task to exist (capability documents are never approved, and approval is the only
thing that materialises declared tasks), so this is a case with no current instance, not a case this
change special-cases away. If a future change lets a capability document declare tasks directly,
`spec_document_id` scoping and the exclusion rule both already generalize to it with no further code
— the exclusion checks `phase == archived`, which a capability document's phase (`current`) can never
satisfy, so its tasks (were any to exist) would never be excluded from the default view either. That
is arguably wrong-shaped for a capability document specifically, but there is no live case to get
wrong yet, so this proposal does not speculate about one.
