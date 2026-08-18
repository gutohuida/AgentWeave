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

- [x] 2.1 `DELETE /api/v1/projects/{project_id}` in `hub/hub/api/v1/projects.py`,
      `Depends(get_operator)` (not `get_project` — this is an instance-level operation, per
      `design.md`'s "Authentication and route shape"). `204 No Content` on success.
      Added after `relocate_project`. `project_id` is a plain path parameter (not resolved
      through `get_operator_project`, which would 404 on an unknown id itself before
      `delete()` gets a chance to raise its own typed error) — `Depends(get_operator)` only,
      matching the task's literal wording. Verified live over real HTTP (throwaway test file,
      run then deleted, not committed): a successful delete returns 204 with an empty body,
      and the project is absent from a subsequent `GET /api/v1/projects`.
- [x] 2.2 `404` if the project does not exist. `409` with `code="project_has_active_run"` if 1.2's
      guard fires.
      Handled by catching `ProjectPathError` and branching on `.code`, the same shape
      `relocate_project` uses for `project_not_found` — but for `project_has_active_run` this
      route raises `HTTPException(409, detail={"code": ..., "message": ...})` directly rather
      than calling `raise_workspace_http_error`, because that helper maps a bare
      `ProjectPathError` to 422 (it reserves 409 for `ProjectIdentityConflict`/
      `ProjectWorkspaceUnavailable`), which would contradict `design.md`'s explicit "409 with a
      machine-readable code" for this route. Verified live: unknown id → 404; a project with a
      `status="running"` run → 409 with `detail["code"] == "project_has_active_run"` and the
      project row still present afterward; no `Authorization` header → 401 (auth runs before
      either check).
- [x] 2.3 Broadcast an SSE event (`project_deleted`, matching the `project_opened`/`project_created`
      pattern already in this file) with the id and name, before the row is gone, so a connected
      client's own project list updates without a poll.
      Broadcasts **after** `ProjectLifecycleService.delete()` returns, not before — this
      supersedes this task's literal "before the row is gone" wording per round 1 review's watch
      item (recorded in `STATE.json`'s `next_action` after Entry 6): `delete()` already commits
      inside its own transaction (phase 1, D2), so by the time the route regains control the row
      is unavoidably already gone; broadcasting first would not change that, and broadcasting
      after is what "confirm the commit happened before telling clients it happened" actually
      requires. `summary.id`/`summary.name` (captured by `delete()` before the sweep, per 1.1)
      supply the payload since `project.name` is no longer readable off a deleted ORM instance.

## 3. Backend tests — agent-verifiable

- [x] 3.1 Happy path: create a project, add at least one row in a representative sample of the
      27 project-scoped tables (an agent, a runner, a charter, a task, a conversation with a
      message, a run in a terminal state, an event log row), delete it, assert every one of those
      rows is gone and the `projects` row is gone.
      `hub/tests/test_project_delete_api.py::test_delete_removes_a_representative_sample_of_project_scoped_rows`.
      The table count is actually 38, not 27 — see 1.3's note and the new
      `test_sweep_covers_every_project_scoped_table_in_the_model_registry`, which introspects
      `Base.metadata` directly and fails if the live model registry ever disagrees with this
      file's hand-kept `PROJECT_SCOPED_TABLE_NAMES` list, rather than letting that list silently
      go stale the way the design doc's "27"/"16" counts already had.
- [x] 3.2 No orphans, exhaustively: after 3.1's delete, iterate every table in `Base.metadata.tables`
      with a `project_id` column and assert zero rows remain matching that project id — not just the
      sample from 3.1. This is what makes the "no table left behind" claim a test rather than a
      review note.
      `test_delete_leaves_no_orphans_in_any_project_scoped_table` — a shared `_seed_full_project`
      helper adds one row to **every** one of the 38 tables (not a sample), asserts every one is
      populated before delete (so a table left at 0 both before and after cannot pass for the
      wrong reason), deletes, then asserts every one is 0 after.
- [x] 3.3 A second, untouched project's rows of every kind survive the first project's deletion
      unchanged (proves the `WHERE project_id = :id` scoping, not a global truncate).
      `test_a_second_untouched_project_survives_the_first_projects_deletion` — both projects fully
      seeded via the same helper; exact per-table counts for the survivor compared before/after.
- [x] 3.4 A running run refuses deletion: create a project, a `Run` row with `status="running"`,
      attempt delete, assert `409` and that every row for the project (including the run) still
      exists.
      `test_a_running_run_refuses_deletion_and_nothing_is_removed` — asserts at the service layer
      (`ProjectPathError.code == "project_has_active_run"`; the route's `409` mapping is already
      covered by phase 2's HTTP-level checks) and that per-table row counts are byte-identical
      before and after the refused attempt, on a fully-seeded project with a second, running run
      alongside the completed one `_seed_full_project` always adds — proving the guard does not
      require every run on the project to be running.
- [x] 3.5 **The workspace-directory-survives test, mutation-checked** (`design.md` D4): create a real
      temp directory with a marker file and a source file inside it, register it as a project,
      delete the project, assert the directory and both files still exist with unchanged content.
      Then mutation-check: temporarily add a `shutil.rmtree` (or equivalent) call to `delete()`,
      re-run this test, confirm it fails, then revert. Record the mutation check in the PR/commit,
      not just claim it happened.
      `test_workspace_directory_survives_deletion`, using the `bind_project_workspace` fixture
      (real directory, real `ProjectLifecycleService.open_existing`, not the suite's default fake
      resolver). Mutation check done by hand against the real function, not baked into the test as
      a self-injected wrapper (a wrapper that calls the real `delete()` then bolts on its own
      `shutil.rmtree` only proves `shutil.rmtree` deletes directories, not that this assertion
      would catch a real regression) — temporarily added
      `shutil.rmtree(project.working_directory, ignore_errors=True)` directly inside
      `ProjectLifecycleService.delete()`, ran this one test, watched it fail on
      `assert directory.is_dir()` with the directory actually gone, then reverted with `git diff
      --stat hub/hub/project_lifecycle.py` showing empty. Confirms 1.4's mutation check, deferred
      from phase 1, is now done.
- [x] 3.6 A terminal (non-running) run does not block deletion — a project whose only run is
      `completed`/`failed`/`diverged` deletes normally.
      `test_a_terminal_run_does_not_block_deletion`.
- [x] 3.7 A project with conversations and messages, no active run, deletes normally (the "open
      conversation does not block" scenario).
      `test_a_project_with_conversations_and_messages_deletes_normally`.
- [x] 3.8 `agent_job_deletions` rows (no `ForeignKey`, per `design.md`'s D2 note) are removed by the
      sweep despite having no declared relationship — a test that specifically targets this table,
      since it is the one the generic-sweep approach exists to catch without special-casing.
      `test_agent_job_deletions_removed_despite_no_declared_foreign_key`.
- [x] 3.9 `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py` need **no** head
      bump (no migration in this change) — confirm both still pass unmodified as a sanity check that
      this claim is true, not assumed.
      Ran both directly rather than adding a redundant test that merely imports them (importing
      proves nothing about pass/fail): `pytest hub/tests/test_project_delete_api.py
      hub/tests/test_operator_projects_api.py hub/tests/test_project_lifecycle.py
      hub/tests/test_project_persistence.py hub/tests/test_migrations.py` — 104 passed, 1
      pre-existing skip, 0 failed, 65.5s. `test_migrations.py`'s own hardcoded head assertion
      already reads `"0073"` (Q3's conversation-sequence migration, unrelated to this change, not
      `"0058"` as one stale docstring nearby still says) and passed unmodified, confirming no bump
      was needed here.

## 4. UI — delete control

- [x] 4.1 `useDeleteProject(projectId)` in `hub/ui/src/api/projects.ts`, mirroring
      `useRelocateProject`'s shape: `useMutation` calling `DELETE /api/v1/projects/{id}`, `onSuccess`
      removes the project from the `['projects']` query cache and, if it was the selected project,
      resolves the next selection the same way `configStore.bootstrap()` does
      (`design.md` D6) — reuse that resolution, do not reimplement it a second way.
      Added. The mutation bypasses `deleteJson` deliberately — the route returns `204` with an empty
      body, and `deleteJson` always calls `res.json()`, which throws `SyntaxError` on an empty
      response; used `fetchWithAuth` directly and discarded the response. `onSuccess` writes the
      filtered array once via `queryClient.setQueryData`'s functional updater, captures that same
      filtered array as `remaining`, and only then reads `useConfigStore.getState().selectedProjectId`
      to decide whether to call `setSelectedProject(remaining[0]?.id ?? null)` — one source of truth
      for "what's left" rather than a second cache read.
- [x] 4.2 A `DeleteProjectSection` (or extend `ProjectSettingsPanel.tsx` directly) using
      `SettingsSection`/`SettingsRow`, in the `settings` environment section, below the existing
      relocate control. `Icon` component only (`name="trash"` or nearest lucide equivalent already
      used elsewhere in this codebase — check before introducing a new icon name).
      Extended `ProjectSettingsPanel.tsx` with a `SettingsRow` below the Directory row, holding a
      `destructive`-variant `Button` that opens the dialog. No new icon needed — the trigger is a
      labelled button ("Delete project…"), matching the Directory row's own "Locate project" trigger,
      which is also text-only.
- [x] 4.3 Confirmation dialog: names the project, requires typing its current name
      (case-sensitive, trimmed) before the Delete button enables (`design.md` D7). Cancel leaves
      everything unchanged.
      New `hub/ui/src/components/environment/DeleteProjectDialog.tsx`, following
      `AgentCreateDialog.tsx`'s existing dialog pattern (`role="dialog"`, `aria-modal`,
      `useDialogFocus` for focus trap + Escape). `canDelete` compares `typed.trim() === project.name`
      — trimmed at the edges only, case-sensitive otherwise, per D7's literal wording. Cancel calls
      `onClose` with no mutation invoked; the dialog's own `useEffect` resets `typed` and the mutation
      state every time it reopens, so a cancelled attempt leaves no stale input behind.
- [x] 4.4 On `409` (active run), the dialog surfaces that reason instead of a generic error — the
      operator should learn *why* deletion is refused, not just that it was.
      No new branching needed: `hub/hub/api/v1/projects.py`'s 409 already carries
      `detail={"code": ..., "message": "project cannot be deleted while a run is active"}`, and
      `readableApiError` (`hub/ui/src/api/client.ts`) already extracts `detail.message` from exactly
      this shape (it was written for the checkpoint-threshold refusal, but the shape is generic). The
      dialog calls `readableApiError(deleteProject.error, 'The project could not be deleted.')` —
      verified by reading `readableApiError`'s object-detail branch against the route's actual
      `detail` shape, not assumed.
- [x] 4.5 Confirm (by reading `App.tsx` and `Sidebar.tsx` as they exist after 4.1-4.4, not by
      assumption) that a zero-project state renders the rail's existing "Add project" affordance
      with no crash and no stale project header. If it does not, fix it here — `design.md` D6 treats
      a broken last-delete as in-scope, not a follow-up.
      Read both files. Already coherent, no fix needed — better than D6 assumed: `App.tsx` already
      has a `WorkspaceDestination` of `{kind: 'zero'}` (`lib/navigation.ts`), and
      `useWorkspaceNavigation`'s `resolveDestination` falls through to it whenever
      `availableProjectIds` is a non-null empty array with no `lastOpenedProjectId` match
      (`navigation.ts:383-386`). `App.tsx`'s `content` renders "Open or create a project to begin."
      for every destination kind that isn't `conversation`/`agent-settings`/`project` (the final
      `else` at `App.tsx:398`), `<ProjectHeader>` is already gated on `currentProject &&` so it
      renders nothing rather than a stale header, and `Sidebar.tsx`'s rail always renders the
      "Add project" button (`data-testid="create-new-project"`) unconditionally below
      `projects.map(...)`, which is simply empty when `projects` is `[]` — no crash. This path was
      reachable only by wiping the database before; `useDeleteProject`'s cache write to `['projects']`
      is what makes `availableProjectIds` go to `[]` reactively inside a live session, and
      `useWorkspaceNavigation` already recomputes `destination` on that array's content (compared by
      `.join(',')`, not identity) via its `useEffect` dependency — confirmed by reading, not run
      live yet (that's task 6.4, the taste judgement on top of this structural check).

## 5. UI tests — agent-verifiable

- [x] 5.1 A component/integration test (matching the existing pattern in
      `hub/ui/src/__tests__/projectRail.test.tsx` or a new file) that the Delete button stays
      disabled until the typed name matches exactly, and calls the mutation only once enabled.
      New `hub/ui/src/__tests__/deleteProjectDialog.test.tsx`, rendering `DeleteProjectDialog`
      directly with a mocked `useDeleteProject` (matching `next_action`'s suggested approach) rather
      than through `ProjectSettingsPanel`, since the dialog's own gating logic is what this asserts.
      Three cases: disabled until an exact match, then calls the mutation exactly once with
      `(undefined, { onSuccess: onDeleted })`; stays disabled on a case mismatch (`website`) or a
      partial match (`Web`) and never calls the mutation; accepts only edge-trimmed whitespace
      around an otherwise-exact match, per D7's literal wording (checked directly, not inferred from
      5.1's happy path).
- [x] 5.2 A test that a `409` response renders the active-run reason, not a generic failure message.
      Same file — constructs a real `ApiError(409, JSON.stringify({detail: {code:
      "project_has_active_run", message: "project cannot be deleted while a run is active"}}))`,
      matching phase 2's actual route payload exactly rather than a stand-in shape, and asserts the
      dialog's `role="alert"` renders that sentence, not the `readableApiError` fallback string. A
      second case pins the fallback still fires for an unstructured (non-JSON) error, so the first
      assertion is shown to depend on the structured shape rather than always passing regardless.
      `npx vitest run src/__tests__/deleteProjectDialog.test.tsx` — 5 passed.
- [~] 5.3 `npm run lint` clean; `npx openspec validate --changes --strict` clean.
      **openspec half: clean.** 14 passed, this change included.
      **lint half: partially met, and the remainder is out of this change's scope — recorded here
      rather than silently deferred.** `npm run lint` could not run at all before this task (Entry
      10's finding: no `eslint.config.js` anywhere in the repo, despite `eslint@9` requiring flat
      config). Fixed by adding `hub/ui/eslint.config.js` — `@eslint/js` recommended +
      `@typescript-eslint/eslint-plugin`'s `flat/recommended` (used directly; the combined
      `typescript-eslint` meta-package the standard Vite template imports is not installed, and
      installing it was avoidable) + `eslint-plugin-react-hooks`/`eslint-plugin-react-refresh`
      recommended rules. `@eslint/js` and `globals` resolve today only as transitive dependencies
      (pulled in by `eslint` itself and by other devDependencies) — present in `package-lock.json`
      already, so importing them needed no network fetch, but they were undeclared in `package.json`
      despite the config now importing both directly; added both as explicit devDependencies at
      their already-resolved versions (`@eslint/js` `^9.17.0`, `globals` `^14.0.0`) and ran `npm
      install --package-lock-only` to confirm the lockfile needed no other change — this is a
      correctness fix (declaring what is actually imported), not a new install.

      Running lint for the first time surfaced **16 pre-existing problems (7 errors, 9 warnings)**
      across the repo, none in files this change added. Fixed all 7 errors, each a mechanical,
      zero-behavior-change edit verified by rerunning the affected test/suite:
      - `projectSettingsPanel.test.tsx:15` — `let settings` → `const settings` (never reassigned;
        confirmed by grep before changing).
      - `urlNavigation.test.ts:268` — `'spec\windows\spec.html'` had unescaped backslashes, so the
        string literal actually evaluated to `"specwindowsspec.html"` (verified with `node -e`) —
        the test silently never exercised `isSpecDocumentPath`'s `value.includes('\\')` rejection at
        all. Fixed to `'spec\\windows\\spec.html'`, restoring the coverage the test always claimed
        to have. A real bug, not a style nit — found only because lint could finally run.
      - `AgentOutputPanel.tsx:210,302` and `ErrorBoundary.tsx:28` — three
        `eslint-disable-next-line` directives now unused under this config (`react-hooks/
        exhaustive-deps` no longer fires on either effect under the current plugin version;
        `no-console` was never part of any rule set this config enables). Removed; reran the full
        suite after to confirm no new failures.

      The remaining **9 warnings are a pre-existing backlog in files this change never touches**
      (`ChartersPage.tsx`, `Badge.tsx` ×2, `ProjectSettingsPanel.tsx` — the pre-existing top of the
      file, not anything 4.2 added, `SpecFrame.tsx`, `button.tsx`, `agentStatus.tsx` ×2 — all
      `react-refresh/only-export-components`, needing a file split to separate a component export
      from a constant/helper export — and one `OverviewPage.tsx` `react-hooks/exhaustive-deps` on a
      `useMemo` that needs an actual dependency-correctness review, not a mechanical fix). Fixing
      these means editing six files with no relationship to project deletion, which is scope creep
      beyond what a delete-project UI-tests task should carry, and the `useMemo` one specifically
      needs judgement about intended behavior, not a safe mechanical edit. Left for a dedicated
      follow-up; recorded in `decisions_for_user`. Net result: `npm run lint` runs (previously
      impossible), reports **0 errors**, and fails only on `--max-warnings 0` against a documented,
      unrelated 9-item backlog — a materially different, and now measurable, state from "cannot run
      at all."

      Full regression after all of phase 5's edits: `npx tsc --noEmit` clean; `npx vitest run` —
      **91 files / 869 tests passing** (one `runnersUi.test.tsx` timeout on first run, reran alone
      and passed in 3s, consistent with the load-dependent flake class this run's log already
      documents for `chartersUi.test.tsx` — not a regression, not touched by this task's edits).

## 6. Human-only verification

- [x] 6.1 **Drive it for real against the live Hub, on a throwaway project created for this purpose —
      never against `aw-loop10`**, which the operator needs intact for the 29 parked judgement tasks.
      Create a disposable project, add an agent and a conversation, delete it through the UI, confirm
      it disappears from the rail and the workspace directory is untouched on disk.
- [x] 6.2 If Q4a's screenshot harness (`scripts/uishot.py`) is available, capture the confirmation
      dialog and the resulting state (both light and dark) and `Read` the PNGs — this is explicitly
      the harness's first real test per Q4b's `note`, simple enough that a screenshot either
      obviously works or does not.
- [x] 6.3 **Judge the confirmation's proportionality** — does typing the project name feel like the
      right amount of friction for this action, or excessive/insufficient? Taste, not measurable.
- [x] 6.4 **Judge the empty-state.** After deleting the last project on a scratch Hub instance (not
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
