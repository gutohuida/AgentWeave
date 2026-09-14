# Proposal — a spent allowance holds the queue

Finding: **F355 (B)**. Round 1 (explore and propose), 2026-09-14, the day window's build day
(`DECISIONS.md`, `### 2026-09-14 — a day that reads LoopEngine and builds what it finds`).

## Why

On the operator's own Hub (LoopEngine on `:8000`, database read `mode=ro` on 2026-09-14), the
provider's session limit was reached three times overnight. Each time the Hub kept spawning turns
into an allowance that could not serve them, and then gave the input up.

**What the record shows (measured, `%TEMP%\f355b.py`, `mode=ro`):**

- 69 runs failed carrying the harness's notice *"You've hit your session limit · resets 3:10am
  (Europe/Lisbon)"* (and 10:10pm, 8:10am). Each ended `Run failed (exit 1).` in 6–10 s.
- **All 69** also carried a structured `rate_limit_event` whose `rate_limit_info` has
  `"status": "rejected"` and an epoch `resetsAt`. The Hub already stores it on the run's
  `turn_usage.allowance` row (`runner_parsing.py:364-369`, `usage_accounting.py:54`).
- **None** of the 205 completed runs carried `"rejected"`. They carried `allowed` (136) or
  `allowed_warning` (69). So the status separates the two cases perfectly on this corpus.
- The three `resetsAt` values are 21:10, 02:10 and 07:10 UTC. These are the notices' 10:10pm,
  3:10am and 8:10am in Europe/Lisbon (UTC+1).

**What the Hub did with it: nothing.** `return_run_entries` (`inbound_queue.py:181-235`) treats every
failed run alike. Traced on `entry-3203bb7ad4e0` at 01:25:
1. Its first delivery was refused (`run-42cae48b5e1f`).
2. The entry was re-queued and re-delivered 10 s later. That delivery resumed the same session and
   was refused (`run-895a732851b8`). `RESUME_RETRY_LIMIT = 2` then **discarded the conversation's
   provider session**, although nothing was wrong with it.
3. The third delivery started a new session (`run-9f6ddd243259`, session `919e2f08…`) and was
   refused.
4. `DELIVERY_ATTEMPT_LIMIT = 3` then withdrew the entry: *"delivery failed 3 times; the Hub stopped
   retrying"*.

25 entries ended that way, and they were job steps, reviews and peer messages. The Architect's
review of `task-9e89a55ccc84` was one of them. It was never delivered again, and the flow recorded
64 times that the Architect *"is named on … as its reviewer and is not reviewing it"*.

**The limits were written for a different failure.** Their own comments say so
(`inbound_queue.py:165-178`, `:184-192`): they distinguish *"the session was poisoned"* from *"the
input is poisoned"*. A spent allowance is neither. The session and the input are both fine; the
provider will serve them at a time it has already stated. Counting the refusal spends the entry's
retries on a wall that says when it opens. Clearing the session throws away the agent's
provider-side context. Withdrawing the entry drops coordination nobody re-creates, because a flow
re-creates its own job steps on the next tick but nothing re-creates a peer message or a review.

**The session was worth keeping (measured, read-only).** The refused session `2a0bb6e2…`'s
transcript holds the delivered prompt and the refusal notice. The second delivery's resume found it
and appended a second refusal. So a resumed session is the agent's own record of the attempt the
provider refused.

## What changes

1. **A refusal is recognised from the structured reading, not the prose.** A turn is *refused by
   the allowance* when its accounting sample's `allowance` has `status == "rejected"` and a numeric
   `resetsAt` (design D1).
2. **A refused turn is not a delivery attempt.** Its input goes back to the queue with
   `delivery_attempts` unchanged, and the conversation's provider session is kept. The entry
   records the refusal in a new count, `allowance_refusals`, and carries the hold's sentence as its
   `waiting_reason` (D2, D8).
3. **The agent's queue is held until the reset.** The hold is **derived, not stored**: an agent is
   held while its most recent recorded turn outcome is a refusal and the reset has not passed.
   There is a 60 s floor after the refusal, so a `resetsAt` already in the past cannot become a
   spin (D3). While held, the scheduler starts no turn for autonomous input (D4).
4. **The operator's new input probes the allowance once.** A queued operator entry that arrived
   after the refusal lets one turn start. If the provider refuses that turn too, the refusal
   renews the hold, so there is no loop. If the provider serves it, the hold ends (D4).
5. **The Hub wakes the queue at the reset.** A one-shot timer at the hold's end re-schedules the
   agent. It is armed at every refused turn's end and re-armed at Hub start (D5).
6. **A loop does not fire into a held agent,** exactly as it does not fire into a running one
   (`agent-loops` *A firing is refused while its loop's agent is already running*). A flow inherits
   this through the rule that already composes it (D6).
7. **A plain job coalesces while its agent is held.** A firing whose job already has an entry
   queued for the held agent is recorded as skipped, not queued again. One copy of the standing
   instruction is delivered at the reset, not one per tick (D7).
8. **The hold is visible.** The queue status route names it. A `queue_agent_held` event is
   persisted and broadcast when a refusal starts or renews a hold (D9).

## Is any of this the operator's to decide?

The finding left two questions to R1: hold or drop, and whether a held queue also holds the flow's
job. `STATE-day.json` asks R1 to write an OPERATOR QUESTION if either is the operator's, and says
the change then stops after REV, unbuilt. **R1 finds that neither is open.** Each is settled by a
decision already shipped. The argument is written out so R2, R3 and REV can reject it:

- **Hold, not drop.** `agent-conversation-workspace` *Repeated delivery failure does not wedge an
  agent* gives up on input only because *"retrying without limit is indistinguishable from being
  stuck"*, and F96's decision (`turn_scheduler.py:536-546`, *"the input the product promised to
  hold until they performed the repair"*) keeps input across an environment failure the operator
  can wait out. A refusal with a stated reset time is not retrying without limit: it is a wait
  with a known end, and the input is delivered at that end. Nothing in the shipped contract
  prefers dropping.
- **Loops and flows.** `loop-notices-and-reacts` design D4 decided that a loop must not queue a
  briefing its agent cannot take now, because *"a second copy is stale before it is read"*. That
  argument applies unchanged to an agent that cannot take a turn until 02:10. A flow composes D4
  through D12 (`_loop_flow_busy_reason`: busy *and* nobody else free), so it needs no new rule.
- **Plain jobs are the weakest of the three, and the one most open to challenge.** The shipped
  position (`_loop_agent_busy_reason`'s docstring, `scheduler.py:235-238`) is that a plain job
  firing while its agent is busy *queues*, *"a standing instruction still true when the agent
  frees up"*. Queuing every tick was harmless while a busy turn lasted minutes. A hold can last
  five hours, or days for a `seven_day` refusal, and it would pile up one copy per tick. Coalescing
  keeps the shipped position's reason (the instruction is delivered when the agent frees up) and
  drops only the duplicates. It dominates both alternatives: skipping would lose a daily job's
  instruction until the next day, and queuing every tick would deliver the same instruction many
  times. **If REV judges this a policy choice, it is the change's one candidate OPERATOR QUESTION,
  and D7 is severable:** without it, plain jobs behave as today, which is to queue every tick.

## What does not change

- **No edit to `hub/hub/mcp_server.py`** (day rule, F354). Nothing here needs one.
- **No UI change**, and no UI bundle. The existing queue status sentence carries the hold.
- **Codex** is unchanged. The only code that fills `AccountingSample.allowance` is Claude's
  `rate_limit_event` branch (`runner_parsing.py:364-369`). `grep -rn "allowance=" hub/hub` finds
  only that and its pass-throughs, and `read_codex_rollout_accounting` (`:669`) sets none. So
  recognition cannot fire for Codex. Codex is undrivable on this machine (plan cancelled
  2026-08-29).
- **The prose notice is not parsed.** Its time is local, formatted by the harness, and carries no
  date.
- **Poisoned sessions and poisoned input** keep today's limits exactly.

## Migration

**One: `0103`, adding `inbound_queue_entries.allowance_refusals`** (integer, not null, server
default `0`, guarded for a missing table). The operator's next restart of `:8000` applies it to
their real database. It is additive. See design D8 for why it is a column and not a reinterpretation
of `delivery_attempts`.

## Capabilities

- `agent-conversation-workspace`: MODIFIED *Repeated delivery failure does not wedge an agent* and
  *A re-delivered turn says the earlier attempt was cut off*; ADDED *A turn the provider's allowance
  refused holds the agent's queue until the reset*.
- `agent-loops`: MODIFIED *A firing is refused while its loop's agent is already running*; ADDED
  *A job firing into a held queue is coalesced*.

## Impact

- `hub/hub/provider_allowance.py` (new): recognition, the derived hold, and the sentence.
- `hub/hub/inbound_queue.py`: `return_run_entries(..., held_until=...)` and `format_turn_prompt`.
- `hub/hub/turn_scheduler.py`: the hold check in `_attempt_turn`.
- `hub/hub/api/v1/agent_trigger.py`: `_execute_run` passes the recognition, arms the wake, emits
  the event.
- `hub/hub/scheduler.py`: `_loop_agent_busy_reason`, the plain-job coalesce in `_do_fire_job`, and
  the wake's date job.
- `hub/hub/main.py`: re-arm at start.
- `hub/hub/api/v1/inbound_queue.py`: the status route's reason.
- `hub/hub/db/models.py` and migration `0103`.
- The migration head assertions in `hub/tests/test_migrations.py` and
  `hub/tests/test_project_persistence.py`.
