## Why

A loop bound to one agent is run by a different one whenever its own agent is busy. Driven live
(`scripts/drive/t_run_while_busy.py`, finding **F128**): job `busy-run` was created with
`agent: gamma`, gamma was put mid-turn on an unrelated errand, pressing Run answered **200**, and
the work went to **alpha** — `conv-a51b18211d43`, agent `alpha`, origin `job`, and the queued
task's `assignee` read `alpha`.

**An agent is not only a name.** `charter_id` (`hub/hub/db/models.py:219`), `runner_id` (`:216`) and
the three authority flags `can_read_checkpoints` / `can_recall` / `can_accept_evidence`
(`:254-268`) all live on the `Agent` row. So a substitution silently swaps the behaviour text, the
runner, **and the permissions the operator selected that agent for**. Nothing in the job form, the
loop list or the API says `job.agent` is only a default.

**The corpus already forbids this, and the implementation did not follow it.** `agent-flows:11`
states that a loop declaring no document "SHALL be unaffected by [the flow requirements] and SHALL
behave exactly as it does today", with the scenario *"WHEN a loop declares no specification
document THEN every firing fires the job's own agent, as before"*. Before
`loop-becomes-a-flow`, no substitution was possible: `_loop_agent_busy_reason` refused the whole
firing whenever the job's agent was running. Design **D12** then narrowed that guard so a flow could
staff another agent for independent work — correctly — but implemented the narrowing
**project-wide** rather than for flows only. `_loop_flow_busy_reason`'s own docstring
(`hub/hub/scheduler.py:335-338`) records the gap it left: *"the pool is **project-scoped**, so a
loop naming one agent is not single-agent as far as this guard can tell."*

So this is a conformance fix, not a new design. The operator decided its shape on 2026-09-19
(`spec-queue/DECISIONS.md:748`): **the free list becomes loop-scoped.**

## What Changes

- **A documentless loop staffs unassigned work only with the agent its job names.** Where that agent
  is unavailable, the firing staffs nobody rather than substituting a sibling. A flow — a loop that
  declares a specification document — is unchanged and keeps the project-wide pool, so D12's width
  survives exactly where D12 meant it.
- **Staffing, not resumption.** A task that already names an assignee keeps being worked by that
  assignee. The walk resumes through `task.assignee` (`hub/hub/scheduler.py:1573-1577`), not through
  the pool, and this change does not touch that.
- **One explicit exception: the F70 wedged-review recovery stays project-wide.** A task in a review
  status whose assignee is the agent that produced the work reaches the reviewer ladder even on a
  documentless loop (`scheduler.py:1522-1527` sets `wedged_review`, so `:1653`'s `awaiting_landing`
  branch does not fire), and resolves a reviewer from the whole project at `:1263`. Narrowing that
  to the loop's one agent — who is the author, whom the resolver excludes — would leave the row
  wedged permanently. The exception is written into the requirement and bounded to recovery.
- **The narrowing is a scope filter over availability, never a second opinion about it.** The pool
  is computed as it is today and then restricted; no new rule about whether an agent can take a turn
  is introduced. `_agents_that_are_free`'s docstring already states why a third opinion must not
  appear (`hub/hub/scheduler.py:1093-1094`).
- **BREAKING (behavioural, no API shape change): a loop pinned to a busy agent now waits.** On the
  operator's live instance, loops that currently keep moving by substituting will start idling
  until their own agent is free. This is the accepted cost recorded with the decision.
- **The busy guard stops depending on whether anyone else is free, for a documentless loop.**
  `_loop_flow_busy_reason` (`scheduler.py:312-350`) refuses when the job's agent is busy **and**
  either the loop holds no open task (`:346`) or the pool is empty (`:348`). Once the pool is empty
  both arms return the same reason, so the guard collapses back to `_loop_agent_busy_reason` — the
  pre-D12 behaviour D12 said was right for loops.
- **F127's 409 sentence is re-derived.** `run_job` answers *"…, and no other agent is free to take
  this loop's work. Nothing was started."* (`hub/hub/api/v1/jobs.py:1353-1360`). Once the pool is
  loop-scoped that clause is false whenever a sibling outside the loop is free: it would send the
  operator to free an agent that changes nothing, which is the exact harm design D8's wording was
  written to prevent. The sentence must name the real reason — this loop runs only the agent it
  names.
## Capabilities

### New Capabilities

None. This change corrects an implementation that already departs from a shipped capability.

### Modified Capabilities

`agent-loops` only, and **deliberately not `agent-flows`** — flow behaviour does not change, and
`agent-flows`' first requirement says *"A loop that declares no document SHALL be unaffected by
[the requirements in this capability]"* (`:14`), so a documentless-loop rule written there would
contradict the requirement this change cites as its authority. It would also reproduce F128's own
mechanism: an implementer reads `:14`, concludes the capability does not govern documentless loops,
and never reads the rule.

- `agent-loops` **ADDED**: *"A firing staffs a loop that declares no document only with the agent its
  job names"* — the rule, its staffing-not-resumption scope, and the one exception for the wedged-
  review recovery.
- `agent-loops` **MODIFIED**: *"A firing is refused while its loop's agent is already running"*
  (`:791`). Its allowance-hold paragraph and two of its scenarios are conditional on *"no other
  agent in the project is free"*, which stops being necessary for a documentless loop. Its
  unconditional first sentence is also scoped — it is already false for flows today, which the REV
  of `a-spent-allowance-holds-the-queue` recorded (`scripts/drive/FINDINGS.md:28155-28157`) and left
  dormant by adding no flow scenario. This change adds that scenario, so it fixes the sentence in
  the same delta rather than shipping a requirement its own scenario refutes.

## Impact

**Code.** `hub/hub/scheduler.py` — the three call sites of `_agents_that_are_free`
(`:348` in `_loop_flow_busy_reason`, `:1263` in `resolve_reviewer`, `:1444` in `decide_firing`;
located by `grep -n "await _agents_that_are_free("`, never by line number). Only the two loop-aware
ones narrow; `resolve_reviewer` is reached for flows alone, because a documentless loop does not
staff a review at all (`scheduler.py:1653`, design D5, finding F161).
`hub/hub/api/v1/jobs.py:1353-1360` — F127's 409 sentence.

**Ordering — there is no collision with `an-unstaffed-review-names-its-holders` group 1.** R1
asserted one; R2 disproved it from that change's own task 1.2, as corrected in R7 the same
afternoon: `_loop_flow_busy_reason` (`:348`) and `decide_firing` (`:1444`) **keep** calling
`_agents_that_are_free` unchanged, and only `resolve_reviewer` (`:1263`) moves to
`_roster_availability`. A filter placed above the pool touches neither site this change narrows.
Group 1 landing first is convenient, not required.

**No migration, no schema change, no API shape change, no UI bundle.** There is no per-flow roster
column to add: `Loop.spec_document_id` (`hub/hub/db/models.py:1473`) and `AIJob.agent` (`:1303`) are
the whole of "the agents this loop names". The Python lint set is required; `make ui` is not.

**Tests that encode today's behaviour and must be re-read, not assumed.** R2 measured the surface:
`grep -rl --include=*.py "decide_firing\|_loop_flow_busy_reason" hub/tests/` returns **16 files**
(the bare grep returns 35, the extra 19 being `__pycache__` binaries), and the ones
that matter most build **documentless** loops by default — `test_a_loop_does_not_staff_its_own_review.py:56`
(`declares_document=False`), `test_actor_aware_claimability.py:36`, and `test_a_review_nobody_is_doing.py`,
which exercises the wedged-review path above. **`test_flow_width.py` defaults to
`declares_document=True` (`:54`), so its greenness proves nothing about this change** — the opposite
of the assumption R1 made.

**Non-Goals**, stated rather than left to omission:

- **Not re-homing existing assignments.** Tasks a past substitution assigned to a sibling keep that
  assignee and keep being worked. Changing that is a data migration over live rows and a separate
  decision. Note the limit of that guarantee: while the loop's named agent is itself busy or held,
  the busy guard refuses the whole firing before the walk runs (`scheduler.py:2758-2772`), so those
  tasks are not resumed either. Under a provider-allowance hold that can be hours.
- **Not narrowing the F70 wedged-review recovery.** See *What Changes*; it is an exception in the
  requirement, bounded to recovery.
- **Not giving a flow a roster of its own.** A flow's pool stays the project's available agents.
  A per-flow roster is a new concept with a migration behind it, and nothing measured asks for one.
- **Not adding a per-job opt-in width flag.** Rejected with the decision: a flow already *is* the
  width case, so the flag re-implements an existing concept at the cost of a migration and a
  control.
- **Not changing the UI.** The rejected alternative was UI/API honesty *instead of* this fix, on the
  grounds that it leaves the authority hole — a UI that correctly reports you have no control. With
  the pool narrowed, `job.agent` becomes true as presented, so no UI text has to change for it to
  stop lying.
- **Not fixing F127's status code.** `spec-queue/DECISIONS.md:748` requires *"F127's 500 must be
  fixed in the same change"*. **That row was already stale when it was written on 2026-09-19:**
  F127 was fixed five days earlier by `c8e3bbd`, and `hub/hub/api/v1/jobs.py:1341-1362` re-asks the
  busy guard and raises 409 before the 500 branch at `:1379`. Only F127's *sentence* is in scope
  here. Task 6.3 appends that correction to the decision log rather than editing the row, because a
  decision log that is silently rewritten stops being evidence.
