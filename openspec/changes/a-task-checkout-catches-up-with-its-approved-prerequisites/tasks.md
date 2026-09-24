## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1 (bundle B1, 2026-09-24): proposal, design (Q-F158 with (B) recommended), delta, tasks, test guide; F158 re-verified at `404c7d5`
- [x] 0.2 R2 (2026-09-24): done by reading (shape 1 confirmed from `takes_own_checkout` and `_prerequisite_commits`' docstring; no throwaway test) — design.md round log. Original brief: re-derive against `hub/hub/worktrees.py:459-625` and `:776-900`, `hub/hub/task_workspace.py`, `hub/hub/api/v1/agent_trigger.py:960-1030`, `hub/hub/turn_scheduler.py:506-560`, and the delta. Confirm by a throwaway test that a turn bound to a `pending` task with an unapproved prerequisite really cuts the branch today (F158's shape 1 was read, not driven), and that `takes_own_checkout` does not exclude it
- [x] 0.3 R3 (2026-09-24): done — see design.md round log; `openspec validate a-task-checkout-catches-up-with-its-approved-prerequisites --strict` passes
- [ ] 0.4 The operator answers Q-F158, including D2 vs D2' for a conflict on an existing branch, and approves (DECISIONS.md, APPROVALS.md)

## 1. Tests first — each fails on today's code unless marked as a control

New file `hub/tests/test_a_task_checkout_catches_up.py`, on a real temporary repository (as `test_task_turn_collision.py`'s `_init_repo` does).

- [ ] 1.1 (D1, shape 1) Task B depends on A. A turn bound to B while A is `in_progress` cuts B's branch (assert: A's commit is not an ancestor). A is approved (with a commit that did not reach the main branch). The next turn bound to B: A's commit is an ancestor of B's `HEAD`, and B's own earlier commit is still there. FAILS today
- [ ] 1.2 (D1, shape 2) B worked first; then `POST /tasks/B/dependencies` names approved A; the next turn bound to B has A's commit. FAILS today
- [ ] 1.3 (D2) As 1.1, with B's own commit conflicting with A's. The turn is refused naming A; B's branch tip and working tree are byte-identical to before (hash both). FAILS today only in that the turn is not refused (today it starts, silently without A)
- [ ] 1.4 (D2) As 1.1, with an uncommitted file in B's checkout: refused naming A, the file untouched. FAILS today
- [ ] 1.5 (D3) Control: a prerequisite `in_progress` with accepted evidence does not reach an **existing** checkout; a **new** checkout is still seeded from it (F159's rule, `test_*` that pins it today keeps passing)
- [ ] 1.6 Control: a task with no prerequisites — `ensure_task_worktree` runs no merge and no `merge-base` (patch `_run_git` and count)

## 2. Implementation

- [ ] 2.1 (D1) `TurnWorkspace.approved`; its computation in `resolve_turn_workspace_inputs`; threaded through `resolve_turn_workspace`
- [ ] 2.2 (D1, D2) `worktrees._catch_up_prerequisites`, called on both existing-branch paths of `ensure_task_worktree`; update its docstring (*"merged only when the branch is created"*) and `_prerequisite_commits`' (*"Resolved on every task-bound turn even though…"*)
- [ ] 2.3 Run the new file and every test touching `ensure_task_worktree`, `_prerequisite_commits` or `resolve_turn_workspace` **with `claude` stripped from PATH**; the CLAUDE.md lint block; the full `hub/tests/`
