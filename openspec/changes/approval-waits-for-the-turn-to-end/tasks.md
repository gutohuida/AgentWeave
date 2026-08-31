## 1. Reproduce F162 before fixing anything

- [ ] 1.1 Write a failing test that reproduces the window in `hub/tests/`: a task whose bound run is
  live, moved to `approved`, currently yielding a recorded `ALREADY_INTEGRATED` skip against the
  **base** commit and a task reading `approved`. Assert today's wrong behaviour so the test flips.
- [ ] 1.2 Assert the consequence, not only the state: the task's work is *not* an ancestor of the
  project's main branch after the approval, and the recorded integration is not retryable.
- [ ] 1.3 Confirm the test fails for the stated reason by reading its failure output, not by
  assuming — a test that passes today is reproducing something else.

## 2. The liveness predicate

- [ ] 2.1 Test the predicate directly: a run this Hub process owns and holds a live handle for reads
  live; a run recorded `running` with no handle in this process reads **not** live; an
  app-server run in `_active_app_server_runs` reads live.
- [ ] 2.2 Implement the predicate in a module `requirement_gate` can import without importing
  `api/v1/agent_trigger` (design D3, open question 2). Registry first; absence means not live.
- [ ] 2.3 Do not use `pid_alive` as the sole test, and record why in a comment citing its own
  docstring's warning about a caller that checks a process this same Hub killed
  (`pty_runner.py:150-156`).
- [ ] 2.4 Scope it to runs bound to this task (`Run.task_id`), and note the unbound-run residual in
  a comment so it is a known gap rather than an oversight.

## 3. The gate refuses a live turn

- [ ] 3.1 Test each scenario in `specs/task-lifecycle-governance/spec.md`: refused during the turn;
  permitted after it; not refused when the process is gone; unaffected with no run; refused
  identically at `sketch` and `gate` rigor.
- [ ] 3.2 Add the fifth `GateRefusal` category with the comment its four siblings each have, stating
  what kind of claim it is and why it is not one of the others.
- [ ] 3.3 Implement the check in `evaluate`, **above** the `if not enforced` early return, for the
  same reason the two repository-aware checks sit there (`requirement_gate.py:392-398`).
- [ ] 3.4 Compose its sentence in `detail()` alongside the others — never as an early return
  (`requirement_gate.py:115-124` records why that mattered once already).
- [ ] 3.5 Write the refusal sentence so it names the agent, states that the turn is still running,
  and says the refusal clears itself when the turn ends. It must not read as a defect in the work
  (design D4).
- [ ] 3.6 Verify the sentence survives the UI's error path the way F152's fix did — check
  `readableApiError` renders it as prose, not a dict repr.
- [ ] 3.7 Re-run task 1's reproduction; it must now assert the refusal.

## 4. Determine whether the evidence route shares the window

- [ ] 4.1 Read `_targets` (`task_integration.py:219`) and `restamp_run_footprints`
  (`requirement_evidence.py:846`) together and state, in the design's D9, whether approving mid-turn
  on the evidence route merges a stale commit.
- [ ] 4.2 If it does, add a test covering the evidence route through the same refusal, and say so in
  the requirement's rationale. If it does not, record what prevents it.

## 5. A loop stops entering the review arm

- [ ] 5.1 Test the `agent-loops` scenarios: a loop's completed task is not selected for review; no
  firing reports a missing commit to review; the unstaffed report stays empty for it; a flow's
  review leg is unchanged.
- [ ] 5.2 Implement the exclusion at the selection site in `scheduler.py` (design D5), not inside
  `commit_for_task_review`.
- [ ] 5.3 Make sure the loop's completed task does not reach `unstaffed` — it is not a step anything
  failed at.
- [ ] 5.4 Check the other loop populations before assuming nothing is lost: a loop with a document is
  a flow (`agent-flows:13`), so establish exactly which loops lose the arm.

## 6. One action lands a loop's work

- [ ] 6.1 Test the `agent-loops` landing scenarios: one action reaches `approved` and merges; each
  transition is recorded and attributed to the operator; the action is refused while the turn is
  live; a refused landing leaves holder, status and integration record untouched.
- [ ] 6.2 Implement it as a composition of the existing transitions (design D6). Do not add
  `completed -> approved` to `TRANSITIONS`.
- [ ] 6.3 Evaluate the gate before performing any transition (design D7).
- [ ] 6.4 Add the UI affordance that issues it, and render the live-turn refusal where the operator
  takes the action.

## 7. Prove it end to end

- [ ] 7.1 Re-run `scripts/drive/t_f162_window.py` against a Hub restarted from this branch. Lane 1
  must now reach a refusal instead of `REPRODUCED`; update the harness's pass condition and say in
  `FINDINGS.md` what changed.
- [ ] 7.2 Re-run `scripts/drive/t_drive2_loop_lands.py`: a loop's work still reaches the main branch,
  now in one operator action, with no review stall on the way.
- [ ] 7.3 Re-run `scripts/drive/t_drive1_flow_lands.py`: the flow still lands its work and its review
  leg is untouched.
- [ ] 7.4 Record the outcome of each drive in `scripts/drive/FINDINGS.md`, including anything new the
  drives surface.

## 8. Close it out

- [ ] 8.1 `openspec validate approval-waits-for-the-turn-to-end --strict`.
- [ ] 8.2 `pytest hub/tests/ -v` with `py -3.11`, and the CLI suite if anything under `src/` moved.
- [ ] 8.3 `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/
  hub/tests/ tests/`, `mypy src/`.
- [ ] 8.4 If `hub/ui/src` changed, rebuild and refresh the bundle with
  `py -3.11 scripts/refresh_ui_bundle.py`, and commit source and bundle together.
