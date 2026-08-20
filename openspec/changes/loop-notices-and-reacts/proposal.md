## Why

A loop fires blind. It does not look at whether its agent is already working, whether the task it
finished was ever handed to a reviewer, or whether anything has changed since the last time it fired
and found the same thing. Three consequences, all reachable today:

1. **A finished task can wait forever with nobody coming.** An agent cannot approve its own work
   (`hub/hub/task_transition_service.py:119`), so it must hand off to a reviewer — and the comment
   explaining why `assigned` had to become claimable already records why that is not enough:
   reaching the next status *"needs the agent to call `update_task` itself, which it may simply not
   do"* (`hub/hub/scheduler.py:236-237`). When the handoff does not happen, the task sits at
   `completed` and, under `task-dependencies`, every task behind it is unreachable.
2. **A firing during a live turn queues a duplicate briefing.** There is no already-running guard in
   `_do_fire_job` (`hub/hub/scheduler.py`); the task is claimed and an inbound entry queued before
   `schedule_agent` gets a chance to refuse (`hub/hub/turn_scheduler.py:43`). Measured: five firings
   during one turn produced five queued entries and five `JobRun`s. Turning the cron *up* multiplies
   the waste.
3. **Repeated no-op ticks bury the real history.** `JobRun` feeds the last-ten-runs view
   (`hub/hub/api/v1/jobs.py:509`) and the *is this loop running* check (`:216`). A loop that ticks
   while stalled or busy fills that window with rows saying the same thing, and a healthy loop reads
   as dead.

All three are the same missing behaviour: **the loop does not notice what is actually happening.**

Explored and decided with the operator in
`openspec/explorations/2026-08-20-who-guarantees-the-review-handoff.md`.

## What Changes

**The review handoff is guaranteed without taking the choice away from the agent.**

- The Hub derives whether a completed task has a review in flight, from rows that already exist:
  a `Message` naming the task with type `"review"` (`hub/hub/db/models.py:509,513`), and — for a task
  at `under_review` — which agent moved it there (`TaskTransition.actor_agent`, read exactly this way
  by `_agent_that_completed`, `hub/hub/task_transition_service.py:92-116`).
- A firing that finds its loop's task finished with **no** review in flight spends its turn
  re-briefing its own agent to perform the handoff, instead of claiming new work. The agent still
  chooses the reviewer.
- The re-brief is bounded. After a fixed number of unheeded reminders the loop stops reminding and
  surfaces the situation to the operator.

**The firing stops firing blind.**

- A firing whose loop agent already has a running turn is skipped before anything is claimed or
  queued.
- A skipped-because-busy tick records **no** `JobRun`. A stalled tick records **one** `JobRun` that
  counts subsequent ticks in place rather than appending a row per tick.

**Every task status gets classified once, in one place.**

- Four constants answer *"is this task live?"* today, and disagree:
  `CLAIMABLE_LOOP_TASK_STATUSES` (`hub/hub/scheduler.py`), `TERMINAL_FOR_BINDING`
  (`hub/hub/run_task_binding.py:272`), `_ACTIVE_TASK_STATUSES` (`hub/hub/api/v1/agents.py:60`) and
  `_LIVE_TASK_STATUSES` (`hub/hub/checkpoints.py:62`) — the last two identical in content and
  separate in code. **Both of the stall bugs fixed on 2026-08-20 lived in the gaps between them.**
- One named vocabulary classifies every status, and each of the four sets is derived from it, so a
  status added to the transition machine cannot silently belong to none.

**Non-Goals — explicitly out of scope, not merely omitted:**

- **Event-driven firing.** Decided against (exploration §9): the latency gap is invisible at a loop's
  timescale, and unfired wakers are a failure this codebase has already shipped and measured
  (`hub/hub/api/v1/agent_trigger.py:1236-1238`). The cron stays.
- **The loop choosing a reviewer.** The loop guarantees the *asking*; the agent keeps the *choosing*.
  A loop that routed work itself would need `list_agents` (L2) and would discard the operator's
  design.
- **A review-wait timeout** for a handoff that *did* happen to a reviewer who never runs
  (exploration R4/§8). Needs a decision not yet taken.
- **A reviewer field on `Task`** (L4), **charter summaries in the Team section** (L1), and
  **`list_agents`** (L2). Independent, and this change is deliberately built not to need them.
- **A review-wait timeout** for a handoff that *did* reach a reviewer who never runs. Decided
  against, not deferred: once a stalled tick counts in place, such a loop reads *"stalled, waiting on
  review, N ticks since …"* — visible, cheap, and recoverable the moment anyone reviews it. A timeout
  would have to decide what to *do* when it fires, and stopping, reassigning and re-briefing are all
  worse than staying visible and waiting.
- **Changing any loop's default cron interval.** A faster cron becomes safe once the busy guard
  lands, but choosing a new default is a separate decision.
- **Changing which statuses any of the four sets contains.** The vocabulary work above is a
  refactor: every set keeps exactly the members it has today, derived rather than listed. Any change
  in membership is a behaviour change and belongs to a different proposal.

## Capabilities

### New Capabilities

- `loop-review-handoff`: How the Hub determines whether a finished task has a review in flight, what
  a firing does when it does not, how many times it re-asks, and what happens when that bound is
  reached.

### Modified Capabilities

- `agent-loops`: A firing gains two refusal conditions before it claims — the loop's agent already
  running, and its queue stalled — and the rules for what a firing records when it does not fire.
  Today every firing that is not stopped proceeds to claim (`hub/hub/scheduler.py::_do_fire_job`).
- `task-lifecycle-governance`: Every task status must be classified into exactly one lifecycle band,
  and the sets that ask *"is this task live?"* must be derived from that classification rather than
  listed independently. Today four constants list their members by hand and none is checked for
  completeness against the transition machine.

## Impact

**Code**

- `hub/hub/scheduler.py` — `_do_fire_job` (the busy guard, the re-brief branch, tick recording),
  `_loop_stall_reason`, and the shared claimability predicate `_batch_loop_summaries` must reuse.
- `hub/hub/api/v1/jobs.py` — `_batch_loop_summaries` imports the claim's derivation rather than
  restating it (`:170`); that sharing must survive claimability becoming conditional.
- New derivation reading `Message` and `TaskTransition`; no new columns for the signal itself.
- `hub/hub/run_task_binding.py`, `hub/hub/api/v1/agents.py`, `hub/hub/checkpoints.py` — each stops
  listing its status set and derives it from the shared vocabulary. No membership changes.

**Database**

- A migration for the stall tick counter and the re-brief counter. Guard for a missing table, as
  `0033`/`0034` do; bump the head assertions in `hub/tests/test_migrations.py` and
  `hub/tests/test_project_persistence.py`.

**API / UI**

- `GET /api/v1/jobs/{job_id}` and `/history` return fewer, denser rows for an idle loop.
- The loop board's *current item* derivation must agree with the firing's — human-only check 13.1,
  and the reason `_loop_queue_order` is shared today (`hub/hub/scheduler.py:202-226` records what
  happened the one time they drifted).

**Behaviour already shipped that this builds on** (2026-08-20, committed): the stall skip
(`_loop_stall_reason`) and `revision_needed` joining `CLAIMABLE_LOOP_TASK_STATUSES`.

**Risk.** Claimability stops being a flat tuple and becomes conditional. A condition is far easier to
duplicate-and-drift than a constant, and the board and the firing disagreeing is a failure this
codebase has already had — *"two consistent wrong answers read as a match, which is how it survived
review"* (`hub/hub/scheduler.py:210-220`).
