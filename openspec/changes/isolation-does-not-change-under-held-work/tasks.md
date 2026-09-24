## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1: explore and propose (2026-09-24, bundle B5)
- [x] 0.2 R2: independent re-derivation against `agents.py` (`patch_agent`, `register_agent`, `_merge_patch`), `worktrees.py` (`is_writing_agent`, `resolve_turn_workspace`, `snapshot_worktree`), `api/v1/worktrees.py` (`get_agent_workspace`, `_task_checkouts`), `run_liveness.py`, and any other writer of `Agent.config` (grep `\.config =`). Decide assigned-vs-provisioned; answer design Open Question 1's filing
- [x] 0.3 R3: second independent re-derivation; `openspec validate isolation-does-not-change-under-held-work --strict` passes
- [ ] 0.4 The operator answers D12's first question (recommended: refuse under held work) and approves (APPROVALS.md); the 2026-09-24 review's fixes, with decision 4 (guard `/session/sync`), are applied — design.md "Operator review, 2026-09-24"

## 1. Tests first — each fails on today's code unless marked as a control

New file `hub/tests/test_isolation_does_not_change_under_held_work.py`.

- [ ] 1.1 (D1) Agent `beta` assigned an `in_progress` task. `PATCH /agents/beta {"config": {"read_only": true}}` → **409** `isolation_change_under_held_work`, the task id in `held`; `GET /agents/beta` config unchanged. FAILS today (200)
- [ ] 1.2 (D1) The same with `{"config": null}` on an agent stored `read_only: true` → 409 (clearing is a change). FAILS today
- [ ] 1.3 (D1) Agent with a run registered in `run_liveness.active_ptys` and no task: flip → 409 naming the run. FAILS today
- [ ] 1.4 (D1) `POST /agents/register` for an existing self-registered agent holding a task, with `config: {"read_only": true}` → 409; `contact_mode`, `mcp_endpoint` unchanged too. FAILS today
- [ ] 1.5 (D1) Refused whole: a PATCH carrying `description` and the flip → 409, description unchanged. FAILS today
- [ ] 1.5a (D1) Turning isolation **on**: agent stored `read_only: true`, assigned an `in_progress` task, no task checkout on disk. `PATCH {"config": {"read_only": false}}` → 409. FAILS today; FAILS if the rule is narrowed to provisioned checkouts
- [ ] 1.6 Control: the same flip on an idle agent with only `approved`/`rejected` tasks → 200. Passes before and after
- [ ] 1.7 Control: `{"config": {"model": "…"}}` on a busy agent → 200; `{"config": {"read_only": true}}` on an agent already read-only and busy → 200. Pass before and after
- [ ] 1.9 (D1, effective config) Busy agent (in-progress task) whose synced session entry says `read_only: false` (seeded by `POST /session/sync` before the task). `PATCH /agents/{name} {"config": {"read_only": true}}` → **200**, and `GET /worktrees/{name}` still reports it isolated. Passes today; FAILS against a helper that compares `Agent.config` alone (it would answer 409 for a change that moves nothing)
- [ ] 1.10 (D1, effective config) Busy agent whose synced session entry says `read_only: true` and whose `Agent.config` is `{}`. `PATCH {"config": {"read_only": false}}` → **200**; `GET /worktrees/{name}` still reports it sharing. Passes today; FAILS against the `Agent.config`-only helper
- [ ] 1.11 (D1, third door) Agent `beta` synced without `read_only`, then assigned an `in_progress` task. `POST /session/sync` with `beta: {"read_only": true}` and a second, previously synced agent `gamma` omitted → **409** `isolation_change_under_held_work` naming `beta` and the task; `GET /session/sync` returns the old data, `gamma` still exists, and no `worktree_released` event was written. FAILS today (200, and `gamma` deleted)
- [ ] 1.12 (D1, third door) Agent stored `read_only: true` via its old session entry, busy with a task and with a run registered in `run_liveness.active_ptys`: `POST /session/sync` whose `beta` entry omits `read_only` (so the effective config becomes isolated) → **409** naming the run and the task. FAILS today
- [ ] 1.13 Control: re-sending the current payload for a busy agent, and a sync that adds `read_only: true` to a busy agent whose `Agent.config` already has it, both → 200. Pass before and after
- [ ] 1.14 Control: every suite that calls `/session/sync` to seed a roster (`grep -l "session/sync" hub/tests/*.py`, including `test_session_sync.py`, `test_agent_trigger.py`, `test_project_scoped_runtime.py`) unchanged — seeding holds no work
- [ ] 1.8 Controls: `test_a_request_means_what_it_says.py` (F243's merge-patch legs) and `test_worktrees.py`, `test_task_worktrees.py`, `test_turn_workspace.py` unchanged

## 2. The fix

- [ ] 2.1 `launchability.effective_agent_config` (the one merge rule; `get_agent_config` switches to it, `launchability.py:485-486`) and `launchability.isolation_change_refusal`; correct `get_agent_config`'s docstring (`:453-456`), which states the opposite precedence to the code
- [ ] 2.1a Call sites: `patch_agent` and `register_agent` (`agents.py:2648-2659`, `:2300-2308`), each before it mutates the row
- [ ] 2.1b Call site: `sync_session` (`api/v1/session_sync.py:46-75`), for each agent in the new payload that has a row, before `row.data = body.data` (`:67`)
- [ ] 2.2 `AgentSettingsPage.tsx:290-294`: the comment states the rule and names this change (comment only)
- [ ] 2.3 Full `hub/tests/`; ruff; black `--target-version py311`

## 3. Drive

- [ ] 3.1 Trial Hub: F242's leg-8 sequence (`t_sweep_row15_worktrees.py`) — record the 409 body; confirm `git status` in the project root is clean after the turn
