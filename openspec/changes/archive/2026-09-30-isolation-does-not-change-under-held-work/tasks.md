## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1: explore and propose (2026-09-24, bundle B5)
- [x] 0.2 R2: independent re-derivation against `agents.py` (`patch_agent`, `register_agent`, `_merge_patch`), `worktrees.py` (`is_writing_agent`, `resolve_turn_workspace`, `snapshot_worktree`), `api/v1/worktrees.py` (`get_agent_workspace`, `_task_checkouts`), `run_liveness.py`, and any other writer of `Agent.config` (grep `\.config =`). Decide assigned-vs-provisioned; answer design Open Question 1's filing
- [x] 0.3 R3: second independent re-derivation; `openspec validate isolation-does-not-change-under-held-work --strict` passes
- [x] 0.4 The operator answers D12's first question (recommended: refuse under held work) and approves (APPROVALS.md); the 2026-09-24 review's fixes, with decision 4 (guard `/session/sync`), are applied — design.md "Operator review, 2026-09-24"

- [x] 0.5 Verification round at IMPL, 2026-09-30: approved in APPROVALS 2026-09-27 (B5, F242); design's round log records the register door gone and the merge rule reused as `launchability.agent_config`.

## 1. Tests first — each fails on today's code unless marked as a control

New file `hub/tests/test_isolation_does_not_change_under_held_work.py`.

- [x] 1.1 (D1) Agent `beta` assigned an `in_progress` task. `PATCH /agents/beta {"config": {"read_only": true}}` → **409** `isolation_change_under_held_work`, the task id in `held`; `GET /agents/beta` config unchanged. FAILS today (200)
  Done 2026-09-30: failed before (200), passes after; the stored config read from the row (there is no `GET /agents/{name}`).
- [x] 1.2 (D1) The same with `{"config": null}` on an agent stored `read_only: true` → 409 (clearing is a change). FAILS today
  Done 2026-09-30: failed before, passes after.
- [x] 1.3 (D1) Agent with a run registered in `run_liveness.active_ptys` and no task: flip → 409 naming the run. FAILS today
  Done 2026-09-30: failed before, passes after.
- [x] 1.4 (D1) `POST /agents/register` for an existing self-registered agent holding a task, with `config: {"read_only": true}` → 409; `contact_mode`, `mcp_endpoint` unchanged too. FAILS today
  **Moot as of 2026-09-30:** `agents-no-longer-register-themselves` landed first and deleted the route (design *Cross-bundle*). Drop this task when building.
  Dropped 2026-09-30, not built: the route no longer exists (`agents-no-longer-register-themselves`, archived today).
- [x] 1.5 (D1) Refused whole: a PATCH carrying `description` and the flip → 409, description unchanged. FAILS today
  Done 2026-09-30: failed before, passes after.
- [x] 1.5a (D1) Turning isolation **on**: agent stored `read_only: true`, assigned an `in_progress` task, no task checkout on disk. `PATCH {"config": {"read_only": false}}` → 409. FAILS today; FAILS if the rule is narrowed to provisioned checkouts
  Done 2026-09-30: failed before, passes after (an `assigned` task, no checkout on disk).
- [x] 1.6 Control: the same flip on an idle agent with only `approved`/`rejected` tasks → 200. Passes before and after
  Done 2026-09-30: a control, passes before and after.
- [x] 1.7 Control: `{"config": {"model": "…"}}` on a busy agent → 200; `{"config": {"read_only": true}}` on an agent already read-only and busy → 200. Pass before and after
  Done 2026-09-30: controls, pass before and after.
- [x] 1.9 (D1, effective config; moved to `/session/sync`, design round log at IMPL) Busy agent, `Agent.config` `{"read_only": true}`, synced entry `{"read_only": false}` (isolated). `POST /session/sync` whose entry omits `read_only` (sharing) → **409**. FAILS today; also against an `Agent.config`-only helper (it sees no change)
  Done 2026-09-30 (`test_the_sync_door_reads_the_effective_config`): failed before; mutation: comparing `Agent.config` alone at the sync door fails it (and the two other sync tests).
- [x] 1.10 (D1, effective config; moved to `/session/sync`) Busy agent, `Agent.config` `{}`, synced entry `{"read_only": true}`. A sync keeping `read_only: true` and adding another key → **200**, still sharing. A control: passes before and after
  Done 2026-09-30 (`test_a_sync_that_moves_nothing_is_accepted`): a control.
- [x] 1.11 (D1, third door) Agent `beta` synced without `read_only`, then assigned an `in_progress` task. `POST /session/sync` with `beta: {"read_only": true}` and a second, previously synced agent `gamma` omitted → **409** `isolation_change_under_held_work` naming `beta` and the task; `GET /session/sync` returns the old data, `gamma` still exists, and no `worktree_released` event was written. FAILS today (200, and `gamma` deleted)
  Done 2026-09-30: failed before (200, `gamma` deleted); after, the session data, `gamma`'s row and the absence of `worktree_released` are asserted.
- [x] 1.12 (D1, third door) Agent stored `read_only: true` via its old session entry, busy with a task and with a run registered in `run_liveness.active_ptys`: `POST /session/sync` whose `beta` entry omits `read_only` (so the effective config becomes isolated) → **409** naming the run and the task. FAILS today
  Done 2026-09-30: failed before, passes after, naming the run and the task.
- [x] 1.13 Control: re-sending the current payload for a busy agent, and a sync that adds `read_only: true` to a busy agent whose `Agent.config` already has it, both → 200. Pass before and after
  Done 2026-09-30: controls, in `test_a_sync_that_moves_nothing_is_accepted` (same payload, and one adding a key).
- [x] 1.14 Control: every suite that calls `/session/sync` to seed a roster (`grep -l "session/sync" hub/tests/*.py`, including `test_session_sync.py`, `test_agent_trigger.py`, `test_project_scoped_runtime.py`) unchanged — seeding holds no work
  Done 2026-09-30: the full suite (2.3) ran every `/session/sync` seeding suite unchanged: 5502 passed, 87 skipped, 0 failed.
- [x] 1.8 Controls: `test_a_request_means_what_it_says.py` (F243's merge-patch legs) and `test_worktrees.py`, `test_task_worktrees.py`, `test_turn_workspace.py` unchanged
  Done 2026-09-30: the full suite (2.3) ran them unchanged: 5502 passed, 87 skipped, 0 failed.

## 2. The fix

- [x] 2.1 `launchability.effective_agent_config` (the one merge rule; `get_agent_config` switches to it, `launchability.py:485-486`) and `launchability.isolation_change_refusal`; correct `get_agent_config`'s docstring (`:453-456`), which states the opposite precedence to the code
  Done 2026-09-30: `isolation_change_refusal` beside `get_agent_config`, over `launchability.agent_config` (design round log at IMPL: the merge rule already existed under that name); `get_agent_config`'s docstring precedence corrected.
- [x] 2.1a Call sites: `patch_agent` and `register_agent` (`agents.py:2648-2659`, `:2300-2308`), each before it mutates the row
  **2026-09-30:** `register_agent` no longer exists (`agents-no-longer-register-themselves`); only `patch_agent` remains, and its line numbers moved.
  Done 2026-09-30 (`patch_agent` only).
- [x] 2.1b Call site: `sync_session` (`api/v1/session_sync.py:46-75`), for each agent in the new payload that has a row, before `row.data = body.data` (`:67`)
  Done 2026-09-30.
- [x] 2.2 `AgentSettingsPage.tsx:290-294`: the comment states the rule and names this change (comment only)
  Done 2026-09-30. The bundle was rebuilt: byte-identical, only `ui-build-stamp.json` changed (the stamp fingerprints the source, so a comment moves it).
- [x] 2.3 Full `hub/tests/`; ruff; black `--target-version py311`
  Done 2026-09-30: `py -3.11 -m pytest hub/tests/ -q -n 8` with `claude` off PATH: 5502 passed, 87 skipped, 0 failed, 12:36. ruff and black clean.

## 3. Drive

- [x] 3.1 Trial Hub: F242's leg-8 sequence (`t_sweep_row15_worktrees.py`) — record the 409 body; confirm `git status` in the project root is clean after the turn
  Done 2026-09-30 at API level on a throwaway Hub (`:8037`, profile `drive0930g`, project `proj-6e09ba1f3cbd`), not `:8010`, with no model turn: the flip under an `in_progress` task answered 409 `{"code": "isolation_change_under_held_work", "message": "beta cannot move to the shared checkout while it holds work, because the work would be left where its next turn no longer looks: unfinished tasks (task-862dd9a00945); finish, reassign or reject them.", "held": {"runs": [], "tasks": ["task-862dd9a00945"]}}`; `GET /worktrees/beta` still isolated; after rejecting the task the same flip answered 200; `git status` in the project root clean. F242's leg-8 turn itself was not re-run: the refusal is what stops it now.
