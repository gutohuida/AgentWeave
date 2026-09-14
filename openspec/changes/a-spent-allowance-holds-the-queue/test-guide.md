# Test guide — a spent allowance holds the queue

## Agent-verifiable

Everything below runs without a person. Each item names the task that pins it.

| What | How | Task |
|---|---|---|
| A refusal is recognised from the reading, not the prose | unit tests over the measured reading | 1.1 |
| The hold is derived, floored, and survives rows that say nothing | `provider_hold` and `agents_held` tests, including the real `record_turn_usage(sample=None)` row and 60 rows after a refusal | 1.2, 1.2b, 1.3 |
| A refused turn is not counted, keeps its session, and is never withdrawn | `return_run_entries` tests; `_execute_run` through `_fake_pty` with a spawn count of 1 | 2.2, 2.4 |
| The retry note counts refusals | `format_turn_prompt` test | 2.3 |
| A refused firing reads in progress, and takes its delivery's outcome | the 2.4 fixture fired by a plain job | 2.5 |
| A completed turn with a refused reading still wakes the queue | the 2.4 fixture with exit 0 | 2.6 |
| Autonomous input waits; new operator input probes once; a refused probe does not loop | `_attempt_turn` tests | 3.1 |
| The queue wakes at the reset, and again after a restart | a real `JobScheduler` with a 1 s floor and a known address; the start-up re-arm | 3.2, 3.3 |
| Loops refuse and plain jobs coalesce while held | `_do_fire_job` tests | 3.4, 3.5, 3.6 |
| A flow neither re-briefs nor recruits a held agent, and briefs a held assignee's unbriefed task once | `decide_firing` and free-list tests with a second, free agent | 3.4b, 3.4c |
| An unstaffed review names the hold when a hold is why | `resolve_reviewer` rung 3 with a held non-author | 3.4d |
| A held firing survives a restart in progress | `reconcile_stale_job_runs` tests | 3.7 |
| The operator is told, and not told once it is over | the queue status route and the `queue_agent_held` row | 4.1, 4.2, 4.3 |
| Pressing Run on a held or busy loop answers 409 with the reason, never 500 or "nothing is wrong" | `POST …/jobs/{id}/run` tests beside F48's | 4.4 |
| The whole thing on a live Hub | the stub-provider drive | 6.1–6.5 |

## Human-only

These need the operator, because only they can see the real allowance and the real app.

1. **The next real wall.** When your plan's session limit is next reached on `:8000` (after a
   restart that applies this change), open the agent's conversation and its queue.
   - The runs list should show **one** refused run per agent, not three per entry.
   - The queue should read *"… usage limit is spent until HH:MM UTC …"*, and no entry should be
     withdrawn.
   - At the reset, the agents should resume without you. Their first turn should resume the same
     session, and the turn should say *"delivery attempt 2"*.
   - A job that fired into the wall should read *in progress*, not *failed*, until its instruction
     is delivered after the reset. That should hold even if you restart the Hub in between.
   - Pressing **Run** on a loop whose agent is held should say the agent is held until HH:MM UTC.
     It should not say the work is being done, and it should not be an error.
2. **Your probe.** While an agent is held, send it one message.
   - If you have not changed your plan, you should see one refused run and nothing after it.
   - If you have enabled extra usage, the turn should run, and the queue behind it should drain.
3. **The migration.** The first restart of `:8000` after this lands applies `0103` to your real
   database. It adds one column, `inbound_queue_entries.allowance_refusals`, with a default of 0.
   Nothing else changes.
