## 1. Reproduce it first

- [ ] 1.1 New file `hub/tests/test_approval_refuses_unaccepted_evidence.py`. Not
  `test_requirement_gate.py` (the gate's own file, which gains only the shape assertions in group 6)
  and not `test_task_integration.py`.
- [ ] 1.2 **The fixture is the whole reproduction, and a fixture that skips the footprint proves
  nothing.** A project with a configured `main_branch` on a real git repository, a requirement, a
  task linked to it through `TaskRequirementLink`, and a `RequirementEvidence` row in
  `review_state='awaiting'` carrying an `EvidenceFootprint` of `kind='git'` with a real
  `commit_sha` on a branch. Read the rows back and assert they are what they claim before asserting
  anything about behaviour — B-IMPL found two fixture defects this way, and each would have made an
  assertion pass without the behaviour existing.
- [ ] 1.3 **F122's reproduction.** Approve that task through `apply_transition` and assert **today's**
  behaviour: the transition succeeds, `task.status == 'approved'`, and a `TaskIntegration` row
  records `outcome='skipped'` with `reason == task_integration.NOTHING_TO_MERGE`. Confirm it passes
  against unmodified code. A reproduction that does not pass first is not a reproduction.
- [ ] 1.4 **The second half's reproduction, and it is the one that would be missed.** With that task
  now `approved` and unmerged, accept the evidence through `requirement_evidence.decide` as the
  operator, commit, and assert that **nothing is merged**: no new `TaskIntegration` row, and the
  commit is not reachable from `main`. This is the sentence "accept the evidence" being ignored,
  measured.
- [ ] 1.5 Reproduce the two wedges the scoping constraint exists to prevent, as *passing* assertions
  about today that must **still pass** afterwards: a task whose only awaiting evidence has a `paths`
  footprint approves; a task with no evidence at all approves.

## 2. `awaiting_targets` — one query shape, two review states (D5)

- [ ] 2.1 In `hub/hub/task_integration.py`, extract the body of `integration_targets` into a private
  `_targets(session, task, review_state)` and make `integration_targets` call it with `ACCEPTED`.
  The docstring stays on `integration_targets`; `_targets` gets the query's own reasoning.
- [ ] 2.2 Add `awaiting_targets(session, task)`, calling `_targets` with
  `requirement_evidence.AWAITING`. Its docstring states the property D5 buys: the refusal fires
  precisely when acceptance would produce a target that does not exist now, and two independently
  written queries would drift.
- [ ] 2.3 Return the evidence id alongside the commit and branch — the refusal must **name each
  piece of evidence**, not count them, and `Target` carries only `commit_sha` and `branch` today.
  Decide between widening `Target` with an optional `evidence_id` and returning a second shape;
  prefer widening, because the accepted path can carry it harmlessly and a second shape is a second
  thing to keep in step.
- [ ] 2.4 Unit-test `awaiting_targets` directly: awaiting-with-commit returns it; accepted does not;
  rejected does not; `paths` footprint does not; evidence linked through a requirement this task is
  not linked to does not.

## 3. The refusal (D1, D2, D4)

- [ ] 3.1 `GateRefusal` gains `unaccepted: List[Dict[str, Any]]` beside `unmergeable`, with a comment
  saying what kind of claim it is — not "this is unproven" and not "this cannot go in", but "nothing
  would go in while something is waiting to be judged".
- [ ] 3.2 **Add it to `refuses`.** Tripwire D11: a list absent from
  `bool(self.blocking or self.diagnostics or self.unmergeable)` refuses nothing and every existing
  test still passes.
- [ ] 3.3 **Add it to `detail()`, and mind the early return.** `detail()` returns `_merge_detail()`
  immediately when `unmergeable` is set and nothing else is — a third category appended carelessly
  is dropped from the sentence in the case that matters most. Restructure so each category
  contributes its own sentence and the composition is explicit.
- [ ] 3.4 The sentence names each awaiting evidence row (its requirement identifier and commit) and
  **both remedies** — accept it, or grant an agent `can_accept_evidence`. The requirement is
  explicit that a refusal naming a remedy its reader cannot reach must say so.
- [ ] 3.5 Add it to `to_dict()`. `main.py:415` serialises exactly that; a field missing there reaches
  no surface at all.
- [ ] 3.6 `_check_unaccepted(session, task, refusal)` in `requirement_gate.py`, called from
  `evaluate` beside `_check_mergeable`. Refuse when `awaiting_targets` is non-empty **and**
  `integration_targets` is empty.
- [ ] 3.7 **Share `_check_mergeable`'s preconditions (D4)**, and share them by construction rather
  than by copying: resolve project, main branch, workspace and `is_repository`/`branch_exists` once
  and pass the result to both checks. Two copies of four preconditions is two things to keep in
  step, and the approval path would run the same two subprocess calls twice.
- [ ] 3.8 `GateRefusal` gains `advisory: List[Dict[str, Any]]` (D3), populated with the awaiting rows
  in the mixed case — where accepted targets exist. It is **not** counted by `refuses` and **not**
  part of `detail()`.
- [ ] 3.9 In `task_transition_service.apply_transition`, carry `refusal.advisory` out alongside
  `refusal.reported` into `transition.reported_advisories`. Note in the comment there that the list
  now carries two kinds and each entry says which it is, so a consumer cannot confuse a
  `contract`-rigor report with an evidence advisory.

## 4. Acceptance attempts the integration (D7)

- [ ] 4.1 `tasks_skipped_for_want_of_accepted_evidence(session, evidence)` in `task_integration.py`,
  written against `tasks_skipped_for_want_of_a_main_branch` as its template: the newest
  `TaskIntegration` per task, `Task.status == 'approved'`, `outcome == SKIPPED`,
  `reason == NOTHING_TO_MERGE`, and the task reached through `TaskRequirementLink` from the
  evidence's `requirement_id`. Keep the `.unique()` handling the sibling needed — two integration
  rows sharing the newest timestamp would otherwise retry twice.
- [ ] 4.2 A shared `integrate_what_was_waiting_for_this_evidence(session, evidence)`, wrapped in
  `try/except` with a `logger.warning` and `session.rollback()`, exactly as
  `_integrate_what_was_waiting_for_a_branch` is. It returns early unless the evidence's
  `review_state` is `ACCEPTED` **and** it carries a git footprint naming a commit.
- [ ] 4.3 Call it from `hub/hub/api/v1/spec.py`'s `decide_evidence`, **after** `session.commit()`.
- [ ] 4.4 Call it from `hub/hub/api/v1/agent_actions.py`'s `decide_evidence`, after its commit. Both
  routes, or the granted agent's acceptance — which is the whole point of the grant — merges
  nothing.
- [ ] 4.5 Do **not** put this inside `requirement_evidence.decide`. It neither commits nor knows
  about tasks, and integration must run after the commit.
- [ ] 4.6 Which actor is recorded on the integration? The sibling uses `operator()`. Here the
  accepting actor is known and is sometimes an agent. Record the actor that *accepted*, and write
  the reason down: the integration happened because of that decision, and an integration record
  naming the operator for an agent's decision is a false account of who caused it. Check
  `task_integration.record`'s `actor_kind` values accept it.

## 5. The behaviour tests

- [ ] 5.1 Invert 1.3: the same fixture now refuses, `task.status` is unchanged, and no
  `TaskIntegration` row exists.
- [ ] 5.2 The refusal's sentence contains the evidence's requirement identifier, the word for
  accepting, and the word for granting.
- [ ] 5.3 Invert 1.4: accepting the evidence for an already-approved, unmerged task merges it, and
  the task is not reopened.
- [ ] 5.4 1.5's two wedge cases still approve. These are the scoping constraint; if either fails the
  change is wrong, not the test.
- [ ] 5.5 Rejected evidence approves and records a skip.
- [ ] 5.6 The mixed case: accepted evidence naming commit A and awaiting evidence naming commit B —
  approval succeeds, A is merged, and the awaiting row appears in `approval_report`. Then accept B
  and assert B is merged too. **This pair is D3's whole argument**; without the second half the
  first half is the defect in miniature.
- [ ] 5.7 Refusal at `sketch` rigor, which is where a default project lives.
- [ ] 5.8 No main branch: approval succeeds with awaiting evidence present, and the skip is recorded.
  Same for a non-repository project.
- [ ] 5.9 The granted-agent route: an agent with `can_accept_evidence` accepting through
  `agent_actions` merges the work.
- [ ] 5.10 A dirty-checkout skip is **not** retried by an acceptance (D7's "only that cause").
- [ ] 5.11 Rejecting attempts nothing.
- [ ] 5.12 Acceptance stands when the attempt raises — patch the integration call to raise and assert
  `review_state == 'accepted'` afterwards.

## 6. Surfaces

- [ ] 6.1 `hub/ui/src/__tests__/taskIntegration.test.ts` gains a case for the new structured detail,
  asserting the sentence survives `readableApiError`. **No component change** — the UI reads
  `message` off the detail, and `main.py` already serialises `to_dict()`. If that turns out to be
  false, stop and record it rather than growing this change into a UI one.
- [ ] 6.2 Confirm the agent plane sees the refusal: `update_task_for_actor` is shared, and the
  app-level `TransitionRefusedError` handler is not route-scoped. Assert it in a test rather than
  reasoning about it — this change's entire premise is that a refusal must reach the agent that has
  to act on it.

## 7. Verification

- [ ] 7.1 The reproductions of group 1, green against unmodified code, **before** any fix.
- [ ] 7.2 `py -3.11 -m pytest hub/tests/test_approval_refuses_unaccepted_evidence.py
  hub/tests/test_requirement_gate.py hub/tests/test_task_integration.py
  hub/tests/test_task_transitions.py hub/tests/test_spec_evidence.py -q`.
- [ ] 7.3 `py -3.11 -m pytest hub/tests -q -k "integration or evidence or approve or approval or
  gate"`.
- [ ] 7.4 **Grep before changing any existing test.** Every test that walks a task to `approved`
  with recorded-but-unaccepted evidence now refuses. Find them first, read each, and write the
  reason for the change into the test — a test changed to make a suite green is how a real
  regression ships.
- [ ] 7.5 `cd hub/ui && npm run lint` and the vitest run, if 6.1 touched the UI tests. No
  `npm run build` — no component changed, so `hub/hub/static/ui` must not move.
- [ ] 7.6 `ruff check src/ hub/ tests/` and `black --check --target-version py311 src/ hub/hub/
  hub/tests/ tests/`.
- [ ] 7.7 `openspec validate approval-refuses-unaccepted-evidence --strict`.
- [ ] 7.8 Commit.

## 8. Not in this change — recorded so it is not silently absorbed

- [ ] 8.1 Break 7 (the "Try again" button that skips identically) is change D's.
- [ ] 8.2 Splitting `NOTHING_TO_MERGE` into its three worlds is change D's.
- [ ] 8.3 The `approval_report` advisory reaches no UI component (D3's named gap). Confirm during
  `DRIVE-1` and file it; do not fix it here.
