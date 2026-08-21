## Why

A loop fires blind. It does not look at whether its agent is already working, and it cannot tell
whether anything has changed since the last time it fired and found the same thing. Two consequences,
both reachable today and both measured:

1. **A firing during a live turn queues a duplicate briefing.** There is no already-running guard in
   `_do_fire_job` (`hub/hub/scheduler.py`); the task is claimed and an inbound entry queued before
   `schedule_agent` gets a chance to refuse (`hub/hub/turn_scheduler.py:43`). Measured: five firings
   during one turn produced five queued entries and five `JobRun`s. Turning the cron *up* multiplies
   the waste.
2. **Repeated no-op ticks bury the real history.** `JobRun` feeds the last-ten-runs view
   (`hub/hub/api/v1/jobs.py:509`) and the *is this loop running* check (`:216`). A loop that ticks
   while stalled or busy fills that window with rows saying the same thing, and a healthy loop reads
   as dead.

Both are the same missing behaviour: **the loop does not notice what is actually happening.**

Underneath them is a third problem that is not a bug and causes both: **four constants answer *"is
this task live?"* and disagree**, and there is no single place where a firing decides what it is
about to do. Both stall bugs fixed on 2026-08-20 lived in the gaps between those constants.

Explored and decided with the operator in
`openspec/explorations/2026-08-20-who-guarantees-the-review-handoff.md`.

**Scope narrowed 2026-08-21.** This change originally also guaranteed the review handoff — detecting
a missing one and re-briefing the agent to send it. That half is superseded by
`openspec/explorations/2026-08-21-a-review-is-a-task-not-a-message.md` and
`2026-08-21-the-loop-becomes-a-flow.md`: a finished task becomes claimable by an agent that did not
write it, and the flow fires the reviewer, so there is no message to forget. What remains is the
firing hygiene — which the flow needs *more* than the loop does, because a flow fires more often and
for more reasons.

## What Changes

**The firing stops firing blind.**

- A firing whose loop agent already has a running turn is skipped before anything is claimed or
  queued.
- A skipped-because-busy tick records **no** `JobRun`. A stalled tick records **one** `JobRun` that
  counts subsequent ticks in place rather than appending a row per tick.

**A loop ticks every five minutes by default, which the busy guard is what makes safe.**

- `create_loop` requires `cron` with no default (`hub/hub/mcp_server.py:541`), and the UI offers five
  examples, none more frequent than every six hours (`hub/ui/src/components/jobs/JobForm.tsx:13-19`).
  A loop therefore polls on whatever a caller invents, and the honest advice today is *slowly*,
  because a fast tick manufactures duplicate briefings.
- Once a busy tick is refused and records nothing, five minutes costs one query and no row. The
  operator sets the default to `*/5 * * * *`, and the UI offers it.

**Every task status gets classified once, in one place.**

- Four constants answer *"is this task live?"* today, and disagree:
  `CLAIMABLE_LOOP_TASK_STATUSES` (`hub/hub/scheduler.py`), `TERMINAL_FOR_BINDING`
  (`hub/hub/run_task_binding.py:272`), `_ACTIVE_TASK_STATUSES` (`hub/hub/api/v1/agents.py:60`) and
  `_LIVE_TASK_STATUSES` (`hub/hub/checkpoints.py:62`) — the last two identical in content and
  separate in code. **Both of the stall bugs fixed on 2026-08-20 lived in the gaps between them.**
- One named vocabulary classifies every status, and each of the four sets is derived from it, so a
  status added to the transition machine cannot silently belong to none.

**One place decides what a firing does.**

- What a firing does — claim, refuse because stalled, or proceed with an unfilled queue — becomes one
  function that both `_do_fire_job` and the board's `_batch_loop_summaries` call, so the board can
  say *why* a loop is doing nothing from the same computation that decided it.
- **This is what the flow needs from this change.** The flow adds a fourth answer — *fire a different
  agent for this task* — and this is where it lands.

**Non-Goals — explicitly out of scope, not merely omitted:**

- **Event-driven firing.** Decided against (exploration §9): the latency gap is invisible at a loop's
  timescale, and unfired wakers are a failure this codebase has already shipped and measured
  (`hub/hub/api/v1/agent_trigger.py:1236-1238`). The cron stays.
- **The loop choosing a reviewer.** The loop guarantees the *asking*; the agent keeps the *choosing*.
  A loop that routed work itself would need `list_agents` (L2) and would discard the operator's
  design.
- **A reviewer field on `Task`** (L4), **charter summaries in the Team section** (L1), and
  **`list_agents`** (L2). Independent, and this change is deliberately built not to need them.
- **A review-wait timeout** for a handoff that *did* reach a reviewer who never runs. Decided
  against, not deferred: once a stalled tick counts in place, such a loop reads *"stalled, waiting on
  review, N ticks since …"* — visible, cheap, and recoverable the moment anyone reviews it. A timeout
  would have to decide what to *do* when it fires, and stopping, reassigning and re-briefing are all
  worse than staying visible and waiting.
- **Changing which statuses any of the four sets contains.** The vocabulary work above is a
  refactor: every set keeps exactly the members it has today, derived rather than listed. Any change
  in membership is a behaviour change and belongs to a different proposal.

## Capabilities

### New Capabilities

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

- `hub/hub/scheduler.py` — `_do_fire_job` (the busy guard, tick recording), `_loop_stall_reason`,
  and the shared firing decision `_batch_loop_summaries` must reuse.
- `hub/hub/api/v1/jobs.py` — `_batch_loop_summaries` imports the claim's derivation rather than
  restating it (`:170`); that sharing must survive claimability becoming conditional.
- `hub/hub/run_task_binding.py`, `hub/hub/api/v1/agents.py`, `hub/hub/checkpoints.py` — each stops
  listing its status set and derives it from the shared vocabulary. No membership changes.

**Database**

- One migration, for the stall tick counter on `JobRun`. Guard for a missing table, as `0033`/`0034`
  do; bump the head assertions in `hub/tests/test_migrations.py` and
  `hub/tests/test_project_persistence.py`. The status vocabulary needs no migration — it changes
  code, not data.

**API / UI**

- `GET /api/v1/jobs/{job_id}` and `/history` return fewer, denser rows for an idle loop.
- The loop board's *current item* derivation must agree with the firing's — human-only check 13.1,
  and the reason `_loop_queue_order` is shared today (`hub/hub/scheduler.py:202-226` records what
  happened the one time they drifted).

**Behaviour already shipped that this builds on** (2026-08-20, committed): the stall skip
(`_loop_stall_reason`) and `revision_needed` joining `CLAIMABLE_LOOP_TASK_STATUSES`.

**Risk.** The firing's decision moves out of `_do_fire_job` into a function the board also calls. A
shared function is the mitigation, not the risk — the risk is anyone re-deriving it, which is the
failure this codebase has already had: *"two consistent wrong answers read as a match, which is how
it survived review"* (`hub/hub/scheduler.py:210-220`).
