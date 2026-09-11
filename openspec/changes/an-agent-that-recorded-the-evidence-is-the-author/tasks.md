# Tasks — an agent that recorded the evidence is the author

Implementation is a night window's. Nothing here is complete on the strength of this plan existing;
only verified implementation closes a task.

**This change is Python-only.** No UI file is modified, so the committed bundle in
`hub/hub/static/ui` is **not** rebuilt — and the Python lint set *is* required (§6).

**It repairs two defences and must be verified as two.** The ladder half (§1, §2) is what the
operator sees; the guard half (§3) is the one nobody sees. A run that closes one and reports the
change done has closed half a change, and the half it is most tempting to skip is the guard, because
no test fails for its absence today.

## 1. The fourth source

- [ ] 1.1 In `hub/hub/task_transition_service.py`, add
  `agents_that_recorded_evidence_for(session, task_id) -> set[str]`, immediately before
  `agents_that_may_have_authored`, beside the other two term functions. Select
  `RequirementEvidence.actor` distinct, filtered to `task_id == task_id`,
  `actor_kind == "agent"`, and a non-empty `actor`; drop falsy values on the way out as the other
  two terms do.
- [ ] 1.2 Add `RequirementEvidence` to the existing `from .db.models import …` line. Confirm no
  import cycle appears (`py -3.11 -c "import hub.task_transition_service"`): `db.models` is already
  imported by this module, so this is a name on an existing import, not a new edge.
- [ ] 1.3 Docstring it with **why each filter is there**, from `design.md` D2 — that `actor_kind`
  is what keeps the operator's own evidence out of an exclusion of agents and what preserves the
  untouched-task case, and that `review_state` is deliberately *not* filtered. A reader's first
  instinct will be to add `review_state == 'accepted'`; the docstring is what stops them.
- [ ] 1.4 State in the docstring that this term has **two** consumers and that the second one uses
  it alone (`design.md` D1/D3). Without that sentence the next reader folds it into the union and
  deletes the function.

## 2. The union, and the two call sites that inherit the fix

- [ ] 2.1 `agents_that_may_have_authored` unions the new term with the existing three.
- [ ] 2.2 Update that function's docstring table — it enumerates three sources by name and says
  *"Three sources for one question is not elegant"*. A fourth row: **evidence** names *every agent
  that asserted authorship of it*, and misses *work nobody recorded evidence for*. The docstring is
  the load-bearing statement of the principle this change extends, not decoration.
- [ ] 2.3 Confirm by reading, not by assuming, that `hub/hub/scheduler.py:625`
  (`task_is_claimable_by`) and `hub/hub/scheduler.py:1574` (the review-staffing arm) both call the
  union and need **no edit**. If either turns out to recompose the terms, stop: that is the drift
  the union's own comment says must not exist, and it is a finding.

## 3. The guard, falling back to the evidence actors alone

- [ ] 3.1 In `_guard_author_is_not_reviewer`, where `agent_that_completed` returns `None` and the
  actor is an agent, refuse when that agent appears in `agents_that_recorded_evidence_for`.
  **The fallback is that term alone and never `agents_that_may_have_authored`** — `design.md` D3
  and the measurement in `proposal.md` §3. Falling back to the union refuses the flow's own
  reviewer on every operator-completed task.
- [ ] 3.2 The refusal names the evidence as the reason. The existing message pattern in this
  module states the record it read and what the asker must do instead; match it, and do not reuse
  the completion sentence — no agent completed this task, and a message saying one did is the class
  of untruth `agent-flows`' surfaced-reason requirement already forbids one layer up.
- [ ] 3.3 Keep the operator exempt and keep `_REVIEW_OUTCOMES` as the gate. Both are the existing
  first two lines of the guard; the fallback goes **after** them, not before.
- [ ] 3.4 Do not touch `_guard_reviewer_is_not_the_author`. It is a different rule about a different
  fact (the state the move produces, binding the operator too) and is out of scope.

## 4. Tests, mutation-checked because nothing existing fails today

The blast-radius measurement (`proposal.md`) found **zero** existing tests whose expectation
changes. That is a warning, not a reassurance: it means the whole of this change's coverage is new,
and a new test that would pass against the unfixed tree is worth nothing.

- [ ] 4.1 New file `hub/tests/test_the_evidence_names_the_author.py`, with `F306`'s live
  reproduction in its module docstring including the run and task ids.
- [ ] 4.2 The ladder leg: an operator-completed task, one agent-authored evidence row naming a
  commit, two free agents with the author sorting **first** by name. Assert the flow staffs the
  other agent. The name order is load-bearing — `design.md` D6 — and a fixture where the author
  sorts second passes against the unfixed tree.
- [ ] 4.3 The guard leg: the same shape, with the author moving the task to `approved` directly.
  Assert `ActorNotPermittedError`, that the task's status is unchanged, and that no transition was
  recorded.
- [ ] 4.4 The reviewer-is-not-refused leg: the agent the flow staffed records `approved` and is
  **accepted**, with `task.assignee` equal to that reviewer at the moment it does. This is the
  regression test for `design.md` D3, and it is the one that fails if a later change "simplifies"
  the fallback to the union.
- [ ] 4.5 The operator-evidence leg: evidence recorded with `actor_kind='operator'` leaves every
  agent eligible. `F306`'s own untouched-task carve-out, and the test for the `actor_kind` filter.
- [ ] 4.6 The `review_state` leg: evidence in `awaiting` and evidence in `rejected` each exclude
  their author. This is the operator's verdict in executable form, and the thing a future
  simplification is most likely to break.
- [ ] 4.7 **Mutation-check every leg.** Revert each of §1–§3 in turn and record which legs fail:
  remove the union term (4.2 must fail), remove the guard fallback (4.3 must fail), change the
  fallback to the union (4.4 must fail), drop the `actor_kind` filter (4.5 must fail), add
  `review_state == 'accepted'` (4.6 must fail). A leg that survives its own mutation is not
  testing what it claims — fix the fixture, do not weaken the claim. Write the table into the log.
- [ ] 4.8 Re-run the 15 files from the blast-radius measurement, as the real run rather than a
  prototype: the 7 using `hub/tests/review_evidence.py` and the 8 review/guard/staffing suites
  named in `proposal.md`. 210 tests, all green, or the change is not done.

## 5. Drive it — the proposal is an argument, a drive is the product

- [ ] 5.1 Reproduce `F306` on a live Hub **before** the fix and keep the transcript: a throwaway
  port, a fresh project, two Haiku agents, `scripts/drive/t_row12_review_leg.py` with
  `AW_COMPLETE_BY=untouched`. Read `task_transitions` and `requirement_evidence` from the drive
  database — `F306`'s own note says the drive's assertion passes either way and only those two
  tables tell the states apart.
- [ ] 5.2 Re-run it after the fix. The flow staffs the other agent, and the author's approval is
  refused if attempted by hand. Record the sequence numbers, not a summary.
- [ ] 5.3 Drive the **operator-sees-it** half: a project where the author is the only other agent.
  The firing must surface *"could not staff this step"* naming the task, and the sentence must not
  claim any agent completed it. That sentence is the whole of what the operator gets in place of the
  queue's status histogram, and it is the cost this change knowingly buys.
- [ ] 5.4 Every real agent turn binds `claude-haiku-4-5`. Never leave a job enabled.

## 6. The gate

- [ ] 6.1 `ruff check src/ hub/ tests/`, `black --check src/ hub/hub/ hub/tests/ tests/
  --target-version py311`, `mypy src/`. The CI path list, not a narrower one.
- [ ] 6.2 `py -3.11 -m pytest hub/tests/ -q` from `hub/`. Under `py -3.11`, never bare `python`.
- [ ] 6.3 No migration is added, and `hub/tests/test_migrations.py` head assertions are **not**
  bumped. If a migration appears in the diff, something has gone wrong: `RequirementEvidence`
  already carries all three columns this change reads.

## 7. Close it out

- [ ] 7.1 Set `F306`'s Status line in `scripts/drive/FINDINGS.md` to `fixed <sha>`, and correct the
  two statements R1 measured false: the *"Unverified: whether ordering is deterministic"* note
  (`design.md` D6) and the `kind`-scoping suggestion in its shape-of-a-fix list (`design.md` D5).
  The entry is the ledger; leaving a refuted suggestion in it is how the next round re-proposes it.
- [ ] 7.2 `openspec validate --strict an-agent-that-recorded-the-evidence-is-the-author`, then
  archive with the `openspec-archive-change` skill.
