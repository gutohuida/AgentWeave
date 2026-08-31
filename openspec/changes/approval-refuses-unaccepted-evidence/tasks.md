## 1. Reproduce it first

- [x] 1.1 New file `hub/tests/test_approval_refuses_unaccepted_evidence.py`. Not
  `test_requirement_gate.py` (the gate's own file, which gains only the shape assertions in group 6)
  and not `test_task_integration.py`.
- [x] 1.2 **The fixture is the whole reproduction, and a fixture that skips the footprint proves
  nothing.** A project with a configured `main_branch` on a real git repository, a requirement, a
  task linked to it through `TaskRequirementLink`, and a `RequirementEvidence` row in
  `review_state='awaiting'` carrying an `EvidenceFootprint` of `kind='git'` with a real
  `commit_sha` on a branch. Read the rows back and assert they are what they claim before asserting
  anything about behaviour — B-IMPL found two fixture defects this way, and each would have made an
  assertion pass without the behaviour existing. **Round 2: do not build this from scratch.**
  `hub/tests/test_task_integration.py` already has `set_main_branch`, `linked_task`,
  `commit_on_branch`, `accept_evidence`, `approve`, `integrations`, `commits_on` and `files_on`
  working against a real repository; reuse them and the fixture risk mostly goes away.
- [x] 1.3 **F122's reproduction.** Approve that task through `apply_transition` and assert **today's**
  behaviour: the transition succeeds, `task.status == 'approved'`, and a `TaskIntegration` row
  records `outcome='skipped'` with `reason == task_integration.NOTHING_TO_MERGE`. Confirm it passes
  against unmodified code. A reproduction that does not pass first is not a reproduction.
- [x] 1.4 **The second half's reproduction, and it is the one that would be missed.** With that task
  now `approved` and unmerged, accept the evidence through `requirement_evidence.decide` as the
  operator, commit, and assert that **nothing is merged**: no new `TaskIntegration` row, and the
  commit is not reachable from `main`. This is the sentence "accept the evidence" being ignored,
  measured.
- [x] 1.5 Reproduce the two wedges the scoping constraint exists to prevent, as *passing* assertions
  about today that must **still pass** afterwards: a task whose only awaiting evidence has a `paths`
  footprint approves; a task with no evidence at all approves.

## 2. `awaiting_targets` — one query shape, two review states (D5)

- [x] 2.1 **Round 3 rewrote 2.1-2.3; do not extract the whole body.** In
  `hub/hub/task_integration.py`, extract only the **filter** of `integration_targets` into a private
  `_targets(session, task, review_state)`: the join through `TaskRequirementLink` →
  `RequirementEvidence` → `EvidenceFootprint`, the project scope, the review state, `kind == "git"`,
  and the `commit_sha` guard — including the `if not row.commit_sha: continue` that sits inside
  today's loop but belongs to the filter. It returns the matching rows, **undeduplicated**, oldest
  first. The docstring stays on `integration_targets`; `_targets` gets the filter's own reasoning.
- [x] 2.2 **The per-branch reduction stays in `integration_targets`, not in `_targets`.** Keying
  `newest` by branch answers *what do I merge* and is a decision about merging;
  `awaiting_targets(session, task)` is enumerating what has not been judged and returns every row.
  Design D5 round 3: a shared reduction would collapse two awaiting rows on one branch into one and
  breach requirement 1's *"SHALL name each piece of evidence that is waiting rather than only how
  many there are"*. D5's actual property — the refusal fires precisely when acceptance would produce
  a target that does not exist now — is about **non-emptiness**, which both reductions preserve
  identically, so it survives the split whole. Say that in `awaiting_targets`' docstring.
- [x] 2.3 Carry the evidence id, the `RequirementEvidence.requirement_id`, **and the recording
  `task_id`** alongside the commit and branch — the refusal must name each piece and say which task
  recorded it (round 2's D6). All three are already on the joined `RequirementEvidence`, so this is a
  wider `select`, **not a new join**. **Do not put the requirement's human identifier here** (round
  3): `RequirementEvidence.requirement_id` is the `spec_requirements.id` FK
  (`models.py:2334-2336`) and the identifier lives on `SpecRequirement`, which `task_integration`
  does not import — reaching it would add a join to the *merge* query for a field only the sentence
  uses, which is the drift D5 exists to prevent. `requirement_gate` already imports `SpecRequirement`
  at module level; resolve `requirement_id` → identifier there, where the sentence is composed.
  `Target` carries only `commit_sha` and `branch` today; widen it with optional fields rather than
  returning a second shape, since the accepted path can carry them harmlessly.
- [x] 2.4 Unit-test `awaiting_targets` directly: awaiting-with-commit returns it; accepted does not;
  rejected does not; `paths` footprint does not; a `git` footprint whose `commit_sha` is `""` does
  not; evidence linked through a requirement this task is not linked to does not.
- [x] 2.5 **Round 3's regression test for the split.** Two awaiting evidence rows on the **same**
  branch naming different commits: `awaiting_targets` returns **both**, and `integration_targets`
  over the same two rows accepted returns **one**. This is the test that would have caught the shared
  reduction, and without it the refusal silently names one of two waiting pieces.

## 3. The refusal (D1, D2, D4)

- [x] 3.1 `GateRefusal` gains `unaccepted: List[Dict[str, Any]]` beside `unmergeable`, with a comment
  saying what kind of claim it is — not "this is unproven" and not "this cannot go in", but "nothing
  would go in while something is waiting to be judged".
- [x] 3.2 **Add it to `refuses`.** Tripwire D11: a list absent from
  `bool(self.blocking or self.diagnostics or self.unmergeable)` refuses nothing and every existing
  test still passes.
- [x] 3.3 **Add it to `detail()`, and mind the early return.** `detail()` returns `_merge_detail()`
  immediately when `unmergeable` is set and nothing else is — a third category appended carelessly
  is dropped from the sentence in the case that matters most. Restructure so each category
  contributes its own sentence and the composition is explicit.
- [x] 3.4 The sentence names each awaiting evidence row — its requirement identifier (resolved here
  from `requirement_id` against `SpecRequirement`, per 2.3), its commit,
  **and the task that recorded it**, saying so explicitly where that is not the task being approved
  (round 2's D6: a shared `TaskRequirementLink` is ordinary, so this happens in normal use).
  `RequirementEvidence.task_id` carries it and is populated even when an agent omits it
  (`requirement_evidence.py:125-129`); it is nullable, so tolerate its absence. The sentence also
  names **both remedies** — accept it, or grant an agent `can_accept_evidence`. The requirement is
  explicit that a refusal naming a remedy its reader cannot reach must say so.
- [x] 3.5 Add it to `to_dict()`. `main.py:415` serialises exactly that; a field missing there reaches
  no surface at all.
- [x] 3.6 `_check_unaccepted(session, task, refusal)` in `requirement_gate.py`, called from
  `evaluate` beside `_check_mergeable`. Refuse when `awaiting_targets` is non-empty **and**
  `integration_targets` is empty. **Round 3: "beside" means before `evaluate`'s early return**, which
  is `if not enforced: return refusal, ""` two statements later (`requirement_gate.py:205-209`). A
  call placed after it is dead in every default project, because `_enforced_requirements` filters
  `sketch` out and a default document is a sketch — the same trap that let F122 survive, one layer
  down. `_check_mergeable` is already on the correct side of it; put this one next to it and the trap
  is closed by position.
- [x] 3.7 **Share `_check_mergeable`'s preconditions (D4)**, and share them by construction rather
  than by copying: resolve project, main branch, workspace and `is_repository`/`branch_exists` once
  and pass the result to both checks. Two copies of four preconditions is two things to keep in
  step, and the approval path would run the same two subprocess calls twice. A third reason round 2
  found: `resolve_project_workspace` is not a pure read — it writes `project.directory_state` and
  `project.last_seen_at` (`project_workspace.py:210-233`) — so calling it twice per approval writes
  the same fields twice on the same session for no gain.
- [x] 3.8 `GateRefusal` gains `advisory: List[Dict[str, Any]]` (D3), populated with the awaiting rows
  in the mixed case — where accepted targets exist. It is **not** counted by `refuses` and **not**
  part of `detail()`.
- [x] 3.9 In `task_transition_service.apply_transition`, carry `refusal.advisory` out alongside
  `refusal.reported` into `transition.reported_advisories`. Note in the comment there that the list
  now carries two kinds and each entry says which it is, so a consumer cannot confuse a
  `contract`-rigor report with an evidence advisory.

## 4. Acceptance attempts the integration (D7)

- [x] 4.1 **Round 2 rewrote this task; do not implement the version it replaced.**
  `tasks_awaiting_this_commit(session, evidence)` in `task_integration.py`: approved tasks reached
  through `TaskRequirementLink` from the evidence's `requirement_id`, **excluding** any task that
  already has a `TaskIntegration` row with `outcome == MERGED` and this evidence footprint's
  `commit_sha`. It is **not** `tasks_skipped_for_want_of_a_main_branch` with a different reason
  string: filtering on the most recent attempt's reason misses the mixed case entirely, because
  there the most recent attempt is a `MERGED` row (design D3, round 2's table; D7 as rewritten).
  Deduplicate the task list — one task can hold several integration rows.
- [x] 4.2 A shared `integrate_what_was_waiting_for_this_evidence(session, evidence, actor)`, wrapped
  in `try/except` with a `logger.warning` and `session.rollback()`, exactly as
  `_integrate_what_was_waiting_for_a_branch` is. It returns early unless the evidence's
  `review_state` is `ACCEPTED` **and** it carries a git footprint naming a commit. It calls
  `retry_integration` per task, which recomputes `integration_targets` and self-guards with
  `ALREADY_INTEGRATED` — that self-guard (`task_transition_service.py:699-702`) is what licenses a
  predicate wider than the sibling's, so do not add a second reachability check here.
- [x] 4.3 Call it from `hub/hub/api/v1/spec.py`'s `decide_evidence`, **after** `session.commit()`.
- [x] 4.4 Call it from `hub/hub/api/v1/agent_actions.py`'s `decide_evidence`, after its commit. Both
  routes, or the granted agent's acceptance — which is the whole point of the grant — merges
  nothing.
- [x] 4.5 Do **not** put this inside `requirement_evidence.decide`. It neither commits nor knows
  about tasks, and integration must run after the commit.
- [x] 4.6 Record the actor that *accepted*, not `operator()` as the sibling does: the integration
  happened because of that decision, and a record naming the operator for an agent's decision is a
  false account of who caused it. **Round 2 checked this and it needs an explicit conversion.**
  Both routes hold a `spec_lifecycle.Actor(kind="agent"|"operator")`; `retry_integration` takes a
  `task_transitions.Actor`, which admits only `run`/`operator` and *requires* both `run_id` and
  `agent` for `run` (`task_transitions.py:59-67`). So build `run_actor(actor.run_id, actor.agent)`
  on the agent route and `operator()` on the operator route. Passing the `spec_lifecycle` actor
  through raises `ValueError`. `task_integration.record` itself constrains nothing — no
  `CheckConstraint` on `actor_kind` in the model or any migration (design D13).

## 5. The behaviour tests

- [x] 5.1 Invert 1.3: the same fixture now refuses, `task.status` is unchanged, and no
  `TaskIntegration` row exists.
- [x] 5.2 The refusal's sentence contains the evidence's requirement identifier, the word for
  accepting, and the word for granting.
- [x] 5.2a **Round 3, the behavioural half of 2.5.** Two awaiting evidence rows on one branch: the
  refusal's sentence names **both** commits, not one. Requirement 1 says each waiting piece is named
  rather than only how many there are, and the shared-reduction defect round 3 found would have
  passed 5.2 while failing this.
- [x] 5.3 Invert 1.4: accepting the evidence for an already-approved, unmerged task merges it, and
  the task is not reopened.
- [x] 5.4 1.5's two wedge cases still approve. These are the scoping constraint; if either fails the
  change is wrong, not the test.
- [x] 5.5 Rejected evidence approves and records a skip.
- [x] 5.6 The mixed case: accepted evidence naming commit A and awaiting evidence naming commit B —
  approval succeeds, A is merged, and the awaiting row appears in `approval_report`. Then accept B
  and assert B is merged too. **This pair is D3's whole argument**; without the second half the
  first half is the defect in miniature. **Round 2: this test was already right and the requirement
  behind it was wrong** — round 1's `NOTHING_TO_MERGE` predicate could not have passed it, because
  the newest integration row here is `MERGED`. Write it in both shapes: B on A's branch, and B on a
  second branch.
- [x] 5.7 Refusal at `sketch` rigor, which is where a default project lives.
- [x] 5.8 No main branch: approval succeeds with awaiting evidence present, and the skip is recorded.
  Same for a non-repository project.
- [x] 5.9 The granted-agent route: an agent with `can_accept_evidence` accepting through
  `agent_actions` merges the work.
- [x] 5.10 **Round 2 inverted this.** An acceptance on a task whose last attempt skipped
  `CHECKOUT_DIRTY` **is** attempted again and records the dirty reason a second time — the trigger
  is a commit that is not in the product, not the previous attempt's reason (D7 as rewritten). Also
  assert the noise guard the new predicate does keep: accepting evidence whose commit already has a
  `MERGED` row for that task attempts nothing.
- [x] 5.11 Rejecting attempts nothing.
- [x] 5.12 Acceptance stands when the attempt raises — patch the integration call to raise and assert
  `review_state == 'accepted'` afterwards.

## 6. Surfaces

- [x] 6.1 `hub/ui/src/__tests__/taskIntegration.test.ts` gains a case for the new structured detail,
  asserting the sentence survives `readableApiError`. **No component change** — the UI reads
  `message` off the detail, and `main.py` already serialises `to_dict()`. If that turns out to be
  false, stop and record it rather than growing this change into a UI one.
- [x] 6.2 Confirm the agent plane sees the refusal: `update_task_for_actor` is shared, and the
  app-level `TransitionRefusedError` handler is not route-scoped. Assert it in a test rather than
  reasoning about it — this change's entire premise is that a refusal must reach the agent that has
  to act on it.
- [x] 6.3 **F152, added by round 2.** `mcp_server._readable_detail` handles a `list` detail and
  falls through to `str(detail)` for a `dict`, so a gate refusal reaches an agent as a Python dict
  repr with the sentence buried in it. Return `detail["message"]` where a dict carries a non-empty
  string one; otherwise keep today's behaviour. Stdlib only — `mcp_server.py` may import nothing
  else. Test it in `hub/tests/` against `_readable_detail` directly with a real `to_dict()` payload,
  and assert the dict-repr braces are absent from what an agent would read.

## 7. Verification

- [x] 7.1 The reproductions of group 1, green against unmodified code, **before** any fix.
- [x] 7.2 `py -3.11 -m pytest hub/tests/test_approval_refuses_unaccepted_evidence.py
  hub/tests/test_requirement_gate.py hub/tests/test_task_integration.py
  hub/tests/test_task_transitions.py hub/tests/test_spec_evidence.py -q`. **There is no
  `test_spec_evidence.py`** — the list was written from memory. Substituted
  `test_requirement_evidence.py`, `test_agent_evidence_grant.py` and `test_agent_evidence_plane.py`,
  plus the other four blast-radius candidates: 200 passed.
- [x] 7.3 `py -3.11 -m pytest hub/tests -q -k "integration or evidence or approve or approval or
  gate"`.
- [x] 7.4 **Grep before changing any existing test.** Every test that walks a task to `approved`
  with recorded-but-unaccepted evidence now refuses. Find them first, read each, and write the
  reason for the change into the test — a test changed to make a suite green is how a real
  regression ships. **Measured: exactly one test moved**, `test_task_integration.py`'s
  `test_evidence_awaiting_review_merges_nothing`, which was F122's own shape asserted as intended
  behaviour. Its real property — nothing reaches `main` on unreviewed evidence — is kept verbatim
  and now stated as a refusal; the reason is written into the docstring. The other four candidate
  files round 3 named were all green unchanged, as were the 418 tests matching 7.3's selection and
  the flow and scheduler suites.
- [x] 7.5 `cd hub/ui && npm run lint` and the vitest run, if 6.1 touched the UI tests. No
  `npm run build` — no component changed, so `hub/hub/static/ui` must not move.
- [x] 7.6 `ruff check src/ hub/ tests/` and `black --check --target-version py311 src/ hub/hub/
  hub/tests/ tests/`.
- [x] 7.7 `openspec validate approval-refuses-unaccepted-evidence --strict`.
- [ ] 7.8 Commit.

## 8. Not in this change — recorded so it is not silently absorbed

- [ ] 8.1 Break 7 (the "Try again" button that skips identically) is change D's.
- [ ] 8.2 Splitting `NOTHING_TO_MERGE` into its three worlds is change D's.
- [ ] 8.3 The `approval_report` advisory reaches no UI component (D3's named gap). Confirm during
  `DRIVE-1` and file it; do not fix it here.
