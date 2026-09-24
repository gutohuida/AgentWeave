## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1: explore and propose (2026-09-24, bundle B5)
- [x] 0.2 R2: independent re-derivation against `requirement_evidence.py` (`read_footprint`, `_branch_at`, `_take_footprint`, `footprint_root`, `capture_footprint`, `restamp_run_footprints`, `detect_drift`), `task_integration.py` (`_targets`, `integration_targets`, `merge_targets`), `worktrees.py` (review and task checkouts, `release_task_worktree`), `task_transition_service.release_task_workspace`. In particular: re-measure the `(HEAD detached at …)` line; decide D3's seam; count drift candidates D2 adds on an existing fixture; answer design Open Question 1
- [ ] 0.3 R3: second independent re-derivation; `openspec validate a-footprint-names-the-line-of-work-its-commit-is-on --strict` passes
- [ ] 0.4 The operator answers D12's third question (recommended: one spelling `""`, resolved, with a data migration) and approves

## 1. Tests first — each fails on today's code unless marked as a control

New file `hub/tests/test_a_footprint_names_its_line_of_work.py`, reusing the git helpers and `conflicted`/`resolve_on_branch` from `test_conflict_refusal_names_what_clears_it.py`.

- [ ] 1.1 (D2, bug) Unit: in a repo whose checkout is detached at a non-tip commit X, `line_of_work(root, X)` returns the containing branch, never a string starting with `(`. And on today's code, `_branch_at(root, X)` returns `(HEAD detached at …)` — record that it FAILS today's expectation
- [ ] 1.2 (D2, F165) Flip `test_an_operator_naming_the_resolved_sha_does_not_supersede` (`:347-391`): the footprint's branch is `agentweave/builder`; `integration_targets` is `[resolved]`; approval **succeeds** and merges. Rename it to say what it now asserts; comment names this change. FAILS today
- [ ] 1.3 (D1/D2, addendum) A reviewer-shaped footprint: record agent evidence from a checkout detached at the task branch's tip → `footprint.branch == <task branch>`. Detached at a commit no single branch contains → `""`, never `"HEAD"`. FAILS today (`"HEAD"`)
- [ ] 1.4 (D1) `restamp_run_footprints` on a detached checkout writes the resolved branch, not `"HEAD"`. FAILS today
- [ ] 1.5 (D4) Two accepted footprints on one task branch: author at D (observed first), reviewer at D's parent C (observed later). `merge_targets(session, task, root)` → `[D]`, while `integration_targets(session, task)` still answers `[C]` (its observation order, unchanged). Must be staged after D2 (or with branches set directly on the rows). FAILS on today's reduction when both rows carry the task branch
- [ ] 1.6 (D4) Control: a rebase — two commits neither containing the other on one branch → the later observation wins. Passes before and after
- [ ] 1.7 (D3, F166) Stage as `test_evidence_footprint_root.py::test_a_released_workspace_falls_back_rather_than_naming_a_missing_directory` (`:982-1013`) does, **plus** `Run.task_id` bound to the released task and a commit on its task branch: the footprint names `agentweave/task/<id>` and that branch's tip — not the agent's own checkout's commit (what the unbound test pins today) and not `main`. FAILS today
- [ ] 1.7a (D2) `test_a_reviewers_evidence_is_footprinted_at_the_tree_it_reviewed` (`test_evidence_footprint_root.py:944-979`) gains `assert footprint.branch == "agentweave/task/task-dd44ee55ff66"` (the review checkout is detached at that branch's tip). FAILS today (`"HEAD"`)
- [ ] 1.8a (D3) Control: `test_a_released_workspace_falls_back_rather_than_naming_a_missing_directory` itself (unbound run) still answers the agent's own checkout; its docstring gains a line saying a task-bound run is D3's case
- [ ] 1.8 (D3) Control: `test_an_agent_whose_workspace_is_gone_does_not_supersede` (`:474-514`) — a run with **no** task and no recorded directory — still falls back as today. It stays a non-guarantee; update its docstring to say why it is not D3's case
- [ ] 1.9 (D1) Migration test: a row with `branch='HEAD'` reads `''` after upgrade; a real branch name is untouched
- [ ] 1.10 Controls: `test_conflict_refusal_names_what_clears_it.py` (all but 1.2's flipped test), `test_requirement_evidence.py`, `test_task_integration.py`, `test_requirement_drift.py`, `test_task_integration_retry.py`, `test_evidence_footprint_root.py` (all 30-odd tests; it pins which root is read) — run before and after, record counts

## 2. The fix

- [ ] 2.1 (D2) `line_of_work`; `_branch_at` removed (its one caller moves)
- [ ] 2.2 (D1/D2) `read_footprint` and `restamp_run_footprints` call it; callers pass the task branch
- [ ] 2.3 (D3) `read_evidence_footprint`; `_take_footprint` and `capture_footprint` call it
- [ ] 2.4 (D4) `_accepted_targets` shared; the ancestry reduction in `merge_targets`' governed path; `integration_targets` unchanged. The preview's governed path (`tasks.py:1122`) calls `merge_targets` with the resolved root, wrapped as its ungoverned path is (skip if the F141 change already did)
- [ ] 1.11 (D4) Preview control: with 1.5's rows, `GET /tasks/{id}/integration-preview` lists `D` only — the commit approval would merge. FAILS today (lists `C`)
- [ ] 2.5 (D1) The migration at the next free revision; bump head assertions in `test_migrations.py` and `test_project_persistence.py`
- [ ] 2.6 Full `hub/tests/`; ruff; black `--target-version py311`

## 3. Drive

- [ ] 3.1 Trial Hub: F155's reproduction (`scripts/drive/t_row17_integration.py` shape), then the operator records evidence naming the resolved sha after the branch has moved on; approval now merges. Record the before/after bodies
