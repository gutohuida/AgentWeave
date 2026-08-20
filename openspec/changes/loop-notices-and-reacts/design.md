## Context

A loop is *"an `AIJob` wearing a purpose and an optional stop condition"* with 24 requirements
accumulated around it. Its firing path (`hub/hub/scheduler.py::_do_fire_job`) asks exactly one
question before working — *should this loop stop?* — and otherwise proceeds. This change adds the
two questions it should also be asking: *is my agent already busy?* and *did the work I finished
last time actually go anywhere?*

**What already landed 2026-08-20, before this change**, and which this design builds on rather than
redoing:

- `_loop_stall_reason` — a firing that would claim nothing on a non-drained queue is skipped instead
  of spawning an agent to do nothing. Reproduced first, in
  `test_loop_whose_tasks_are_all_completed_but_unapproved_spins`.
- `revision_needed` joined `CLAIMABLE_LOOP_TASK_STATUSES` — a reviewer who correctly sent work back
  no longer strands the loop.

Neither was specified through openspec; the `agent-loops` delta in this change is where the stall
refusal gets its requirement, retroactively and deliberately.

**The constraint that shapes everything below.** `_batch_loop_summaries`
(`hub/hub/api/v1/jobs.py:170`) imports `CLAIMABLE_LOOP_TASK_STATUSES` and `_loop_queue_order` from
the scheduler rather than restating them, because the board and the firing must not disagree about
which queue item is current. `_loop_queue_order`'s own comment records what happened the one time
they drifted: *"Both derivations shared the flaw, so the board and the firing agreed on the wrong
task — two consistent wrong answers read as a match, which is how it survived review."*

## Goals / Non-Goals

**Goals:**

- A finished task never waits on a handoff that silently never happened.
- The loop's agent keeps deciding *who* reviews; the loop only guarantees it is *asked*.
- A firing costs nothing when there is nothing to do, at any cron interval.
- A loop's execution history stays readable when the loop is idle.

**Non-Goals:** as stated in the proposal — no event-driven firing, no loop-chosen reviewer, no
review-wait timeout (R4), no `Task` reviewer field, no `list_agents`, no status-set unification, no
change to any loop's default cron interval.

## Decisions

### D1 — The handoff signal is derived, never stored

Two lookups over rows that already exist: a `Message` with `task_id` and `type == "review"`
(`hub/hub/db/models.py:509,513`), and `TaskTransition.actor_agent` for the move into `under_review`
compared against the agent recorded moving it to `completed` — the pattern `_agent_that_completed`
already uses (`hub/hub/task_transition_service.py:92-116`).

*Rejected:* **a `handed_off_at` column on `Task`.** A denormalised copy of a fact two tables already
hold, and it would go stale exactly when it matters — an agent that sends the message through any
path not updating the column produces a task that looks un-handed-off forever. The same reasoning
that made `_loop_stop_reason` derive its queue state from task rows rather than a flag on `Loop`.

*Rejected:* **asking the agent whether it handed off.** The product does not ask agents to attest to
their own compliance, and it would be unfalsifiable.

**Why this is not the retired question-detection backstop.** CLAUDE.md is explicit that inferring
whether trailing prose is a question is *"a judgement the product should not make on the operator's
behalf"*, and that feature was deleted for it. The distinction that permits this one: the backstop
**inferred intent from prose**; every branch here is a lookup on a row, and returns the same answer
to whoever asks it.

### D2 — `under_review` alone does not mean a reviewer has it

`completed -> under_review` is `_BOTH` (`hub/hub/task_transitions.py:135`) and **unguarded** —
`_REVIEW_OUTCOMES` is `{approved, rejected, revision_needed}`
(`hub/hub/task_transition_service.py:89`), so `_guard_author_is_not_reviewer` returns early for it.
With no reviewer field on `Task`, an author can move its own task to `under_review` with nobody on
the other end. The actor comparison is what closes that hole, and omitting it would leave a silent
stall reachable through a status that *looks* like progress.

**The operator moving a task to `under_review` counts as a review in flight.** The operator may
approve their own work by design (`_guard_author_is_not_reviewer`, D9 of the transition machine), so
operator involvement is by definition a review that can complete.

### D3 — Claimability becomes a shared predicate, not a widened tuple

`completed` must **not** join `CLAIMABLE_LOOP_TASK_STATUSES`. That tuple means *"the firing works
this task"*, and a re-brief is not working the task — it changes nothing about it. Widening the tuple
would also make the board show a `completed` task as the loop's current item, which is false.

Instead the firing gains a decision **after** the claim returns nothing:

```
   _do_fire_job
     ├── loop stopped?          -> refuse, record, disable      (unchanged)
     ├── agent already running? -> refuse, record NOTHING       (D4)
     ├── claim a task           -> proceed as today
     └── claimed nothing?
           ├── un-handed-off finished task, under the bound? -> RE-BRIEF   (D5)
           ├── otherwise stalled?                            -> refuse, count (D6)
           └── queue never filled / drained?                 -> proceed as today
```

*Rejected:* **a second status tuple for "re-briefable".** Two tuples read by two callers is the
drift shape the codebase has already been bitten by. The re-brief decision lives in one function that
both `_do_fire_job` and `_batch_loop_summaries` call, so the board can label the loop *"waiting for a
handoff"* from the same computation that drives the behaviour.

### D4 — A busy firing records nothing at all

There is no already-running guard in the firing path today; `schedule_agent` refuses to *start* a
turn (`hub/hub/turn_scheduler.py:43`) but the firing has already claimed and queued by then.
**Measured:** five firings during one turn produced five queued entries and five `JobRun`s, which the
agent then drains as five separate turns all briefed on the same task.

The guard is the same shape as `_job_agent_skip_reason`, already in that function, and must run
**before** the claim and before `new_entry`.

It writes no `JobRun`. A busy tick carries no information the `in_progress` `JobRun` does not already
carry, and `_batch_loop_summaries` reads exactly that row to decide whether a loop is running
(`hub/hub/api/v1/jobs.py:216`). Recording the tick would duplicate a fact and evict real history
through `_prune_job_history`'s 100-row window.

*Rejected:* **recording busy ticks behind a UI filter.** The prune window still fills, so real
history ages out at a fast cron — the problem moved rather than solved.

### D5 — The re-brief occupies a whole firing

The firing composes a briefing naming the task and stating it was completed without being sent for
review, and does not claim anything else.

*Rejected:* **appending the reminder to the next task's briefing.** Cheaper — no tick spent on one
message — but it breaks the one-item-per-firing model (`_claim_loop_task` returns exactly one task),
and a reminder buried under a fresh task assignment is precisely the instruction an agent skips.
That is the failure being fixed, reintroduced as the fix.

The firing **does not** change the task's status. Moving it would manufacture a transition nobody
made, which is the class of untrue record the transition machine exists to prevent.

### D6 — Repetition is counted, not appended

A stall records one `JobRun`, and subsequent refusals for the same stall increment a count on it.

The precedent is `InboundQueueEntry.delivery_attempts` (`hub/hub/db/models.py:551-557`), which chose
a counter over duplicate rows for the identical problem: *"an entry returned five times is
indistinguishable from one never tried."*

**A departure taken knowingly:** this row is *updated*, where `JobRun` is otherwise written once.
`JobRun` is not held to `TaskTransition`'s explicit append-only rule, so it is permitted — but it is
a change in that table's write semantics and is being chosen rather than discovered.

"The same stall" means the most recent `JobRun` for this job is a stall record and the stall reason
is unchanged. A different reason starts a new row, so a stall that changes shape is visible.

### D7 — The re-brief count lives on the task, and resets on success

Per task, because *"task 1 was asked about three times"* is the sentence an operator needs, and a
per-loop count would exhaust on one stubborn task and silence reminders for every other.

It resets when the task acquires a review in flight. Without a reset a task through a legitimate
`revision_needed` cycle — which reaches `completed` more than once by design — would arrive at its
second completion with the budget already spent.

### D8 — Exhaustion surfaces; it never stops the loop

Setting `job.enabled = False` and calling `remove_job` is what `_loop_stop_reason` does, and it is
unrecoverable by the operator simply resolving the situation afterwards. That is the same objection
that chose *skip* over *stop* for the stall on 2026-08-20, and it applies unchanged here.

*Rejected:* **surfacing on the first failure** — a single missed handoff can be one bad turn, and
pulling the operator into an unattended loop for something that self-corrects is the wrong default.
*Rejected:* **re-briefing without a bound** — the silent-forever failure with extra steps.

**The single-agent project needs no special case.** It has nobody to hand off to, so it exhausts the
bound immediately and surfaces — which is the correct outcome, reached by the general rule.

### D9 — One status vocabulary, four derived sets, no membership changes

Four constants answer *"is this task live?"* and none knows the others exist:

| Constant | Where | Members |
|---|---|---|
| `CLAIMABLE_LOOP_TASK_STATUSES` | `hub/hub/scheduler.py` | `pending assigned in_progress blocked revision_needed` |
| `TERMINAL_FOR_BINDING` | `hub/hub/run_task_binding.py:272` | `approved rejected` |
| `_ACTIVE_TASK_STATUSES` | `hub/hub/api/v1/agents.py:60` | `pending assigned in_progress under_review revision_needed` |
| `_LIVE_TASK_STATUSES` | `hub/hub/checkpoints.py:62` | identical to the row above |

**Both stall bugs fixed on 2026-08-20 lived in the gaps.** The spin, because `completed` was in
neither of the first two. `revision_needed`, because it was in neither — while the *other two* sets
already called it live work. Four opinions, and the disagreement was the bug both times.

The fix is a classification, not a fifth set: every status in `TRANSITIONS` belongs to exactly one
band, and each of the four sets is derived from the bands rather than listed. A status added to the
transition machine and not classified fails at import, not at 3am in a loop that fires forever.

**Membership does not change.** Each derived set must contain exactly what it contains today; a test
asserts each one against its current literal before the literal is deleted. This is what keeps a
refactor from smuggling in a behaviour change — and it is why this can safely ride along with the
rest of this proposal rather than needing its own.

*Rejected:* **leaving it and relying on the derived-gap test** added on 2026-08-20. That test catches
a status in neither `CLAIMABLE` nor `TERMINAL` — the exact shape that bit twice — but says nothing
about the other two sets, and nothing about a status that belongs to the wrong band rather than to
none.

*Rejected:* **its own change.** The vocabulary's first real consumer is D3's shared claim decision,
which is in this change. Landing them apart means writing D3 against the four-set world and
rewriting it immediately.

## Risks / Trade-offs

**[The board and the firing drift, because claimability is now conditional]** → One function, called
by both, per D3. A test asserts the board's *current item* and the firing's claim agree for a queue
holding an un-handed-off task — this is human-only check 13.1 made mechanical.

**[The re-brief is itself ignored, and the loop burns turns reminding]** → Bounded by D7, and the
bound is small. Worst case is N wasted turns per task, against today's unbounded silence.

**[An agent had a good reason not to hand off]** → It has the bound's worth of turns to act
otherwise, and exhaustion surfaces to the operator rather than forcing anything. The product does not
try to distinguish "forgot" from "chose not to" — that would be inferring intent, which D1 refuses.

**[The counted stall row makes `JobRun` writes non-idempotent]** → Confined to stall records, whose
identity is "most recent run for this job, same reason". Accepted explicitly in D6.

**[A migration on a table the scheduler orders by]** → Guard for a missing table as `0033`/`0034` do,
because upgrades from an early revision reach it with only that revision's tables. Bump the head
assertions in `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`.

**[The D9 refactor silently changes a set's membership]** → Each derived set is asserted equal to its
current literal *before* the literal is removed, per D9. A refactor that changes behaviour fails that
assertion rather than shipping.

## Migration Plan

Additive columns only; no backfill. A task with no recorded re-brief count reads as zero, which is
correct for every task that existed before this change. A `JobRun` with no tick count reads as one.

Rollback is dropping the columns: the derivation in D1 reads pre-existing tables, so the signal
survives a rollback even though the behaviour does not.

## Open Questions

- **Is the re-brief bound configurable per loop or per project?** A constant of **three** for this
  change (see below). Nothing has measured it, so the first real use is the evidence.
- **What does the board show for a loop that is re-briefing?** The state is derivable per D3; whether
  it gets its own label or reuses the stall presentation is undecided.
- **What band does `blocked` belong to under D9?** It is claimable by the loop yet means *"waiting on
  a person"*. Today's sets disagree — `CLAIMABLE_LOOP_TASK_STATUSES` includes it, the other three do
  not. The classification must state which it is, and the answer is not obvious from existing code.

**Closed since first drafting:**

- **How many re-briefs?** **Three.** A number nothing has measured, chosen because it is small enough
  that three wasted turns are cheap and large enough that a single bad turn does not escalate to the
  operator. Cheap to change once real use says otherwise.
- **R4, the review-wait timeout.** **Decided against**, not deferred — see the proposal's non-goals.
  Once a stalled tick counts in place, a loop waiting on an absent reviewer is already visible and
  already recoverable; a timeout would have to choose an action, and every candidate is worse than
  continuing to wait visibly.
