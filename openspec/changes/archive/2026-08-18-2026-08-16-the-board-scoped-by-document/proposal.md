# The board scoped by document

## Why

**The task board has no answer for scale, and the operator named the exact worry: "with time
things will pile up there."** `openspec/explorations/2026-08-16-a-corpus-at-scale.md` (N1, this
session) answered it with evidence rather than in the abstract: `Task.spec_document_id` already
exists, is indexed, and is unused for scoping (`hub/hub/db/models.py:641`); the board is already
filtered from outside itself by proven, shipped code —
`taskFilterStore.activeTaskIds` (`hub/ui/src/store/taskFilterStore.ts`), wired by
`SpecCoverageBar.tsx`'s task-count links through `App.tsx:352-355`, read by
`TasksBoard.tsx:150-151`/`:237-238`. Nothing about scoping the board needed inventing; it needed a
second caller.

`2026-08-16-the-corpus-keeps-what-shipped` (N2, this session) shipped the other half of N1's
brief — the `archived` phase and the `current` capability-document kind — and left this exact
piece for whichever change landed second, stated once in its own design D8: *"`document.phase ==
'archived'` is now a real, queryable fact a task-list filter can join against."* N2 shipped first.
This is that filter.

## What Changes

- **`GET /tasks` gains two independent, optional query parameters.**
  `spec_document_id` scopes the result to exactly the tasks one document declared — every one of
  them, regardless of status, because an explicit scope is never allowed to hide anything (N1 §5:
  "nothing is ever hidden from a document-scoped view").
  `exclude_archived_completed` (default `false`, so every existing caller — the MCP `list_tasks`
  tool, the Overview page, the Quality panel — is unaffected) drops a task from the result when,
  and only when, its declaring document's phase is `archived` **and** the task's own status is
  terminal (`approved` or `rejected` — reusing `run_task_binding.TERMINAL_FOR_BINDING`, the
  existing name for exactly this pair, rather than inventing a second list). If both parameters are
  given, `spec_document_id` wins and the exclusion is not applied — an explicit scope always shows
  everything it names.
- **The task board's own fetch passes `exclude_archived_completed=true` when it is showing its
  default, unscoped view** (`activeTaskIds === null`), and drops back to the unfiltered fetch the
  moment an explicit scope is active — so a document-scoped view (via the existing
  `SpecCoverageBar` link or the new one below) is never missing a task the exclusion would
  otherwise have hidden.
- **A new affordance on the open specification document**: "N tasks declared by this document,"
  next to the existing coverage detail, calling the exact `setActiveTaskIds` mechanism
  `SpecCoverageBar`'s requirement-level task links already prove live — a second caller, not new UI
  machinery. Unlike the requirement-level links (which only ever cite tasks linked to a specific
  requirement), this shows **every** task the document declared, matching what the board would show
  if scoped by `spec_document_id`.
- **No schema change.** Everything this needs — `Task.spec_document_id` (indexed),
  `SpecDocument.phase`, `TERMINAL_FOR_BINDING` — already exists.

## Capabilities

### Modified Capabilities

- `task-lifecycle-governance`: a task list SHALL be scopeable to one specification document's
  declared tasks, and the board's default (unscoped) view SHALL exclude a task whose declaring
  document is archived and whose own status is terminal, while never excluding such a task from an
  explicitly scoped view.

### Added Capabilities

- None. This is a query-and-affordance addition within `task-lifecycle-governance`'s existing
  domain (which tasks a caller is shown), not a new capability area.

## Impact

**Behaviour** — the task board's default view stops accumulating every completed task from every
archived specification forever; an open task from an archived document, or any task at all viewed
through an explicit document scope, is never hidden. No task's `status`, `assignee`, or any other
field is ever touched by this change — it is a read-path filter, nothing more.

**API** — `GET /tasks` gains `spec_document_id` and `exclude_archived_completed`, both optional,
both defaulting to the current, unfiltered behaviour. No new endpoint.

**Migration** — none. No column, no table, no constraint.

**UI** — `useTasks()` gains an optional `{ excludeArchivedCompleted }` argument, defaulting to
`false`, so its three other call sites (`App.tsx`, `OverviewPage.tsx`, `QualityHealthPanel.tsx`)
are unchanged. `TasksBoard.tsx` passes it based on whether an explicit scope is active. One new
small component surfaces the document-tasks affordance next to `SpecCoverageBar`.

## Non-Goals

- **Not changing what any caller other than the task board's default fetch sees.** The MCP
  `list_tasks` tool, the Overview page, and the Quality panel keep seeing every task exactly as
  today — this proposal does not extend the exclusion to them, because nothing in this session's
  evidence asks for it and doing so unannounced would be a silent behaviour change to a tool
  surface agents already rely on.
- **Not an unarchive-aware or configurable exclusion.** The rule is fixed: archived document,
  terminal task, hidden from the default view only. No operator setting to change the terminal-status
  list or turn the exclusion off is added.
- **Not building any part of N2 over again.** N2's design D8 is explicit that no task is read or
  written by anything it shipped; this proposal is the read-path filter D8 left for whichever change
  landed second.
- **Not a merge-history or capability-document task view.** A capability document's own
  `spec_document_id` linkage (if any task ever declares one against a `kind="capability"` document,
  which nothing in N2 causes to happen) is scoped identically to any other document — no special
  case is added for it.
