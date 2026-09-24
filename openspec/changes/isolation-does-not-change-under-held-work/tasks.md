## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1: explore and propose (2026-09-24, bundle B5)
- [x] 0.2 R2: independent re-derivation against `agents.py` (`patch_agent`, `register_agent`, `_merge_patch`), `worktrees.py` (`is_writing_agent`, `resolve_turn_workspace`, `snapshot_worktree`), `api/v1/worktrees.py` (`get_agent_workspace`, `_task_checkouts`), `run_liveness.py`, and any other writer of `Agent.config` (grep `\.config =`). Decide assigned-vs-provisioned; answer design Open Question 1's filing
- [x] 0.3 R3: second independent re-derivation; `openspec validate isolation-does-not-change-under-held-work --strict` passes
- [ ] 0.4 The operator answers D12's first question (recommended: refuse under held work) and approves

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
- [ ] 1.8 Controls: `test_a_request_means_what_it_says.py` (F243's merge-patch legs) and `test_worktrees.py`, `test_task_worktrees.py`, `test_turn_workspace.py` unchanged

## 2. The fix

- [ ] 2.1 The helper and its two call sites in `agents.py`
- [ ] 2.2 `AgentSettingsPage.tsx:290-294`: the comment states the rule and names this change (comment only)
- [ ] 2.3 Full `hub/tests/`; ruff; black `--target-version py311`

## 3. Drive

- [ ] 3.1 Trial Hub: F242's leg-8 sequence (`t_sweep_row15_worktrees.py`) — record the 409 body; confirm `git status` in the project root is clean after the turn
