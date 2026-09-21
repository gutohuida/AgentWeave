# Design — a loop staffs the agent it names

**Round 1, 2026-09-19.** Explored against the tree at `ddf73aa`.
**Round 2, 2026-09-19 — adversarial, independent, returned DO NOT APPROVE with five blocking
findings. All five were verified at the source before being accepted. Round 3 applied every one.**
**Round 4, 2026-09-19 evening — a second adversarial pass, run because R1 and R3 were the same
session. It also returned DO NOT APPROVE, with eight blocking findings; six were re-verified at the
source and all six held. This document is R4-applied.** The round log is at the bottom; read it
before re-proposing anything this document rejects.

**Read this before starting another round.** Four passes have now found a defect each, and three of
the four were the *same* shape: an artifact of this change contradicting another artifact of this
change, while each one reads correctly alone. R2-3 (requirement in the wrong capability), R4-1
(proposal citing the design that refutes it), R4-2 (two requirements governing one sentence), R4-3
(D9's fix applied to prose but not to its own scenarios), R4-5 (the spec's exception not reaching
what a task asserts) are all that shape. `openspec validate --strict` passes through every one of
them, because it checks each requirement alone. **A round that only re-reads the design will not
find the fifth. Compare the artifacts against each other, and against the code.**

R2's summary of R1 is the thing to carry: *"The argument is right; three of the four things built on
it are not."* The conformance framing survived. D5 was false, the ADDED requirement was falsified by
two code paths the change does not touch, it was written into the capability that exempts
documentless loops from it, and the ordering premise contradicted a correction made the same
afternoon.

## Context

`_agents_that_are_free(session, project_id)` (`hub/hub/scheduler.py:1064`) answers *may a flow give
this agent work*: a non-archived agent with a runner bound, not running, not held by a provider
allowance, and holding no task anything will move. It is **project-scoped**, and
`grep -n "await _agents_that_are_free("` returns `:348`, `:1263`, `:1444` and nothing else.

Design **D12** of `loop-becomes-a-flow` narrowed the old whole-firing busy guard so a flow could
staff a second agent for independent work while its job's agent was mid-turn. That was right for a
flow. It was implemented project-wide, and `_loop_flow_busy_reason`'s own docstring records the
consequence (`:335-338`):

> Where neither holds, the pool is **project-scoped**, so a loop naming one agent is not
> single-agent as far as this guard can tell: a documentless loop whose agent is mid-turn can hand
> its next pending task to a free sibling (finding F128, the operator's open decision).

**The corpus never permitted that**, and R2 re-derived the reading independently and agreed.
`agent-flows:14-15` says a loop declaring no document "SHALL be unaffected by them and SHALL behave
exactly as it does today", and its scenario at `:27-28` says *"WHEN a loop declares no specification
document THEN every firing fires the job's own agent, as before"*. It is unconditional, it names the
agent fired, and nothing in either capability qualifies it.

Two facts make the departure matter rather than merely differ. An `Agent` row carries
`charter_id` (`hub/hub/db/models.py:219`), `runner_id` (`:216`) and
`can_read_checkpoints`/`can_recall`/`can_accept_evidence` (`:254-268`), so a substitution swaps
behaviour text, runner and authority together. And nothing tells the operator: `AIJob.agent`
(`:1303`) is presented by the job form and the loop list as who runs this loop.

## Goals / Non-Goals

**Goals:**

- A documentless loop staffs unassigned work with the agent its job names, or with nobody.
- A flow is bit-for-bit unchanged, including its width.
- The narrowing is a **scope filter over availability**, never a new rule about whether an agent can
  take a turn.
- Every operator-visible sentence that today says *"no other agent is free"* stops saying it where
  it is no longer the reason.

**Non-Goals:**

- Re-homing tasks a past substitution already assigned (D6).
- Narrowing the F70 wedged-review recovery (D5).
- Giving a flow a roster of its own.
- A per-job width flag — a flow already *is* the width case.
- Any UI change.
- F127's status code, already fixed in `c8e3bbd`.

## Decisions

### D1 — The narrowing is a new named question, not a parameter on `_agents_that_are_free`

Add `_agents_a_loop_may_staff(session, loop)` to `scheduler.py`. It calls the existing availability
read and filters its result; it computes no availability of its own.

*Why not a `limit_to=` parameter:* `_agents_that_are_free` answers a question about a **project**
and knows nothing about loops. Its docstring draws exactly this line — *"The roster and the pool
differ on purpose (design D5) … They were never the same question"* (`:1089-1092`).

*Why not filter inline at each call site:* the rule would exist in two places and could drift.

**R2-8: no `default_agent` parameter.** R1 specified one; D2 then made the documentless branch
return `[]` and the flow branch return the pool unchanged, so nothing reads it. An unused parameter
in a function about *which agents* invites a future reader to add the named agent to the result.

### D2 — For a documentless loop the pool is **empty**, not `{job.agent}`

The job's own agent never comes from the pool. `decide_firing`'s ordinary-work arm reaches the
default agent through its own branch (`:1601-1618`), tested against `running`, `held_agents` and
`taken` and **deliberately not** against the pool; the comment at `:1609-1616` names the test that
caught the alternative.

**R2 verified the equivalence and corrected the stated condition.** R1 said the pool is read
"exactly when the default agent is already taken, running or held". It is also read when the default
agent is perfectly free and merely **already spent this firing** (`default_taken`) — which is the
width case, so the conclusion holds and the premise did not. In the running/held/taken cases the
named agent is excluded from `free` by construction (`:1114-1122` ORs `running` with `agents_held`;
`:1166` filters both), and in the `default_taken` case selecting it again would breach design D6. At
`:348` the equivalence is tighter still: the guard reads the pool only after
`_loop_agent_busy_reason` returned non-`None`, so the agent is running or held and absent from
`free` anyway.

**What this removes, deliberately: width for loops.** A documentless loop with two startable,
**unassigned** tasks and a free sibling today staffs the sibling for the second. After this change
the second waits.

**R2-11 — say which requirement entitles width, and which merely looks like it does.** Width is
entitled by `agent-flows:404-408`, *"A firing of a **flow** MAY start more than one task"*.
`agent-loops:571` says *"A firing MAY claim more than one task, so a loop's current items are a set
rather than a single value"* — unqualified, and in the loop capability. It is **permissive and about
reporting**, and its scenarios are `GIVEN a firing that has claimed two tasks`, so D2 does not
falsify it: a loop can still present two current items whenever resumption and the default branch
select two (see D6). R1's flat *"width is a flow capability, and a loop is not a flow"* is
contradicted on its face by anyone who opens `agent-loops`, and is replaced by this paragraph.

*Alternative rejected:* a one-element pool. `schedule_agent` refuses a second concurrent start for
one agent and design D6 forbids it, so the element would never be selectable.

### D3 — `_loop_flow_busy_reason` collapses to `_loop_agent_busy_reason` for a documentless loop

**R2-10 — the guard's real shape.** It is *busy* **and** *(no open task **or** pool empty)*
(`:343-350`); `:346` returns the reason before the pool is consulted. R1 described it as busy *and*
pool-empty, which would let a reader think the empty-queue arm is new. It is not. Once the pool is
empty both arms return `busy_reason`, so a documentless loop is refused whenever its agent is busy
— the pre-D12 behaviour.

**This is the accepted cost.** A loop pinned to a busy agent now waits, including on the operator's
live instance, where loops that keep moving by substituting will start idling.

### D4 — Two operator-visible sentences stop naming a reason that is no longer true

`run_job` answers 409 with `f"{busy_reason}, and {why}. Nothing was started."`
(`hub/hub/api/v1/jobs.py:1353-1360`). R2 confirmed both clauses reachable and one wrong:

- *"no other agent is free to take this loop's work"* — **false for a documentless loop once the
  pool is scoped.** Design D8's own comment (`jobs.py:1350-1352` — R3 cited `:1352-1354` and R4's correction said `:1351-1353`; **both were wrong, and the third reading is the measured one**) states the standard it breaks:
  *"Telling the operator nobody else is free when somebody is would send them to free an agent,
  which changes nothing."*
- *"this loop's queue holds no open task for another agent to take"* — the trailing five words are
  equally wrong for a loop.

**The board path is correct, but only by one line.** R2 traced it: for a documentless loop with a
busy agent and a pending task, `decide_firing` records nothing at `:1621-1625`,
`_stall_reason_from_walk` returns *"no claimable task among 1 open (1 pending)"*, and
`jobs.py:355` replaces it with the busy reason. Task 3.4's insistence on asserting the decision
**kind** as well as the sentence is load-bearing, not belt-and-braces.

**2026-09-21 — D4 moved out of this change, to F400 (`scripts/drive/FINDINGS.md`), by operator
decision.** It was never approved (`proposal.md`'s banner): its half of D10 was written in R4 and
no round re-derived it, and Open Question 2 was never answered. Moving it lets the built groups
(0-4, 6, 8) and tonight's drive (7) archive without syncing a requirement the code does not meet.
**Removed from the delta, because `run_job` (`hub/hub/api/v1/jobs.py:1347-1361`) still answers a
documentless loop with an open task *"no other agent is free to take this loop's work"* whoever is
free:** the MODIFIED `:791` paragraph *"Where a refusal is reported to the operator, its stated
reason SHALL be true…"* and its scenario *"The refusal of a documentless loop does not blame a busy
roster"*; in the MODIFIED `:1471`, the three-way *"SHALL say which of those three held"* paragraph
and the scenario *"Run on a documentless loop while another agent is free"*. **Kept**, because the
built code does them: `:1471`'s three-condition description of the guard (`scheduler.py:312-350`,
`_agents_a_loop_may_staff` returns `[]` for a documentless loop at `:1237-1257`), now followed by
the two answers the code does give truthfully — the empty queue (`jobs.py:1355-1359`, tested by
`test_run_on_a_busy_agents_empty_loop_names_the_empty_queue`) and a flow's exhausted roster — and an
explicit statement that the documentless open-task sentence is not yet governed. The board scenario
*"The loop's summary names the hold rather than a stall"* is unchanged from the main spec and true
via `jobs.py:355` (`test_a_held_single_agent_loop_reads_held_not_no_claimable_task`).

### D5 — `resolve_reviewer` stays project-scoped, and the F70 recovery is an explicit exception

**R1 was wrong and R2-1 is the blocking finding.** R1 claimed a documentless loop never reaches
`resolve_reviewer` from the walk, via `awaiting_landing` at `:1653`. Verified at the source, it
does:

- `_loop_candidates` (`:754-764`) selects `WITH_REVIEWER_LOOP_TASK_STATUSES` rows deliberately;
- `candidate_is_startable` (`:724-729`) returns `True, None` for `under_review`;
- `:1522-1527` sets `wedged_review = True` where the assignee is the author, so `:1546-1547` does
  **not** `continue`;
- `:1653`'s guard is `not wedged_review and not loop.spec_document_id` — with `wedged_review` true
  the `awaiting_landing` branch **does not fire**;
- the walk reaches the ladder at `:1738`, whose rung 2 walks the project-wide pool at `:1263`.

So a documentless loop can staff a project-wide sibling, as a reviewer, on a wedged row.

**The decision is to allow it and say so, not to narrow it.** Such a loop names one agent, and on a
wedged row that agent **is** the author, whom the resolver excludes by construction. Narrowing the
recovery would leave the row wedged permanently — trading a substitution for an unrecoverable task.
The rows are legacy: `_guard_reviewer_is_not_the_author` (`task_transition_service.py:387`) blocks
new ones, and `:1497-1498` says in terms that *"rows already wedged before that guard existed, or
written straight into the status, still can"* — i.e. exactly what `:8000` may hold.

R1's second justification for D5 was also false and is withdrawn: it said a review on a loop task
"can only have been dispatched by the operator's own hand", which the path above disproves — once
that reviewer's turn ends with no verdict, `run_divergence.py:441` substitutes a *second* project-
wide reviewer with no operator anywhere near it.

**R4-5: "the exception in the spec covers both" was false as R3 wrote it, and the spec is now
widened so that it is true.** On the `run_divergence` path `task.assignee` is the **silent
reviewer**, not the author: `hub/hub/run_divergence.py:432-441` builds `barred` from
`_reviewers_that_gave_no_verdict` plus the run's agent plus the author, and the function never reads
`loop.spec_document_id`. R3's exception was scoped to *"a task in a review status whose assignee is
the agent that produced the work"* — which is exactly what that row is **not**. So a second
project-wide substitution on a documentless loop was governed by nothing in the delta, while task
4.2 asserted it must keep working. *Rejected:* stating it as a Non-Goal (task 4.2 would then test
behaviour the spec does not admit — the same shape as B3/D9, a change whose own artifacts
disagree); adding a second exception (two exceptions for one concept, against the standing
cleanest-solution preference). **Taken:** one exception over *reviewer recovery*, defined by the
assignee being unable to complete the review, which both rows satisfy.

**R4-4: the exception is a non-restriction, not a guarantee, and R3 wrote it as a guarantee.** R3's
text — *"the Hub SHALL resolve a replacement reviewer from every available agent in the project"* —
and its scenario's *"THEN a replacement reviewer is resolved"* promise an outcome the code does not
make. Two branches drop a review row before the ladder at `:1738`:

- `scheduler.py:1669` — `if not attribution.recorded:` appends to `unstaffed` and `continue`s. This
  is reachable on precisely the rows the exception exists for: `:1523-1527` detects a wedge through
  `agents_that_worked` when `completion_attribution(...).agent is None`, i.e. when nothing recorded
  a completion — the legacy shape D5 itself calls *"written straight into the status or predates the
  transition table"*.
- `scheduler.py:1698` — `if not review_target.resolved:` does the same when
  `commit_for_task_review` finds no commit.

This is R2-4's shape surviving into R3 in a second place. The requirement now says only that **this
requirement** adds no narrowing; whether anyone is found is governed by the requirement named in
D8b and by the ladder's own rules.

**Task 3.5 is therefore load-bearing rather than a formality**, and the exception is written into
the requirement rather than left to the code.

### D6 — Existing assignments are left alone, and the requirement says so

The walk resumes through `task.assignee` (`:1573-1577`), not the pool, then
`selections.append(...)` at `:1627-1628`.

**R2-2 — R1's requirement was falsified by this arm.** A documentless loop naming `gamma`, with
`task1` assigned to `alpha` and `task2` pending, fires `alpha` for `task1` *and* `gamma` for
`task2`: an agent the job does not name, and two tasks in one firing, after the change and
unchanged by it. The requirement now governs **staffing, not resumption**, and the width scenario
says *"neither has an assignee"*. Without that, the change ships a requirement its own D6 guarantees
is untrue.

**R2-6 — and D6 is conditional on the named agent being idle.** `_loop_flow_busy_reason` refuses the
**whole firing** at `:2758-2772` before `decide_firing` runs, so while `gamma` is running or held a
documentless loop resumes nothing at all — including tasks held by free agents. Under a provider
allowance hold that can be hours. This is part of the accepted cost and is now stated with it.

### D7 — "Documentless loop" is `loop.spec_document_id is None`

`hub/hub/db/models.py:1473`. The same discriminator the review arm uses (`:1653`), and the one
`agent-flows:16-17` mandates: *"The distinction SHALL be the presence of the declared document and
nothing else."*

### D8 — The delta belongs to `agent-loops`, not `agent-flows` (R2-3)

R1 added a documentless-loop requirement to `agent-flows`, whose **first** requirement says *"A loop
that declares no document SHALL be unaffected by them"* (`:14`). The delta contradicted the
requirement it cited as its authority — and reproduced F128's own mechanism: an implementer reads
`:14`, concludes the capability does not govern documentless loops, and never reads the new
requirement.

Both halves now live in `agent-loops`, where loops live and where `:791` was already being modified.
**`agent-flows` gets no delta at all**, because flow behaviour does not change. That also dissolves
the question of whether `agent-flows:14` needed relaxing: it did not.

**A flow scenario nonetheless appears in this delta (R4-N6), and that is deliberate.** *"A flow
still staffs every available agent"* duplicates `agent-flows:411-415`. It stays because the ADDED
requirement's own last paragraph — *"A loop that declares a specification document SHALL be
unaffected"* — is itself in `agent-loops`, and a paragraph with no scenario is the dormancy D9 was
written to end. The scenario proves that paragraph, not flow width.

### D8b — `agent-loops:1232` already holds half the exception, and R4 reconciles with it (R4-8)

*A loop does not staff a review of its own agent's work* (`openspec/specs/agent-loops/spec.md:1232`)
already states at `:1242` that *"a loop's task already recorded in `under_review` under its own
author's name SHALL still be recovered by reassignment without moving status"*, with the scenario
*"A loop's wedged review still recovers"* (`:1271`). **No document in this change cited it through
R3** — `grep` over the change directory returned nothing. D8 decided where the delta belongs without
reading the requirement that already contained half of it, and R3's exception then restated the same
rule in a second requirement with **wider** wording (*"every available agent in the project"*),
which is the drift hazard D1 invokes against inline filters.

*Rejected:* modifying `:1232` as well — it is true as written and this change does not alter what it
requires. *Taken:* the exception is reworded as a non-restriction (D5/R4-4) and **defers the
recovery guarantee to `:1232` by name**, so the two requirements state one rule between them rather
than two versions of it. Task 6.7 records the cross-reference.

### D9 — `agent-loops:791`'s first sentence is scoped (R2-5)

R1 kept the shipped sentence verbatim — *"The Hub SHALL refuse a firing whose loop agent already has
a running turn"* — **and** added a scenario saying a flow in that state is not refused. A
requirement cannot say both, and R1's answer to its own Open Question 2 (*"the first sentence is
already unconditional and already describes the post-change behaviour"*) was true for loops and
false for flows.

**R4-3: D9 fixed the prose and left the scenarios, so the defect it names survived one level down.**
The delta retained *"WHEN a loop's agent has a running turn and the loop's job fires THEN the firing
is refused"* and *"Repeated firings during one turn do not accumulate work"* unconditionally, and
the very scenario D9 added — *"A flow is not refused while another agent is free"* — is a strict
specialization of the first WHEN with the opposite THEN. Verified: `scheduler.py:343-350` returns
`None` for a flow with an open task and a non-empty pool, and `:1620-1628` then staffs a sibling.
Both retained scenarios now carry the roster arm, matching the already-scoped held scenario. **The
lesson is D9's own: a requirement cannot say both — and neither can its scenario list.**

This is a **pre-existing** falsity, not one this change introduces:
`scripts/drive/FINDINGS.md:28160-28162` (R3 cited `:28155-28157`, which is a blank line and the REV
header) records the REV of `a-spent-allowance-holds-the-queue`
finding *"The MODIFIED `agent-loops` SHALL was false for every flow. The guard lets a firing through
when anyone is free."* That round left it dormant by adding no flow scenario. This change adds the
scenario that detonates it, so it fixes the sentence in the same delta rather than shipping a
requirement its own scenario refutes.

The deferral sentence is narrowed rather than deleted: `agent-flows` still governs which agent a
**flow** staffs; the documentless answer now lives in this capability.

### D10 — `agent-loops:1471` is modified too, or two requirements govern one sentence (R4-2)

*Pressing Run on a loop that declines names why it declined* (`:1471`) describes the guard as
refusing on *"either no other agent in the project is free or the loop's queue holds no task in a
non-terminal status"*, and requires that the answer *"SHALL say **which of those two** held"*.

D3 makes the first of those two conditions inapplicable to every documentless loop, and **task 5.3
mandates a third clause** — *"this loop runs only the agent its job names"* — that a two-way SHALL
does not admit. Through R3 the delta modified `:791` and nothing else, so the change would have
shipped two requirements in one capability governing the same 409 sentence and disagreeing about
what it may say. **`openspec validate --strict` cannot see this**: both requirements are
individually well-formed, and nothing checks two requirements against each other. That is the same
blind spot that let D9's contradiction live in one requirement's own scenario list.

The condition becomes three-way, the answer is required to name the one that held and **not** to
name one that did not, and a documentless-loop scenario is added. *Rejected:* dropping task 5.3's
third clause (it is D4, and the whole operator-facing point of the change — the 409 would keep
telling the operator to free an agent that changes nothing); leaving `:1471` for a later change (it
is false the day this ships, which is what "dormant" meant in D9 and cost this change two rounds).

**2026-09-21:** D10's reason for existing survives D4's move, in half. `:1471`'s two-way guard
description is false of the built code (D3), so the MODIFIED requirement stays and describes three
conditions. What went is the mandate that the answer name the third one — the code does not, and
that is F400. The requirement now says which answers it governs and states that the documentless
open-task sentence is undecided, rather than ship a SHALL the 409 violates.

## Risks / Trade-offs

- **The operator's live loops start idling**, and while their agent is held they stop resuming even
  work other agents hold (D6/R2-6). → Accepted with the decision; recorded as behavioural BREAKING.
- **The operator's board will move on the first restart after this ships (R4-N1).**
  `hub/ui/src/components/spec/loopCounts.ts:23` buckets any loop with a `stall_reason` as
  `'stalled'`, and `jobs.py:355` now sets one where a substitution previously kept the loop reading
  `running`/`idle`. `runningLoopCount` (`:36`) falls, the stalled count rises, **no UI code
  changes**, and every sentence shown is true. → The risk is that it reads as a regression. The test
  guide says so explicitly, and this is the first thing to say to the operator after the deploy.
- **The F70 exception is a real, if narrow, substitution that survives this change.** → Written into
  the requirement, bounded to recovery, and tested (task 4.1). The alternative is an unrecoverable
  row.
- **A loop's skipped second task records nothing.** → R2 answered this: it is not F23's silence.
  Where something else was selected the decision is `DECISION_CLAIM` and the skipped task is absent
  from the board exactly as a flow's width-bound task is today (`agent-flows:418-422` ships that
  silence); where nothing was selected the guard refused before the walk, and the board's sentence
  is replaced at `jobs.py:355`. What *is* owed is documentation: `:1622-1624` says *"Width is bounded
  by available agents"*, and for a loop the bound is now "one agent, permanently".
- **No ordering hazard after all (R2-7).** R1 said this change would collide with
  `an-unstaffed-review-names-its-holders` group 1. That change's own task 1.2 — as corrected in R7
  the same afternoon — says `_loop_flow_busy_reason` (`:348`) and `decide_firing` (`:1444`) **keep**
  calling `_agents_that_are_free` unchanged; only `resolve_reviewer` moves to `_roster_availability`.
  A filter above the pool touches neither. D1 survives group 1 for a simpler reason than R1 gave,
  `_agents_a_loop_may_staff` keeps reading `_agents_that_are_free`, and task 0.1 is downgraded from
  a hard gate to a check — R2 noted that a window obeying it as written, and reading that change's
  stale *"STOPPED AT REV — do not build any task here"* banner, would stop forever.

## Round log

### Round 2 — adversarial, 2026-09-19, DO NOT APPROVE

Five blocking findings, all verified at the source before being accepted, all applied in R3:

- **R2-1** D5 false; the F70 wedged-review recovery reaches `resolve_reviewer` on a documentless
  loop. → D5 rewritten; the exception is in the requirement.
- **R2-2** the resumption arm falsifies the ADDED requirement. → scoped to staffing; the width
  scenario gained *"neither has an assignee"*.
- **R2-3** the requirement was written into the capability that exempts documentless loops from it.
  → moved to `agent-loops`; `agent-flows` gets no delta (D8).
- **R2-4** the runnerless scenario asserted *"no task is started"*, which the default branch does not
  do (no runner test at `:1601-1606`) and which collides with `loop-firing-accountability:16-21`.
  → restated as *"no other agent is selected in its place"*.
- **R2-5** the delta contradicted itself on the unconditional first sentence. → D9.

Non-blocking, all applied: **R2-6** (D6 conditional), **R2-7** (ordering premise, task 0.1),
**R2-8** (unused parameter), **R2-9** (the baseline list was a quarter of the surface — 16 test files
touch this code and `test_flow_width.py` defaults to `declares_document=True`, so its greenness
proves nothing here), **R2-10** (guard shape), **R2-11** (`agent-loops:571`), **R2-12**
(`test-guide.md` must be written, not re-derived), **R2-13** (model citations), **R2-14**
(`DECISIONS.md:748` was stale when written).

**What R2 could not check, carried forward for R3 and the drive:** it ran no tests and drove no Hub,
so R2-1's wedged-review path is derived from code and has never been observed; it did not read
`hub/ui/`'s `loopCounts.ts`; it did not run `openspec validate --strict`; and it searched
`openspec/specs/` only, not `openspec/changes/archive/`.

### Round 4 — adversarial, 2026-09-19 evening, DO NOT APPROVE

The second adversarial pass, run because R1 and R3 were written by the same session and the
repository's own `DEAD-ENDS.md` records that *"a round you wrote yourself is not a check"*. Six of
its eight blocking findings were re-verified at the source before being accepted; all six held.

- **R4-1** `proposal.md`'s Impact still carried R1's blocked claim — *"a documentless loop does not
  staff a review at all"* — citing **D5**, the section that refutes it, as its authority.
  → Impact rewritten; the green test that falsifies it is named.
- **R4-2** `agent-loops:1471` is falsified by D3 and task 5.3, and was not in the delta. → **D10**;
  a second MODIFIED requirement.
- **R4-3** the delta kept two unconditional scenarios that its own new flow scenario refutes —
  **D9's defect one level down**. → both scoped; D9 amended.
- **R4-4** the exception promised *"a replacement reviewer is resolved"*, which `scheduler.py:1669`
  and `:1698` do not do. **R2-4's shape, surviving R3 in a second place.** → restated as a
  non-restriction; D5 amended.
- **R4-5** the exception was scoped to authorship, so it did not reach `run_divergence.py:441`'s
  substitution, where the assignee is the *silent reviewer* — while task 4.2 asserted that path must
  keep working. → exception widened to reviewer recovery; second scenario added.
- **R4-6** task 4.1's *"No existing test covers this"* is false and checked the wrong file.
  → corrected; Open Question 1 restated.
- **R4-7** four of task 0.3's nine named baseline files are flows, not documentless loops, and task
  6.1's triage rule is keyed to that label. → both rewritten in terms of the fixture.
- **R4-8** the exception duplicates `agent-loops:1232`, which no document in the change cited.
  → **D8b**.

Non-blocking, all applied: **R4-N1** (`loopCounts.ts`, now a stated Risk), **R4-N2** (two citations
off), **R4-N3** (`test_flow_width.py:622` is documentless and its docstring becomes false),
**R4-N5** (`test_loop_busy_guard.py` missing from the baseline), **R4-N6** (a flow scenario in
`agent-loops`, kept deliberately — D8).

**What R4 cleared, so a later round need not redo it:** `--strict` passes; the three call sites are
`:348`, `:1263`, `:1444` and nothing else; **the no-collision claim with
`an-unstaffed-review-names-its-holders` group 1 is true** in either landing order; **the fix can
fire** — `decide_firing`'s only pool read is `:1620`, an empty pool falls to `continue` at `:1625`,
and no second staffing path bypasses it; **no shipped scenario is dropped** (all 8 of
`agent-loops:820-863` appear in the delta); and every `models.py`, `scheduler.py` and
`task_transition_service.py` citation checked is exact.

**What R4 could not check:** it drove no Hub and ran no live firing, so tasks 7.1-7.4 are
unexecuted and R4-4's two drop-out branches are derived from code, not observed; it queried nothing
on `:8000`; it ran only two test files (12 passed), not the 16-file baseline, the full suite,
`ruff`/`black`/`mypy` or `npm run lint`; it did not read `loop-firing-accountability`,
`task-lifecycle-governance:317`/`:1481` or `agent-conversation-workspace`; it did not read
`_stall_reason_from_walk`'s body, so **D4's claim about the exact sentence it replaces is still
unverified**; and it audited only 4 of the 16 baseline files beyond the greps it reported.

### 2026-09-21 — §5 / D4 moved out (operator decision, not a round)

Not an adversarial round: an edit made so the change can archive. §5 re-filed as **F400**; the delta
trimmed to what the built code does (D4's and D10's dated notes list each removal and each keep
with its code evidence). Open Question 2 moves with it — it only ever gated task 5.4.

## Open Questions

1. **Does `:8000` actually hold a wedged review row on a documentless loop?** R2-1's path is real in
   code, and **R4-6 establishes it is also covered by a green regression test** —
   `test_a_loops_wedged_review_still_recovers` (`test_a_loop_does_not_staff_its_own_review.py:328`,
   `declares_document=False`). So it is no longer "unobserved": it is observed in the suite and
   unobserved in life. What remains open is only whether task 4.1 is a guard over a hypothetical or
   over rows the operator is actually holding, which changes the urgency of shipping and nothing
   about the design. Answerable by a read-only query, which **task 7.4** carries.
2. **Moved to F400 with §5, 2026-09-21.** **`_stall_reason_from_walk`'s exact current sentence is still unverified** (R4's own gap). D4
   asserts which string `jobs.py:355` replaces. **Task 5.4** must read that function's body before the
   operator-visible sentence is changed, not after.
