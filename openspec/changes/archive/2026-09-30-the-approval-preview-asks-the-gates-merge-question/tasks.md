## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1: explore and propose (2026-09-24, bundle B5)
- [x] 0.2 R2: independent re-derivation against `tasks.py` (`task_integration_preview`), `requirement_gate.py` (`_merge_situation`, `_check_mergeable`), `task_integration.py` (`merge_targets`, `would_conflict`, `_git`), `TaskDetailDrawer.tsx`, `api/tasks.ts`. Decide D1's sharing; trace the approval route's answer when the gate's own `would_conflict` raises; answer Open Question 1
- [x] 0.3 R3: second independent re-derivation; `openspec validate the-approval-preview-asks-the-gates-merge-question --strict` passes
- [x] 0.4 The operator answers D12's second question (recommended: not persisted; the preview asks live) and approves (APPROVALS.md); the 2026-09-24 review's fixes are applied — design.md "Operator review, 2026-09-24"

- [x] 0.5 Verification round at IMPL, 2026-09-30: approved in APPROVALS 2026-09-27 (B5, F141); design's round log records the footprint change's landing and the gate's `to_thread` calls. Nothing else moved.

## 1. Tests first — each fails on today's code unless marked as a control

Add to `hub/tests/test_conflict_refusal_names_what_clears_it.py`'s neighbourhood a new file `hub/tests/test_the_preview_asks_the_merge_question.py`, reusing `conflicted`, `approve`, `git`.

- [x] 1.1 (D1) The `conflicted` fixture: `GET /tasks/{id}/integration-preview` → `conflicts == [{"commit_sha": judged, "source_branch": "agentweave/builder", "paths": ["shared.txt"]}]`, reason names `shared.txt` and `judged[:12]`; `main`'s HEAD unchanged; `git status` clean. FAILS today (no `conflicts` key)
  Done 2026-09-30 (`test_the_preview_names_the_conflict_before_approval`): failed before (no `conflicts`); `main` unchanged and `git status` unchanged by the call (the fixture's untracked `spec/` is there before and after).
- [x] 1.2 (D1) Then approve → 409; preview again → identical `conflicts` to the refusal's `unmergeable` paths and commit. FAILS today
  Done 2026-09-30: failed before, passes after.
- [x] 1.3 (D1) After `resolve_on_branch` and accepting evidence recorded from the branch (as `test_evidence_recorded_from_the_branch_supersedes_and_clears_it`) → `conflicts == []`, reason says it merges cleanly. FAILS today
  Done 2026-09-30: failed before, passes after.
- [x] 1.4 Control: `test_dashboard_truth.py:470-500` (fake commit, no repository) — `conflicts` is `null` and the F156 reason is byte-identical. Passes before (modulo the new key's absence) and after
  Done 2026-09-30: `test_dashboard_truth.py::test_the_preview_names_the_commit_and_both_branches` gains `body.get("conflicts") is None`; passes before and after, reason byte-identical.
- [x] 1.5 (D1) `would_conflict` patched to raise → 200, `conflicts: null`, the F156 reason. FAILS today (no `conflicts` key); `_git` raises `TimeoutExpired`/`OSError`, so this is the case that must not 500
  Done 2026-09-30: failed before (no key), passes after.
- [x] 1.5a (D1) `task_integration.branch_exists` patched to raise `subprocess.TimeoutExpired` → 200, `conflicts: null`, targets still listed. FAILS if only the probe loop is wrapped
  Done 2026-09-30 (`test_a_precondition_that_raises_is_an_answer`): failed before, passes after.
- [x] 1.5b (D1 step 2, operator review) The ungoverned fixture of `test_loop_lands_its_work.py:582-601` (`test_the_preview_names_the_branch_tip_for_an_evidence_free_loop_task`: a loop task with a commit on its own branch, main branch `main`) with `task_integration._git` patched to raise `subprocess.TimeoutExpired` → **200**, `conflicts: null`, `targets == []`, `will_attempt_merge is False`, `reason == task_integration.GIT_UNANSWERED` (and **not** `NO_TASK_BRANCH`); and the patched `_git` is called **once** (no repeat after the first failure). FAILS today: `merge_targets` at `tasks.py:1131` sits outside the wrap at `:1126-1129`, so the route raises (a bare 500 through the app)
  Done 2026-09-30: failed before (the `TimeoutExpired` escaped the route: today's 500), passes after, `_git` called once.
- [x] 1.5c (D1 step 2) Same ungoverned fixture with `requirement_gate.merge_situation` patched to return `None` and `task_integration.task_branch_tip` patched to raise `OSError` → 200, `reason == GIT_UNANSWERED`. Pins the second wrap on its own (1.5b's first failure is caught by step 1's wrap). FAILS today (raises)
  Done 2026-09-30: failed before (no `merge_situation`), passes after.
- [x] 1.7 Control (D1 step 3, operator review): `test_loop_lands_its_work.py:604-622` (`test_the_preview_is_unchanged_where_evidence_governs`: real repository, main branch set, governed task, no accepted evidence — so `merge_situation` is present with `will_merge == []`) still answers `reason == NOTHING_TO_MERGE`, `targets == []`, and now `conflicts == []` with no "merges cleanly" in the reason. Passes today; FAILS under R2's D1 (sentence chosen from `conflicts` alone)
  Done 2026-09-30 (`test_nothing_to_merge_is_never_read_as_merges_cleanly`, in the new file rather than editing the loop test).
- [x] 1.8 (D1 step 3) Two targets that merge cleanly (two accepted evidence rows naming commits on two agent branches, each clean against `main`) → `conflicts == []` and `reason == "approval will merge 2 commits into main; it merges cleanly as of now"`. FAILS today (reason is the F156 hedge), and fails under a hard-coded "one commit"
  Done 2026-09-30: two accepted evidence rows, on `agentweave/builder` and `agentweave/other`; failed before (the F156 hedge), passes after.
- [x] 1.6 (D2, UI) `taskApprovalWrites.test.tsx`: a preview with non-empty `conflicts` renders each path and the refusal tone; with `conflicts: []` and `null`, the existing renders are unchanged. FAILS today on the first
  Done 2026-09-30: failed before on the conflict case; `[]` and `null` keep the amber note.

## 2. The fix

- [x] 2.1 (D1) Rename `requirement_gate._merge_situation` → `merge_situation` (its call site at `:618` and the three tests that name it); the preview on it, wrapped with the probe; its docstring
  Done 2026-09-30: renamed in `requirement_gate.py` (definition, call site, two docstrings), `task_integration.py`'s docstring and the two test files' docstrings; the preview calls it and probes through `asyncio.to_thread`, as the gate now does.
- [x] 2.1a (D1 steps 2-5) Add `task_integration.GIT_UNANSWERED`; wrap the ungoverned listing (workspace resolution **and** `merge_targets` in one `try`), skip it after step 1 caught; choose the reason in today's order with the real count. Do **not** wrap inside `merge_situation` — the gate's git failures are F424's, and its repair refuses (design, "What the route returns")
  Done 2026-09-30.
- [x] 2.2 (D2) Type and drawer; `npm run lint`, `npm test`, build, `py -3.11 scripts/refresh_ui_bundle.py`; commit source and bundle together
  Done 2026-09-30: vitest 171 files, 1771 passed; eslint, tsc clean; bundle refreshed.
- [x] 2.3 Full `hub/tests/`; ruff; black `--target-version py311`
  Done 2026-09-30: `py -3.11 -m pytest hub/tests/ -q -n 8` with `claude` off PATH: 5491 passed, 87 skipped, 0 failed, 12:42. ruff and black clean.

## 3. Drive

- [x] 3.1 Trial Hub: `scripts/drive/t_f156_preview_promises_the_merge.py`'s conflicting lane — the preview now names the conflict before approve is pressed. Record the body; time the call on this repository (Open Question 1)
  Done 2026-09-30 on a throwaway Hub (`:8036`, profile `drive0930f`), not `:8010`: `scripts/drive/t_f156_preview_promises_the_merge.py`. Lane 1 (before approval) and lane 3 (after the refusal) both answer `conflicts: [{commit_sha: d72bc40ed38d…, source_branch: work/ledger, paths: [ledger.py]}]`, reason "approval will be refused: ledger.py in commit d72bc40ed38d conflict with main"; the clean task reads "approval will merge one commit into main; it merges cleanly as of now" and approves; the nothing-to-merge task keeps its reason with `conflicts: []`. The script's four `[BAD]` checks are its F156 reproduction no longer reproducing (17/21). Timed: 122-163 ms per preview call on the drive's repository; Open Question 1's git cost on this repository was measured by R2 (0.03-0.16 s).
