# Design — a loop staffs the agent it names

**Round 1, 2026-09-19.** Explored against the tree at `ddf73aa`.
**Round 2, 2026-09-19 — adversarial, independent, returned DO NOT APPROVE with five blocking
findings. All five were verified at the source before being accepted. Round 3 applied every one.**
The round log is at the bottom; read it before re-proposing anything this document rejects.

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
  pool is scoped.** Design D8's own comment (`jobs.py:1352-1354`) states the standard it breaks:
  *"Telling the operator nobody else is free when somebody is would send them to free an agent,
  which changes nothing."*
- *"this loop's queue holds no open task for another agent to take"* — the trailing five words are
  equally wrong for a loop.

**The board path is correct, but only by one line.** R2 traced it: for a documentless loop with a
busy agent and a pending task, `decide_firing` records nothing at `:1621-1625`,
`_stall_reason_from_walk` returns *"no claimable task among 1 open (1 pending)"*, and
`jobs.py:355` replaces it with the busy reason. Task 3.4's insistence on asserting the decision
**kind** as well as the sentence is load-bearing, not belt-and-braces.

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
wide reviewer with no operator anywhere near it. The exception in the spec covers both.

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

### D9 — `agent-loops:791`'s first sentence is scoped (R2-5)

R1 kept the shipped sentence verbatim — *"The Hub SHALL refuse a firing whose loop agent already has
a running turn"* — **and** added a scenario saying a flow in that state is not refused. A
requirement cannot say both, and R1's answer to its own Open Question 2 (*"the first sentence is
already unconditional and already describes the post-change behaviour"*) was true for loops and
false for flows.

This is a **pre-existing** falsity, not one this change introduces:
`scripts/drive/FINDINGS.md:28155-28157` records the REV of `a-spent-allowance-holds-the-queue`
finding *"The MODIFIED `agent-loops` SHALL was false for every flow. The guard lets a firing through
when anyone is free."* That round left it dormant by adding no flow scenario. This change adds the
scenario that detonates it, so it fixes the sentence in the same delta rather than shipping a
requirement its own scenario refutes.

The deferral sentence is narrowed rather than deleted: `agent-flows` still governs which agent a
**flow** staffs; the documentless answer now lives in this capability.

## Risks / Trade-offs

- **The operator's live loops start idling**, and while their agent is held they stop resuming even
  work other agents hold (D6/R2-6). → Accepted with the decision; recorded as behavioural BREAKING.
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

## Open Questions

1. **Does `:8000` actually hold a wedged review row on a documentless loop?** R2-1's path is real in
   code and unobserved in life. It changes nothing about the design — the exception is right either
   way — but it decides whether task 4.1's test is a regression guard or a live repair. Answerable
   only by a read-only query against the operator's database, which task 5.1 can carry.
