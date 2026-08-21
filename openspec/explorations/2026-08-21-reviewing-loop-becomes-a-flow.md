# Review — `loop-becomes-a-flow` (2026-08-21)

**Status:** reviewed, not approved — approval is the operator's. 0/60, unimplemented.
**Reviewed:** `proposal.md`, `design.md`, `tasks.md`, and all four spec deltas, in full.
**Reviewer:** the interactive session, alongside run 3. Read only; nothing in the change was edited.

**Verdict: the shape is right and the change should proceed.** The central claim — *a flow is a loop
that declares a document* — survives scrutiny, and the two structural commitments that make it safe
(D2's default-not-mandate, D3's actor-aware claimability rather than widening the status tuple) are
the right calls for reasons the design states correctly. Four findings below; **one is a
contradiction in D4 that will stop a flow resuming its own work**, and the rest are smaller.

---

## 0. Two findings I withdrew, and what that says

Both were written before I had read the whole change, and both were wrong. Recording them because
the pattern matters more than the errors:

- *"§626's collapse rule is not fixed in the delta."* It is —
  `specs/agent-loops/spec.md:27-57` already keys the run on *"the same loop **and belonging to the
  same agent**"*, with a scenario. I had read the current corpus and the exploration's §9 without
  checking the delta.
- *"The design says runner-bound is part of eligibility, but no requirement says so."* It does —
  `specs/agent-flows/spec.md:33-35`, under *A firing determines both the task and the agent* rather
  than under the reviewer-resolution requirement where I was looking, plus a scenario at 43-47, plus
  task 4.3.

Both corrections point the same way: **this change is more careful than a partial reading suggests,
and its requirements are not always filed where you would guess.** A reviewer who samples it will
generate false findings. I did, twice.

---

## 1. FINDING (significant) — D4's rung 2 forbids a flow from resuming its own work

The design's own open question asks: *"Does a flow ever fire the same agent for a task it is already
working? Resumption of an `in_progress` task should keep its agent; nothing says so yet."*

It is worse than unstated. **As written, the ladder makes the only correct agent ineligible.**

- `_claim_loop_task` selects an `in_progress` task first — that is the resume case, and
  `specs/agent-loops/spec.md:81-84` keeps it (*"a firing resumes an item a prior firing left
  unfinished"*).
- D4 rung 2 is *"any agent not running and holding no active task"*, and
  `_ACTIVE_TASK_STATUSES` is `("pending", "assigned", "in_progress", "under_review",
  "revision_needed")`.
- The agent holding the resumed task holds a task in `in_progress`. **It is therefore excluded by
  rung 2**, by the rule's own definition.

So a flow that selects a task for resumption asks the ladder who should work it, and the ladder
answers *"anyone but the agent who is working it"* — either handing live work to a second agent, or,
if no one else is free, reaching rung 3 and reporting it *cannot staff a step that is already
staffed*.

The same shape bites width without resumption at all: firing 1 assigns task A to agent X; in firing
2, X holds an active task and is ineligible for A. The exclusion is deliberate for *selecting new
work* — D4 rejects not-running-alone precisely to prevent the pile-up the operator named — but it is
wrong for *continuing existing work*.

**Fix:** the ladder must not be consulted for a task that already has an assignee. Resumption keeps
its agent; the ladder resolves only unstaffed tasks. That is one sentence in D4, one in the
`agent-flows` reviewer-resolution requirement, a scenario, and a task in group 4. It is not a design
change — it is what everyone already means — but implemented from the current text it produces a
flow that cannot continue anything.

**Related, and I could not resolve it from the text:** rung 1 is a *declared* reviewer. If a task
declares a reviewer that also holds an active task, does rung 1 respect the declaration or fall
through to rung 2? `specs/agent-flows/spec.md:78-80` says fall-through happens where the declaration
*"does not resolve"*, which reads as "names nobody in this project" rather than "names someone
busy". If a declared reviewer being momentarily busy silently reassigns the review to whoever is
idle, the declaration is much weaker than `task-dependencies` D11 implies. Worth one scenario either
way.

## 2. FINDING (real, small) — task 10.1 records a baseline that is an artefact

> 10.1 `pytest hub/tests/ -q` passes, with the three pre-existing `test_pty_runner` environment
> failures unchanged and no new failures.

There are no such failures. Handoff 0069 established that those three are an **interpreter
artefact**: `python -m pytest` (the hermes venv) fails 3 and skips 13; `py -3.11` — what the
autonomous driver uses — passes all 29 and skips 84. The previous session called them "pre-existing
environment failures" twice before measuring it.

Written as it is, 10.1 tells a future worker that three reds are normal. The two ways that goes
wrong are a worker accepting three real failures, or a worker switching to the venv interpreter to
reproduce the stated baseline and inheriting an unrelated environment.

**Fix:** state the interpreter and drop the exemption — *"`cd hub && py -3.11 -m pytest tests/ -q`
passes with no failures"*. Same for 10.2.

## 3. FINDING (real) — width multiplies a defect the change inherits, and 5.4 does not cover it

Task 5.4 requires that a dropped selection be *"visible rather than silent"* — but it is scoped to
design D6, one agent resolving for two tasks in one firing. That is a **selection-time** drop.

There is a second drop, at **delivery** time, and width multiplies it. Per
`2026-08-21-what-a-flow-fires-into.md` §2: `scheduler.py:1015` discards `schedule_agent`'s
`ScheduleResult`, so a selection that queued but never started leaves its `JobRun` at `in_progress`
and the loop card reading *firing* indefinitely. A serial loop strands one firing that way. **A flow
starting N tasks per firing strands up to N**, and the operator's only signal is a card that says
more work is happening than is.

`schedule_agent` refuses for reasons the ladder does not screen: *"agent is already running"* (D4's
own cross-firing race risk), hop budget, token budget, workspace unavailable. Runner-bound is now
screened at selection — that is exactly the fix, applied to one of five reasons.

**Fix:** extend 5.4, or add a task to group 5, requiring that a selection which does not start is
recorded and surfaced as a *not-started selection*, with its reason — which `ScheduleResult` already
carries. This is the cheapest of the four fixes here and the one that makes wide flows debuggable at
all.

## 4. OBSERVATION — D3's framing is also the answer to `blocked`, and the two changes touch one line

D3's move is that **claimability becomes a question about `(task, agent)` rather than about status
alone**, and task 3.3 guards it: *`CLAIMABLE_LOOP_TASK_STATUSES` does not gain `completed`.*

`2026-08-21-which-band-blocked-belongs-to.md` answers `loop-notices-and-reacts` task 3.4 with a
finding in the same shape: `blocked` should *leave* that tuple, because a task in `blocked` has an
unanswered question and **no** agent can advance it. D3 says *some* agents can claim a `completed`
task; the `blocked` answer says *no* agent can claim a blocked one. Both are the same generalisation
— *claimability is about whether this agent can make progress on this task* — and status alone
cannot express either.

Not a defect in this change. Two consequences worth acting on:

- **Sequencing.** The proposal already says building against the four-set world means rewriting
  immediately. Group 3 of `loop-notices-and-reacts` is where `blocked` is decided, and it edits the
  same tuple group 3 here reads. Land the vocabulary first, as both changes already say.
- **Group 3 could absorb it.** If `(task, agent)` claimability is being built anyway, *"nobody, while
  a question is unanswered"* is a case of it rather than a separate mechanism. Worth deciding
  deliberately rather than discovering the overlap during implementation.

## 5. Smaller notes, no action required

- **Task 10.6 is the best task in the change** — running the 20 unmodified `agent-loops` scenarios
  against the flow implementation *rather than assuming*. That is what makes "20 of 25 untouched"
  a verified claim instead of an audit's opinion. It should not be dropped if the change is cut down.
- **Group 1's ordering is right and load-bearing.** A set-valued claim of one, with the existing
  suite unmodified, is the correct safety net; D3 does not disturb it, because in a single-agent loop
  the author is the only agent, so a `completed` queue still stalls and the 2026-08-20 spin test
  still passes. I checked this specifically, expecting a conflict, and there is none.
- **`blocked` and rung 2.** `_ACTIVE_TASK_STATUSES` excludes `blocked`, so an agent holding only
  blocked tasks reads as free and is eligible. That is defensible — it genuinely has no work it can
  do — and it is untested. One line in task 4.2 would pin it.
- **Non-goals are stated rather than omitted**, including the two the operator withdrew. That is why
  this review could check the change against decisions rather than guessing at them.

## 6. What I did not do

- **Nothing was run.** No test in this change exists; the review is of text against source I read
  today.
- **`task-dependencies` D11's reviewer field was not read**, so finding 1's "related" paragraph about
  declared-but-busy reviewers may already be answered there.
- **The 20 untouched `agent-loops` requirements were not re-audited.** I took the count from the
  exploration's §3 rather than re-deriving it.
- **`loop-notices-and-reacts` was read only where it overlaps** — group 3.
