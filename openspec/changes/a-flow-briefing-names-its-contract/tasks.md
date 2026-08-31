## 1. Reproduce it first

- [x] 1.1 Find where the briefing's existing assertions live before writing new ones. Five test
  files import `_compose_loop_briefing` today — `test_flow_checkpoint_lineage.py`,
  `test_flow_width.py`, `test_loop_claim_is_set_valued.py`, plus references in
  `test_handover_briefs_the_reviewer.py` and `test_scheduler.py:1092`. Add the new file
  `hub/tests/test_briefing_names_its_contract.py` rather than growing `test_scheduler.py`, which is
  2,637 lines.
- [x] 1.2 **F143's reproduction, and the cheap deterministic one.** Compose a briefing for a task
  selected as a review and one for the same task selected as implementation, and assert the two
  strings are **identical**. That is the defect in one line: `_compose_loop_briefing` has no
  `is_review` parameter, so there is nothing that could make them differ. Confirm it passes against
  unmodified code. A reproduction that does not pass first is not a reproduction.
- [x] 1.3 **F140's reproduction.** Compose an implementation briefing for a claimed task and assert
  the current state: `update_task` does not appear, the word `completed` does not appear, and
  `record_evidence` does not appear. Confirm all three pass against unmodified code.
- [x] 1.4 Assert the counterpart that must **stay** true, so the fix is not measured only by what it
  adds: the briefing still names `submit_checkpoint_notes` for a flow, still carries the tier
  paragraph, and a document-less loop's briefing still does not claim anything routes its work
  onward (`agent-flows:314`'s second scenario, which must not regress).

## 2. Thread `is_review` through

- [x] 2.1 Give `_compose_loop_briefing` a keyword-only `is_review: bool` with **no default**,
  matching `_briefing_checkpoint`'s signature one function above (design D6). A default of `False`
  is what would let a future call site silently reintroduce F143.
- [x] 2.2 Pass it at both call sites: `scheduler.py:2362-2366` (the `_do_fire_job` path, where the
  value is already computed as `bool(selection is not None and selection.is_review)`) and
  `scheduler.py:2712-2713` (`_stage_selection`, where a local `is_review` is already in scope). Both
  currently compute it, pass it to `_briefing_checkpoint`, and drop it on the next line.
- [x] 2.3 Update the six existing test call sites to state `is_review=False`. Do not give them a
  helper that defaults it — the explicitness is the point.
- [x] 2.4 Extend the function's docstring with what the parameter decides. That docstring is already
  the record of why the tier statement leads and why the two wordings differ; the review branch is
  the third statement of the same rule and belongs beside them.

## 3. The completion contract, on the implementation branch

- [x] 3.1 After the tier paragraph and before `Purpose:`, and only when a task is claimed, state the
  contract: the task's current status from `claimed_task.status`, the call
  `update_task("<task id>", status="completed")`, and what a turn that ends with the task unmoved
  costs — the next firing claims the same task and briefs somebody for the same work again.
- [x] 3.2 **Derive the hops from the task's actual status — round 2 correction, design D7.** There
  are *three* arrival states, not two: `CLAIMABLE_STATUSES` is `_statuses_in(BAND_AGENT_ACTIONABLE)`
  = `{pending, assigned, in_progress, revision_needed}` (`task_transitions.py:219-222, 286`) and
  `enter_selected_task` moves only `pending -> assigned` (`scheduler.py:796-797`), so a task returned
  for revision is briefed at `revision_needed`. `TRANSITIONS` has no `assigned -> completed` and no
  `revision_needed -> completed` edge; both offer `in_progress` first. Write it as one condition --
  *is the task already `in_progress`?* -- which is correct for all three and cannot drift from the
  map.
- [x] 3.2a Test the `revision_needed` arrival explicitly. It is the case round 1 got wrong, so it is
  the case most likely to be got wrong again.
- [x] 3.3 State what completing *causes* only where true (design D2): the flow branch says the work
  is offered for review by another agent; the loop branch says nothing about routing. Reuse the
  existing branch on `loop.spec_document_id` rather than adding a second one.
- [x] 3.4 Test: implementation briefing for a flow names `update_task`, `completed`, the task's id,
  and its current status. Test: the loop branch names the same transition and does **not** claim
  review routing.
- [x] 3.5 **Every word the loop branch gains must clear two existing absence assertions (round 2,
  design D11).** `test_flow_width.py:600-604` asserts `"review" not in briefing.lower()` and
  `"flow" not in briefing.lower()` over a document-less loop's *entire* briefing -- it is the
  executable form of `agent-flows:314`'s second scenario and must not be weakened to make room. So:
  no *"enters review"*, no *"review_state"*, no *"workflow"* on that branch. Run that file early
  rather than at the end.

## 4. Requirements and evidence, named only when they exist

- [x] 4.1 In the same claimed-task block, read `requirement_links.for_task(session, claimed_task.id)`
  and, when it returns rows, name the identifiers and `record_evidence(identifier, summary)`.
  **Word it so change C does not falsify it (round 2, design D12):** what is recorded enters
  `awaiting`, somebody else decides on it, and the work cannot land until they do. Do *not* copy
  `record_evidence`'s tool-surface phrasing *"approving a task integrates nothing until evidence …
  has been accepted"* (`api/v1/agents.py:938`) — that sentence becomes false the moment C refuses
  approval outright, and this one stays true under both regimes.
- [x] 4.2 Emit nothing about evidence when there are no links. A guessed identifier is refused by
  `agent_actions.py:1041` with `404`, and a document-less loop has no requirements at all, so an
  unconditional instruction is an instruction to fail (design D3).
- [x] 4.3 Import `requirement_links` into `scheduler.py`. **Round 2 verified there is no cycle** --
  `scheduler` is not reachable from `requirement_links`' transitive first-party imports -- so the
  hand-written-join fallback round 1 proposed is dropped. A second copy of that join is exactly the
  drift the queue group-by's own comment warns about.
- [x] 4.4 Test both halves: a task with links names them; a task with none says nothing about
  evidence.
- [x] 4.5 **Keep `submit_checkpoint_notes` and `update_task` in the same breath (round 3, D14).** The
  flow branch already asks for notes *"somebody else reads it"*, and that is false today: nobody
  does, because `consider_handover` declines when `_task_this_run_completed` finds no `completed`
  transition for the run (`checkpoint_handover.py:203-206`, `:93-99`). The completion sentence must
  sit with the notes sentence rather than in a separate block, so the briefing asks for the record
  and for the thing that delivers it together.

## 5. The review branch

- [x] 5.1 Under `is_review`, keep the tier paragraph, replace the *"Finish the task below and stop"*
  instruction with a review statement, and change the task heading from `## Current task:` to one
  that names the work as under review, with a line saying the text below is what the author was asked
  to build (design D4).
- [x] 5.2 Name both verdicts with the calls that record them —
  `update_task("<task id>", status="approved")` and `status="revision_needed"` — and check the
  wording against `api/v1/agents.py:1148-1157`, which states the same thing on the other channel.
  They must agree, not merely coexist (design D5). Where they differ, the context channel's wording
  is the one already driven and reviewed; match it rather than inventing a second phrasing.
- [x] 5.3 Do **not** restate what the context channel says about the detached checkout, running the
  test suite, or not fixing what is found. Those are properties of the workspace, which is the
  context channel's subject; the briefing's subject is the firing. Only the verdict is deliberately
  said twice, and only for the reason recorded in D5.
- [x] 5.4 **Do not name the commit under review (round 2, design D9).** The briefing is composed at
  firing time; the commit is resolved one step later, at spawn, by `commit_for_task_review` inside
  `prepare_review_turn`. Naming it here is a second copy of a fact that can disagree with the
  checkout the reviewer is standing in -- which is the case `ReviewContext.work_moved` already exists
  to handle, on the channel that resolved it.
- [x] 5.5 **Identify the loop's own message, without telling the agent to ignore it (round 2 D8, as
  narrowed by round 3 D16).** The delivered text is `briefing` followed by `job.message` at both call
  sites (`scheduler.py:2367`, `:2719`), and `job.message` is the operator's standing text for every
  firing -- in F143's own transcript it read *"Work the task you have been given. Keep the edit
  minimal."*, delivered to a reviewer. Add one sentence at the end of the review branch saying that
  what follows is the loop's **standing** message, delivered on every firing and not written for this
  turn in particular. Do **not** say it does not apply: a loop's message may itself address a review,
  and that instruction would be wrong exactly where its author thought hardest. Do **not** rewrite
  `job.message` either: it is the durable record of what its author said.
- [x] 5.6 Test: a review briefing states it is a review, does not contain the implementation
  instruction, names both verdicts, and does not present the task under a heading that reads as an
  instruction. Test: the implementation briefing still does contain it — the two must be measured
  against each other, since 1.2's reproduction is that they are the same string.

## 6. The harness assertion inverts

- [x] 6.1 `scripts/drive/t_row12_review_leg.py` currently asserts F143's state — implementation
  wording present, review wording absent — written that way *"so the day it is fixed the lines swap
  and say so."* Swap them. Read the file's own comment first: it records that an earlier version
  passed two checks on a briefing that said the opposite of what was asserted, so the new assertions
  must be specific strings, not `"review" in content`.
- [x] 6.1a **Correct, rather than satisfy, its "the briefing names the commit under review" check**
  (`t_row12_review_leg.py:331-334`). Round 2 (design D9) establishes the briefing must not name the
  commit. Replace the check with one asserting the briefing points the reviewer at its checkout
  without naming a commit, and note in the file that the commit is the context channel's to state.
- [x] 6.2 Add the F140 half to the same harness: after the implementation firing, assert the task's
  status is `completed` rather than `in_progress`. This is the check that makes `DRIVE-1`'s pass
  condition mechanical instead of a reading of the transcript.

## 7. Verify

- [x] 7.1 `py -3.11 -m pytest hub/tests/test_briefing_names_its_contract.py
  hub/tests/test_flow_checkpoint_lineage.py hub/tests/test_flow_width.py
  hub/tests/test_loop_claim_is_set_valued.py hub/tests/test_handover_briefs_the_reviewer.py
  hub/tests/test_scheduler.py -q` — the new file plus everything that composes a briefing.
- [x] 7.2 `py -3.11 -m pytest hub/tests/ -q -k "flow or loop or brief or scheduler"` for anything the
  list above missed.
- [x] 7.2a Run `hub/tests/test_handover_briefs_the_reviewer.py` explicitly and read what it proves.
  Round 3 (D14) establishes the feature it covers is unreachable in a real flow; if its tests are
  green while the drive shows no checkpoint generated, that gap is itself worth a finding at
  `DRIVE-1` rather than a silent pass.
- [x] 7.3 `ruff check src/ hub/ tests/` and
  `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`.
- [x] 7.4 Commit naming F140 and F143. The drive is `DRIVE-1`, not part of this change — but note in
  the commit that the string assertions are not proof, because the thing being fixed is whether a
  real agent acts on the text.
