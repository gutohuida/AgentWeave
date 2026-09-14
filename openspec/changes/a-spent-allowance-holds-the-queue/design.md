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
- `waiting_reason` is left `None`, as `deliver_entries_with_run` cleared it
  (`inbound_queue.py:160`). *(Round 2: R1 wrote the hold sentence here. The one reader of the column
  is the status route (`api/v1/inbound_queue.py:183`), which D9 already derives live. A stored copy
  outlives the hold and then explains a wait that has ended. That is F97's rule
  (`inbound_queue.py:157-160`).)*
- **`delivery_attempts` is not touched,** and **neither limit is evaluated.** So the provider
  session is never cleared, and the entry is never withdrawn, for a refusal.

The id is still returned in the requeued list. So `evaluate_run_end` and the handover are skipped,
as they are for any returned input (`agent_trigger.py:2364-2374`): the work is going to another run.

`_execute_run` computes `refusal = allowance_refusal(accounting_sample.allowance)` once, when
`final_status == "failed"` and `binding_conflict is None`, and passes it. Every other caller passes
nothing:
- the transport-failure tail (`:1927`) and the spawn failure (`:2070`);
- the Codex path (`:2847`, `:2942`);
- startup reconciliation (`run_reconciliation.py:87`).

None of them has a reading, so they keep today's behaviour exactly.

**On a refusal, `finalize_job_run_for_conversation` is not called** (`:2348`). The firing's
`JobRun` stays `in_progress`, and the delivered turn's end flips it at the reset. D10 gives the
reasons.

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
- **Why "informative", and not simply the newest row.** Four paths write a row with
  `sample=None`, which says nothing about the provider:
  - the transport-failure tail (`agent_trigger.py:1917-1924`);
  - a spawn that never started (`:2059-2066`);
  - a Codex app-server run that never started (`:2837-2843`);
  - crash reconciliation (`run_reconciliation.py:79-86`).

  The normal end (`:2320-2326`) writes the same row when the run parsed nothing. *(Round 2: R1
  listed three, and cited the reconciliation writer's comment in `usage_accounting.py` rather than
  the writer.)*

  If one of those rows ended a hold, a Hub restart or a missing CLI would release an agent the
  provider is still refusing. A completed run that happened to emit no `rate_limit_event` is still
  informative, because its row is `measured`: the provider served tokens, and that is the whole
  question. A refused run that used tokens (3 of `dev`'s 51) is both `measured` and a refusal, and
  the reading decides it.
- **JSON `null` is not SQL `NULL` here.** A row written with no reading stores the JSON literal
  `null`, which `allowance IS NOT NULL` matches (measured: 3 such rows on `:8000`, which
  `json.loads` read as `None`). So the informative filter has to test for an object. Either
  `json_type(allowance) = 'object'` on SQLite, or a Python check over rows read newest-first until
  the first informative one. **Not a fixed window** *(Round 2: R1 offered one)*: every spawn failure
  after a refusal adds an uninformative row. A window those rows overflow finds no refusal, and it
  releases the hold. Task 1.3 pins the trap.
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
- the run date is `max(when, now + 1 s)`. *(Round 2, read in APScheduler 3.11.2, the version
  installed here.)* A `DateTrigger` in the past is not refused. `get_next_fire_time` returns it
  (`triggers/date.py:26-27`), and it runs if it is under 60 s late (`misfire_grace_time`, checked in
  `executors/base.py:117-120`); later than that, it is dropped. The floor keeps the date ahead, so
  the grace never applies. A job runs only once the scheduler's wall clock reaches its date
  (`job.py:151`, `<= now`). An early timer only re-arms. So the `schedule_agent` the wake reaches
  reads `now >= hold_until`, and the hold it was armed for is over;
- the function is `schedule_or_defer({(project_id, agent)})`, which is `run_reconciliation._schedule_or_defer`
  made public. It schedules now if the Hub knows its address, and defers to the first request if
  not (`run_reconciliation.py:139-155`).

With no running `JobScheduler` (`get_scheduler()` is `None`: most tests, and any path before
`init_scheduler`), arming does nothing and logs at debug. The next start's re-arm covers it. Arming
never raises into its caller: APScheduler's `add_job` is wrapped as `JobScheduler.add_job` wraps it
(`scheduler.py:2410-2412`).

It is armed:
- **at the end of every run whose recorded reading is a refusal, whatever the run's final status**,
  in `_execute_run`, **immediately after the finalize commit (`:2354`)** and before anything else
  that can raise. *(Round 2: R1 armed only a refused `failed` run.)* D3 derives the hold from the
  row, not from the status. A run that ended `completed`, `stopped` or in a binding conflict, with
  a `rejected` reading, therefore holds the queue as well. Armed only for `failed`, that hold has
  no wake: the run-end re-drain meets it and starts nothing, and nothing comes back. The measured
  corpus has no such run (all 69 refusals failed). But the parser keeps the newest reading
  (`AccountingSample.merged`, `runner_events.py:302-318`), so a turn cut off late can end with one.
  After the commit, and not later, because `_report_abandoned_entries`, the broadcasts and
  `maybe_generate_title` all sit inside the same `try`. An exception in any of them reaches
  `_record_run_failure_tail` (`:2461-2491`) and skips everything below it. A wake placed below them
  is lost to that exception until the next restart;
- **at Hub start**, from `lifespan()` after `init_scheduler()`. This covers every `(project, agent)`
  with a queued entry whose newest *informative* `TurnUsage` (D3) is a refusal. *(Round 2: R1 said
  the newest row. A crash reconciliation, which runs just before in the same `lifespan`, writes an
  uninformative row that would hide the refusal.)* Arm at `hold_until` if it is still ahead, and
  call `schedule_or_defer` if it has passed. A reset that fell while the Hub was down is still a
  promise the Hub made.

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

- **Flows do need a rule, and it is the same fact read in two more places.** *(Round 2 rewrote
  this bullet. R1's argument was wrong, and its outcome with it.)*

  R1 argued that `_loop_flow_busy_reason` (`:274-300`) carries the hold to flows, since it calls
  this function. It does, but it guards only the **job's** agent, and it lets the firing through
  whenever **any** agent in the project is free (`_agents_that_are_free`, project-wide, `:977`).
  Past that guard, `decide_firing` asks its own question, with its own set:
  `running = _agents_running_a_turn(...)` (`:1299`). That set counts runs, not holds, and it
  decides two things:
  - **Resumption** (`:1421-1435`). A task already assigned to agent B is re-selected for B
    whenever `B not in running`. `held` (`:1303`) counts only running turns, and `on_it` is read
    only by the review arm (`:1378`). So a held B, idle by construction, is re-briefed on its
    assigned task **on every tick**: one more queued entry per tick, all waiting for the reset.
  - **The job's default** (`:1445`). `default_agent not in running` selects a held job agent for
    the first unstaffed task.

  So R1's *"the queue gains at most one entry per agent, and stops"* holds only while nobody in the
  project is free. A flow that has one free agent, on another account or merely between tasks,
  re-briefs every held assignee on every tick. That is the pile-up D4 of `loop-notices-and-reacts`
  forbids, and it arrives through the arm that *does* know about running agents (`agent in running`
  → `in_flight`, `:1426-1435`).

  **The rule:** one set, `_agents_that_cannot_take_a_turn(session, project_id)`, defined as
  `_agents_running_a_turn(...) | agents_held(...)`. `agents_held` is the set-valued form of
  `provider_hold` in `provider_allowance.py`: for each agent with a `TurnUsage` row, its newest
  informative row, held per D3 at one `now`. The rule reads it in two places:
  - `decide_firing`'s `running` (`:1299`). A held assignee then reads as in flight, exactly as a
    running one does, and a held default agent is passed over;
  - `_agents_that_are_free`'s running half (`:1003-1011`). A held agent is not recruited for fresh
    work, or chosen as a rung-2 reviewer.

  `_agents_running_a_turn` keeps its meaning and its name.
- **Why `_agents_that_are_free` is touched after all, and why that is not F352-free's question.**
  R1 kept off it because F352-free is open, and because the stopped change
  `an-unstaffed-review-names-its-holders` rewrites it. F352-free asks **which holdings** make an
  agent unavailable: the task half, `holding`, at `:1012-1024`. This change touches only the other
  half, the one its own docstring justifies: *"holding-no-task by itself would pick an agent
  mid-turn and `schedule_agent` would refuse the second start"* (`:983-984`). After D4,
  `schedule_agent` refuses a held agent's start for the same reason it refuses a running one's. Its
  next sentence, *"reads the same running query `schedule_agent` … reads, … so a third opinion
  about whether an agent is busy cannot appear here"* (`:986-988`), is then true only if the hold
  is read there too. Left out, it is the third opinion. None of F352's five options is about this half,
  and none changes if it moves. The collision with the stopped change is line-level. Whichever of
  the two is built second keeps both halves.
- **What the board shows.** `api/v1/jobs.py:339, 1232` read the same `decide_firing`. So a held
  agent's task reads as in flight on the board, as a running agent's does, and the queue status
  (D9) says why nothing moves. That is presentation, not scheduling. This change adds no word for
  it on the board.
- **The review wedge stops by itself.** The flow's *"is named on … as its reviewer and is not
  reviewing it: no turn is running on that task and none is queued"* needs the review entry gone.
  Held, it stays `queued`. That sentence was recorded 64 times on LoopEngine.
- **The general case is F368, and it is not this change's.** A flow re-briefs an assigned, idle
  agent on every tick whenever that agent's queued turn cannot start. The token budget is the
  instance found by reading: `_attempt_turn` returns at `turn_scheduler.py:377-379` with the
  default `terminal_failure=True`, so each such firing's `JobRun` also reads `failed`. The general
  repair would read `on_it` in the resumption arm. It changes flow behaviour beyond a held agent,
  so it is filed, not folded in.

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
  read as `-` (`five-hour`, `seven-day`), and it is omitted when the type is absent. It goes on the
  scheduler's `ScheduleResult` (D4) and is derived by the status route below. It is **not** stored
  on the entries (D2, Round 2).
- **The queue status route** (`api/v1/inbound_queue.py:135-160`) derives it: after the running and
  hop-budget checks and before the token budget, `reason = hold_sentence(...)` when `provider_hold`
  holds and no queued operator entry would probe (D4's condition). This is the only place the
  sentence is produced for the operator, so it is true exactly while the hold is, and it names the
  hold for every queued entry, whenever it arrived. `delivery_attempts` in the response keeps its
  meaning.
- **A `queue_agent_held` event**, persisted at `warn` and broadcast, wherever D5 arms the wake: at
  the end of every run whose reading is a refusal. The payload carries `agent`, `run_id`,
  `hold_until`, `resets_at`, `limit_type` and `entry_ids` (the requeued ids, which are empty for a
  run that was not `failed`). It is emitted just after the wake is armed, before
  `_report_abandoned_entries`. No UI handles it by name today, and none is added. It is the record,
  as `queue_agent_paused` is for a blocked workspace.

### D10 — a firing whose input is held reads `in_progress`, across a refusal and a restart

*(Added in Round 2.)* R1's requirement says a job firing that reaches a held agent is reported as in
progress, not failed. R1 made the one path it read honour that (D4's `terminal_failure=False`). Two
more paths in the code break it:

- **The refused turn's own firing.** `finalize_job_run_for_conversation(db, conversation_id,
  "failed")` runs at every failed run's end (`agent_trigger.py:2348`). So the firing whose turn hit
  the wall reads `failed` while its input is queued for the reset. At the reset the input is
  delivered, and its run's end finds no `in_progress` row to flip (`scheduler.py:1820-1827`
  selects only `in_progress`). The history then shows `failed` for good, for an instruction that
  was carried out. An operator reading that is invited to fire it again by hand, which is a
  duplicate.
  **Fix:** on a refusal (D2's condition), `_execute_run` skips the finalize call. The row stays
  `in_progress`, and the run that finally delivers the input flips it, whatever it ends as. A
  refused probe or wake is itself a refusal, so it leaves the row as it found it.
- **A restart during the hold.** `reconcile_stale_job_runs` (`run_reconciliation.py:189-226`)
  marks `failed` every `in_progress` `JobRun` with no running `Run` behind it. *"Reconciled on Hub
  start: no live run behind this firing"* describes a held firing exactly, and a hold lasts hours
  or days. **Fix:** it leaves `in_progress` any `JobRun` whose `conversation_id` has a `queued`
  entry for an agent whose newest informative `TurnUsage` is a refusal. That covers two cases:
  - the agent is still held;
  - the reset passed while the Hub was down, and D5's start-up re-arm is about to deliver the
    input.

  In both, the Hub has promised the delivery. The rule is keyed on the refusal, deliberately. The
  function's docstring decides that a firing queued for an agent with no runner reads `failed` at
  restart (`:202-206`). That firing is waiting on a repair the Hub cannot promise, so the existing
  rule stands for it.

`reconcile_stale_job_runs` runs before `init_scheduler` in `lifespan()` (`main.py:414-416`), and
D10 needs only the database there.

## What this change does not do

- It does not model provider accounts (D3), and it does not release a hold when an agent is rebound
  to another runner. The operator's probe (D4) is the remedy for both.
- *(Round 2: R1's bullet here said the refused firing's `JobRun` still reads `failed`. D10
  reverses that.)* It does not change the `JobRun` of a firing whose input failed for any **other**
  reason. A counted retry still finalizes `failed` at each failed run's end, as today.
- It does not parse the harness's prose, touch Codex, add UI, or edit `mcp_server.py`.
- It does not change which **holdings** make an agent unavailable, which is F352-free's (D6). It
  adds the hold to the running half only.
- It does not stop `maybe_generate_title` (`agent_trigger.py:2429`) from spawning a titling CLI at
  a refused run's end. That spawn is not a turn: it records no `Run`
  (`conversation_titles.py:7-11`). It is at most one per untitled conversation, and it fails
  quietly (`:95`). Named so that nobody reads it as a hole in the hold.
- It does not repair F368, the general form of D6's pile-up.

## Risks

- **The harness renames `status` or `resetsAt`.** Recognition then returns `None` and the Hub falls
  back to today's counted path. That is a degradation to known behaviour, not a new failure. The
  parser test pins the measured shape.
- **A hold that outlives the operator's patience.** A `seven_day` refusal holds autonomous input
  for days. The queue status says until when, and the operator can withdraw input or probe.
- **The re-arm at start reads every queued agent's latest `TurnUsage`.** That is one indexed query
  per queued agent (`ix_turn_usage_project_observed`, `models.py:1243`), run once per start.
- **`agents_held` runs on every flow firing and every `_agents_that_are_free` call.** That is one
  newest-informative read per roster agent (`ix_turn_usage_project_agent`, `models.py:1242`). A
  roster is a handful of agents, and a firing already asks several set-valued questions of the same
  size (`scheduler.py:1298-1310`).

## Round 2 — re-derived against the code (2026-09-14, `f355-r2`)

R2 re-read the code R1 cites, and the code R1's argument depends on without citing it: the flow walk
(`decide_firing`), `reconcile_stale_job_runs`, every `record_turn_usage` writer, `_execute_run`'s
exception boundary, and APScheduler 3.11.2's own source. Where the code disagreed, the change files
were fixed. Nothing here was driven. Every claim is read from code or source, with its line.

**R1's conclusion that there is no OPERATOR QUESTION stands. R2 re-derived each leg:**
- **Hold, not drop.** The shipped limit gives input up because *"retrying without limit is
  indistinguishable from being stuck"*. Under a hold nothing retries; the queue status names the
  end; operator input still probes. None of the limit's reasons is engaged.
- **The flow's job.** Once D6 is repaired (below), a held agent is treated exactly as a running
  one wherever the flow asks. The shipped rule for running agents then applies unchanged. No new
  policy is made.
- **`_agents_that_are_free`.** The one place R2 goes where R1 would not. Argued in D6: the running
  half, never the holdings half F352-free asks about.
- **Plain-job coalescing (D7).** Still the one candidate, and still severable. R2 adds one fact
  against it, for REV: a job whose message the operator edits during a hold delivers the old text
  at the reset, and the new text from the first firing after it.

**What R2 changed, in order of weight:**
1. **D6's flow argument was wrong, and its outcome with it.** The busy guard covers only the job's
   agent, and lets a firing through when anyone in the project is free. `decide_firing` reads its
   own `running` set (`scheduler.py:1299`). Its resumption arm (`:1421-1435`) therefore re-selects a
   held assignee's task on every tick, and its default branch (`:1445`) selects a held job agent.
   R1's *"at most one entry per agent, and stops"* was false for any project with one free agent.
   The repair reads one set, `_agents_that_cannot_take_a_turn`, in `decide_firing` and in
   `_agents_that_are_free`'s running half. The spec gained an `agent-flows` delta, and tasks gained
   3.4b and 3.4c.
2. **A hold could exist with no wake.** R1 armed the wake only for a `failed` refusal. D3 derives
   the hold from the row, whatever the status. The wake and the event now follow the reading, and
   the wake sits immediately after the finalize commit. Everything below that commit shares a `try`
   whose failure tail skips the rest (`agent_trigger.py:2461-2491`).
3. **A firing whose input is held read `failed` on two paths R1 did not read**
   (`agent_trigger.py:2348`, `run_reconciliation.py:189-226`). That broke R1's own requirement. New
   D10, and tasks 2.5 and 3.7.
4. **The hold sentence was stored on entries, where it outlives the hold.** Its only reader
   derives it live. D2 now stores nothing (F97's rule).
5. **Smaller:**
   - four `sample=None` writers, not three;
   - the re-arm reads the newest *informative* row, not the newest row;
   - no fixed-window form of the informative filter, since it fails open;
   - APScheduler's past-date handling stated from its source.
6. **Test construction:**
   - 3.2's real-scheduler test must make the bound address known first. Otherwise the wake defers
     (`run_reconciliation.py:152-155`), the test times out, and the *"do not arm"* mutation times
     out identically, which proves nothing.
   - 3.5's *"the first firing queues"* needs a hold from another conversation. The LoopEngine shape
     (the job's own turn refused) coalesces from the first firing, and is now its own test.
   - Drive 6.4 could not observe a probe: 6.3 ends the hold, so 6.4's message is a fresh refusal.
     It now sends two messages.

**Filed:** F368 (B), code-read. A flow re-briefs an assigned, idle agent on every tick while that
agent's queued turn cannot start. The token budget is the instance that reading found. D6 repairs
only the held instance.
