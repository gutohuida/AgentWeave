## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1 (bundle B1, 2026-09-24): proposal, design, delta, tasks, test guide from `404c7d5` and `DECISIONS.md` `F374-fix`
- [x] 0.2 R2 (2026-09-24): done — see design.md round log. Original brief: re-derive against `hub/hub/run_divergence.py:331-487` and `:685-876`, `hub/hub/requirement_gate.py:60-720`, `hub/hub/review_turn.py:178-237`, `hub/hub/scheduler.py` (`decide_firing`'s F154 branch as change 1 leaves it, `_wedged_review_reason`), and the delta. Check D1's category table against every writer of `GateRefusal`'s lists; D1's read-only claim; D3's cost on a board read (measure)
- [x] 0.3 R3 (2026-09-24): done — see design.md round log; `openspec validate a-review-no-reviewer-can-approve-goes-to-the-operator --strict` passes
- [x] 0.4 Opus adversarial review and operator decision, 2026-09-24 (`spec-queue/tracks/reviews/B1-2026-09-24.md` §2): fixes applied — see design.md "Operator review" and round log
- [ ] 0.5 Operator approval (APPROVALS.md). Strike ROUNDS.md's D9 row to point at `F374-fix` and this change

## 1. Tests first — each fails on today's code unless marked as a control

New file `hub/tests/test_a_review_no_reviewer_can_approve_goes_to_the_operator.py`. Stage the gate the way `test_approval_refuses_unaccepted_evidence*.py` does (evidence naming a commit, left `awaiting`, `evidence_governs` true), and a review run as `test_a_review_nobody_is_doing.py` / the F316 tests stage one. Call `evaluate_run_end(run_id)` directly.

- [ ] 1.1 (D2) Availability-picked reviewer `beta`, no verdict, evidence awaiting, `gamma` free and ungranted. After `evaluate_run_end`: no queue entry for `gamma`; `task.assignee == "beta"`; the `run_diverged` event has `outcome: surfaced` and a `reason` containing the gate's `This task's work has been recorded and nobody has judged it` and not `no agent is free`. FAILS today (restaffed to `gamma`, as F374 measured)
- [ ] 1.2 (D2) Same, `gamma` granted `can_accept_evidence` → restaffed to `gamma` as today. Control: PASSES today and must keep passing
- [ ] 1.3 (D2) Declared reviewer `beta`, ungranted, evidence awaiting → surfaced with the gate sentence, not *"asking this one again"*. FAILS today
- [ ] 1.4 (D1) Only an `unmergeable` refusal (a conflicting commit) → restaffed as today. Control
- [ ] 1.5 (D1) Mixed case (accepted evidence naming a commit plus a second awaiting row) → the gate does not refuse → restaffed as today. Control: pins that `evaluate`, not `verdict_evidence_sentence`, decides
- [ ] 1.6 (D1) `approval_held_for_operator` with `evaluate` patched to raise `RuntimeError` → `None`, a `WARNING` record naming the task (`caplog`), and `evaluate_run_end` restaffs as today (no 500, no lost divergence row)
- [ ] 1.6b (D1 savepoint) The same with a real `sqlalchemy.exc.OperationalError` raised after a query inside `evaluate`: `evaluate_run_end` still writes its `RunDivergence` row and commits. FAILS without the savepoint (the session is in a failed transaction)
- [ ] 1.6c (D1, operator: F424 held) 1.1's staging, but `hub.task_integration._git` patched to raise `subprocess.TimeoutExpired`: no queue entry for `gamma`, `task.assignee == "beta"`, the `run_diverged` reason contains `could not ask git`. Repeat with `OSError`, and with `gamma` granted `can_accept_evidence` (still held). FAILS today (restaffed to `gamma`) and under R3's design (the raise read as "not held", restaffed)
- [ ] 1.6d (D1 bound) `approval_held_for_operator` with `_git` patched to record the `timeout` it was given and the thread it ran on: every spawn saw `DIAGNOSTIC_GIT_TIMEOUT_SECONDS` and ran off the event loop's thread; a transition's own `evaluate` still sees 60. FAILS today (60, on the loop thread)
- [ ] 1.7 (D3) After 1.1, `decide_firing` on the flow: `DECISION_STALLED`, the reason starts `Approval of <task>` and contains `accept or reject the evidence`, does not contain `Ask beta again`, and is at most 500 characters. Add a 300-character title and assert the remedy survives the fit. FAILS today
- [ ] 1.7b (D1, R2) A `gate`-rigor requirement whose evidence is `drifting`, reviewer `gamma` granted `can_accept_evidence` → still surfaced (the grant does not reach drift). FAILS today
- [ ] 1.7c (D1, R2) A wedged review with no awaiting evidence and no `gate` document: `approval_held_for_operator` answers `None` without calling `evaluate` (patch `evaluate` to raise `AssertionError`; the predicate must not reach it). Control for the short-circuit
- [ ] 1.8 (D3) The board route (`GET` the jobs summary that calls `decide_firing`, `jobs.py:380`) with `evaluate` patched to raise answers 200 and shows today's wedged sentence

## 2. Implementation

- [ ] 2.1 (D1) `requirement_gate.ApprovalHold` and `approval_held_for_operator`: the short-circuit, the savepoint, the three answers of "What a raise means"; `task_integration.GIT_TIMEOUT_SECONDS` read by `_git`; the four git call sites on `evaluate`'s path through `asyncio.to_thread`
- [ ] 2.2 (D2, D4) `_answer_failed_review`: the three steps; the divergence sentence
- [ ] 2.3 (D3) `scheduler._approval_held_reason` and the reason order at the F154 branch
- [ ] 2.4 Run the new file, `test_a_review_nobody_is_doing.py`, the F316/F352 files (`grep -ln "_answer_failed_review\|evaluate_run_end" hub/tests`), and every `test_approval_refuses_*` file **with `claude` stripped from PATH**; the CLAUDE.md lint block; the full `hub/tests/`
