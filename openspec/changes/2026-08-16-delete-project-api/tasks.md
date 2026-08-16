# Tasks — Delete a project through the product

No migration in this change (`design.md` D1) — every table already exists.

## 1. `ProjectLifecycleService.delete()`

- [x] 1.1 `delete(project_id: str) -> DeletedProjectSummary` (or similar) in
      `hub/hub/project_lifecycle.py`. 404s (raises the same not-found shape `_operator_project_row`
      uses) if the project does not exist.
      Implemented as `ProjectLifecycleService.delete()`, raising `ProjectPathError(code=
      "project_not_found")` — the same shape `relocate()` already raises for the identical case,
      which the API layer already knows how to turn into a 404 (see `relocate_project`'s
      `except ProjectPathError` branch). `DeletedProjectSummary` is a frozen dataclass (`id`, `name`)
      captured before the row is deleted, for phase 2's SSE broadcast payload.
- [x] 1.2 Guard: refuse with a distinct exception (`ProjectHasActiveRun` or reuse
      `ProjectPathError` with `code="project_has_active_run"`, matching the existing
      `code="project_relocation_active"` shape) if
      `SELECT COUNT(*) FROM runs WHERE project_id = :id AND status = 'running'` is non-zero
      (`design.md` D3).
      Reused `ProjectPathError` with `code="project_has_active_run"`. Verified live (throwaway
      in-memory DB, not committed): creating a `Run(status="running")` then calling `delete()`
      raises with that exact code, and the project row still exists afterward.
- [x] 1.3 Enumerate `Base.metadata.tables`, collect every table other than `projects` with a
      `project_id` column (`design.md` D2). Delete from each, in the stable dependency-respecting
      order D2 specifies (satellites before what they reference), all inside one transaction. Delete
      the `projects` row last.
      `_project_scoped_tables()` sweeps `reversed(Base.metadata.sorted_tables)` filtered to tables
      with a `project_id` column — 38 tables today (verified by direct introspection against the
      live model registry: every table `grep`-confirmed to declare `project_id` in
      `hub/hub/db/models.py` is included, `agent_job_deletions` among them despite its missing
      `ForeignKey`, per D2). `sorted_tables` reversed puts referencing tables before what they
      reference for the *whole* FK graph, not just `project_id` FKs, which is a superset of what D2
      asked for and satisfies it. Reviewer's round-1 watch item ("does every swept `project_id`
      column really mean ownership?") was checked against every table name in the sweep output — none
      reads as a cross-project reference column (all are either the row's own FK to `projects.id` or,
      for `project_sessions`/`project_instructions`, their primary key) — recorded here since the
      watch item asked for this to be checked before trusting the sweep, not left implicit.
- [x] 1.4 Confirm by code inspection (not just by test — this is the property 3.5 mutation-checks)
      that `delete()` never imports from `project_workspace.py` and calls no `os`/`pathlib`/`shutil`
      filesystem operation on `Project.working_directory`.
      Confirmed: `delete()`'s only imports are already-present SQLAlchemy/`Project`/`Run` names; it
      reads `project.working_directory` for nothing (not even the summary, since 2.3's SSE payload
      only needs `id`/`name` per the route's existing broadcast shape) and calls no filesystem API.
      The actual mutation check (temporarily adding `shutil.rmtree`, confirming a test fails, then
      reverting) is task 3.5's job, once the test exists — not done in this phase-1-only iteration.
- [x] 1.5 Do not delete `.agentweave/project.json` in the working directory (`design.md` D5) — no
      code path attempts to.
      True by inspection — `delete()` never opens that path or any path.

## 2. API route

- [ ] 2.1 `DELETE /api/v1/projects/{project_id}` in `hub/hub/api/v1/projects.py`,
      `Depends(get_operator)` (not `get_project` — this is an instance-level operation, per
      `design.md`'s "Authentication and route shape"). `204 No Content` on success.
- [ ] 2.2 `404` if the project does not exist. `409` with `code="project_has_active_run"` if 1.2's
      guard fires.
- [ ] 2.3 Broadcast an SSE event (`project_deleted`, matching the `project_opened`/`project_created`
      pattern already in this file) with the id and name, before the row is gone, so a connected
      client's own project list updates without a poll.

## 3. Backend tests — agent-verifiable

- [ ] 3.1 Happy path: create a project, add at least one row in a representative sample of the
      27 project-scoped tables (an agent, a runner, a charter, a task, a conversation with a
      message, a run in a terminal state, an event log row), delete it, assert every one of those
      rows is gone and the `projects` row is gone.
- [ ] 3.2 No orphans, exhaustively: after 3.1's delete, iterate every table in `Base.metadata.tables`
      with a `project_id` column and assert zero rows remain matching that project id — not just the
      sample from 3.1. This is what makes the "no table left behind" claim a test rather than a
      review note.
- [ ] 3.3 A second, untouched project's rows of every kind survive the first project's deletion
      unchanged (proves the `WHERE project_id = :id` scoping, not a global truncate).
- [ ] 3.4 A running run refuses deletion: create a project, a `Run` row with `status="running"`,
      attempt delete, assert `409` and that every row for the project (including the run) still
      exists.
- [ ] 3.5 **The workspace-directory-survives test, mutation-checked** (`design.md` D4): create a real
      temp directory with a marker file and a source file inside it, register it as a project,
      delete the project, assert the directory and both files still exist with unchanged content.
      Then mutation-check: temporarily add a `shutil.rmtree` (or equivalent) call to `delete()`,
      re-run this test, confirm it fails, then revert. Record the mutation check in the PR/commit,
      not just claim it happened.
- [ ] 3.6 A terminal (non-running) run does not block deletion — a project whose only run is
      `completed`/`failed`/`diverged` deletes normally.
- [ ] 3.7 A project with conversations and messages, no active run, deletes normally (the "open
      conversation does not block" scenario).
- [ ] 3.8 `agent_job_deletions` rows (no `ForeignKey`, per `design.md`'s D2 note) are removed by the
      sweep despite having no declared relationship — a test that specifically targets this table,
      since it is the one the generic-sweep approach exists to catch without special-casing.
- [ ] 3.9 `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py` need **no** head
      bump (no migration in this change) — confirm both still pass unmodified as a sanity check that
      this claim is true, not assumed.

## 4. UI — delete control

- [ ] 4.1 `useDeleteProject(projectId)` in `hub/ui/src/api/projects.ts`, mirroring
      `useRelocateProject`'s shape: `useMutation` calling `DELETE /api/v1/projects/{id}`, `onSuccess`
      removes the project from the `['projects']` query cache and, if it was the selected project,
      resolves the next selection the same way `configStore.bootstrap()` does
      (`design.md` D6) — reuse that resolution, do not reimplement it a second way.
- [ ] 4.2 A `DeleteProjectSection` (or extend `ProjectSettingsPanel.tsx` directly) using
      `SettingsSection`/`SettingsRow`, in the `settings` environment section, below the existing
      relocate control. `Icon` component only (`name="trash"` or nearest lucide equivalent already
      used elsewhere in this codebase — check before introducing a new icon name).
- [ ] 4.3 Confirmation dialog: names the project, requires typing its current name
      (case-sensitive, trimmed) before the Delete button enables (`design.md` D7). Cancel leaves
      everything unchanged.
- [ ] 4.4 On `409` (active run), the dialog surfaces that reason instead of a generic error — the
      operator should learn *why* deletion is refused, not just that it was.
- [ ] 4.5 Confirm (by reading `App.tsx` and `Sidebar.tsx` as they exist after 4.1-4.4, not by
      assumption) that a zero-project state renders the rail's existing "Add project" affordance
      with no crash and no stale project header. If it does not, fix it here — `design.md` D6 treats
      a broken last-delete as in-scope, not a follow-up.

## 5. UI tests — agent-verifiable

- [ ] 5.1 A component/integration test (matching the existing pattern in
      `hub/ui/src/__tests__/projectRail.test.tsx` or a new file) that the Delete button stays
      disabled until the typed name matches exactly, and calls the mutation only once enabled.
- [ ] 5.2 A test that a `409` response renders the active-run reason, not a generic failure message.
- [ ] 5.3 `npm run lint` clean; `npx openspec validate --changes --strict` clean.

## 6. Human-only verification

- [ ] 6.1 **Drive it for real against the live Hub, on a throwaway project created for this purpose —
      never against `aw-loop10`**, which the operator needs intact for the 29 parked judgement tasks.
      Create a disposable project, add an agent and a conversation, delete it through the UI, confirm
      it disappears from the rail and the workspace directory is untouched on disk.
- [ ] 6.2 If Q4a's screenshot harness (`scripts/uishot.py`) is available, capture the confirmation
      dialog and the resulting state (both light and dark) and `Read` the PNGs — this is explicitly
      the harness's first real test per Q4b's `note`, simple enough that a screenshot either
      obviously works or does not.
- [ ] 6.3 **Judge the confirmation's proportionality** — does typing the project name feel like the
      right amount of friction for this action, or excessive/insufficient? Taste, not measurable.
- [ ] 6.4 **Judge the empty-state.** After deleting the last project on a scratch Hub instance (not
      the live one), does the resulting screen read as "add your first project" or as broken? Taste.

## 7. User test guide

**Setup.** A running Hub with at least one project you do not mind losing (create one for this if
needed — never use a project you rely on).

1. **Try to delete a project that has a run in progress.** Start any agent run, then open that
   project's Settings and try to delete it.
   - *Expect:* refused, with a message saying a run is active. Nothing is removed.
2. **Delete a project with no active run.** Open Settings for a disposable project, find Delete
   Project, and follow the confirmation.
   - *Expect:* you must type the project's exact name before Delete becomes clickable. After
     confirming, the project disappears from the sidebar.
3. **Check the directory.** Open the folder the deleted project pointed at, in your normal file
   browser or editor — outside AgentWeave entirely.
   - *Expect:* every file is exactly as you left it. AgentWeave never touches this folder on delete.
4. **Delete your last project (on a project you don't need — this step is optional and destructive).**
   - *Expect:* the app does not crash or show a blank error screen; you can still add a new project
     from the sidebar.

**Where it would go wrong:** if step 3 shows any file changed, moved, or missing, stop immediately and
report it — that is the one failure mode this feature exists to prevent.
