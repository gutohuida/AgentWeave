## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1: explore and propose (2026-09-24, bundle B5)
- [x] 0.2 R2: independent re-derivation against `tasks.py` (`task_integration_preview`), `requirement_gate.py` (`_merge_situation`, `_check_mergeable`), `task_integration.py` (`merge_targets`, `would_conflict`, `_git`), `TaskDetailDrawer.tsx`, `api/tasks.ts`. Decide D1's sharing; trace the approval route's answer when the gate's own `would_conflict` raises; answer Open Question 1
- [ ] 0.3 R3: second independent re-derivation; `openspec validate the-approval-preview-asks-the-gates-merge-question --strict` passes
- [ ] 0.4 The operator answers D12's second question (recommended: not persisted; the preview asks live) and approves

## 1. Tests first — each fails on today's code unless marked as a control

Add to `hub/tests/test_conflict_refusal_names_what_clears_it.py`'s neighbourhood a new file `hub/tests/test_the_preview_asks_the_merge_question.py`, reusing `conflicted`, `approve`, `git`.

- [ ] 1.1 (D1) The `conflicted` fixture: `GET /tasks/{id}/integration-preview` → `conflicts == [{"commit_sha": judged, "source_branch": "agentweave/builder", "paths": ["shared.txt"]}]`, reason names `shared.txt` and `judged[:12]`; `main`'s HEAD unchanged; `git status` clean. FAILS today (no `conflicts` key)
- [ ] 1.2 (D1) Then approve → 409; preview again → identical `conflicts` to the refusal's `unmergeable` paths and commit. FAILS today
- [ ] 1.3 (D1) After `resolve_on_branch` and accepting evidence recorded from the branch (as `test_evidence_recorded_from_the_branch_supersedes_and_clears_it`) → `conflicts == []`, reason says it merges cleanly. FAILS today
- [ ] 1.4 Control: `test_dashboard_truth.py:470-500` (fake commit, no repository) — `conflicts` is `null` and the F156 reason is byte-identical. Passes before (modulo the new key's absence) and after
- [ ] 1.5 (D1) `would_conflict` patched to raise → 200, `conflicts: null`, the F156 reason. FAILS today (no `conflicts` key); `_git` raises `TimeoutExpired`/`OSError`, so this is the case that must not 500
- [ ] 1.5a (D1) `task_integration.branch_exists` patched to raise `subprocess.TimeoutExpired` → 200, `conflicts: null`, targets still listed. FAILS if only the probe loop is wrapped
- [ ] 1.6 (D2, UI) `taskApprovalWrites.test.tsx`: a preview with non-empty `conflicts` renders each path and the refusal tone; with `conflicts: []` and `null`, the existing renders are unchanged. FAILS today on the first

## 2. The fix

- [ ] 2.1 (D1) Rename `requirement_gate._merge_situation` → `merge_situation` (its call site at `:618` and the three tests that name it); the preview on it, wrapped with the probe; its docstring
- [ ] 2.2 (D2) Type and drawer; `npm run lint`, `npm test`, build, `py -3.11 scripts/refresh_ui_bundle.py`; commit source and bundle together
- [ ] 2.3 Full `hub/tests/`; ruff; black `--target-version py311`

## 3. Drive

- [ ] 3.1 Trial Hub: `scripts/drive/t_f156_preview_promises_the_merge.py`'s conflicting lane — the preview now names the conflict before approve is pressed. Record the body; time the call on this repository (Open Question 1)
