## Context

A loop is *"an `AIJob` wearing a purpose and an optional stop condition"* with 27 requirements
accumulated around it *(24 when this was written; `task-dependencies` added §690 and §723)*. Its
firing path (`hub/hub/scheduler.py::_do_fire_job`) asks exactly one
question before working — *should this loop stop?* — and otherwise proceeds. This change adds the
question it should also be asking before it works: *is my agent already busy?* — and adds the
vocabulary and the shared decision point that make the answer trustworthy.

**Scope narrowed 2026-08-21.** This change originally also guaranteed the review handoff, by
detecting a missing one and re-briefing the agent. That is superseded by
`openspec/explorations/2026-08-21-a-review-is-a-task-not-a-message.md` and
`2026-08-21-the-loop-becomes-a-flow.md`: a finished task becomes claimable by a non-author and the
flow fires the reviewer, so there is no message to forget and nothing to remind anyone about. The
withdrawn decisions are kept below as numbered stubs rather than renumbered away.

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
(`hub/hub/api/v1/jobs.py`) imports its status set, `_loop_queue_order` and `candidate_is_startable`
from the scheduler rather than restating them, because the board and the firing must not disagree
about which queue item is current. *(Updated 2026-08-24: it used to import
`CLAIMABLE_LOOP_TASK_STATUSES` and restate the startability rule inline. `loop-becomes-a-flow`
group 1 extracted `candidate_is_startable` so the rule is shared rather than mirrored, and the set
it imports is now `CURRENT_ITEM_TASK_STATUSES` — see D9's corrected table for why those are two
sets.)* `_loop_queue_order`'s own comment records what happened the one time
they drifted: *"Both derivations shared the flaw, so the board and the firing agreed on the wrong
task — two consistent wrong answers read as a match, which is how it survived review."*

## Goals / Non-Goals

**Goals:**

- A firing costs nothing when there is nothing to do, at any cron interval.
- A loop's execution history stays readable when the loop is idle.
- Every task status is classified once, so the sets that ask *"is this live?"* cannot disagree.
- One decision point deciding what a firing does — the place the flow will later extend.

**Non-Goals:** as stated in the proposal — no event-driven firing, no reviewer selection of any
kind, no review-wait timeout, no `list_agents`, no change to which statuses any set contains, and
**nothing about who does the work**. That is the flow's, and this change deliberately stops at
giving it somewhere to land.

## Decisions

### D1 — The handoff signal is derived, never stored — **WITHDRAWN 2026-08-21**

Superseded by `openspec/explorations/2026-08-21-a-review-is-a-task-not-a-message.md`. There is no
handoff message to detect: a finished task becomes claimable by a non-author, and the flow fires the
reviewer. Kept as a numbered gap rather than renumbered, so the reasoning that was taken and then
reversed stays findable.

### D2 — `under_review` alone does not mean a reviewer has it — **WITHDRAWN 2026-08-21**

The *observation* survives and matters more than ever: `completed -> under_review` is `_BOTH` and
unguarded (`hub/hub/task_transitions.py:135`), so an author can move its own task there with nobody
on the other end. Under the flow that becomes a question about who may claim, not about how to read a
signal, and it moves to the flow's proposal.

### D3 — Claimability becomes a shared predicate, not a widened tuple

What a firing does stops being spread across `_do_fire_job` and becomes one function both it and
`_batch_loop_summaries` call:

```
   _do_fire_job
     ├── loop stopped?          -> refuse, record, disable      (unchanged)
     ├── agent already running? -> refuse, record NOTHING       (D4)
     └── the decision:
           ├── a claimable task    -> claim and proceed          (as today)
           ├── stalled             -> refuse, count              (D6)
           └── never filled/drained -> proceed                   (as today)
```

**The fourth answer is deliberately left room for.** The flow adds *"fire a different agent for this
task"*, and this is where it lands
(`openspec/explorations/2026-08-21-the-loop-becomes-a-flow.md` §3). Building that decision point now,
with three answers, is most of what the flow needs from this change — which is why it stays in scope
even though the handoff work left.

*Rejected:* **leaving the logic inline in `_do_fire_job` and having the board re-derive it.** Two
derivations read by two callers is the drift shape the codebase has already been bitten by, and the
board must be able to say *why* a loop is doing nothing from the same computation that decided it.

### D4 — A busy firing records nothing at all

There is no already-running guard in the firing path today; `schedule_agent` refuses to *start* a
turn (`hub/hub/turn_scheduler.py:44`) but the firing has already claimed and queued by then.
**Measured:** five firings during one turn produced five queued entries and five `JobRun`s, which the
agent then drains as five separate turns all briefed on the same task.

The guard is the same shape as `_job_agent_skip_reason`, already in that function, and must run
**before** the claim and before `new_entry`.

It writes no `JobRun`. A busy tick carries no information the `in_progress` `JobRun` does not already
carry, and `_batch_loop_summaries` reads exactly that row to decide whether a loop is running
(`hub/hub/api/v1/jobs.py`, the `firing_active` query). Recording the tick would duplicate a fact
and evict real history through `_prune_job_history`'s 100-row window.

*Rejected:* **recording busy ticks behind a UI filter.** The prune window still fills, so real
history ages out at a fast cron — the problem moved rather than solved.

### D5 — The re-brief occupies a whole firing — **WITHDRAWN 2026-08-21**

No re-brief. See D1.

### D6 — Repetition is counted, not appended

A stall records one `JobRun`, and subsequent refusals for the same stall increment a count on it.

The precedent is `InboundQueueEntry.delivery_attempts` (`hub/hub/db/models.py:561`), which chose
a counter over duplicate rows for the identical problem: *"an entry returned five times is
indistinguishable from one never tried."*

**A departure taken knowingly:** this row is *updated*, where `JobRun` is otherwise written once.
`JobRun` is not held to `TaskTransition`'s explicit append-only rule, so it is permitted — but it is
a change in that table's write semantics and is being chosen rather than discovered.

"The same stall" means the most recent `JobRun` for this job is a stall record and the stall reason
is unchanged. A different reason starts a new row, so a stall that changes shape is visible.

### D7 — The re-brief count lives on the task — **WITHDRAWN 2026-08-21**

No re-brief. See D1. The *principle* it rested on — count repetition rather than appending a row —
survives in D6, which is where it is actually load-bearing.

### D8 — Exhaustion surfaces; it never stops the loop — **WITHDRAWN 2026-08-21**

Partly superseded. Nothing exhausts, because nothing reminds. What survives is narrower and belongs
to the flow: a task the flow **could not staff**, because no eligible agent exists, is worth
surfacing — a statement about the roster, not about an agent's diligence. The rule that surfacing
must never disable the job is unchanged and restated wherever it lands.

### D9 — One status vocabulary, four derived sets, no membership changes

**Corrected 2026-08-24.** This table said `CLAIMABLE_LOOP_TASK_STATUSES` contained `blocked`. It
has not since 2026-08-21, when `blocked` left the claim to stop a firing spawning an agent every
tick against work that cannot move. There are also five constants now, not four. The membership
column below is measured, not remembered:

| Constant | Where | Members |
|---|---|---|
| `CLAIMABLE_LOOP_TASK_STATUSES` | `hub/hub/scheduler.py` | `in_progress assigned pending revision_needed` |
| `CURRENT_ITEM_TASK_STATUSES` | `hub/hub/scheduler.py` | the above **plus `blocked`** |
| `TERMINAL_FOR_BINDING` | `hub/hub/run_task_binding.py:293` | `approved rejected` |
| `_ACTIVE_TASK_STATUSES` | `hub/hub/api/v1/agents.py:60` | `pending assigned in_progress under_review revision_needed` |
| `_LIVE_TASK_STATUSES` | `hub/hub/checkpoints.py:62` | identical to the row above |

**`CURRENT_ITEM_TASK_STATUSES` was added on 2026-08-24 to fix a live defect, and it is the sharpest
argument for this whole decision.** The board was using the *claimable* set to answer *"what is this
loop working on"*. When `blocked` left the claimable set — correctly, for the claim — the board
silently lost sight of blocked tasks with it, so a loop parked on an unanswered question reported
`queue: {blocked: 1}` and **no current item**. The one surface that exists to say what a loop is
waiting for said nothing was happening. Reproduced before the fix; no test covered it.

So the framing above — *four constants answer "is this task live?"* — is itself the trap. They do
**not** all answer one question. `blocked` is *no* to "may a firing claim this?" and *yes* to "is
this the loop's current work?", and a classification that cannot express that difference will
re-merge them and reproduce the defect.

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

### D10 — Five minutes

There is no default to change: `create_loop` requires `cron` (`hub/hub/mcp_server.py:547`) and the
UI's five examples bottom out at every six hours (`hub/ui/src/components/jobs/JobForm.tsx:13-19`). So
a loop polls on whatever the caller invents, and until the busy guard lands the honest advice is
*slowly*, because a fast tick manufactures duplicate briefings.

**DECIDED: `*/5 * * * *`.** With D4 refusing a busy tick and D6 counting a stalled one, five minutes
costs one query and no row. That bounds the latency between one step finishing and the next starting
at five minutes, which is the cost of choosing polling over events
(`2026-08-20-who-guarantees-the-review-handoff.md` §9) — and it only becomes payable now.

**A stalled loop's label says what it is waiting on**, not merely that it is waiting. The
*re-briefing* label this decision originally also specified is withdrawn with D1; the flow will need
a label of its own for *"staffing the next step"*, and that belongs with the flow.

## Risks / Trade-offs

**[The board and the firing drift, because claimability is now conditional]** → One function, called
by both, per D3. A test asserts the board's *current item* and the firing's claim agree for a queue
holding an un-handed-off task — this is human-only check 13.1 made mechanical.

**[The counted stall row makes `JobRun` writes non-idempotent]** → Confined to stall records, whose
identity is "most recent run for this job, same reason". Accepted explicitly in D6.

**[A migration on a table the scheduler orders by]** → Guard for a missing table as `0033`/`0034` do,
because upgrades from an early revision reach it with only that revision's tables. Bump the head
assertions in `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`.

**[The D9 refactor silently changes a set's membership]** → Each derived set is asserted equal to its
current literal *before* the literal is removed, per D9. A refactor that changes behaviour fails that
assertion rather than shipping.

## Migration Plan

Additive only; no backfill. A `JobRun` with no tick count reads as one, which is correct for every
row written before this change. The status vocabulary (D9) changes no data at all — it replaces
literals with a derivation, asserted equal to those literals before they are deleted.

Rollback is dropping the tick column and restoring the literals.

## Open Questions

- ~~**What band does `blocked` belong to under D9?**~~ **Answered 2026-08-21, before this change
  starts.** `openspec/explorations/2026-08-21-which-band-blocked-belongs-to.md` decided it, and
  `scheduler.py` carries the reasoning in full: `blocked` sits with `completed` and `under_review`
  in the *"someone else's turn"* band, and its "someone else" is the most literal of the three — a
  person holding an unanswered question. The test that separates it from `revision_needed`, which
  went the other way the day before, is whether firing an agent makes progress *possible*.
  The premise of the question was also wrong: it said `CLAIMABLE_LOOP_TASK_STATUSES` includes
  `blocked`. It does not.

  **What is still open is narrower and newer:** a band alone cannot produce both
  `CLAIMABLE_LOOP_TASK_STATUSES` and `CURRENT_ITEM_TASK_STATUSES`, because `blocked` belongs to one
  and not the other. Deriving both from one classification needs the sets to be defined as unions
  of bands *per question*, not as a single "live" band — see D9.

**Closed since first drafting:**

- **R4, the review-wait timeout.** **Decided against**, not deferred — see the proposal's non-goals.
  Once a stalled tick counts in place, a loop waiting on an absent reviewer is already visible and
  already recoverable; a timeout would have to choose an action, and every candidate is worse than
  continuing to wait visibly.
