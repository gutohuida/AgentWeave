# Tasks — an agent that recorded the evidence is the author

Implementation is a night window's. Nothing here is complete on the strength of this plan existing;
only verified implementation closes a task.

**This change is Python-only.** No UI file is modified, so the committed bundle in
`hub/hub/static/ui` is **not** rebuilt — and the Python lint set *is* required (§6).

**It repairs three defences across five call sites, and must be verified as all five.** The ladder
half (§1, §2) is what the operator sees; the guard half (§3) is the one nobody sees. R1 believed the
two `scheduler.py` call sites were the whole of it; R2 found two more — `review_dispatch_refusal`
(§3.5) and `_answer_failed_review` (§2.4) — and each of those is a place where the guard's new
refusal would otherwise arrive *after* a review turn has already run. A run that closes §1–§3.3 and
reports the change done has left the change breaching two requirements that shipped before it
(`design.md` D8). The half it is most tempting to skip is the guard, because no test fails for its
absence today.

**The fifth call site was added by R4 and reverses what all three rounds agreed on** (`design.md`
D14): `_guard_reviewer_is_not_the_author` (§3.4) guards the *entry* to `under_review`, so it sat
outside D8's resolver-shaped frame and every round ruled it out of scope without asking what §3.1
did to it. Permitting the entry while refusing every exit strands the task permanently, held by an
agent no transition names, reported as a review in progress and never restaffed. **§3.4 is not
optional and it is not polish: without it this change manufactures the failure class it exists to
remove.**

## 1. The fourth source

- [x] 1.1 In `hub/hub/task_transition_service.py`, add
  `agents_that_recorded_evidence_for(session, task_id) -> set[str]`, immediately before
  `agents_that_may_have_authored`, beside the other two term functions. Select
  `RequirementEvidence.actor` distinct, filtered to `task_id == task_id`,
  `actor_kind == "agent"`, and a non-empty `actor`; drop falsy values on the way out as the other
  two terms do.
- [x] 1.2 Add `RequirementEvidence` to the existing `from .db.models import …` line. Confirm no
  import cycle appears (`py -3.11 -c "import hub.task_transition_service"`): `db.models` is already
  imported by this module, so this is a name on an existing import, not a new edge.
- [x] 1.3 Docstring it with **why each filter is there**, from `design.md` D2 — that `actor_kind`
  is what keeps the operator's own evidence out of an exclusion of agents and what preserves the
  untouched-task case, and that `review_state` is deliberately *not* filtered. A reader's first
  instinct will be to add `review_state == 'accepted'`; the docstring is what stops them.
- [x] 1.4 State in the docstring that this term has **three** consumers — the union (§2.1), the
  transition guard (§3.1) and the dispatch refusal (§3.5) — and that the last two use it **alone**,
  never through the union (`design.md` D1/D3/D8). Without that sentence the next reader folds it
  into the union and deletes the function.

## 2. The union, the two call sites that inherit the fix, and the one that does not

- [x] 2.1 `agents_that_may_have_authored` unions the new term with the existing three.
- [x] 2.2 Update that function's docstring table — it enumerates three sources by name and says
  *"Three sources for one question is not elegant"*. A fourth row: **evidence** names *every agent
  that asserted authorship of it*, and misses *work nobody recorded evidence for*. The docstring is
  the load-bearing statement of the principle this change extends, not decoration.
- [x] 2.3 Confirm by reading, not by assuming, that `hub/hub/scheduler.py:625`
  (`task_is_claimable_by`) and `hub/hub/scheduler.py:1574` (the review-staffing arm) both call the
  union and need **no edit**. If either turns out to recompose the terms, stop: that is the drift
  the union's own comment says must not exist, and it is a finding.
- [x] 2.4 **`hub/hub/run_divergence.py` — the third composition, which is the drift 2.3 looks for
  and finds somewhere else** (`design.md` D8, `F316`). `_answer_failed_review` builds its own
  exclusion from `agent_that_completed` alone. Replace that one term with the two-branch derivation
  call sites 1 and 2 share: `completion_attribution`, then `agents_that_may_have_authored` where no
  agent completed. Keep the silent reviewers and `run.agent` as they are — those are facts about
  the review, not about authorship. **Call the union; do not add a fourth term here.** Four call
  sites composing the same question three ways is what made this change need two of them edited.
- [x] 2.4a **Pass `excluded_because="has worked on this task"` on that same branch** — R3, and it is
  the half of 2.4 that reaches the operator. `_answer_failed_review` calls `resolve_reviewer`
  without the argument, so it takes the default *"is the one that completed this task"*. Widening
  the exclusion without widening the reason makes the ladder surface that sentence about a task the
  **operator** completed, which `agent-flows:552-558` forbids in terms — *"A surfaced reason SHALL
  NOT state that an excluded agent completed the task where no agent completed it … Where the
  exclusion is the set of agents that worked the task, the reason SHALL say so"* — and which that
  requirement's own shipped scenario (*"The surfaced reason does not claim an agent completed the
  work"*) already tests one call site along. `resolve_reviewer`'s `excluded_because` parameter
  exists for exactly this and says so (*"it is a parameter because it is not always the same
  reason"*, design D13 of the change that added it); call site 2 switches it at
  `scheduler.py:1555/1575` and call site 4 never learned to. Measured against a prototype of 2.4 without it: the
  `run_diverged` event carried *"…or is the one that completed this task and so may not review
  it"* on an operator-completed task, at `severity="warn"`, which is the whole of what the operator
  is shown. Keep the default on the `attribution.agent is not None` branch, where an agent really
  did complete it.
- [x] 2.5 Correct that function's docstring, which currently asserts the invariant this breaks:
  *"an escalation target that authored the work is a guaranteed 403 from `agent_that_completed` —
  cannot arise here at all, because the resolver already excludes the author by construction."* The
  resolver excludes what its caller passes, and until 2.4 this caller passed nothing about the
  author on the operator-completed arm. Say what it passes now and why.

## 3. The guard, falling back to the evidence actors alone

- [x] 3.1 In `_guard_author_is_not_reviewer`, where `agent_that_completed` returns `None` and the
  actor is an agent, refuse when that agent appears in `agents_that_recorded_evidence_for`.
  **The fallback is that term alone and never `agents_that_may_have_authored`** — `design.md` D3
  and the measurement in `proposal.md` §3. Falling back to the union refuses the flow's own
  reviewer on every operator-completed task.
- [x] 3.2 The refusal names the evidence as the reason. The existing message pattern in this
  module states the record it read and what the asker must do instead; match it, and do not reuse
  the completion sentence — no agent completed this task, and a message saying one did is the class
  of untruth `agent-flows`' surfaced-reason requirement already forbids one layer up.
- [x] 3.3 Keep the operator exempt and keep `_REVIEW_OUTCOMES` as the gate. Both are the existing
  first two lines of the guard; the fallback goes **after** them, not before.
- [x] 3.4 **`_guard_reviewer_is_not_the_author` takes the same fallback** — reversed after R3
  (`design.md` D14). Where `agent_that_completed` returns `None` and `task.assignee` recorded
  evidence for the task, refuse the move to `under_review`. It is still a different rule about a
  different fact — the state the move produces, binding the operator too — and it keeps its own
  message and its own shape. What changed is that its permissive `None` branch stopped being safe
  the moment §3.1 began refusing the same agent's verdict: entry permitted plus every exit refused
  is a task no actor can move, held by an agent no transition names, which the flow reports as a
  review in progress and never restaffs. Fail-closed at the entry is the whole point of the guard.
- [x] 3.4a The fallback is `agents_that_recorded_evidence_for` **alone**, exactly as §3.1's is, and
  for the same reason: the union would refuse the flow's own reviewer on every operator-completed
  task. It cannot refuse the flow's path — §2.1 guarantees the staffed reviewer is never an
  evidence author — and it binds the operator, which is this guard's existing character and is the
  right outcome: the operator is told before a turn is spent, and the remedy is the one the
  existing message already names. Keep the two permissive cases the requirement keeps: no assignee,
  and a no-completer task whose assignee recorded nothing.
- [x] 3.4b Amend the guard's docstring. Its "**No recorded completer**" bullet currently states the
  refuse-to-offer/permit-to-act asymmetry as unconditional; it is now conditional on the assignee
  having recorded no evidence, and the docstring must say why — acting is no longer possible for an
  evidence author, so permitting the entry strands the task rather than freeing it.
- [x] 3.5 **`hub/hub/api/v1/agent_trigger.py` — `review_dispatch_refusal` takes the same fallback**
  (`design.md` D8). Where `agent_that_completed` returns `None` and the named reviewer recorded
  evidence for the task, return `403` with a sentence naming the evidence. After the status and
  holder checks, in place of the completer comparison's silent `None` branch, so the ordering of
  refusals an operator meets is unchanged. **This is not optional polish:**
  `task-lifecycle-governance:1719-1722` requires a review that cannot be staffed to be refused
  *before a turn is started*, and without it the turn runs and the verdict is refused afterwards.
- [x] 3.6 Check, and state in the commit, that the refusal at 3.5 and the refusal at 3.1 read as
  two statements of one rule rather than two rules. `review_dispatch_refusal`'s docstring says it is
  *"the read-only half"* of what the transition layer would refuse and *"must not drift from it"*;
  a fallback added to one and not the other is that drift arriving by the door the docstring names.

## 4. Tests, mutation-checked because nothing existing fails today

> **Mutation hygiene — read before §4.7, and before any other task that reverts code.** This window
> commits and pushes at the end of every firing, and §4.7, §4.9, §4.10, §4.10a and §5.1 all require
> a tree with the fix deliberately removed. An iteration boundary or a context death landing inside
> one of those cycles pushes the hole reopened, under a commit message saying it is closed — on a
> change whose entire subject is a failure nobody can see.
>
> So: **commit the complete implementation before the first mutation.** Perform every mutation and
> its restore **inside a single firing** — never across one. After each restore, run
> `git status --short` and require it empty before anything else happens; if it is not empty, the
> restore is incomplete and nothing may be committed until it is. If a firing is running out of
> room, stop *before* starting the next mutation rather than partway through one, and record in the
> log which mutations remain.

The blast-radius measurement over the **whole** suite (`proposal.md`) found **one** existing test
whose expectation changes (§4.11) and nothing else — 1 failed, 4044 passed. Read that as a warning
rather than a reassurance: near enough the whole of this change's coverage is new, and a new test
that would pass against the unfixed tree is worth nothing. R1's narrower measurement found zero, so
do not treat a green file list as evidence of anything here.

- [x] 4.1 New file `hub/tests/test_the_evidence_names_the_author.py`, with `F306`'s live
  reproduction in its module docstring including the run and task ids.
- [x] 4.2 The ladder leg: an operator-completed task, one agent-authored evidence row naming a
  commit, two free agents with the author sorting **first** by name. Assert the flow staffs the
  other agent. The name order is load-bearing — `design.md` D6 — and a fixture where the author
  sorts second passes against the unfixed tree.
- [x] 4.3 The guard leg: the same shape, with the author moving the task to `approved` directly.
  Assert `ActorNotPermittedError`, that the task's status is unchanged, and that no transition was
  recorded.
- [x] 4.4 The reviewer-is-not-refused leg: the agent the flow staffed records `approved` and is
  **accepted**, with `task.assignee` equal to that reviewer at the moment it does. This is the
  regression test for `design.md` D3, and it is the one that fails if a later change "simplifies"
  the fallback to the union.
- [x] 4.5 The operator-evidence leg: evidence recorded with `actor_kind='operator'` leaves every
  agent eligible. `F306`'s own untouched-task carve-out, and the test for the `actor_kind` filter.
- [x] 4.6 The `review_state` leg: evidence in `awaiting` and evidence in `rejected` each exclude
  their author. This is the operator's verdict in executable form, and the thing a future
  simplification is most likely to break.
- [x] 4.6a **The entry leg** (§3.4): an operator-completed task, an agent-authored evidence row, and
  a single `PATCH` setting `assignee` to that evidence author and `status` to `under_review`.
  Assert `ActorNotPermittedError`, that the status is unchanged, and that the refusal does not claim
  any agent completed the task. Then the permissive half in the same leg: the same move with a
  **different** agent as assignee succeeds, which is the flow's own path and must not be refused.
  This leg fails against a tree carrying §1–§3.3 alone — that is the wedge D14 exists for, so run it
  against that tree as well as the finished one and record both.
  *Measured 2026-09-12:* green on the finished tree; with the §3.4 fallback removed it fails at the
  refusal (`DID NOT RAISE`); with that fallback read through the union it fails at the permissive
  half (`ev-reviewer` refused, `403`).
- [x] 4.7 **Mutation-check every leg.** Revert each of §1–§3 in turn and record which legs fail:
  remove the union term (4.2 must fail), remove the guard fallback (4.3 must fail), change the
  fallback to the union (4.4 must fail), drop the `actor_kind` filter (4.5 must fail), add
  `review_state == 'accepted'` (4.6 must fail), remove the §3.4 entry fallback (4.6a must fail),
  and change **that** fallback to the union (4.6a's permissive half must fail, because the flow's
  own reviewer would then be refused at the entry). A leg that survives its own mutation is not
  testing what it claims — fix the fixture, do not weaken the claim. Write the table into the log.
  *Measured 2026-09-12, ten mutations in one firing, tree clean after each restore:* every target
  leg failed under its own mutation and none survived, so no fixture changed. Table in
  `.claude/autonomous/2026-09-11-night-log.md`, iteration 4.
- [x] 4.8 Re-run the whole Hub suite, not a file list: `py -3.11 -m pytest tests/ -q` from `hub/`.
  R1 measured 15 files and 210 tests against a prototype and concluded no existing expectation
  changes; R2 re-measured over the whole suite (`proposal.md`, R2-D). A file list chosen by name is
  a guess about which suites reach this code, and the two call sites R1 missed are what that kind of
  guess costs. **What R2's whole-suite run did NOT cover:** its prototype was §1–§3.4
  only. The blast radius of §2.4 (`run_divergence`) and §3.5 (`review_dispatch_refusal`) is
  **unmeasured** by R2 — `hub/tests/test_review_dispatch_staffs_the_task.py` and the divergence
  suites are the obvious places to look, and the implementing run measures it rather than assuming
  R2's number covers code R2 did not patch. **R3 measured that gap and it is 88 passed, 0 failed**
  (`test_review_dispatch_staffs_the_task.py`, `test_run_divergence.py`,
  `test_review_divergence.py`, `test_flow_divergence_regime.py`,
  `test_a_flow_names_what_it_cannot_staff.py`, 102s, against a prototype of §1, §2.1, §2.4, §3.1
  and §3.5). Read it the way R2 taught: **88 green is the reassurance that hid 2.4a.** The sentence
  the operator is shown became untrue and every one of those suites stayed green, because no test
  asserts on it. A whole-suite run is still required here; five files are not a suite.
  *Measured 2026-09-12 on `99d64fc`, the finished tree:* **4057 passed, 86 skipped, 0 failed, 0
  errors**, 27m06s. So R4's §3.4 reversal moved no expectation beyond 4.11 and 4.11a, and neither
  known intermittent (`F314`, `F292`) fired this run. The count agrees with the proposal's arithmetic
  (4044 + 1 repaired + 12 new = 4057). That is consistent with, not proof of, an unchanged suite.
- [x] 4.9 **The dispatch leg** (3.5): `POST /agent/trigger` naming the evidence author as reviewer
  of an operator-completed task answers `403`, the task's status and holder are unchanged, and **no
  checkout was created** — `task-lifecycle-governance`'s *"A refused review leaves nothing
  provisioned"*. Mutation: remove the 3.5 fallback and this leg must fail; if it passes, it is
  asserting the status code and not the ordering.
  *Measured 2026-09-12:* it fails, and **only on the holder** — the `403`, the evidence sentence and
  the unprovisioned checkout all survive the mutation, because the scheduler's own refusal is
  answered as `403` (F108) and its session commits the staged assignee (filed as F319).
- [x] 4.10 **The silent-review leg** (2.4): an operator-completed task, an agent that worked it
  without moving it, a staffed reviewer whose turn ends with no verdict. Assert the re-resolution
  does **not** pick the worker. This is `F316` in executable form and it fails against today's tree
  as well as against a tree with only §1–§3 applied — so run it against both and record which.
  **Both halves were driven by R3 and the numbers are the target:** against today's tree the
  divergence is `restaffed`, `task.assignee` becomes the worker and a `divergence` entry is queued
  to it; against the prototype the divergence is `surfaced`, the assignee stays the silent reviewer
  and nothing is queued. Assert those, not merely that the worker is absent from a list.
  *Measured 2026-09-12:* with `_answer_failed_review` restored to its pre-fix composition
  (`agent_that_completed` alone, default reason) the outcome is `restaffed`. "Today's tree" cannot
  be run literally — the file does not import at `37b8226` — so that restoration on the fixed tree is
  the stand-in for both halves: nothing else in the fixed tree reaches this exclusion.
- [x] 4.10a **The reason leg** (2.4a): the same fixture with nobody left to staff. Assert the
  `run_diverged` event's `reason` says the excluded agents **worked on** the task and does **not**
  say any agent completed it. Mutation: drop the `excluded_because` argument and this leg must
  fail. It is the only leg that fails for 2.4a's absence — R3 ran the five obvious suites against a
  prototype **without** it and got 88 passed, so nothing existing defends this sentence.
  *Measured 2026-09-12:* with the argument dropped the reason reads *"…or is the one that completed
  this task and so may not review it"* and the leg fails on `has worked on this task`.
- [x] 4.11 **Repair the one existing test whose expectation this change moves**, and repair it the
  right way. `tests/test_approval_refuses_unaccepted_evidence.py::test_the_agent_plane_sees_the_refusal`
  walks a task to `under_review` with the **operator's** key, has `builder` record the evidence, and
  asserts `builder`'s `approved` request answers `409` (evidence not accepted). After §3.1 it
  answers `403` (author) first. **Give the approval to a second agent that recorded no evidence**;
  do not relax the guard, do not special-case the fixture, and do not change the assertion to `403`
  — the test exists to prove the *evidence* refusal reaches the agent plane, and an assertion on a
  different refusal proves nothing about that. Leave a comment saying why the approver is not the
  agent that recorded the evidence, naming `F306`: the fixture as written **is** `F306`'s
  precondition, and the next person to simplify it will put the author back.
- [x] 4.11a **The second moved expectation, which R2's "exactly one" could not see** (added by the
  implementing night run, 2026-09-11). R2's whole-suite number was measured against a prototype of
  §1–§3.4 when §3.4 still read *"do not touch `_guard_reviewer_is_not_the_author`"*; R4 reversed
  §3.4 into a fallback and did not re-measure, so R4's blast radius was unmeasured. The 20-file
  baseline chunk found it: `tests/test_a_flow_names_what_it_cannot_staff.py::
  test_an_operator_completed_task_wedged_in_review_is_restaffed` built its wedge with an operator
  hand move into `under_review` while the task was assigned to `builder` — and `builder` had also
  recorded the task's evidence, so §3.4 now refuses that entry (`ActorNotPermittedError` at the
  fixture's own `apply_transition`, 1 failed / 439 passed). That refusal is D14 working. The test's
  claim is the wedged-review branch's *recovery*, and the wedge that can still form is an assignee
  named on the transitions that recorded nothing — so the evidence became the **operator's**
  (`_evidence` gained an `actor_kind` keyword) and the claim is unchanged, with a docstring naming
  `F306` so the author is not put back. File green, 24 passed. §4.8's whole-suite run is still the
  measurement of record; this is one chunk's finding, not a census.

## 5. Drive it — the proposal is an argument, a drive is the product

- [x] 5.1 Reproduce `F306` on a live Hub **before** the fix and keep the transcript: a throwaway
  port, a fresh project, two Haiku agents, `scripts/drive/t_row12_review_leg.py` with
  `AW_COMPLETE_BY=untouched`. Read `task_transitions` and `requirement_evidence` from the drive
  database — `F306`'s own note says the drive's assertion passes either way and only those two
  tables tell the states apart.

  **"Before the fix" is not where this run is standing, and this task is ordered after §1–§4.** Get
  a pre-fix tree explicitly rather than hoping: `git worktree add ../aw-f306-prefix <sha>` at the
  commit **before** §1's, drive there, and remove the worktree afterwards. Do **not** use
  `git stash` in this window — a stash that survives a context death is invisible to the next
  firing, which will find a clean tree with the fix missing and no record of why.

  **The green here is the trap.** The drive's assertion passes on both trees, so a run that
  accidentally drives the *fixed* tree gets exactly the result it expects and records a
  reproduction that never happened. The only proof is the two tables: on the pre-fix tree the
  approving transition exists and its `actor_agent` is the evidence author. If you cannot show that
  row, you have not reproduced it — say so in the log and leave 5.2 unticked rather than reporting
  a pair.

  **Done 2026-09-12 (night iteration 7), proven from the tables, on the second of two attempts.**
  Pre-fix worktree at `37b8226` (`hub` imported from inside it, `agents_that_recorded_evidence_for`
  absent), port 8014, profile `drive0912p`, Haiku. **Attempt 2**, `proj-34d006e2f3e5`,
  `task-9ba36b0bd788`: seq 5–7 `pending→in_progress→completed→under_review` all
  `actor_kind='operator'`, `actor_agent` NULL; **seq 8 `under_review→approved`, `actor_kind='run'`,
  `actor_agent='r7af306q'`, `run-bb80909c0e15`**; `ev-4d13beb472c4` `implementation`, `accepted`,
  **`actor='r7af306q'`**, recorded on `run-1a7f8b790e34` whose `task_id` is NULL. The drive printed
  19/19, as predicted. **Attempt 1** (`proj-7a9ec0f070ba`, `task-11fd55c52ee1`) did **not**
  reproduce the approval: the flow staffed the evidence author `r7af306p` as reviewer
  (`run-b9d360b2d62c`), which ran `ToolSearch` for `update_task` twice and never called it; the
  silent review was restaffed (`div-c524b3378859`, `restaffed`) and seq 4 `under_review→approved` is
  `r7bf306p`'s. Staffing reproduced 2/2, approval 1/2. Transcripts beside the kept database in
  `profiles/drive0912p/n6-transcripts/`.
- [x] 5.2 Re-run it after the fix. The flow staffs the other agent, and the author's approval is
  refused if attempted by hand. Record the sequence numbers, not a summary.

  **Done 2026-09-12 (night iteration 8), from the tables.** Fixed tree from the main checkout at
  `cddf32b`, port 8015, profile `drive0912`, PID 17692 started 01:01:25 with no `.py` under
  `hub/hub` or `src` newer. `proj-192ee0e59efb`, `task-88efa63d19ee`, author `r7af7a` (sorts
  first): `ev-b6a5a19738e9` `implementation`, `actor='r7af7a'`, on unbound `run-1feb9dc376f2`;
  seq 1–3 `pending→in_progress→completed→under_review` all `operator`; the **first and only run
  bound to the task is `run-1d7e3883437a`, agent `r7bf7a`, initiator `autonomous`**, and
  `run_divergences` is empty for the task — so this is firing 2's own staffing, not a restaff;
  **seq 4 `under_review→approved`, `actor_kind='run'`, `actor_agent='r7bf7a'`,
  `run-1d7e3883437a`.** Drive 19/19. The pre-fix tree staffed the author 2/2 on the same fixture
  shape (5.1). **The author's approval by hand**, on 5.3's task `task-714b1ea52e2e` (evidence
  `ev-36b8d06a09fd`, `actor='r7af7b'`): operator seq 7 `completed→under_review` with no assignee,
  then `r7af7b` triggered unbound (`run-cee1b5540146`) called
  `mcp__agentweave__update_task(status='approved')` on the first attempt and was answered **403**
  *"agent 'r7af7b' recorded evidence for this task … No agent is recorded as completing it"*;
  status stayed `under_review`, no seq 8.
- [x] 5.3 Drive the **operator-sees-it** half: a project where the author is the only other agent.
  The firing must surface *"could not staff this step"* naming the task, and the sentence must not
  claim any agent completed it. That sentence is the whole of what the operator gets in place of the
  queue's status histogram, and it is the cost this change knowingly buys.

  **Done 2026-09-12 (night iteration 8).** `proj-99af62baca17`, `task-714b1ea52e2e`, only `r7af7b`
  bound. Firing 2 answered **409** *"could not staff this step: no agent is free to take it. Every
  agent on the roster is either running a turn, already holding active work, or has worked on this
  task and so may not review it."* — the same sentence as the loop's `stall_reason`. It does not
  say *completed*. **The sentence names "this task", not its id; the id reaches the operator on
  `review_unstaffed` (`evt-c52509784f8b`, `task_id: task-714b1ea52e2e`, same reason)** — the
  split `a-review-a-flow-cannot-staff-is-named` shipped, not a gap here. By hand on the same task:
  the **S3.5** dispatch (`POST /agent/trigger`, `agent=r7af7b`, `review_task_id`) → **403**, no run,
  no queue entry, no new worktree; the **S3.4** wedge (`PATCH assignee=r7af7b,
  status=under_review`) → **403**, status `completed` and assignee `None` afterwards, no
  transition. Drive 13/13.
- [x] 5.4 Every real agent turn binds `claude-haiku-4-5`. Never leave a job enabled.

  **Held 2026-09-12 (night iteration 8).** All four runs in `drive0912` joined to their runner:
  `claude-haiku-4-5-20251001`. `GET /jobs` is `[]` on both projects; `ai_jobs` holds both jobs
  `enabled=0` with `archived_at` set; `apscheduler_jobs` is empty. (5.1's `drive0912p` was checked
  the same way in iteration 7.)

## 6. The gate

- [x] 6.1 `ruff check src/ hub/ tests/`, `black --check src/ hub/hub/ hub/tests/ tests/
  --target-version py311`, `mypy src/`. The CI path list, not a narrower one.
  *Measured 2026-09-12 on `99d64fc`, all under `py -3.11 -m`:* ruff `All checks passed!`, black
  `565 files would be left unchanged`, mypy `no issues found in 22 source files`. The change touches
  no `hub/ui` file, so CI's `npm run lint` is not in this change's reach.
- [x] 6.2 `py -3.11 -m pytest hub/tests/ -q` from the **repo root** — or `tests/` from `hub/`, which
  is the same suite. `hub/hub/tests` does not exist, so `hub/tests/` from `hub/` errors. Under
  `py -3.11`, never bare `python`.
  *Measured 2026-09-12:* the same run as 4.8 (`tests/` from `hub/`), 4057 passed, 0 failed.
- [x] 6.3 `openspec validate --strict an-agent-that-recorded-the-evidence-is-the-author` after every
  delta edit, not only at the end.
  *Measured 2026-09-12:* `is valid`. No delta has been edited since the approval. §7.2 runs it
  again, with `--specs --strict`, after the hand sync.
- [x] 6.4 No migration is added, and `hub/tests/test_migrations.py` head assertions are **not**
  bumped. If a migration appears in the diff, something has gone wrong: `RequirementEvidence`
  already carries all three columns this change reads.
  *Measured 2026-09-12:* `git diff 37b8226.. -- hub/hub/migrations` is empty, and so is the diff of
  `test_migrations.py` and `test_project_persistence.py`.

## 7. Close it out

- [ ] 7.0 Set `F316`'s Status line to `fixed <sha>` as well, and say which task closed it (2.4).
  It was filed by this change's R2 and is closed by it; a finding left open because it was fixed
  inside somebody else's change is how the ledger grows entries nobody can resolve.
- [ ] 7.1 Set `F306`'s Status line in `scripts/drive/FINDINGS.md` to `fixed <sha>`, and correct the
  two statements R1 measured false: the *"Unverified: whether ordering is deterministic"* note
  (`design.md` D6) and the `kind`-scoping suggestion in its shape-of-a-fix list (`design.md` D5).
  The entry is the ledger; leaving a refuted suggestion in it is how the next round re-proposes it.
- [ ] 7.2 `openspec validate --strict an-agent-that-recorded-the-evidence-is-the-author`, then
  archive with the `openspec-archive-change` skill.
