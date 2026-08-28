# Design — A delivery attempt means a delivery

## D1. The counter is right; the place it is called from is wrong

There are two increments of `delivery_attempts`, and only one of them describes a delivery.

`inbound_queue.return_run_entries:211` runs when a `Run` carried an entry and then failed. Something
was attempted and it did not work; counting it is the plain meaning of the field. That site is
untouched here, and the abandonment it eventually causes is the behaviour
*Repeated delivery failure does not wedge an agent* was written for.

`turn_scheduler.py:191` runs when `trigger_agent_directly` raised **before any `Run` existed** — its
own comment says so: *"No `Run` was ever created for this attempt, so `selected` never became
`delivered`"*. Nothing was carried anywhere. The count is a fiction, and it is a fiction the
operator is eventually shown: *"delivery failed 3 times; the Hub stopped retrying"*.

So this change edits one condition at one site, and deliberately nothing else. Rewriting what the
counter *means*, or splitting it into two fields, would be a larger change that this one has not
driven.

## D2. Why F56 was right to add the second site, and still is for half of it

F56's reasoning, quoted from the code:

> a refusal raised here (a review target with no evidence naming a commit, an archived agent, a task
> that does not exist, ...) repeats identically forever, and every entry queued behind it starves
> along with it.

Every example in that list is a refusal about **what was asked**. For those, "repeats identically
forever" is exactly true — no repair to the environment changes the answer, and the entry at the
head of the queue would block everything behind it indefinitely. Counting and abandoning is right.

The list contains no environment-level example, which is the tell: the case this change is about was
not the case F56 was looking at. It arrived under the same branch because, at the time, there was
nothing at that line able to tell the two apart.

## D3. Nothing starves behind an environment-level refusal

The starvation argument does not carry over, and this is the load-bearing claim of the change.

An environment-level refusal is **agent-wide**, not entry-specific: no runner is bound, the runner's
CLI is not installed, an isolated workspace could not be prepared. While it holds, *no* entry for
that agent can be delivered — so there is nothing behind the head entry that would otherwise run.
Dropping the head buys nobody a turn. When the environment is repaired, the whole queue drains in
arrival order.

Compare a request-level refusal, which is genuinely entry-specific: the review target is in the
wrong state, this particular name is on no roster. Every other entry for that agent could run. There
the head entry really is in the way, and F56's argument holds exactly.

This is also why transient refusals already decline to count (design D8 of
`every-run-knows-its-task`): a turn parked behind another agent's checkout blocks that agent
entirely, so nothing is starving behind it either. **The rule this change lands on is not new — it
is the rule that already governs the transient branch, applied to the other population that shares
its shape.**

## D4. The strongest objection, stated rather than answered away

`agent-conversation-workspace` says, of the abandonment behaviour:

> Retrying without limit is indistinguishable from being stuck, and an agent that never accepts new
> input is worse than a message that was dropped loudly.

After this change, an environment-level refusal retries without limit.

Two halves, and they come apart here:

- *"an agent that never accepts new input"* — an unlaunchable agent **does** accept new input. Every
  trigger returns `200`, queues the entry, and states the reason. It is not wedged; it is waiting.
- *"indistinguishable from being stuck"* — this is the half that has force, and it depends entirely
  on whether the operator can see why. Today `GET /queue/{agent}/status` reports the reason, and the
  conversation view renders it under the composer. So it is distinguishable — **but that is a claim
  about today's surfaces, and R2 should verify it against them rather than against this paragraph.**

If that verification fails, the answer is not to keep destroying the input. It is that this change
needs a companion: something that makes a long-waiting entry visible *as* long-waiting. Recorded as
an open question rather than smuggled in.

## D5. What the operator loses, honestly

Today an environment-level entry disappears after three schedules, and the operator is told
something false about why. After this change it stays until the environment is repaired or they
withdraw it.

The cost is that an abandoned project accumulates queue entries nobody will ever deliver. That is a
tidiness problem with a manual answer already built (`DELETE /queue/entries/{id}`), against a
correctness problem with none. The trade is not close, and it is stated here so that a reader who
disagrees can see what was weighed.

## D6. Alternatives considered

**Count elapsed time rather than schedule calls.** A truer measure — three *retries over an hour*
is a real signal where three schedules in two seconds is not. Rejected for this change: it needs a
notion of when the last attempt happened and a policy for how long is long enough, neither of which
exists, and it would change the request-level case too, which nothing has complained about.

**Count only when the refusal differs from the last one.** Attractive, and wrong in the same
direction as today: an environment-level refusal repeats *identically*, so this would still count it
every time.

**Keep counting, never abandon; mark instead.** Possibly the better long-term answer, and D4's
failure mode points at it. Larger than this change: it needs a state, a surface and an operator
action, where this change removes an increment.

## D7. Blast radius

The condition change is one line. What it can move is any test that reaches
`DELIVERY_ATTEMPT_LIMIT` **through the refusal path** rather than through a failed run —
`test_delivery_attempts.py` and `test_runner_binding_redrain.py` are the two to read first, and
`tasks.md` group 1 makes enumerating them a task rather than a hope.

`test_agent_trigger.py::test_spawn_failure_marks_run_failed` is deliberately *not* in that set: its
entries are delivered to a real (mocked) spawn that then fails, so they count through
`return_run_entries` and are unaffected. It is worth naming because it looks like a casualty and is
not — and because it is currently flaky for an unrelated reason (F109), which would otherwise be
easy to misattribute to this change.

## Filed, not fixed here

1. **The recorded reason lies about what happened.** `"delivery failed 3 times"` is written by the
   surviving site too, where the failures were refusals rather than deliveries. This change makes it
   fire far less often; it does not make it true.
2. **`terminal_failure`'s dishonest defaults**, carried over from
   `2026-08-28-a-refused-request-says-so` and still unfixed: six early returns claim `True` without
   meaning it, and `scheduler.py`'s two flow consumers gate on that flag.
