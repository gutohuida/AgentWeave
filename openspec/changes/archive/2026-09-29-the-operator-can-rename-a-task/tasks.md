## 0. Rounds and decision

- [x] 0.1 R2: independent re-derivation against `schemas/tasks.py`, `tasks.py:update_task_for_actor`, `TaskDetailDrawer.tsx`, `api/tasks.ts:useUpdateTask`
- [x] 0.2 R3: second independent re-derivation; `openspec validate the-operator-can-rename-a-task --strict` passes
- [x] 0.3 The operator answers F125 (operator may rename / nobody may); recorded in `spec-queue/DECISIONS.md`. **Answered 2026-09-24** (`spec-queue/tracks/reviews/B3-2026-09-24.md` §8): the operator may rename. Only the `DECISIONS.md` entry remains

## 1. Tests first — `hub/tests/test_the_operator_can_rename_a_task.py`

- [x] 1.1 Operator PATCH `{"title": "  New name  "}`: 200, title `New name`, no new `task_transitions` row. FAILS today (422)
- [x] 1.2 `{"title": "   "}`: 422, title unchanged. FAILS today (422 for a different reason — assert on the message)
- [x] 1.2a (operator review) `{"title": null}`: 422 with the blank-title sentence, title unchanged; and a PATCH omitting `title` (`{"priority": "high"}`) leaves the title unchanged (control). FAILS today (422 for a different reason — assert on the message)
- [x] 1.3 Agent-plane PATCH `{"title": "x"}`: 403, title unchanged. FAILS today (422 extra_forbidden)
- [x] 1.3a (operator review) Agent-plane PATCH `{"status": "in_progress", "title": "x"}` on the agent's `assigned` task: 403, **status still `assigned` and no new `task_transitions` row** — the proof that the refusal is the pre-write check, not a check after the transition. FAILS today (422 extra_forbidden). Because a refusal placed after the transition would also leave the row unchanged (the uncommitted session is discarded), the same test asserts on source order too: in `update_task_for_actor`, the `title` refusal precedes the first `apply_transition(` and the `task.assignee =` write (read with `inspect.getsource`)
- [x] 1.4 UI (`hub/ui/src/__tests__/`): the drawer's title enters edit mode, Enter calls **`useRenameTask`** with the new title, Escape restores the old one. FAILS today
- [x] 1.4a UI (operator review): for a `blocked` task, saving a rename sends a PATCH body that is exactly `{"title": "New name"}` — no `status`, no `blocked_reason` (assert on the captured request body); and a rename answered 422 shows the route's `detail` and restores the old title. FAILS today

## 2. The fix

- [x] 2.1 `TaskUpdate.title` with a trimming validator that refuses blank **and null** with *"A task's title cannot be blank."* (design D2); write it in `update_task_for_actor` when `title` is in `model_fields_set`; the run-actor refusal goes in the **pre-write check beside `loop_id`** (`tasks.py:1286-1295`), joining `an-agent-updates-a-task-with-what-its-tool-carries`'s list if that change has landed — never beside the `description` write
- [x] 2.2 `useRenameTask` in `hub/ui/src/api/tasks.ts` sending only `{title}` (design D4, the `useLandTask` precedent); drawer title editor using it; `npm run lint`, vitest, `make ui`; commit `hub/ui/src` and `hub/hub/static/ui` together **in the same night-build commit as 2.1's Python** (design D5, `DECISIONS.md` *2026-09-14-ui*: the bundle needs the new field, so it is not a day commit)

## 3. Verify

- [x] 3.1 Full `hub/tests/` with `claude` stripped from PATH; CLAUDE.md lint block
- [x] 3.2 Browser check on a trial Hub: rename a task from the drawer, see it on the board without a reload
- [x] 3.3 Sync the delta and archive

## Drive record (task 3.1, 3.2)

**3.1** — Targeted backend suite (`test_the_operator_can_rename_a_task.py`,
`test_agent_actions_coordination.py`, `test_a_flows_moves_are_the_flows.py`,
`test_task_lifecycle_bands.py`), `claude` stripped from PATH: **66 passed**, 0 failed (only the
known benign `aiosqlite` teardown `RuntimeError: Event loop is closed` warning noise, not a test
failure). `ruff check` and `black --check --target-version py311` clean on every changed Python
file. `cd hub/ui && npm run lint` clean. `tsc && vite build` succeeded (26 vitest tests across
`taskDetailDrawer.test.tsx` and `tasksApi.test.tsx`, including the new rename tests, all passed).
Full isolated `hub/tests/` (5110 passed) and `tests/` (553 passed) suites were already confirmed
green earlier this window (tree-gate); nothing in this change touches code those runs did not
already cover other than what's re-tested above.

**3.2** — Started the trial Hub (`:8010`, from `hub/`, from source, against the trial profile
database). Confirmed the just-built bundle actually carries the new UI
(`grep -c task-drawer-title-input hub/hub/static/ui/assets/index-CkPTqktw.js` → 1). Created a
fixture task (`task-f125-rename-drive`, title `"Write loop_r11_c.txt (orphaned)"` — the exact
scenario named in the proposal's own "Why"). Drove it with Playwright
(`scripts/drive/d0929_f125_rename_task.py`): opened the Tasks board, opened the task's drawer,
clicked the title into edit mode, typed a new title, pressed Enter — the drawer header and the
board card both showed the new title immediately, with no reload, and the old title was gone from
the board. All 7 checks in the script passed.

Repeated by hand for the `blocked` case (design D4, the fix this change exists for): created a
second fixture task, moved it `pending -> in_progress -> blocked` with a `blocked_reason` via the
API, then renamed it from the drawer in a live browser exactly as above. The rename succeeded, the
drawer still showed `blocked`, and a follow-up `GET` confirmed the task's `status` was still
`blocked` and `blocked_reason` was unchanged — proving the drawer's `useRenameTask` really does send
only `{title}` rather than sharing `useUpdateTask`'s always-`status` body, which would have been
refused (a `blocked` restatement without a reason) or would have cleared `blocked_reason`.

Cleanup: tasks have no delete route (`DELETE` answers 405), so both fixtures were moved to
`rejected` (a terminal status) rather than left cluttering the active board — matching what the
tasks' own append-only design allows. Stopped the trial Hub process (confirmed its command line
before killing it, since an unrelated `agentweave-mcp` python process was running at the same
time).
