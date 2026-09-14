# Design — a spent allowance holds the queue

## Context

Three things happen today when a Claude turn is refused by the provider's usage limit. Each was
read in the code, and each was measured on LoopEngine (`mode=ro`, 2026-09-14).

1. **The refusal is parsed and filed as accounting.** `parse_claude_line` turns a
   `rate_limit_event` into an `AccountingSample` carrying `allowance` and nothing else
   (`runner_parsing.py:364-369`). `_execute_run` merges it into `accounting_sample`
   (`agent_trigger.py:2213-2218`). `record_turn_usage` stores it on `turn_usage.allowance` in the
   same transaction as the run's end (`agent_trigger.py:2320-2326`, `usage_accounting.py:54`).
   The `result` line becomes `error_event(code="claude_result_error", …)`, and the run ends
   `failed` on exit 1 (`:2272-2275`).
2. **The failure is counted like any other.** `return_run_entries` is called for every `failed`
   run that is not a binding conflict (`agent_trigger.py:2349-2353`). It increments
   `delivery_attempts`. At 2 it clears `provider_session_id`, and at 3 it withdraws the entry
   (`inbound_queue.py:210-235`).
3. **Re-delivery is immediate.** The run-end path re-drains the project
   (`agent_trigger.py:2433-2460`). Nothing in `_attempt_turn` asks about the provider, so the next
   turn spawns about 10 s later (measured: 01:25:00, :10, :21).

**The reading's shape (measured; 277 rows carry one).** The keys are `status`, `resetsAt` (epoch
seconds), `rateLimitType` (`five_hour`, `seven_day`), `isUsingOverage`, `unifiedWindows`, and
sometimes `overageStatus`, `overageDisabledReason`, `utilization` and `surpassedThreshold`. The
`status` values: `allowed` 136 (all on completed runs), `allowed_warning` 69 (all completed),
`rejected` 69 (all failed). 3 failed runs had no reading at all.

## Decisions

### D1 — recognise a refusal by `status == "rejected"` and a numeric `resetsAt`

`allowance_refusal(allowance) -> Optional[AllowanceRefusal]` in a new `hub/hub/provider_allowance.py`
returns `(resets_at: datetime UTC, limit_type: Optional[str])` when `allowance` is a dict,
`allowance.get("status") == "rejected"`, and `resetsAt` is an `int` or `float` that is not a
`bool`. Otherwise it returns `None`.

- **Not the prose.** *"resets 3:10am (Europe/Lisbon)"* has no date, it is in the harness's locale,
  and its wording is the harness's to change. The structured reading carries the same instant
  (`1789351800` is 02:10 UTC, which is 3:10am at UTC+1). Measured on all 69 refusals.
- **A refusal with no `resetsAt` is not recognised,** so it keeps today's counted path. Without a
  reset time there is nothing to hold until, and a guessed backoff is a policy nobody has decided.
  No such row exists in the corpus.
- **Not `overageStatus`.** It read `rejected` on completed runs too (`out_of_credits` with
  `isUsingOverage: false`), so it describes the overage option, not this turn.

### D2 — a refused run returns its input without counting it

`return_run_entries(db, run_id, *, refusal: Optional[AllowanceRefusal] = None)`. When `refusal` is
given, for each delivered entry:
- `allowance_refusals += 1`, and `delivered_at = None`;
- `state = "queued"`, and `delivered_in_run_id = None`, as for any requeue;
- `waiting_reason =` the hold sentence (D9);
- **`delivery_attempts` is not touched,** and **neither limit is evaluated.** So the provider
  session is never cleared, and the entry is never withdrawn, for a refusal.

The id is still returned in the requeued list. So `evaluate_run_end` and the handover are skipped,
as they are for any returned input (`agent_trigger.py:2364-2374`): the work is going to another run.

`_execute_run` computes `refusal = allowance_refusal(accounting_sample.allowance)` once, when
`final_status == "failed"` and `binding_conflict is None`, and passes it. Every other caller passes
nothing: the pre-spawn and transport failures (`:1927`, `:2070`), the Codex path (`:2847`,
`:2942`), and startup reconciliation (`run_reconciliation.py:87`). None of them has a reading, so
they keep today's behaviour exactly.

**Why the provider session must be kept, not merely may be.** `RESUME_RETRY_LIMIT` exists because
*"a provider session which cannot be resumed"* makes input undeliverable (`agent-conversation-workspace`).
Here the session *was* resumed: the second delivery found it and was refused by the allowance, not
by the resume. Clearing it discards the agent's provider-side context for nothing. On a
conversation with real history, that is the costliest thing this path does.

### D3 — the hold is derived from the agent's most recent turn outcome

`provider_hold(db, project_id, agent) -> Optional[ProviderHold]` reads **the provider's most recent
word about this agent**: the newest `TurnUsage` row for (`project_id`, `agent`), by `observed_at`,
that is *informative*, meaning its `allowance` is a JSON object **or** its `status` is `measured`.
The agent is held when:

- that row's `allowance` is a refusal (D1), and
- `now < hold_until`, where `hold_until = max(resets_at, row.observed_at + 60 s)`.

`ProviderHold` carries `hold_until`, `resets_at`, `limit_type`, `observed_at` and `run_id`.

- **Derived, not a column.** The fact is already recorded, in the transaction that ends the run.
  A stored `held_until` would be a second copy that can drift, and it would need its own release
  path. Derived, the hold survives a restart and is released by the next outcome that is not a
  refusal, whoever caused it.
- **Why "informative", and not simply the newest row.** Three paths write a row that says nothing
  about the provider, each with `sample=None`:
  - the transport-failure tail (`agent_trigger.py:1917-1924`);
  - a spawn that never started (`:2059-2066`);
  - crash reconciliation (`usage_accounting.py:21-23`).

  If one of those rows ended a hold, a Hub restart or a missing CLI would release an agent the
  provider is still refusing. A completed run that happened to emit no `rate_limit_event` is still
  informative, because its row is `measured`: the provider served tokens, and that is the whole
  question. A refused run that used tokens (3 of `dev`'s 51) is both `measured` and a refusal, and
  the reading decides it.
- **JSON `null` is not SQL `NULL` here.** A row written with no reading stores the JSON literal
  `null`, which `allowance IS NOT NULL` matches (measured: 3 such rows on `:8000`, which
  `json.loads` read as `None`). So the informative filter has to test for an object
  (`json_type(allowance) = 'object'` on SQLite, or a Python check over a bounded window of recent
  rows). Task 1.3 pins it.
- **The 60 s floor** is the spin guard. A `rejected` reading whose `resetsAt` is already past
  (clock skew, or a provider that reset late) would otherwise release immediately, refuse again and
  requeue. That is a tight loop of uncounted spawns, which is worse than today's bounded three. The
  floor caps it at one refused spawn a minute per agent. It is not a backoff policy; it only
  bounds a pathological reading.
- **Per agent, not per provider account.** All four LoopEngine agents shared one Claude login, so
  a per-account hold would have saved three spawns per wall. But the Hub has no model of which
  runners share an account. A `claude` runner's flags or environment can point at another
  account, and `claude_proxy` is another provider path entirely. A per-agent hold is never wrong in
  the direction that matters: it holds only an agent the provider actually refused. Its cost is one
  refused spawn per agent per wall. Measured, those take 6–10 s, and 48 of `dev`'s 51 used 0
  tokens.

### D4 — while held, autonomous input waits, and new operator input probes once

In `_attempt_turn` (`turn_scheduler.py:312`), after `selected` and `initiator` are computed and
**before** the token-budget check (`:377-379`):

```python
hold = await provider_hold(db, project_id, agent)
if hold is not None and not any(
    e.origin_type == "operator" and e.arrived_at > hold.observed_at for e in entries
):
    return _Attempt(ScheduleResult(waiting_reason=hold_sentence(agent, hold), terminal_failure=False))
```

- **`terminal_failure=False`.** A job firing that reaches a held agent leaves its `JobRun`
  `in_progress` (`scheduler.py:2917-2924` fails it only on a terminal result). The entry is going to
  be delivered, so the firing has not failed. The token-budget return uses the default
  (`terminal_failure=True`); this deliberately does not copy it.
- **The probe is keyed on `entries`, the agent's whole queue, not on `selected`.** The operator's
  message can sit in a conversation behind an autonomous head, and keyed on `selected` it would
  never probe. The probe turn is whatever the queue would ordinarily start. If the provider serves
  it, the hold ends (D3) and the queue drains in order, the operator's message included. If the
  provider refuses it, the renewed reading's `observed_at` is later than every entry already
  queued, so the same entries cannot probe again. That is what makes it one probe per new operator
  input, and what rules out a loop.
- **Why an operator probe at all.** Only the operator can change the allowance: enable overage, buy
  credits, or rebind the agent to a runner on another account. The hold is derived from the
  provider's last word, so it cannot see any of those. Without a probe, a `seven_day` refusal would
  hold the agent for days after the operator fixed it. The probe costs one refused spawn (D3's
  cost). The token budget sets the precedent: operator input is not held by a project allowance
  either (`turn_scheduler.py:376-379`).
- **`arrived_at` and `observed_at` are both `UTCDateTime`** (`models.py:561`, `:1226`), so the
  comparison is aware on both sides.

### D5 — the wake: a one-shot date job at `hold_until`, re-armed at start

`arm_allowance_wake(project_id, agent, when)` adds an APScheduler `DateTrigger` job to the running
`JobScheduler` (`scheduler.py:2346-2355`, memory store):
- the id is `allowance-wake:{project_id}:{agent}`, with `replace_existing=True`;
- the run date is `max(when, now + 1 s)`, because a date job already in the past is a misfire under
  the store's 60 s `misfire_grace_time`, and is dropped if it is older than that;
- the function is `schedule_or_defer({(project_id, agent)})`, which is `run_reconciliation._schedule_or_defer`
  made public. It schedules now if the Hub knows its address, and defers to the first request if
  not (`run_reconciliation.py:139-155`).

It is armed:
- **at every refused run's end**, in `_execute_run` after the finalize commit;
- **at Hub start**, from `lifespan()` after `init_scheduler()`. For every `(project, agent)` with a
  queued entry whose most recent `TurnUsage` is a refusal: arm at `hold_until` if it is still
  ahead, and call `schedule_or_defer` if it has passed. A reset that fell while the Hub was down is
  still a promise the Hub made.

**Why a timer and not a tick.** The turn scheduler has no tick, which its own comments say three
times (`turn_scheduler.py:649-651`, `agent_trigger.py:2086-2089`, `:2442-2445`). The job scheduler
is the only clock the Hub runs, and it is already in memory by design (F351), so a date job adds no
store.

**What the run-end re-drain does meanwhile.** It still runs (`agent_trigger.py:2460`), and it now
meets the hold in `_attempt_turn` and starts nothing. That is correct: it is the same pass, now
answered honestly.

### D6 — a loop's busy guard also answers "held"

`_loop_agent_busy_reason` (`scheduler.py:218-251`) returns, after its `running` check, the hold's
short form when `provider_hold` finds one: *"{agent} is held until {HH:MM} UTC by its provider's
usage limit"*. Its docstring's invariant, *"reads the same fact `schedule_agent` reads … so the two
cannot disagree about whether the agent is busy"*, now holds for the hold as well. A loop briefing
is autonomous input, so `_attempt_turn` would hold it too.

- **Flows need no rule of their own.** `_loop_flow_busy_reason` (`:274-300`) calls this function
  and refuses only when nobody else is free. A flow whose job agent is held, with another agent
  free, proceeds and staffs that agent. That agent, if it shares the account, is refused once and
  then held. Its entry waits, and its claim makes it not free on later ticks (F352's rule). So the
  queue gains at most one entry per agent, and stops.
- **`_agents_that_are_free` is not touched.** Who counts as free is F352-free, an open operator
  question (`decisions_for_user`), and the stopped change `an-unstaffed-review-names-its-holders`
  rewrites that function. This change stays off its lines.
- **The review wedge stops by itself.** The flow's *"is named on … as its reviewer and is not
  reviewing it: no turn is running on that task and none is queued"* needs the review entry gone.
  Held, it stays `queued`. That sentence was recorded 64 times on LoopEngine.

### D7 — a plain job coalesces while its agent is held

In `_do_fire_job`, for a job with **no** `Loop` row, after `_job_agent_skip_reason`
(`scheduler.py:2577-2597`). If `provider_hold(job.agent)` holds **and** an entry is `queued` for
`job.agent` on a conversation one of this job's `JobRun`s names (`JobRun.conversation_id`, the same
correlation `finalize_job_run_for_conversation` uses), then:
- the firing is recorded `skipped`, with the hold's coalesce sentence as `error_summary`;
- consecutive identical skips collapse into one row through `_stall_run_to_increment`, as the
  loop's stall path does (`:2741-2760`, `tick_count += 1`).

Otherwise the firing queues as today. At the reset the one queued copy is delivered.

- The sentence must fit `JobRun.error_summary`, which is `String(500)` (`models.py:1349`). The
  shape is *"{agent}'s provider usage limit is spent until {HH:MM} UTC, and this job's earlier
  firing is still queued for it. This firing adds nothing."* That is 161 characters at a 32-character
  agent name (measured by `f355len.py` in `%TEMP%`). The hold sentence (D9) is 285 there. Task 3.4 pins both.
- The `resetsAt` time is in the reason, so a new wall gives a new reason and a new row. That is the
  loop path's *"a stall that changes shape stays visible"*, unchanged.
- **Severable.** D7 is the one decision the proposal names as open to challenge. Removing it
  changes nothing else in this design.

### D8 — the count is a new column, and the retry note reads both counts

`InboundQueueEntry.allowance_refusals: int` (not null, default 0), migration `0103`.
`format_turn_prompt` states the retry note when `delivery_attempts + allowance_refusals > 0`, and
names attempt `delivery_attempts + allowance_refusals + 1`. The wording is unchanged: *"an earlier
attempt was cut off before it finished"*. That is true of a refused delivery, which the provider
cut off before or during the turn. 3 of `dev`'s 51 refused runs used tokens, so they were cut off
mid-turn.

**Considered and rejected: no column, and a narrowed note requirement.** A refused delivery keeps
its session (D2), and the resumed session holds the agent's own copy of the refused prompt
(measured, transcript `2a0bb6e2…`). So *"no way to tell"*, the shipped requirement's premise, is
false for a refusal, and the requirement could be narrowed to counted attempts. That was rejected
for three reasons:
- it modifies a shipped requirement to save a column;
- the queue status route's *"N attempts left"* (`api/v1/inbound_queue.py:184-194`) must keep
  meaning counted attempts, so `delivery_attempts` cannot simply absorb refusals;
- an entry refused three times and then delivered would carry no record of it, and the operator's
  question *"what happened to my message overnight?"* would have to be answered from event rows.

### D9 — what the operator sees

- **The hold sentence**, one function `hold_sentence(agent, hold)`:
  *"{agent}'s provider refused its last turn: its {limit} usage limit is spent until {HH:MM} UTC
  ({ISO}). The Hub holds its queue until then and does not count the refusal against any input. A
  new message from the operator is tried once sooner."* Here `{limit}` is `limit_type` with `_`
  read as `-` (`five-hour`, `seven-day`), and it is omitted when the type is absent. It goes on
  each requeued entry's `waiting_reason` (D2) and on the scheduler's `ScheduleResult` (D4).
- **The queue status route** (`api/v1/inbound_queue.py:135-160`) derives it: after the running and
  hop-budget checks and before the token budget, `reason = hold_sentence(...)` when `provider_hold`
  holds and no queued operator entry would probe (D4's condition). So a message that arrived during
  the hold, and never had a `waiting_reason` written, still shows why it waits. `delivery_attempts`
  in the response keeps its meaning.
- **A `queue_agent_held` event**, persisted at `warn` and broadcast, at each refused run's end. The
  payload carries `agent`, `run_id`, `hold_until`, `resets_at`, `limit_type` and `entry_ids`
  (the requeued ids). Beside `_report_abandoned_entries`. No UI handles it by name today, and none
  is added. It is the record, as `queue_agent_paused` is for a blocked workspace.

## What this change does not do

- It does not model provider accounts (D3), and it does not release a hold when an agent is rebound
  to another runner. The operator's probe (D4) is the remedy for both.
- It does not change a refused firing's `JobRun`. `finalize_job_run_for_conversation` still marks
  it `failed` at the refused run's end (`agent_trigger.py:2348`), exactly as for any failed run
  whose input was returned. That is existing behaviour for every retried input, not F355's.
- It does not parse the harness's prose, touch Codex, add UI, or edit `mcp_server.py`.
- It does not change `_agents_that_are_free` or anything else F352-free will decide (D6).

## Risks

- **The harness renames `status` or `resetsAt`.** Recognition then returns `None` and the Hub falls
  back to today's counted path. That is a degradation to known behaviour, not a new failure. The
  parser test pins the measured shape.
- **A hold that outlives the operator's patience.** A `seven_day` refusal holds autonomous input
  for days. The queue status says until when, and the operator can withdraw input or probe.
- **The re-arm at start reads every queued agent's latest `TurnUsage`.** That is one indexed query
  per queued agent (`ix_turn_usage_project_observed`, `models.py:1243`), run once per start.
