# User test guide — a loop notices and reacts

Task 9.1. What an operator does, what they should see, and what it looks like when it goes wrong.

The suite proves the three refusals happen: a busy agent queues nothing, a stalled queue counts in
place, the board and the firing name the same task. What it cannot prove is group 8 — whether a
loop that is *waiting* reads as waiting rather than as dead. That judgement is yours, and it is the
reason this guide exists. A loop that has quietly stopped and a loop that is being re-checked every
five minutes are the same picture until the product says otherwise; getting that wrong makes a
working loop look broken and invites the operator to restart something that needed nothing.

## Before you start

- The trial Hub on port **8010**, started **from `hub/`** so the source package is what runs:

  ```bash
  cd hub
  DATABASE_URL="sqlite+aiosqlite:///$HOME/.agentweave/hub/profiles/beta/agentweave.db" \
    py -3.11 -m uvicorn hub.main:app --port 8010 --host 127.0.0.1
  ```

  **Not `agentweave --port 8010`.** The console script is the *installed* `agentweave-hub`, whose
  migrations stop short of this branch's head (`0087`, which adds the tick count this guide reads).

- One agent on the roster with a runner bound. The walkthrough uses `looper`.
- Nothing to configure. Unlike the hop-budget guide, no project setting needs changing and nothing
  needs putting back afterwards.

## Creating a loop

In the app: the **Jobs** tab, new job, then open **Make this a loop** and give it a purpose. A loop
is a job with a purpose, so this is one form rather than two. Leave the schedule alone — opening
that section moves it to **Every 5 minutes**, which the form now offers and a loop now defaults to.
A plain scheduled job still defaults to 9am, because nothing here makes a fast *job* cheap; and if
you had already picked a schedule by hand, opening the loop section leaves your choice alone.

An agent creating its own loop gets the same default from `create_loop` without passing `cron`.

Five minutes is the whole point of this change and it is worth knowing why it is now safe. Before
the busy guard, a tick that landed mid-turn claimed a task and queued a briefing anyway, and the
agent drained them afterwards as several turns all briefed on the same work — so turning the cron
up multiplied the waste rather than the throughput. Now a busy tick costs nothing, and a repeated
stall costs one row.

## Watching a firing claim work

Give the loop something claimable — a `pending` task on its queue — and wait for the next tick, or
trigger it by hand.

You should see the loop's row move to **running**, with the claimed task named as its current
item, and the run appear in the job's history as a firing that fired. The loops index is the
**Loops** tab of an agent conversation's side panel — open a conversation and open that tab; the
job's own run history is on its card under **Jobs**. You will want both in view, because this
change puts half its answer in each.

**The current item is the thing to watch here.** A loop parked on an unanswered question — a task
in `blocked` — must still show that task as what it is working on. It is the loop's current item
even though no firing will claim it, and a board that showed nothing there would report a loop
waiting on *you* as if it were idle. That was a live bug until 2026-08-24.

## Letting the queue stall

Get the loop's queue into a state where nothing is claimable but the work is not finished. The
easiest: let the agent take its task to `completed` and then leave it there, unreviewed. `completed`
is not terminal — someone still has to approve it — and it is not claimable either, so the loop has
open work and nothing it may touch.

Now leave it alone for fifteen minutes, which at a five-minute cadence is three refused firings.

## What you should see

**On the loops index, an amber `stalled` badge** — not `idle`. Under the row, in amber, the reason
with its prefix trimmed:

> `stalled: no claimable task among 1 open (1 completed)`

That text is the Hub's own refusal reason, taken from the same computation that refuses the firing,
so the board and the firing cannot say different things about why nothing is happening.

**In the job's run history, exactly one skipped row** — not three. It carries the same reason, and
next to it:

> `re-checked 3 times`

**This is group 8's judgement call, and here is what to weigh.** The row's timestamp does *not*
move as the count climbs — it stays at the first refusal, deliberately, so a stalled loop does not
walk back to the top of the history every five minutes and bury the firings that did real work. So
after an hour the row reads "re-checked 12 times · about 1 hour ago", and that pair is the whole
claim: *this began an hour ago and is still being looked at*. Read it as an operator who has not
read this paragraph. Does it read as waiting, or as stuck? If it reads as stuck, the count is not
doing its job and that is a finding — the mechanism is fine, the wording is the deliverable.

**Group 8 in full**, each of which needs a running Hub and your eye rather than a test:

| Check | What to look at |
|---|---|
| 8.1 | With a loop mid-turn, the board must not flicker or drop to `idle` while firings are being refused behind it. |
| 8.2 | The stalled history row as its count climbs — a live re-check, or a stuck row? |
| 8.3 | The loop overall: waiting, or dead? |
| 8.4 | With a five-minute tick, the last-ten-runs view still shows the firings that claimed work. |

8.4 is the one with a cheap decisive test: let a loop stall for an hour, then unstall it and let it
fire for real. The real firing must be visible in the history without scrolling past a screen of
refusals. Before this change it would have been the twelfth row down.

## Resolving it

Approve the `completed` task. Do nothing else — no restart, no re-enable, no touching the job.

The next tick claims whatever is next, and the `stalled` badge goes. **That "do nothing else" is
the requirement**, not a convenience: a stalled queue is not a finished one, so the loop keeps its
schedule and stays enabled throughout, and resolving the stall is sufficient on its own. If you
ever have to re-enable a loop that merely stalled, that is a bug — the stop path disables the job
and removes it from the scheduler, and reversing the condition afterwards would not bring it back.

## Telling the three refusals apart

Task 9.2. A firing can be refused for three reasons, and they leave three different traces. The
differences are deliberate, so knowing which trace you are looking at tells you what the loop is
waiting for.

| Refusal | What it leaves in the history | What it means | What you do |
|---|---|---|---|
| **The agent is already running a turn** | **Nothing at all** — no row, no event | The loop is working. It ticked mid-turn and declined to interrupt itself. | Nothing. The tick is meant to be invisible. |
| **The queue is stalled** | One `skipped` row, amber, naming the count and statuses, with a re-check count that climbs | Open work exists and none of it is the loop's to touch — usually something awaiting review, or blocked on an unanswered question | Resolve what it names: approve, review, or answer. The loop resumes on the next tick by itself. |
| **The loop's stop condition is met** | The loop reads **complete** or **stopped early**, and the job is disabled | The queue drained and the loop was asked to stop when it did. This is an ending, not a wait. | Nothing, unless it ended earlier than you meant — in which case the job must be re-enabled by hand. |

**The empty cell in that table is the one to internalise.** A busy refusal records *nothing*: no
`JobRun`, no event. That is not an omission — the agent's running turn already carries the fact, the
board reads exactly that row to show the loop as firing, and a record per busy tick would evict real
history through the run list's own window at a five-minute cadence. So: **a loop that is running
looks like a loop that is running, and its refused ticks are silent.** If you go looking in the
history for evidence of a busy tick, you will not find any, and nothing is wrong.

A stalled queue that is stalled for a *different* reason starts its own row rather than incrementing
the previous one — the count only ever stands for repetitions of the same reason. So two rows
reading different reasons is a queue whose situation changed, not a bookkeeping fault.

A fourth reason exists and is a special case of the second: a queue where every candidate is held
by the dependency gate. It reads differently on purpose — `still awaiting a prerequisite's approval`
versus `gated on a rejected prerequisite that will not clear on its own` — because the remedies
differ. The first waits; the second needs the rejected prerequisite reopened, and will never clear
on its own.

## Reading it from the database

Everything above is visible in the app. When you want the raw fact:

```bash
sqlite3 "file:$HOME/.agentweave/hub/profiles/beta/agentweave.db?mode=ro" \
  "select fired_at, status, tick_count, error_summary from job_runs
     where job_id = '<job>' order by fired_at desc limit 10"
```

A stalled loop should show **one** `skipped` row with a `tick_count` above 1, not one row per tick.

## What it looks like when it goes wrong

**Several identical skipped rows instead of one.** The stall is appending rather than counting. The
reason text is what keys the increment, so check whether the two rows really do say the same thing —
if they do, the increment is broken; if they differ, this is working as designed.

**A queued entry after a refusal.** Any refusal that leaves an `InboundQueueEntry` behind hands the
agent a briefing about work it was just told not to do, and the agent runs it the next time it
drains its queue. The refusal happened and the work happens anyway, later, out of order:

```bash
sqlite3 "file:$HOME/.agentweave/hub/profiles/beta/agentweave.db?mode=ro" \
  "select state, count(*) from inbound_queue_entries where agent = 'looper' group by state"
```

**A stalled loop showing as `idle`.** `idle` says both that nothing is happening and that nothing is
wrong, and only the first is true. If the badge is grey rather than amber, the board is not seeing
the stall reason — check that the Hub serving 8010 is built from this branch.

**A loop that stalled and had to be restarted.** Stalled must never disable the job. If you find one
that did, the firing took the stop branch when it should have taken the skip branch, and the
difference matters: an operator who resolves the underlying condition afterwards would find the loop
never comes back.
