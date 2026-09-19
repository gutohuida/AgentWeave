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

- **A documentless loop's recruitment pool becomes the one agent its job names.** Where that agent
  is unavailable, the firing staffs nobody rather than substituting a sibling. A flow — a loop that
  declares a specification document — is unchanged and keeps the project-wide pool, so D12's width
  survives exactly where D12 meant it.
- **The narrowing is a scope filter over availability, never a second opinion about it.** The pool
  is computed as it is today and then restricted; no new rule about whether an agent can take a turn
  is introduced. `_agents_that_are_free`'s docstring already states why a third opinion must not
  appear (`hub/hub/scheduler.py:1093-1094`).
- **BREAKING (behavioural, no API shape change): a loop pinned to a busy agent now waits.** On the
  operator's live instance, loops that currently keep moving by substituting will start idling
  until their own agent is free. This is the accepted cost recorded with the decision.
- **The busy guard stops depending on whether anyone else is free, for a documentless loop.**
  `_loop_flow_busy_reason` (`scheduler.py:312-350`) refuses only when the job's agent is busy
  **and** the pool is empty; once the pool is `{job.agent}`, the second half is satisfied by
  construction, so the guard collapses back to `_loop_agent_busy_reason` — the pre-D12 behaviour
  D12 said was right for loops.
- **F127's 409 sentence is re-derived.** `run_job` answers *"…, and no other agent is free to take
  this loop's work. Nothing was started."* (`hub/hub/api/v1/jobs.py:1353-1360`). Once the pool is
  loop-scoped that clause is false whenever a sibling outside the loop is free: it would send the
  operator to free an agent that changes nothing, which is the exact harm design D8's wording was
  written to prevent. The sentence must name the real reason — this loop runs only the agent it
  names.
- **Tasks already assigned to a substituted agent keep their assignee.** The walk resumes a task
  through `task.assignee` (`scheduler.py:1573-1577`), not through the pool, so existing rows
  continue to be worked by whoever holds them. Re-homing them is a **Non-Goal** (below).

## Capabilities

### New Capabilities

None. This change corrects an implementation that already departs from two shipped capabilities.

### Modified Capabilities

- `agent-flows`: the requirement that a firing determines both the task and the agent gains the
  **scope** of the pool it determines that agent from — the project's available agents for a flow,
  and the agent the job names for a documentless loop. Today the capability states *which* agent
  resolution happens and is silent on *whom it may choose among*, which is the silence the
  implementation filled project-wide.
- `agent-loops`: *"A firing is refused while its loop's agent is already running"* (`:791`)
  currently makes two of its clauses conditional on *"no other agent in the project is free"* — in
  the allowance-hold paragraph and in two scenarios. For a documentless loop that condition stops
  being necessary: the refusal stands whoever else is free. The requirement's own deferral,
  *"This requirement does not state which agent a firing staffs when another agent in the project is
  free. `agent-flows` governs that"*, is what makes this a delta on both capabilities rather than
  one.

## Impact

**Code.** `hub/hub/scheduler.py` — the three call sites of `_agents_that_are_free`
(`:348` in `_loop_flow_busy_reason`, `:1263` in `resolve_reviewer`, `:1444` in `decide_firing`;
located by `grep -n "await _agents_that_are_free("`, never by line number). Only the two loop-aware
ones narrow; `resolve_reviewer` is reached for flows alone, because a documentless loop does not
staff a review at all (`scheduler.py:1653`, design D5, finding F161).
`hub/hub/api/v1/jobs.py:1353-1360` — F127's 409 sentence.

**Ordering — this change follows `an-unstaffed-review-names-its-holders` group 1.** That change is
approved and scheduled to build first, and its task 1.2 re-expresses `_agents_that_are_free` as a
projection over a new `_roster_availability`. Written against today's tree this change would collide
in the same function. It must be written against the post-group-1 shape, where the narrowing is a
filter over the projection.

**No migration, no schema change, no API shape change, no UI bundle.** There is no per-flow roster
column to add: `Loop` carries `spec_document_id` and its `AIJob` carries `agent`
(`hub/hub/db/models.py:1428-1473`), and those two facts are the whole of "the agents this loop
names". The Python lint set is required; `make ui` is not.

**Tests that encode today's behaviour and must be re-read, not assumed:** `test_flow_width.py`,
`test_reviewer_ladder.py`, `test_a_task_nothing_will_move_holds_nobody.py`,
`test_a_held_agent_is_busy.py`, and the board-agreement tests that read the same walk
(`test_the_board_summary_agrees_with_the_firing_for_a_gated_queue`).

**Non-Goals**, stated rather than left to omission:

- **Not re-homing existing assignments.** Tasks a past substitution assigned to a sibling keep that
  assignee and keep being worked. Changing that is a data migration over live rows and a separate
  decision.
- **Not giving a flow a roster of its own.** A flow's pool stays the project's available agents.
  A per-flow roster is a new concept with a migration behind it, and nothing measured asks for one.
- **Not adding a per-job opt-in width flag.** Rejected with the decision: a flow already *is* the
  width case, so the flag re-implements an existing concept at the cost of a migration and a
  control.
- **Not changing the UI.** The rejected alternative was UI/API honesty *instead of* this fix, on the
  grounds that it leaves the authority hole — a UI that correctly reports you have no control. With
  the pool narrowed, `job.agent` becomes true as presented, so no UI text has to change for it to
  stop lying.
- **Not fixing F127's status code.** F127 is already fixed (`c8e3bbd`, 2026-09-14): `run_job`
  re-asks the busy guard and answers 409, not 500. Only its *sentence* is in scope here.
