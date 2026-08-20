# Exploration — Who guarantees the review handoff (2026-08-20)

**Status:** Explored with the operator 2026-08-20, immediately after
`2026-08-20-the-loop-under-dependencies.md`, whose §7 left this as an open fork. Resolved to a
decision in this session.

Decisions the operator took are marked **DECIDED**. Every claim was checked against the code;
`file:line` is given so the next reader can re-check rather than trust.

**The short version.** §7 framed this as *"agent alone, loop alone, or both"* and recommended
"both" without saying what "both" meant mechanically. It turns out the thing being argued over —
*guaranteeing the handoff happens* and *deciding who it goes to* — is two things, not one. The
operator's objection to the loop doing it was entirely about the second. Splitting them dissolves
the fork, and the resulting design needs no new state: the signal it depends on is already recorded
in rows the Hub writes today.

---

## 1. The situation, concretely

A loop points at a spec document with three tasks. ALPHA is the loop's executor.

```
   tick 1   loop claims task 1, hands it to ALPHA
            ALPHA does the work, marks it `completed`
                 │
                 ▼
            ALPHA cannot approve its own work.
            `_guard_author_is_not_reviewer` (`task_transition_service.py:119`)
                 │
                 ▼
            Operator's design: ALPHA sends a message to a tester.
            "Task 1 is done, please review it."
```

If ALPHA sends it, the whole chain already exists and works — `send_message` with
`message_type="review"` (`mcp_server.py:174`), the recipient's durable inbound queue,
`schedule_agent` waking them (`messages.py:259`), review, `approved`, next task unlocks.
**Nothing in that path needs building.**

If ALPHA does not send it, task 1 sits at `completed` forever and the loop cannot advance, because
under `task-dependencies` task 2 needs task 1 **approved**.

This is not a hypothetical failure mode. It is the same one the codebase already recorded, in the
comment explaining why `assigned` had to become claimable (`scheduler.py:236-237`):

> *"reaching `in_progress` needs the agent to call `update_task` itself, **which it may simply not
> do.**"*

## 2. What the fork actually is

**One question: when ALPHA forgets, whose job is it to notice?**

Until 2026-08-20 the answer was *nobody*, and the consequence was the §3 spin — a firing every tick,
claiming nothing, forever. That is fixed (`_loop_stall_reason`, `scheduler.py`): the loop now goes
quiet instead of spinning. **Quiet is better than spinning and still wrong.** The work is stuck and
nothing says so.

| | What happens when ALPHA forgets | Cost |
|---|---|---|
| **A** Agent alone | Nothing. The work sits. The loop stays quiet forever. | This is today. The failure is silent and permanent. |
| **B** The loop sends it | The loop picks a tester and sends the message itself. | Bypasses ALPHA — who knows what it built and what needs checking. Discards the operator's design. Needs L2 first. |
| **C** The loop tells the operator | *"Task 1 is finished and nobody is reviewing it."* | Works, needs nothing new — but puts a person back inside a loop meant to run unattended. |
| **D** The loop hands it back to ALPHA | Next tick, instead of claiming new work: *"you completed task 1 and never sent it for review. Do that now."* | ALPHA still picks the tester. The loop guarantees only that ALPHA is **asked again**. |

**DECIDED: D.**

The reason D is not a compromise between the others is that it splits what §7 treated as atomic:

```
   GUARANTEE THE HANDOFF HAPPENS   ──▶  the loop's job
   DECIDE WHO REVIEWS IT           ──▶  the agent's job, unchanged
```

The operator's *"we don't need to assign another agent… once the agent finishes the work it needs to
send a message to a tester"* is a statement about the second. D leaves it exactly where they put it.

It also sits correctly beside the loop's own standing principle (`agent-loops` §211):

> *"No firing SHALL leave the choice of which queued task to work to the firing agent's own
> judgement."*

The loop already refuses to let the agent choose *what to work on*. Under D it still does not choose
*who reviews*. It only refuses to let *"the agent forgot"* be a silent permanent state — which is
the same class of thing §211 is about.

## 3. How the loop knows — and why this is not the retired backstop

D is only possible if *"ALPHA forgot"* is knowable. It is, from rows that already exist.

**Two facts already recorded:**

| Fact | Where |
|---|---|
| A message can name the task it is about, and can be typed `"review"` | `Message.task_id` (`models.py:513`), `Message.type` (`models.py:509`), and `message_type`'s vocabulary already includes `"review"` (`mcp_server.py:174-190`) |
| Every status change records which agent made it | `TaskTransition.actor_agent`, read exactly this way by `_agent_that_completed` (`task_transition_service.py:92-116`) |

```
   task is `completed`
        no Message(task_id=T, type="review")   ──▶  nobody is coming   ──▶  remind ALPHA
        such a Message exists                  ──▶  someone was asked  ──▶  wait

   task is `under_review`
        ALPHA moved it there itself            ──▶  nobody is coming   ──▶  remind ALPHA
        a different agent moved it             ──▶  a reviewer has it  ──▶  wait
```

**The `under_review` branch is not decoration, and I had it wrong at first.** I initially claimed
`under_review` means a reviewer is on it. It does not. `completed -> under_review` is `_BOTH`
(`task_transitions.py:135`) and **unguarded** — `_REVIEW_OUTCOMES` is
`{approved, rejected, revision_needed}` (`task_transition_service.py:89`), so
`_guard_author_is_not_reviewer` returns early for `under_review`
(`task_transition_service.py:135`). Combined with L4 — a task has no reviewer field
(§6.4 of the previous exploration) — an author can move its own task to `under_review` with nobody
on the other end. Same silent stall, different status. The actor check is what closes it.

**Why this is admissible where the retired question-detection backstop was not.** CLAUDE.md is
explicit that guessing whether trailing prose is a question is *"a judgement the product should not
make on the operator's behalf"*, and that feature was deleted for it. §7 of the previous exploration
already spotted the distinction and it holds up: **the backstop inferred intent from prose.** Every
branch above is a lookup on a row. Nothing is inferred, nothing is parsed, and the answer is the
same whoever asks it.

## 4. What stops the reminder becoming the same bug one level up

If ALPHA is reminded and still does not act, the loop reminds forever — which is the stuck-ness the
whole exercise is removing, just quieter.

**DECIDED: a small fixed number of reminders, then surface to the operator.**

So **option C is not a rejected alternative — it is D's floor.** D is what happens while there is
reason to think ALPHA will act; C is what happens once there is not.

The precedent to copy rather than invent is `InboundQueueEntry.delivery_attempts`
(`models.py:551-557`), which exists for the identical reason:

> *"an input whose delivery kills the runtime is served again immediately… Without a count, an entry
> returned five times is indistinguishable from one never tried."*

*Rejected:* **surface on the first failure** — a single missed handoff can be one bad turn, and
pulling the operator into an unattended loop for something that self-corrects on the next tick is
the wrong default. *Rejected:* **remind forever** — the silent-forever failure with extra steps.
*Rejected:* **stop the loop instead of surfacing** — the same objection that chose *skip* over
*stop* this morning: a stopped loop sets `job.enabled = False` and calls `remove_job`, so the
operator resolving the situation afterwards cannot bring it back.

**The solo-project case falls out of this for free.** A one-agent project has nobody to hand off to,
ever, so author/reviewer separation makes the chain unadvanceable without the operator. Reminding
ALPHA is pointless there — and it will exhaust the reminder count immediately and surface, which is
the correct outcome. No special case needed.

## 5. The reminder gets its own turn

**DECIDED.** The loop fires, hands task 1 back to ALPHA with the reminder as the whole briefing,
ALPHA sends the review message, the turn ends. Task 2 waits for the next tick.

*Rejected:* **bundling the reminder into the next task's briefing.** Cheaper — no tick spent on a
single message — but it breaks the one-item-per-firing model the loop is built on
(`_claim_loop_task` returns exactly one task, `scheduler.py:249`), and a reminder buried underneath a
fresh task assignment is precisely the kind of instruction an agent skips. That is the failure being
fixed, reintroduced as the fix.

## 6. The one implementation constraint that is not the operator's call

Claimability stops being a flat tuple. Today it is
`CLAIMABLE_LOOP_TASK_STATUSES` (`scheduler.py:246`), a shared constant — and the sharing is
load-bearing, not incidental. `_loop_queue_order`'s own comment (`scheduler.py:210-220`) records
what happened the one time the board's derivation and the firing's drifted:

> *"Both derivations shared the flaw, so the board and the firing agreed on the wrong task — two
> consistent wrong answers read as a match, which is how it survived review."*

Under D, *"is this claimable"* becomes conditional — a `completed` task is claimable only if no
handoff is in flight. **A condition is far easier to duplicate-and-drift than a tuple.** So whatever
shape this takes, `_claim_loop_task` and `_batch_loop_summaries` (`api/v1/jobs.py`) must call one
function, not two implementations of one rule.

## 7. A separable bug found on the way: `revision_needed` is not claimable

Not part of D, and it needs no decision. Enumerated by execution rather than by reading:

```
   all statuses   pending assigned in_progress blocked completed
                  under_review revision_needed approved rejected
   CLAIMABLE      pending assigned in_progress blocked
   TERMINAL       approved rejected
   ─────────────────────────────────────────────────────────────
   NEITHER        completed   under_review   revision_needed
```

**Three, not two.** `_loop_stall_reason`'s docstring, written earlier the same day, says *"the only
two"* — that is wrong and is corrected alongside this.

`revision_needed` is the odd one out and does not belong in §7's territory at all:

- it is reached when a **reviewer did everything right** and sent the work back;
- `revision_needed -> in_progress` is `_BOTH` (`task_transitions.py:144`), so the loop's own agent is
  exactly who should resume it;
- but the loop cannot claim it, so a correct review **stalls the loop**.

That is backwards, and it is the same shape as the `assigned` omission fixed on 2026-08-19: an entry
missing from a tuple, not a policy question. **Operator approved fixing it directly.**

**A related smell, not yet acted on.** There are three overlapping notions of "this task is live" —
`CLAIMABLE_LOOP_TASK_STATUSES` (`scheduler.py:246`), `TERMINAL_FOR_BINDING`
(`run_task_binding.py:272`), and `_ACTIVE_TASK_STATUSES` (`api/v1/agents.py:60`, which includes
`under_review` and `revision_needed` but not `completed`). Three sets, three different answers, no
shared definition. That is how both the spin and this one survived.

## 8. What this leaves for the stop condition

Today's fix skips a stalled firing but the loop still cannot tell *a review that is coming* from
*one that never will*, so `stop_when_queue_empties` remains unable to end a permanently-stalled
loop. §3 of the previous exploration left that open, and **D closes most of it**: the reminder count
reaching its limit is exactly the signal that the wait is permanent.

What is still unaddressed is the other side — a handoff that **did** happen to a reviewer who never
runs. There is a precedent shaped for it: `Agent.permission_timeout_seconds` and
`Agent.question_timeout_seconds`, carried to the spawned process as `AW_DECISION_TIMEOUT` and
`AW_QUESTION_TIMEOUT` (CLAUDE.md, operator-in-the-loop). *"How long does this loop wait for a
reviewer"* is the same shape. **Not decided, and not required for D.**

## 9. What this becomes

| # | Change | Depends on | State |
|---|---|---|---|
| **R0** | `revision_needed` joins the claimable set; correct the `_loop_stall_reason` docstring | nothing | **approved to fix directly** — §7 above |
| **R1** | Handoff detection — the two lookups of §3, behind one shared predicate | nothing | ready to propose |
| **R2** | The re-brief — its own turn, bounded reminder count | R1 | ready to propose |
| **R3** | Surface to the operator when the count is exhausted | R2 | ready to propose |
| **R4** | Review-wait timeout for a handoff that happened but was never picked up | R1 | **open** — §8 |

R1–R3 are one change. They are the answer to §7 and they replace L5 in the previous exploration's
L0–L5 table.

**Relationship to L1/L2/L4.** D deliberately does not need them. `list_agents` (L2) and charter
summaries (L1) make ALPHA *better at choosing* a reviewer; D only makes sure ALPHA is *asked*. They
compose and neither blocks the other — which is the main practical benefit of choosing D over B.

## 10. Still open

- **The review-wait timeout** (§8) — a handoff that happened to a reviewer who never runs.
- **How many reminders?** *"A small fixed number"* is decided; the number is not. Three is the
  obvious starting point and `delivery_attempts` offers no precedent value for the count itself.
- **Is the reminder count per task or per loop?** Per task is the natural reading of "task 1 was
  asked about three times", but nothing has been said.
- **Does a reminder that succeeds reset the count?** Relevant after a `revision_needed` cycle, where
  the same task legitimately reaches `completed` more than once.
- **Unifying the three "active task" sets** (§7) — a cleanup, not a bug, and larger than either fix
  it would have prevented.
