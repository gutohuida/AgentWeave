# Tasks — The board scoped by document

## 1. API (`hub/hub/api/v1/tasks.py`)

- [x] 1.1 Import `spec_lifecycle` (module) and add `SpecDocument` to the existing
      `from ...db.models import (...)` block. `TERMINAL_FOR_BINDING` needs no new import — it is
      already imported at the top of this file (`from ...run_task_binding import (TERMINAL_FOR_BINDING,
      release_conversations_bound_to, release_reason)`), verified this session. Ruff's import-sort
      merged the module import into the existing `from ... import project_workspace, spec_lifecycle,
      spec_reading` line rather than a separate statement — same effect, one line.
- [x] 1.2 `list_tasks`: add `spec_document_id: Optional[str] = Query(None)` and
      `exclude_archived_completed: bool = Query(False)` parameters.
- [x] 1.3 Apply them per design D1's `elif` ordering — `spec_document_id` exact-match filter when
      given, else the archived-and-terminal exclusion via an `IN` subquery when
      `exclude_archived_completed` is true. Neither applies to any other route in this file (task
      creation, single-task GET, PATCH are untouched). **Implementation corrections, both found only
      once real rows were run through the query (design D6/D7, not caught by any of the three spec
      rounds):** (a) the exclusion clause needed `Task.spec_document_id.isnot(None)` ANDed in before
      `.in_(archived_ids)` — SQL's `IN` returns NULL, not `false`, for a NULL left operand, so the
      original expression silently excluded every unlinked task with a terminal status, the opposite
      of the stated guarantee; (b) `hub/hub/api/v1/agent_actions.py`'s `list_shared_tasks` calls
      `list_tasks(...)` as a plain Python function (not through FastAPI dispatch) and forwarded only
      the parameters it already knew about, leaving the two new ones bound to their raw `Query(...)`
      sentinel defaults — fixed by forwarding `spec_document_id=None, exclude_archived_completed=
      False` explicitly, caught by the pre-existing `test_agent_task_crud_retains_create_and_latest_
      update_runs`.

## 2. UI (`hub/ui/src`)

- [x] 2.1 `hub/ui/src/api/tasks.ts`: `useTasks()` gains an optional
      `{ excludeArchivedCompleted?: boolean }` argument per design D2, defaulting to `false`; query
      key includes it so the two variants cache independently.
- [x] 2.2 `hub/ui/src/api/tasks.ts`: new `useDocumentTasks(documentId: string | null)` per design D3.
- [x] 2.3 `hub/ui/src/components/tasks/TasksBoard.tsx`: pass
      `useTasks({ excludeArchivedCompleted: activeTaskIds === null })` — the only change to this
      file; no change to how `activeTaskIds` itself filters the fetched array.
- [x] 2.4 New `hub/ui/src/components/spec/SpecDocumentTasksLink.tsx` per design D3.
- [x] 2.5 `hub/ui/src/components/spec/SpecDocumentPanel.tsx`: render
      `<SpecDocumentTasksLink path={path} onOpenTasks={onOpenTasks} />` beside `SpecCoverageBar`
      (no new prop — `onOpenTasks` is already threaded to this component).
- [x] 2.6 `cd hub/ui && npm run build && python ../../scripts/refresh_ui_bundle.py` after the above,
      confirming `hub/hub/static/ui/ui-build-stamp.json` updates and `diff -rq` between `dist/` and
      the committed bundle reports no difference (CLAUDE.md's standing rule for any `hub/ui/src`
      change). Run this again after committing, not only before — the fingerprint folds in `git
      status --porcelain`, so a run against a dirty tree stamps a fingerprint the post-commit clean
      tree will not reproduce (found and recorded in N2's own log, Entry 4). First pass done before
      commit; the post-commit re-run is the last step before pushing, recorded in the log.

## 3. Tests — agent-verifiable

- [x] 3.1 `hub/tests/test_tasks.py` (existing file — confirmed present, holds the `GET /tasks`
      coverage this belongs beside): `GET /tasks?spec_document_id=X` returns exactly the tasks with
      that `spec_document_id`, including ones whose status is terminal and whose declaring document
      is archived. `GET /tasks?exclude_archived_completed=true` excludes a task iff its declaring
      document is archived and its own status is `approved` or `rejected`; a task with the same
      terminal status but a non-archived (or no) declaring document is not excluded; an
      `in_progress` or `blocked` task from an archived document is not excluded. Both parameters
      given together: `spec_document_id` wins, exclusion is not applied (design D1's `elif`) —
      assert against a document that is itself archived, citing one of its own terminal tasks, and
      confirm it is returned. This test is what caught design D6's NULL-handling bug — the first run
      failed with an unlinked terminal task wrongly excluded, fixed in the same iteration (D6).
- [x] 3.2 Same file: a task with `spec_document_id = None` is never excluded by
      `exclude_archived_completed`, regardless of its own status (the subquery's `~(...)` must not
      match a null against `.in_(archived_ids)` in a way that excludes it — this is the one subtlety
      design D1 calls out explicitly). Folded into 3.1's own test (`task-exc-6`) rather than a
      separate test function — same assertion, same seeded rows.
- [x] 3.3 `hub/ui/src/__tests__/tasksApi.test.tsx` (new — **`.tsx`, not `.ts` as originally written**:
      the file renders a `<QueryClientProvider>` wrapper via `renderHook`, which is JSX and fails
      esbuild's transform under a `.ts` extension; every existing UI test file lives flat under
      `hub/ui/src/__tests__/`, confirmed by listing the directory): `useTasks({
      excludeArchivedCompleted: true })` requests `?exclude_archived_completed=true`; `useTasks()`
      with no argument requests the bare path, unchanged; `useDocumentTasks(id)` requests
      `?spec_document_id=<id>`; `useDocumentTasks(null)` does not fire (`enabled` false).
- [x] 3.4 `hub/ui/src/__tests__/specDocumentTasksLink.test.tsx` (new, same flat convention): renders
      nothing when the document has no tasks; renders the count and, given `onOpenTasks`, clicking
      calls it with every task id the document declared (not merely ones linked to a requirement);
      renders a plain span with no click target when `onOpenTasks` is omitted, mirroring
      `SpecCoverageBar`'s existing fallback for the same prop.
- [x] 3.5 `hub/ui/src/__tests__/tasksBoardFilter.test.tsx` (existing — this is where
      `activeTaskIds`'s board-level filtering is already tested). Per design D5 (round 2 correction):
      first make the file's `useTasks` mock argument-sensitive — accept the options object and
      return a filtered array when `excludeArchivedCompleted` is true (a seeded terminal task from an
      archived document removed), the full `TASKS` array otherwise — standing in for the server-side
      exclusion this proposal actually implements, since `TasksBoard.tsx` itself has no client-side
      filter for it. Then add a case where a seeded task's declaring document is archived and the
      task's own status is terminal: confirm it is absent from the default board render (exercising
      the now argument-sensitive mock) and present once `activeTaskIds` includes it explicitly
      (exercising `TasksBoard.tsx`'s real, unchanged client-side membership filter — simulating the
      coverage-bar / document-tasks-link click path).
- [x] 3.5b **Not in round 1's plan, found during implementation, not a spec round.**
      `hub/ui/src/__tests__/projectScopedApiContract.test.tsx` asserts `client.getQueryData(['project',
      'proj-a', 'tasks'])` (and the `proj-1`/`proj-2` equivalent) against the exact query key
      `useTasks()` with no argument produces — which, after D2's options object, is `['project',
      projectId, 'tasks', { excludeArchivedCompleted: false }]`, not `['project', projectId,
      'tasks']`. Two of that file's assertions updated to the new key shape; both pass. Design D2's
      own "why the query key includes the options object" reasoning only checked
      `invalidateQueries`'s prefix-match behaviour, not this file's exact-match `getQueryData` calls —
      recorded as design D7's sibling finding rather than a new D-entry, since the fix is the test,
      not the production code.
- [x] 3.6 `pytest hub/tests/ -n 8` and `pytest tests/ -n 4` — both green, counts recorded in the log
      against the baseline in `STATE.json` (updated by N2 to 2089/11 and 362/3). Actual:
      2093/11 and 362/3 (2093 = 2089 + 4 new `test_tasks.py` functions). One unrelated
      `test_agent_trigger.py::test_spawn_failure_broadcasts_run_failed_event` failure under `-n 8`
      did not reproduce standalone or on a second full run — xdist flakiness, not a regression.
- [x] 3.7 `cd hub/ui && npm test`, `npm run lint`, `npx tsc --noEmit` — all clean, counts recorded
      against N2's baseline of 934/934. Actual: 943/943 (934 + 9 new: 4 in `tasksApi.test.tsx`, 4 in
      `specDocumentTasksLink.test.tsx`, 1 new case in `tasksBoardFilter.test.tsx`).
- [x] 3.8 `ruff check hub/ src/` and `black --check` on every file touched — clean (ruff's own
      `--fix` resolved one import-order violation in `tasks.py`; black reformatted `test_tasks.py`
      once, then both re-ran clean).
- [x] 3.9 `npx openspec validate --changes --strict` (this change validates) and
      `npx openspec validate --specs --strict` (the modified `task-lifecycle-governance` delta
      merges cleanly) — both clean, 19/19.

## 4. Driven against the running Hub

Not a test — the real HTTP surface, the real database. Restart the trial Hub onto the implementing
commit first; confirm `/health` reports `ok` before trusting any observation.

- [x] 4.1 Using this session's own N2 verification technique (a directly-minted run credential
      standing in for a live agent process — no Claude/Codex process needed), approve a document
      that declares at least two tasks, archive it, approve one of the two resulting tasks (moving it
      to a terminal status), leave the other at `in_progress`. Confirm `GET /tasks?
      exclude_archived_completed=true` returns the `in_progress` task and omits the approved one;
      confirm `GET /tasks?spec_document_id=<that document>` returns both. Used `rejected` rather than
      `approved` for the terminal task — a single operator-only hop from `pending`
      (`TERMINAL_FOR_BINDING` covers both, and `task_transitions.py`'s own map makes `pending ->
      approved` a multi-hop path not worth the extra round trips for this check). **Caught a real
      restart-hygiene gap the first pass, not a code defect**: the "restart" landed on a stale Hub
      process left running from N2's own session (PID bound to :8010 since 23:08, before tonight's
      commits) — the new `uvicorn` invocation silently failed to bind the already-taken port and
      exited, so the first verification pass exercised **old** code and (correctly, given the old
      code) found `task-a` still present in the excluded set. Diagnosed via `Get-NetTCPConnection`
      (owning PID's `CreationDate` predated this iteration's commits) rather than assumed from the
      failure; killed the stale process, confirmed the port free, started clean, re-ran — 19/19
      checks passed, including both halves of this task.
- [x] 4.2 Confirm `GET /tasks` with neither parameter (the MCP `list_tasks` tool's own call shape)
      still returns both tasks — the default is unchanged. Also checked the actual agent-facing route
      behind that MCP tool, `GET /api/v1/agent-actions/tasks` (`list_shared_tasks`) — this is the D7
      regression's real surface, and a 500 there would have meant the fix didn't hold live, not just
      in the unit test.
- [x] 4.3 Teardown per N2's own convention: delete every row and file this verification created
      (this repo is the trial project's own working directory, so verification writes land as real
      files under `spec/` here — do not commit synthetic test debris), confirm `git status` clean
      afterward. The script's own DB teardown had one wrong column name
      (`task_requirement_references` is keyed by `task_id`, not `requirement_key`) on its first
      attempt, caught immediately by the raised `OperationalError`; since it errored before
      `commit()`, nothing had actually been deleted, so no data was lost — fixed and re-run cleanly.
      The one thing the DB teardown never touches, the on-disk `spec/n2b-live-verify/spec.html` file,
      was removed by hand; `git status` clean afterward. Verification script itself lives in
      `testbed/scratch/` (gitignored by `testbed/.gitignore`), left there rather than deleted —
      it is exactly what that directory is for.

## 5. Human-only verification

- [ ] 5.1 **Does the board read as tidy, not as broken?** With an archived document's completed
      task no longer on the default board, confirm there is no visual gap or empty-looking column
      where it used to be — the board should read as "current," not as "something is missing."
- [ ] 5.2 **Does the document-tasks link read as the same kind of control as the coverage bar's
      per-requirement links?** They sit in the same panel and do the same kind of thing (open the
      board, filtered); confirm they do not visually compete or look like two different features.

## 6. User test guide

**Setup.** Hub running on `:8010`. A project with at least one approved document that declares
tasks, and (from N2) the ability to archive one.

1. **A completed task from an archived document leaves the default board.** Approve a document
   that declares a task, approve the resulting task, then archive the document.
   - *Expect:* the task disappears from the board's default view.
2. **The task still exists.** Open the archived document.
   - *Expect:* a "1 task declared by this document" link (or however many the document declared)
     appears near the coverage detail.
3. **Clicking it shows the task anyway.** Click the link from step 2.
   - *Expect:* the board switches to a filtered view showing the task, with the same "Showing N
     tasks…" banner the coverage bar's own links already produce.
4. **An open task from an archived document is never hidden.** Repeat step 1 with a task left
   `in_progress` rather than approved before archiving.
   - *Expect:* that task stays on the default board throughout.

**Where it would go wrong:** if step 1's task is still visible, task 1.3's exclusion clause is not
wired into the board's own fetch (task 2.3); if step 3 shows zero tasks, the board's fetch is
applying the exclusion even when scoped (design D1's `elif` not implemented, or `TasksBoard.tsx`
not switching the argument based on `activeTaskIds`).
