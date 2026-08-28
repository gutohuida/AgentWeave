# A delivery attempt means a delivery

## Why

An operator sends three messages to an agent whose runner is not bound yet. The first one is
destroyed. Measured against the trial Hub on 2026-08-28, in under two seconds, with nothing else
happening in the project:

```
entry              content      state       attempts  abandoned_reason
entry-aeef0099…    message 1    withdrawn      3       delivery failed 3 times (…); the Hub stopped retrying
entry-2e1f5501…    message 2    queued         2
entry-f6cb62eb…    message 3    queued         0
```

**No run was ever attempted for message 1.** Its recorded reason describes three deliveries that
never happened. What actually happened is that the operator sent two more messages: every
`POST /agent/trigger` calls `schedule_agent`, which selects the oldest conversation's entries and,
on a non-transient refusal, increments `delivery_attempts` on each of them
(`turn_scheduler.py:191`). Three *messages* consume the three *delivery attempts*.

This is finding **F114**, severity A.

### The product's own suggested remedy destroys it faster

The conversation view offers a button for exactly this situation — *"`<agent>` has work waiting —
start it without sending a message"* — which calls `POST /conversations/{id}/continue`, which
reaches `schedule_agent` like everything else:

```
after queueing:      state='queued'     attempts=1
Continue click 1:    started=False  ->  state='queued'     attempts=2
Continue click 2:    started=False  ->  state='withdrawn'  attempts=3
```

Two clicks. Every one answered `200`. An operator who cannot see why their message is not moving,
and presses the button the product put there to move it, deletes it. `redrain_queued_agents` — which
runs at the end of **every** turn in the project — counts the same way, so an entry can also be
consumed by activity that has nothing to do with it.

### It undercuts F96 exactly

F96 exists so that binding a runner delivers the message queued while none was bound. Its own live
log shows this mechanism from the other side: `waiting_reason` had become
*"delivery failed 1 time; 2 attempts left"*, the retry counter having taken the reason's place. An
operator who sends a few messages before getting round to the binding has already lost the first
ones, and F96's repair arrives to find nothing left to deliver.

### There are two counters, and only one of them is wrong

| Site | When it fires | Verdict |
|---|---|---|
| `inbound_queue.return_run_entries:211` | An entry **was delivered** to a run, and that run failed | **Correct.** A delivery was attempted and it failed. This is F56's original case and this change does not touch it. |
| `turn_scheduler.py:191` | The turn was **refused before any run existed**, so nothing was ever delivered | **The defect.** It counts an attempt for an attempt that did not occur. |

F56 extended the counter to the second site for a stated reason, and the reason is sound as far as it
goes:

> a refusal raised here … repeats identically forever, and every entry queued behind it starves
> along with it … so a permanently wrong entry stops wedging the whole queue.

That is true of a refusal about **what was asked** — a review target with no evidence, a name on no
roster. It is exactly wrong for a refusal about **the environment**, where the entry is supposed to
wait for a repair and the product has promised to keep it.

### The distinction did not exist until yesterday

Until `2026-08-28-a-refused-request-says-so`, that line had no way to tell those apart:
`transient` answers a different question (does this clear on its own, without anybody doing
anything). `TriggerAgentError.request_level`, added for F108, is the classification this line has
been missing.

## What changes

1. `schedule_agent`'s refusal branch counts a delivery attempt **only when the refusal is
   request-level** — the same way it already declines to count for a transient one.
2. An environment-level refusal therefore leaves `delivery_attempts` where it was, and can never
   abandon the entry. The entry keeps waiting, with its reason stated, until the environment is
   repaired or the operator withdraws it.
3. Nothing about `return_run_entries` changes. An entry a run actually carried and lost still counts
   its attempt and is still abandoned at the limit.

## What does not change

- **The abandonment mechanism itself**, its limit, its event, and its recorded reason.
- **`return_run_entries`.** The counter that means what it says keeps meaning it.
- **Transient refusals.** Already uncounted; unaffected.
- **What is refused.** This change moves no guard and adds none.
- **`POST /agent/trigger`'s answers.** F108 decides those; this decides only what happens to the
  entry afterwards.

## Open questions for review rounds

- **The strongest objection, and R2 must take it seriously.** `agent-conversation-workspace`
  already says: *"Retrying without limit is indistinguishable from being stuck, and an agent that
  never accepts new input is worse than a message that was dropped loudly."* This change makes an
  environment-level refusal retry without limit. The reply is that the two halves of that sentence
  do not both apply — an unlaunchable agent *does* accept new input, and the queue status states
  the reason rather than leaving the operator guessing — but that is an argument, and R2 should
  check it against what the status surfaces today rather than against this paragraph.
- Whether the recorded `abandoned_reason` at the surviving site should stop saying "delivery failed
  N times" when what failed was a refusal before delivery. That wording is what made the false claim
  legible on screen; it may belong to this change or to its own.
- Whether an entry that can never be delivered should be *visible as such* rather than merely
  waiting — a surfaced "this has been stuck for a long time" is a different answer to F56's worry
  than a counter, and might be the better one.
- **R2 must enumerate** every test that asserts an entry reaches `DELIVERY_ATTEMPT_LIMIT` through
  the refusal path rather than through a failed run. `test_agent_trigger.py::test_spawn_failure_marks_run_failed`
  is *not* one of them — it goes through a real spawn — but `test_delivery_attempts.py` and
  `test_runner_binding_redrain.py` both need reading before a line is written.
