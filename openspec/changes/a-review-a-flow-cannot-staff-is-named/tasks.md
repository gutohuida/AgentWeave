## 1. Reproduce it first

- [ ] 1.1 New file `hub/tests/test_a_flow_names_what_it_cannot_staff.py`. Do not grow
  `test_scheduler.py` (2,637 lines) or `test_actor_aware_claimability.py`, which is the claimability
  rule's own file and gains only its two new cases in group 4.
- [ ] 1.2 **The fixture is the hard part, and getting it wrong makes every assertion below
  meaningless.** Three tasks that differ only in provenance, all sitting at `completed`:
  (a) walked `pending → assigned → in_progress → completed` through `apply_transition` as an agent;
  (b) the same walk, with the final `→ completed` applied by `Actor(kind="operator")`;
  (c) written into `completed` with no transition history at all.
  `test_flow_fires_a_review_turn.py:78` and `test_flow_chain_end_to_end.py:64` both record that a
  fixture skipping the history produces a queue the flow correctly refuses — which is case (c), not
  case (b). Assert the fixtures are what they claim by reading the rows back before asserting
  anything about behaviour.
- [ ] 1.3 **F142's reproduction.** Fire `decide_firing` on a queue holding only (b) and assert
  today's state: `decision.unstaffed == ()`, `decision.deferred == ()`, `decision._cannot_staff ==
  ()`, and `decision.stall_reason` contains `"no claimable task among"`. Confirm it passes against
  unmodified code. A reproduction that does not pass first is not a reproduction.
- [ ] 1.4 **The self-approval reproduction, which is the one that matters (design D5).** On queue
  (b), with the agent that worked the task as the *only* free agent, assert what a naive
  `exclude=set()` would produce: `resolve_reviewer(session, task, exclude=set())` returns that very
  agent. This is not a defect today — the arm is unreachable — so write it as an assertion about
  `resolve_reviewer` directly, with a comment saying it exists to prove the trap is real before the
  arm that would walk into it is built.
- [ ] 1.5 **Round 2's reproduction, and it is the one that would have shipped a self-approval.**
  Fixture (d): the operator moves a task `pending -> in_progress` **by hand**, an agent's run binds to
  it (`bind_run_to_task`), the agent records evidence naming a commit, and the operator moves it
  `in_progress -> completed`. Assert directly that `agents_that_worked` returns the **empty set** for
  it — no `in_progress -> in_progress` edge exists, so the binding recorded nothing — and that
  `task.assignee` names the agent. This is the fixture that proves the exclusion cannot be the
  transition set alone (design D5, round 2). Write it before task 2.4.
- [ ] 1.6 **D8's reproduction.** Move (b) to `under_review` by hand with the working agent still in
  `assignee`, fire, and assert it lands in `_cannot_staff` — the false *"a reviewer holds this"*.
  Confirm against unmodified code.

## 2. The attribution, read once

- [ ] 2.1 Add `CompletionAttribution` (frozen dataclass: `recorded: bool`, `actor_kind:
  Optional[str]`, `agent: Optional[str]`) and `completion_attribution()` to
  `task_transition_service.py`, immediately above `agent_that_completed`. Same query, same
  `ORDER BY sequence DESC LIMIT 1`, one extra selected column.
- [ ] 2.2 Make `agent_that_completed` a wrapper returning `attribution.agent`, with its signature and
  return type **unchanged**. Move the docstring's argument about reading from history and ordering by
  `sequence` to the new function; leave `agent_that_completed` a short docstring that points at it.
  Four of its seven callers are correct as written (design D3) and this change must not reach them.
- [ ] 2.3 Test the invariant D2 rests on, rather than assuming it: for a `→ completed` row,
  `actor_agent IS NULL` ⟺ `actor_kind == 'operator'`. Assert `Actor(kind="run", run_id="r", agent=None)`
  raises and `Actor(kind="operator", agent="x")` raises, in this change's own test file, so the day
  someone relaxes `__post_init__` this change fails rather than silently mis-attributes.
- [ ] 2.4 Add `agents_that_worked(session, task_id) -> set[str]` beside it: `SELECT DISTINCT
  actor_agent FROM task_transitions WHERE task_id = ? AND actor_agent IS NOT NULL`. Docstring records
  why it is not `{task.assignee}` (design D5): `assignee` is one mutable column overwritten by every
  restaff, and a task returned for revision has two authors. It records the converse just as plainly,
  because round 2 found round 1 asserting the opposite: this set does **not** contain every agent
  that worked the task. An agent binding to a task already `in_progress` takes no edge and is absent.
- [ ] 2.5 The exclusion the ladder is given is `agents_that_worked(...) | ({task.assignee} if
  task.assignee else set())`. Put that union behind one named helper rather than composing it at each
  of the two call sites — the wedge predicate in group 5 uses the **transitions-only** set and the
  two must be impossible to confuse. Name them so a reader cannot pick the wrong one by accident.
- [ ] 2.6 Test `agents_that_worked` on all four fixtures: (a) returns the agent, (b) returns the
  agent that worked it even though the operator completed it, (c) returns the empty set, (d) returns
  the empty set **while an agent worked the task** — and test that the union of 2.5 returns that
  agent for (d).

## 3. The review arm

- [ ] 3.1 Replace `scheduler.py:1364-1368` with the three-way split. Keep the gate order: the
  `commit_for_task_review` check stays **before** reviewer resolution (design D9), so an
  operator-completed task with no evidence still gets that function's existing, more specific
  sentence.
- [ ] 3.2 The *nothing recorded* arm appends to `unstaffed`, naming the task and the remedy. Wording
  must satisfy `agent-flows`' new requirement: say that no completion is recorded, and that reviewing
  it directly is the way forward, because nothing the flow can do will give the task provenance it
  never had. Do **not** say a later firing will pick it up — it will not.
- [ ] 3.3 The *operator completed it* arm resolves through the ladder with the 2.5 union as
  `exclude`, **not** the bare transition set (design D5, round 2). Otherwise the call is unchanged:
  `unavailable=taken` still, `choice.rung` handled exactly as today, plus `excluded_because` from
  group 3a.
- [ ] 3.3a **Round 2's self-approval reproduction inverts.** On fixture (d), with the agent that did
  the work as the only free agent, assert the firing does **not** select it. Written against the arm
  rather than against `resolve_reviewer`, because 1.5 already proves the trap at the resolver.
- [ ] 3.4 The *an agent completed it* arm is byte-identical to today, `exclude={author}`. Design D6:
  where the product has a decided answer to who the author is, do not widen it.
- [ ] 3.5 Test each arm against its fixture, and test that the operator arm reaches an *approved*
  verdict end to end rather than merely resolving a name — a resolution that then gets refused by a
  transition guard is the failure `agent-flows:59`'s third scenario forbids.
- [ ] 3.6 Test the exclusion actually excludes: queue (b), two agents, one of which worked the task.
  Assert the other is selected. Then remove the other and assert the firing surfaces rather than
  selecting the worker.

## 3a. The ladder stops asserting a completion that did not happen

- [ ] 3a.1 `resolve_reviewer` gains `excluded_because: str = "is the one that completed this task"`
  (design D13) and uses it in both refusal sentences — rung 1b (`scheduler.py:1074-1083`) and rung 3
  (`:1111-1118`). Rung 1b's wording shifts from *"the work"* to *"this task"*; that is intended.
- [ ] 3a.2 The operator-completed arm passes `excluded_because="has worked on this task"`. The
  attributed arm passes nothing and keeps the default.
- [ ] 3a.3 Test both sentences on both arms, asserting the **absence** of the word `completed` in the
  operator arm's rung-3 reason as well as the presence of the new clause. This is the sentence
  `decide_firing` promotes to `stall_reason` and `_emit_review_unstaffed` broadcasts, so it is the
  text F142's whole finding is about — an assertion on presence alone would pass on a sentence that
  still misattributes the completion beside it.
- [ ] 3a.4 Grep for existing assertions on either sentence before changing them
  (`test_flow_fires_a_review_turn.py`, `test_reviewer_is_not_the_author.py`, `test_scheduler.py`) and
  update them deliberately rather than discovering them in the run.

## 4. Claimability, so the two walks agree

- [ ] 4.1 `task_is_claimable_by` (`scheduler.py:546-593`) gains the operator arm: claimable by any
  agent not in the 2.5 union. The *nothing recorded* case keeps returning `False` unchanged. It must
  be the **same** set the review arm excludes, or the two walks disagree about fixture (d) — which is
  the disagreement group 4 exists to prevent, arriving through the term round 1 left out.
- [ ] 4.2 Extend the docstring rather than replacing it. Its argument — *"handing finished work to an
  agent the Hub cannot rule out as its author … is self-approval reached by two permissive defaults
  agreeing"* — is what **licenses** this change, because `agents_that_worked` is exactly what rules
  them out. Say so, or the next reader will read the new arm as an exception carved out of the rule.
- [ ] 4.3 Add the two cases to `test_actor_aware_claimability.py` beside its existing
  unattributed-task assertion at `:169`, which stays true for case (c). The new fixtures must be
  built through `apply_transition`; the existing one at `:169` is the direct-write kind and is case
  (c), not case (b).
- [ ] 4.4 Check `_first_startable_candidate` and the board summary now agree with the flow walk on
  fixture (b). `test_loop_current_item_includes_blocked.py:151` records that the board's current item
  comes through this same rule.

## 5. The wedged-review branch

- [ ] 5.1 `scheduler.py:1279-1284`: where no agent is recorded as completing the task and
  `task.assignee` is in `agents_that_worked` — **the transitions-only set, never the 2.5 union** —
  set `wedged_review = True` rather than appending to `in_flight`. Where a completion names an agent,
  behaviour is unchanged. With the union the predicate holds for every task that has an assignee at
  all and every review in flight is reported unstaffable (design D8, round 2); 5.4 is the test that
  catches it.
- [ ] 5.2 Confirm the carry-through: a wedged case (c) reaches the ladder and comes back `unstaffed`
  with 3.2's sentence, which is the honest outcome — `task-lifecycle-governance:313` says such a task
  is claimable by nobody, and telling the operator so beats reporting a reviewer that is not there.
- [ ] 5.3 Test: 1.5's reproduction inverts — case (b) in `under_review` with its worker as assignee
  is restaffed to a different agent and stays in `under_review` (the requirement's *"recovery is a
  reassignment"* clause); case (c) is surfaced.
- [ ] 5.4 Test the case that must **not** change: a task in `under_review` with a legitimate reviewer
  as assignee is still `in_flight`. The wedged branch widening is the risk here, and a flow that
  reports every review in progress as unstaffable is worse than the bug. Build the fixture through
  the flow's own staffing (`enter_selected_task`), not by writing `assignee` — round 2's argument
  that a legitimate reviewer is absent from the transition set rests on `completed -> under_review`
  being operator-attributed and the reviewer's binding recording nothing, and a hand-written fixture
  would not exercise either.

## 6. The stall reason

- [ ] 6.1 No code change is expected — `scheduler.py:1438-1457` already substitutes `unstaffed[0][1]`
  and `_do_fire_job:2402` already emits every `unstaffed` entry as a `review_unstaffed` event
  regardless of decision kind. **Verify both by test rather than by reading**, since the whole
  finding is that a fix which never reaches the operator is not a fix.
- [ ] 6.2 Test the persisted event and the SSE payload, not only the stall string. F64's own history
  is that the sentence *"was already being computed on this very walk and emitted as a
  `review_unstaffed` event; it simply never reached the surface an operator looks at."*
- [ ] 6.3 Check the `DECISION_PROCEED_EMPTY` path: a queue whose only task is case (b) or (c) and
  where `_stall_reason_from_walk` returns `None`. The event still fires; confirm the operator is not
  left with an empty-queue firing that says nothing.

## 7. The harness

- [ ] 7.1 `scripts/drive/t_row12_review_leg.py` already drives all three rows under `AW_COMPLETE_BY`.
  Invert row one's expectation: `AW_COMPLETE_BY=operator` should now reach a staffed review, or — in
  a project with no second agent — a `409` whose reason names the task rather than the histogram.
  Read the file's own comment first: it records an earlier version passing checks on content that
  said the opposite, so assert specific strings.
- [ ] 7.2 Add row four: the operator completes a task **no agent ever touched**, and a review is
  staffed with nobody excluded. That is the arm with the widest exclusion behaviour and it has no
  drive coverage.

## 8. Verify

- [ ] 8.1 `py -3.11 -m pytest hub/tests/test_a_flow_names_what_it_cannot_staff.py
  hub/tests/test_actor_aware_claimability.py hub/tests/test_flow_fires_a_review_turn.py
  hub/tests/test_flow_chain_end_to_end.py hub/tests/test_reviewer_is_not_the_author.py
  hub/tests/test_task_transitions.py hub/tests/test_scheduler.py -q`.
- [ ] 8.2 `py -3.11 -m pytest hub/tests/ -q -k "flow or loop or review or transition or scheduler or
  claim"`.
- [ ] 8.3 **`test_flow_chain_end_to_end.py:344-355`'s set equality must be unchanged.** This change
  adds no operator-attributed transition and removes none (design D12); if that assertion moves,
  something happened that was not intended and the diff is wrong, not the test.
- [ ] 8.4 `ruff check src/ hub/ tests/` and
  `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`.
- [ ] 8.5 `openspec validate a-review-a-flow-cannot-staff-is-named --strict`.
- [ ] 8.5a Grep the hub suite for `"the one that completed"` after 3a lands. Any assertion still
  expecting that clause on an operator-completed path is a sentence this change was supposed to fix
  and did not.
- [ ] 8.6 Commit naming F142. Note in the message that the string assertions are not proof of the
  judgement half — whether staffing a review for operator-completed work is right is settled by
  `DRIVE-1`, not by a green suite.
