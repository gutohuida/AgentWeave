# Design — Delete a project through the product

## Context

`hub/hub/db/models.py` has 27 tables carrying a `project_id` column pointing at `projects.id`
(enumerated by grep against the live schema during this design, not assumed). Of those, `Project`
declares an ORM `relationship(back_populates="project")` for 11: `api_keys`, `messages`, `tasks`,
`questions`, `jobs`, `agents`, `queue_entries`, `conversations`, `turn_usages`, `runners`,
`charters`. The other 16 — `event_logs`, `agent_heartbeats`, `project_sessions`,
`project_instructions`, `runs`, `agent_outputs`, `job_runs`, `permission_requests`,
`unasked_questions`, `checkpoints`, `checkpoint_notes`, `worker_invocations`, `spec_documents` and
its five satellite tables (`spec_rigor_events`, `spec_document_events`, `spec_requirements`,
`spec_requirement_revisions`, `task_requirement_links`, `task_requirement_references`,
`requirement_evidence`, `evidence_reviews`, `evidence_footprints`, `requirement_drift`,
`task_integrations`), plus `agent_job_deletions` (has a `project_id` column but **no**
`ForeignKey` — it is a deliberately durable tombstone, see its docstring) — have no relationship
declared at all. None of the 27 declares `cascade="all, delete-orphan"` or `ondelete="CASCADE"`
except `job_runs`. `hub/hub/db/engine.py` never issues `PRAGMA foreign_keys = ON`, so SQLite enforces
none of this at the database level either — confirmed by Q1's finding in the same run
(`.claude/autonomous/2026-08-16-app-and-test-reform-log.md`, Entry 1: *"a delete confined to the
`projects` table would have left ~7,700 orphaned rows across 27 other tables"*).

## D1 — No schema change

Every table this delete touches already exists. No column, no migration. The current migration head
(`0073`, confirmed against `hub/tests/test_migrations.py`) does not move. If a reviewer expected a
migration here, that expectation is wrong: this is a data-plane operation over the existing schema.

## D2 — Cascade mechanism: a generic sweep over `project_id` columns, not hand-maintained ORM relationships

**Decision:** `ProjectLifecycleService.delete()` introspects `Base.metadata.tables` (SQLAlchemy's own
table registry — the same one Alembic's migrations are generated against), and for every table other
than `projects` that declares a `project_id` column, issues `DELETE FROM <table> WHERE project_id =
:id`. The `projects` row is deleted last, in the same transaction.

**Why not `cascade="all, delete-orphan"` on 27 relationships:** it would require first *writing* the
16 relationships that do not exist today, and then it becomes something a future table addition must
remember to declare — which is exactly the drift already observed: `Project` has carried project-
scoped tables with no relationship for as long as those 16 tables have existed, and nobody noticed
until Q1's raw sweep needed the true list. A relationship-based cascade is only as complete as the
last person who remembered to add one. A generic sweep over "every table with a `project_id` column"
is complete by construction and stays complete when a new project-scoped table is added with no
extra step required — the same property Q1's one-shot script had, now productized instead of
hand-run.

**Why not raw `PRAGMA foreign_keys = ON` plus `ondelete="CASCADE"` everywhere:** turning on foreign-key
enforcement is a much larger, separate change with its own blast radius (every existing insert/update
path would need auditing for now-enforced ordering and orphan-write assumptions) and is out of scope
for a delete endpoint. Recorded as a **non-goal**, not silently declined.

**`agent_job_deletions`:** included in the sweep despite having no `ForeignKey` — it has a
`project_id` column, so the generic sweep catches it for free, consistent with how Q1's script also
worked column-presence-first rather than relationship-first. Its docstring calls it a "durable
attribution tombstone," but a tombstone for a job that no longer exists, in a project that no longer
exists, has nothing left to attribute; keeping it would be the one row in the whole sweep that
outlives its own project for no stated reason.

**`project_sessions` and `project_instructions`:** `project_id` is their *primary key*, not a
secondary column — the generic sweep's `WHERE project_id = :id` still matches and removes them
correctly; no special case needed.

**Ordering:** SQLite enforces no FK constraints here (D1's context), so delete order does not need to
respect dependency order for correctness. The implementation still deletes in a stable, explicit
order (satellite/derivative tables before the tables they reference, e.g. `evidence_reviews` before
`requirement_evidence`, `spec_requirement_revisions` before `spec_requirements`) so that if
`PRAGMA foreign_keys = ON` is ever adopted later (D2's stated non-goal), this code does not need to
change to keep working — good hygiene, not a correctness requirement today.

## D3 — Refuses on an active run; an open conversation does not block

**Decision:** reuse `_guard_relocation`'s existing check verbatim: refuse with 409 if
`SELECT COUNT(*) FROM runs WHERE project_id = :id AND status = 'running'` is non-zero.

**Why an open conversation does *not* block:** a conversation is chat history — a `Conversation` row
with `Message` rows under it, not an in-progress operation. Almost every project that has ever been
used has at least one conversation; treating "has a conversation" as a blocker would make delete
nearly unreachable for the exact projects an operator actually wants to remove (a finished test
project, not an empty one). "Active run" is the codebase's own precedent for what "still doing
something" means for a project-level structural mutation (`_guard_relocation`, written for the
identical question about relocation) — reused rather than inventing a second definition.

**Not extended to "the project's agents are enabled" or any other soft-active state.** Only a `Run`
row with `status = 'running'` blocks. A project with configured, idle agents is deletable.

## D4 — The filesystem is never touched: a structural guarantee, not just a promise

**Decision:** `ProjectLifecycleService.delete()` imports nothing from `project_workspace.py` and
calls no filesystem API. The function receives only `project_id`, reads `Project.working_directory`
for nothing but the SSE broadcast payload (so the UI can say what was removed), and never opens,
lists, or deletes a path.

**Verification is a test, not a review note** (`tasks.md` 3.5): create a real temp directory, register
it as a project, delete the project through the API, assert the directory and every file under it
still exist byte-for-byte, then mutation-check by temporarily adding a `shutil.rmtree(directory)`
call to the delete path and confirming that named test fails. A safety property that is only ever
manually reviewed regresses the first time someone refactors the function under time pressure; a
test that actively proves the code *cannot* delete the directory (by failing when it can) is the only
form of this guarantee worth shipping.

## D5 — The `.agentweave/project.json` marker inside the directory is left alone

**Decision:** do not delete it. The marker is non-secret, contains no credentials, and its only
function is "this directory is bound to project id X." Once the `projects` row for X is gone, the
marker is inert — nothing reads it successfully again unless the *same* directory is re-opened, in
which case `ProjectLifecycleService.open_existing`'s existing marker-mismatch handling already
decides what happens (a marker naming an unknown project id is exactly the "marker was copied"/
identity-conflict shape that path already has to handle for other reasons). Removing it would require
a filesystem write from the delete path — the one thing D4 exists to rule out — in exchange for
tidiness inside a directory AgentWeave does not own. Left alone is the conservative choice and costs
nothing.

## D6 — Deleting the operator's last project

**Current behaviour, read from the code rather than guessed:** `configStore.bootstrap()` sets
`selectedProjectId` to `projects[0]?.id ?? null` whenever the persisted selection no longer exists in
the collection (`hub/ui/src/store/configStore.ts:185`) — but only runs at bootstrap (page load), not
after a mutation inside a live session. `App.tsx` renders `<ProjectHeader>` only `{currentProject &&
...}` (`App.tsx:458`) and always renders `content` and `<SetupModal>`, but nothing in the file branches
on "the project collection is empty" — `SetupModal`'s `open` condition is `!isConfigured || setupOpen`,
and `isConfigured` tracks whether an API key is set, not whether any project exists. **There is
currently no defined zero-project state distinct from "not yet configured."**

**Decision:** the delete mutation's `onSuccess` removes the deleted project from the React Query
`['projects']` cache (matching `useRelocateProject`'s existing pattern of updating that cache
directly) and, if the deleted project was the selected one, calls `setSelectedProject(remaining[0]?.id
?? null)` — reusing `configStore`'s own resolution logic rather than inventing a second one. When that
leaves `selectedProjectId` `null`, the rail (already rendered unconditionally) still shows its
existing "Add project" button (`Sidebar.tsx`, `data-testid="create-new-project"`) with an empty list
above it — which is what a fresh Hub with zero projects already looks like today, since nothing
currently special-cases "zero projects" either. **This proposal does not invent a new empty-state
screen**; it confirms the existing zero-projects rendering is coherent (rail with only the "Add
project" affordance, no header, no crash) and makes that path reachable by test, since today it is
only reachable by wiping the database. If `tasks.md`'s test for this finds the *content* pane renders
something broken with no project selected (as opposed to simply being empty), that is a pre-existing
gap this proposal surfaces rather than one it introduces, and it gets fixed here rather than filed
separately — a "delete your last project" flow that crashes the app is not a shippable version of this
feature.

## D7 — Confirmation UX

**Decision:** type-to-confirm, matching the standard the queue item's `detail` field specifies for an
irreversible action: a dialog naming the project, an input the operator must fill with the project's
exact current name (case-sensitive, no trimming beyond leading/trailing whitespace), and a Delete
button disabled until it matches. This is a new interaction pattern for this codebase — nothing
existing already does type-to-confirm — but it is the standard pattern for exactly this class of
action elsewhere (matches what the review criteria asks for, and is proportionate to a project delete
specifically because it is not undoable, per the stated Non-Goal of no soft-delete). No other
destructive control in this product deletes as much at once, so no lighter existing pattern
(`window.confirm`-style single click, as runner-delete uses) is reused for this one.

## Authentication and route shape

`DELETE /api/v1/projects/{project_id}`, `Depends(get_operator)` — the same instance-operator
dependency `list_projects`/`open_project`/`create_project` already use, not `get_project` (the
per-project agent-scoped dependency `delete_runner` uses). Deleting a project is a decision about the
Hub's collection of projects, made by whoever administers the instance; a credential scoped to
operate *inside* one project has no standing to remove the project it is scoped to. Returns `204 No
Content` on success (matching `delete_runner`), `404` if the id does not exist, `409` with a
machine-readable `code` (`"project_has_active_run"`) if D3's guard fires.
