# Design — a retried firing records how its work ended

**Built on the recommended answer to D1**: a `JobRun` row is a *dispatch* (one agent's share of one
firing, correlated to its run through its own conversation); a `Run` row is an *attempt*; a
*firing* is the rows sharing `(job_id, fired_at)`. If the operator answers D1 otherwise:

- *a row is an attempt*: F123's shape 2 — append a `JobRun` per retry. This change is replaced; the
  counter change `a-firing-is-counted-once-however-many-agents-it-starts` must then count distinct
  `fired_at` values instead;
- *keep the row terminal and mark the job* (F123's shape 3, a `continuity_warning`): this change is
  replaced by a presentation change on `JobResponse`, and the history keeps reading `failed`.

**Round 1, 2026-09-24.** Nothing here is implemented yet.

## Context

### Where a dispatch is concluded today

| Site | Line | Order today | Input handed back? |
|---|---|---|---|
| Failure tail (`_record_run_failure_tail`, both transports) | `agent_trigger.py:2050-2051` | finalize `failed`, then `return_run_entries` | yes, below the limit |
| Pre-spawn failure, process transport | `:2193-2194` | same | yes, below the limit |
| Pre-spawn failure, Codex | `:3065-3066` | same | yes, below the limit |
| Finalize, process transport | `:2521-2528` | finalize `final_status` unless a refusal, then return if `failed` and no binding conflict | if `failed` |
| Finalize, Codex | `:3159-3163` | finalize `final_status`, then return if `failed` and no binding conflict | if `failed` |
| Startup reaper | `run_reconciliation.py:258-281` | `failed` if `.first()` Run is not running and no refusal wait | — |
| Firing's own schedule refusal | `scheduler.py:3471-3477` (primary), `:3611-3616` (each extra selection, `_start_additional_turns`) | `failed` with `waiting_reason` | input stays queued (not a run) |

`finalize_job_run_for_conversation` (`scheduler.py:2282-2303`) flips the newest `in_progress` row on
the conversation and nothing else.

### Where job input leaves the queue without a run

| Writer | Line | Today's effect on the dispatch |
|---|---|---|
| Scheduler gives up at the limit | `turn_scheduler.py:600-640` | none (the row was already `failed` by the first attempt's run end, or by `scheduler.py:3471`) |
| Request-level refusal withdrawn | `agent_trigger.py:1625`, `inbound_queue.py:440` | none, and never can be: the only caller withdraws the trigger route's own entry, always `origin_type="operator"` (`agent_trigger.py:1567-1571`). **Not a D3 writer** (R2) |
| Operator withdraws | `api/v1/inbound_queue.py:259-272` | none |

Today the give-up needs to conclude nothing, because the first failing attempt already did. The
operator's withdrawal **already strands a row today** (R2): a job's input queued behind a busy agent
(`"agent is already running"`, `terminal_failure=False`, so `scheduler.py:3472` does not fire) is
withdrawn, and its `in_progress` row waits for the next Hub start. Once
D2 below stops that, each of them becomes the last event of a dispatch and must conclude it, or the
row strands `in_progress` until the next Hub start. That would break *"A firing that starts no agent
SHALL NOT be reported as running"* (`loop-firing-accountability/spec.md:6`) in a new way.

### Why the conversation is the right correlation still

`JobRun` has no foreign key to `Run` or to the queue entry (`db/models.py:1424-1429`). The
conversation is the correlation every reader already uses (`scheduler.py:2282`, `run_reconciliation.py:236`,
`api/v1/jobs.py:454-466`, `checkpoints.py:150`, `checkpoint_handover.py:113`, `api/v1/agent_chat.py:373`).
A job's input is written with `origin_type="job"` (`scheduler.py:3407`, `:3739`), which is what
distinguishes it from an operator's follow-up message typed into the same conversation.

## Decisions

### D1 — A dispatch concludes when its input has

`conclude_dispatches_for_conversation(db, conversation_id, status, *, reason=None)` replaces
`finalize_job_run_for_conversation`. It concludes nothing if either holds:

- an `InboundQueueEntry` on the conversation has `origin_type == "job"` and `state == "queued"`;
- a `Run` on the conversation has `status == "running"`.

Otherwise it sets **every** `in_progress` row on the conversation to `status`, and writes `reason`
to `error_summary` where one is given (through the model's `@validates` fitter,
`db/models.py:1413-1419`).

*Every*, not the newest: a `resume` job's later firing can queue into the same conversation while an
earlier dispatch's input is still waiting (the D1 rule now lets that happen), and one turn delivers
both (a turn can carry several of one conversation's entries; `inbound_queue.deliver_entries_with_run` refuses only entries from different conversations, `:163-166`). Today's
`first()` would leave the older row `in_progress` forever.

*Job input*, not any input: an operator's follow-up typed into a job's conversation is not the
dispatch's work. Keying on any queued entry would keep a completed dispatch open until that message
is answered.

*Rejected:* **let the retry overwrite a `failed` row** (F123 shape 1). Makes a terminal status
mutable and erases that anything went wrong; also still wrong in between, where the row reads
`failed` while the retry runs.
*Rejected:* **append a row per retry** (F123 shape 2). That is D1's *attempt* answer; it inflates
every counter that reads rows, which is F121.
*Rejected:* **mark the job, keep the row** (F123 shape 3). The job view then carries a warning while
its history still says `failed`; two surfaces disagree.

**What the history loses:** that an attempt was cut off. It is not lost from the product: the
conversation shows *Turn interrupted* on the interrupted run (the run facts map), and the retried
turn is annotated to the agent (`agent-conversation-workspace`, *A re-delivered turn says the earlier
attempt was cut off*). The dispatch record says how the work ended; the attempt record says how
each attempt did.

### D2 — Run-end sites conclude after handing input back

At all five sites the call moves below `return_run_entries` in the same session and before the same
commit. Autoflush is on (`db/engine.py:163`, default), so the query in D1 sees the entries just
returned and the `Run` just made terminal. The status passed is unchanged (`failed` at the three
failure sites, `final_status` at the two finalize blocks).

The allowance-refusal guard at `agent_trigger.py:2521` (`if refusal is None:`) is deleted: its input
is returned `queued` (`inbound_queue.py:262-269`), so D1 does not conclude. The comment at
`:2515-2520` is kept and generalised; it is this change's precedent.

An entry abandoned at the limit by `return_run_entries` is `withdrawn`, not `queued`
(`inbound_queue.py:282-290`), so the rule holds and the dispatch concludes `failed` at that run's end.
The reason written is the entry's `abandoned_reason`, where the run carried one abandoned job entry;
otherwise no reason, as today.

### D3 — Input taken out of the queue concludes its dispatch

After each writer below commits, for each **job-origin** entry it withdrew, call D1's function on
that entry's conversation:

| Writer | Status | Reason |
|---|---|---|
| `turn_scheduler` give-up | `failed` | the entry's `abandoned_reason` |
| operator withdrawal | `stopped` | `"Withdrawn by the operator"` |

`stopped` is an existing `JobRun` status (`db/models.py:1395`), written today when a run is stopped.
An operator withdrawing queued input is the same act on input that has not started.

**What the routes return when this raises.** `DELETE /queue/entries/{id}` withdraws and commits
first (`_withdraw_if_queued`, `inbound_queue.py:387-431`). The conclusion is a second write. If it
raises, the withdrawal has already happened and cannot be un-said, so the route **logs the failure
naming the dispatch and still answers 200 with the withdrawn entry**. The row stays `in_progress`,
which the startup reaper then concludes (D4: no queued input, no running run). The route must not
answer 500 for a withdrawal that happened: the operator would retry it and be told *not queued*.
The scheduler give-up is not a route; it logs and continues, for the same reason.

### D4 — The reaper asks the same question

`reconcile_stale_job_runs` replaces its body's test with D1's two conditions, computed per row as
`EXISTS` queries. That fixes F147's latent `.first()` (`run_reconciliation.py:265-268`) by
construction: the question is *is any run on this conversation running*, which has no order.

**R3 bounds the queued-input half the way the live path is bounded.** The reaper leaves a row open
for its queued job input only where the Hub can still deliver that input: the input's agent has a
runner bound (`Agent.runner_id is not None`, the test `trigger_agent_directly` refuses on,
`agent_trigger.py:688`), or it waits on a provider refusal (today's `_waits_on_a_refusal`,
`:214-229`, narrowed to `origin_type == "job"` entries). Otherwise it concludes `failed` as today.
So `_waits_on_a_refusal` is **kept and widened**, not deleted, and the pinned case
`test_a_held_agent_is_busy.py:732-739` (queued input, no runner, no refusal → `failed`) stays a
control. The F123 crash is still fixed: the crashed run's agent had a runner, or it could not have
run. Why bounded: the live path concludes a firing whose turn cannot begin `failed` at once
(`scheduler.py:3471-3477`, D5, unchanged here). A reaper that left the same firing open when the
Hub died a moment earlier (between the commit at `:3444` and `:3472`) would give one firing two
verdicts according to when the Hub died. Both widen together if Open Question 1's follow-up lands.

**The unbounded form R2 described, kept for Open Question 3.** That comment
(`run_reconciliation.py:251-257`) keeps failing a firing *"waiting for a runner to be bound"*
because the Hub cannot promise that repair. With D1, a row whose **retried** input is queued for an
agent that has since lost its runner stays `in_progress`. That is what the queue itself promises
(F96, `turn_scheduler.py:670-673`: *"the entry waits, the operator performs the repair, and binding
a runner delivers it"*). The card does not show the loop as firing (`firing_active` needs a running
`Run`). A firing whose **first** delivery is refused that way is unaffected: `scheduler.py:3471-3477`
concludes it `failed` at once, before any reaper. What is affected is a row left `in_progress` with
queued input and no runner: after a retry (new with D2), or after a Hub that died between the
firing's commit (`:3444`) and `:3472`. That second shape is exactly what
`test_a_held_agent_is_busy.py:732-739` seeds; it would invert under the unbounded form, and stays a
control under the bounded one.

**The main spec's stranded-firing requirement (R3).** `loop-firing-accountability`'s *"A stranded
firing SHALL be recoverable without restarting the Hub"* has a scenario whose THEN reads *"that
firing is eventually recorded as failed"* for any firing in progress with no live run while the Hub
keeps running. This change makes such a row the normal state while a retry waits, so the delta
MODIFIES it: a firing whose input is still queued is waiting, not stranded. The *"eventually
recorded as failed"* clause is replaced by what the code does, because it never did what it says:
the 2026-08-21 design D2 rejected a periodic sweep and fixed `firing_active`'s derivation instead
(`api/v1/jobs.py:454-466`), and no test in `hub/tests` pins the clause (`grep` for the scenario's
words finds none). The loop stops reading as firing at once; the record is concluded by whatever
settles its input, or by the next start.

### D6 — The loops view hears a conclusion that has no run event (R3)

The loops list and detail (`api/v1/loops.py:60-100`, `history[].status`) are refetched on the
terminal `run_*` events (`useSSE.ts:474-482`), because until now every conclusion happened just
before one. D3 adds two that do not: the operator's withdrawal broadcasts `queue_entry_withdrawn`,
and the scheduler's give-up broadcasts `queue_entry_abandoned` (`turn_scheduler.py:640-650`). Neither
invalidates `['project', pid, 'loops']` today (`useSSE.ts:445-451`, `:501-510`), so the loop's
history would keep reading `in_progress` until something else refetched it. Add that invalidation
to both cases. Unconditional: the withdrawal payload is `{entry_id, agent}` and does not say whether
the entry was a job's, and a refetch of one list is cheap. The Jobs page's history (`['project', pid,
'jobs', id]`) is not refreshed by run events either, today; that is older than this change and is not
carried here.

### D5 — The firing's own refusal is unchanged here

`scheduler.py:3471-3477` (and `:3611-3616` for a wide flow's extra selections) concludes a dispatch
`failed` when its turn did not begin, even though its
input stays queued and may be delivered later. That is the same shape as F123 (a later success under
a `failed` row), and D1 argues against it. It is **not** changed here, because it is the operator's
decision of 2026-08-21 (`2026-08-21-diagnose-and-clear-a-broken-loop` design D1, *"reuse `failed`"*,
and `loop-firing-accountability`'s first requirement). Open Question 1.

## Risks / Trade-offs

- **A row can stay `in_progress` for as long as its input waits** (a held queue, an unbound runner).
  It reads neutral in the history and does not claim the loop is firing. It is concluded by the run
  that delivers the input, by a withdrawal, or by the reaper once nothing is queued.
- **The conversation is still the only correlation.** A job input moved to another conversation
  would not be seen. No code does that today: `return_run_entries` keeps `conversation_id`
  deliberately (`inbound_queue.py:240-241`).
- **More writes at withdrawal.** One `SELECT … EXISTS` pair and at most one `UPDATE` per withdrawn job
  entry.

## Migration Plan

None. Rows already written `failed` by the old order stay `failed`; there is no way to tell, from the
rows, which of them were later retried to completion without re-deriving F147's measurement per row.

## Open Questions

1. **Should a firing whose turn did not begin wait too, rather than conclude `failed`?** *(Reverses
   an operator decision, so it is asked, not taken.)* **What the operator decided on 2026-08-21**
   (`archive/2026-08-21-diagnose-and-clear-a-broken-loop/design.md` D1, and its spec delta, now
   `loop-firing-accountability`'s first requirement): *"A firing whose selection did not start is not
   `in_progress`. It becomes a terminal `JobRun` state carrying the reason"*, and *"That state is
   `failed` — operator decision, 2026-08-21. No new vocabulary."* Rejected in the same decision:
   `skipped` (reads *nothing happened*), a new `not_started` (*"worth revisiting only together with
   the `JobCard` branch"*), inferring it later from the absence of a `Run`, and *"leaving
   `in_progress` and fixing only `firing_active`'s derivation"* (*"every other reader would inherit
   the lie"*). The requirement text: *"the firing's record SHALL reach a terminal state carrying the
   stated reason, without waiting for any later sweep."* That decision was made before F123/F147
   showed that such input is later delivered (F96) and a completed run then finds no `in_progress`
   row. Its sites: `scheduler.py:3471-3477` and `:3611-3616`. *Recommended:* yes, in a follow-up
   change that amends that requirement: the row stays `in_progress` with the reason in
   `error_summary`, and the card shows the reason beside a neutral status. The 08-21 objection to
   `in_progress` was a loop *reported as firing*; `firing_active` now requires a `running` `Run`
   (`api/v1/jobs.py:454-466`), so that objection no longer holds. Not in this change, because it
   changes the requirement's text (*"reach a terminal state"*) rather than its intent.
2. **Is `stopped` right for an operator's withdrawal?** *Recommended:* yes (D3). The alternative,
   `failed`, reads red for the operator's own choice.
3. **May the startup reaper leave open a row whose queued job input waits on an agent with no
   runner?** *(R2. Reverses a pinned case, so it is asked.)* D4 leaves every row with queued job
   input `in_progress`. That covers the F123 crash (input handed back, delivered at startup), and it
   also covers input waiting on a repair the Hub cannot promise. The 2026-08-21 decision D2 measured
   the reaper turning exactly that row (`job-0b490274`, `runner_id` NULL) from `in_progress` to
   `failed` and called it correct. `a-spent-allowance-holds-the-queue` D10 kept that verdict
   deliberately (*"a firing waiting for a runner to be bound waits on a repair the Hub cannot
   promise, so the existing rule stands for it"*), and `test_a_held_agent_is_busy.py:732-739` pins it.
   **R3's recommendation: not in this change; answer it with Question 1, in the same follow-up.**
   D4 as written now takes the bounded form (a runner bound or a refusal hold keeps the row open;
   no runner fails it), so the pinned test stays a control and the F123 crash is still fixed. The
   principle R2 cited is right (input the queue still holds is not a failed dispatch; F96 promises
   its delivery on repair), but it is the same principle as Question 1, and taking it for the
   reaper alone would give one firing two verdicts by the moment the Hub died (D4). *If the
   operator answers yes now:* D4 drops the runner half, 1.8a inverts, and the reaper and the live
   path disagree until Question 1's follow-up lands. *If no for good:* D4 stands as written.
   (R2 recommended *yes, answered together with Question 1*; R3 makes "together" explicit, since
   Question 1 is recommended for a follow-up.)
