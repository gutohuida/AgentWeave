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
`final_status == "failed"` and `binding_conflict is None`, and passes it. **(Round 4 — REV)** Two
more conditions apply, and without either one `refusal` is `None` and the run takes today's counted
path:
- **The reading was recorded.** That is the `if run:` branch that writes the `TurnUsage` row
  (`agent_trigger.py:2298-2327`), the same condition D5 arms on. `return_run_entries` sits outside
  that branch (`:2349-2353`). A run whose row the finalizing session could not see records no
  reading, so D3 derives no hold and D5 arms nothing. An uncounted requeue there would record a
  refusal for a hold that does not exist. It would not loop: that row stays `running`, and
  `schedule_agent` refuses the agent's later turns anyway (the loud branch at `:2279-2297`). But
  the refusal count and the hold would stop describing the same fact. Conditioned, they cannot.
- **`resets_at` is later than the run's end.** A `rejected` reading whose reset is already past
  states no wait with an end. Uncounted, D3's floor would retry it once a minute for ever, never
  counted and never given up, and that is the case the shipped limit calls *"indistinguishable from
  being stuck"*. Counted, the floor still spaces the retries a minute apart, and the shipped limits
  give it up after three.

Every other caller passes nothing:
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
  `json.loads` read as `None`). So the informative filter has to test for an object. It is a
  Python check over rows read newest-first until the first informative one. *(Round 4 — REV:
  R1 also offered `json_type(allowance) = 'object'`. That function is SQLite's, and `models.py`
  still reasons about PostgreSQL (`:756`), so the Python check is the one that holds on both.)*
  **Not a fixed window** *(Round 2: R1 offered one)*: every spawn failure
  after a refusal adds an uninformative row. A window those rows overflow finds no refusal, and it
  releases the hold. Task 1.3 pins the trap.
- **The 60 s floor** is the spin guard. A `rejected` reading whose `resetsAt` is already past
  (clock skew, or a provider that reset late) would otherwise release immediately, refuse again and
  requeue. That is a tight loop of uncounted spawns, which is worse than today's bounded three. The
  floor caps it at one refused spawn a minute per agent. It is not a backoff policy; it only
  bounds a pathological reading. *(Round 4 — REV: the floor bounds the rate, not the count. D2 now
  counts such a refusal as a delivery attempt, so the shipped limits end it.)*
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
- **Which inputs probe, by caller** *(Round 3, read at every `schedule_agent` call site that is
  not the run-end re-drain)*. The probe is keyed on the entry's `origin_type`, not on who called
  the scheduler, so the callers only matter for what they queue:
  - `POST /agent/trigger` queues `operator` (`agent_trigger.py:1490`): **probes**.
  - **An answered question** is queued `operator` too (`questions.py:112-120`, delivered from
    `:399` and `:504`), so answering a held agent's question **probes**. That is right on D4's own
    reason: an answer is the operator's new input, and the operator may have fixed the allowance
    before answering.
  - A peer message (`messages.py:257`), `request_agent` (`agents.py:2114`), a checkpoint successor
    (`checkpoint_cutover.py:136`, even when the operator asked for the cutover), a divergence
    restaff (`run_divergence.py:261`) and a job firing (`scheduler.py:2853`) queue autonomous
    origins: **they wait**.
  - Callers that queue nothing and only re-schedule wait on whatever is queued: a newly bound
    runner (`agents.py:2521`), a budget change (`accounting.py:72`), the settings re-drain
    (`api/v1/inbound_queue.py:107`), a hop-suspension release (`:253`, the entry keeps its
    `agent` origin), and `POST …/conversations/{id}/continue` (`checkpoints.py:283`). Each receives
    the hold as `waiting_reason`, with `terminal_failure=False`. Rebinding the agent to a runner on
    another account does not release the hold (*What this change does not do*); the operator's
    next message does.

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
  is lost to that exception until the next restart. *(Round 3, re-read against `:2277-2460`.)*
  The first statement after the commit is `evaluate_run_end` (`:2364-2365`), reached only when
  nothing was returned. So for a refused `failed` run nothing precedes the arm, and for 2.6's
  `completed` refusal the arm must sit above `evaluate_run_end`. The reading is recorded only
  inside `if run:` (`:2298`, `:2320-2326`), so the condition is *"a row was recorded and its
  reading is a refusal"*. A finalizing session that could not see its run row records no
  `TurnUsage`, so D3 derives no hold, and arming a wake or emitting `queue_agent_held` there would
  announce a hold that does not exist. The Codex app-server end (`:2902-2946`) has the same shape
  and needs nothing, because no Codex sample carries `allowance`;
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

  **The rule** *(Round 3 rewrote it. R2's form, and why it breached a shipped requirement, is the
  paragraph after this one.)*
  `agents_held(session, project_id)` is the set-valued form of `provider_hold` in
  `provider_allowance.py`: for each agent with a `TurnUsage` row, its newest informative row, held
  per D3 at one `now`. `decide_firing` reads it once, beside `running`, as `held_agents`, and uses
  it in three places:
  - **Resumption** (`:1426`): `agent in running or (agent in held_agents and on_it.get(task.id)
    == agent)` records in flight. `on_it` is `tasks_with_a_turn_pending_or_running` (`:1310`),
    already read for the review arm. It maps a task to the agent with a `queued` entry naming it
    (`run_task_binding.py:295-309`), **whichever agent that is**. *(Round 4 — REV: R3 wrote
    `task.id in on_it`, so another agent's stale entry naming the task would have made the held
    assignee's task read in flight, with nothing queued for the assignee.)* A held assignee whose
    task has no input queued for it falls through
    to the ordinary resumption and is briefed **once**. That briefing names the task (job entries
    carry `task_id`, `scheduler.py:2870-2874`), so on the next firing the task is in `on_it` and
    therefore in flight. One briefing per held-assigned task, in total.
  - **The job's default** (`:1445`): `default_agent not in running and default_agent not in
    held_agents`. This one cannot be conditioned on `on_it`, because the task is unassigned. The
    default branch deliberately checks no holdings (its comment at `:1448-1455`), so a held default
    agent would be given a **new** task on every firing, which is a pile-up across tasks rather than
    within one.
  - `_agents_that_are_free`'s running half (`:1003-1011`) reads `running | agents_held`, so a held
    agent is not recruited for fresh work, or chosen as a rung-2 reviewer.

  `_agents_running_a_turn` keeps its meaning and its name.

  **Why a held assignee is not treated exactly as a running one** *(Round 3)*. R2 put held agents
  into `running` itself, so a held assignee's task read in flight on the assignment alone. That
  breaches a shipped requirement: `agent-loops` *A task reported as in flight is one an agent is
  actually working* allows in flight only for a running turn bound to the task, or queued input
  naming it, and says an assignee *"SHALL NOT by itself be sufficient"*. The running arm's
  agent-level reading is a deliberate, commented exception (`:1285-1290`: a run carrying no
  `task_id` must keep counting). A held agent has no run at all, so the exception's reason does not
  reach it. The case is real: a held agent whose refused input was a peer message or an operator
  chat, while it is assigned a flow task nobody has briefed it on.
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
- **But the shipped requirement states the rule, so it is MODIFIED, not added beside** *(Round 3)*.
  `agent-flows` *A flow resolves a reviewer by declaration, then by availability* says the Hub
  *"SHALL select any agent that is not running a turn and holds no task in an active status"*. A
  held agent that holds nothing satisfies that sentence. R2's ADDED requirement said such an agent
  *"SHALL NOT be selected as a reviewer by availability"*, so the corpus would have carried two
  SHALLs that disagree. The delta now MODIFIES that requirement: the availability sentence and its
  two scenarios gain the hold, with a sentence stating that which tasks make an agent unavailable is
  unchanged. Everything else in the block is copied as shipped.
- **Rung 3's sentence names the hold** *(Round 3)*. Once the free half reads the hold, rung 3's
  reason (`scheduler.py:1161-1168`) is false whenever a held agent is why nobody was free: *"Every
  agent on the roster is either running a turn, already holding active work, or {excluded} …"*.
  That sentence is promoted to the stall reason and broadcast as `review_unstaffed`
  (`:1597`, `:2698-2701`). `resolve_reviewer` reads `agents_held` at rung 3 only, and when a
  non-excluded roster agent is held, the enumeration gains *"waiting for its provider's usage limit
  to reset"*. It is conditional, so a project that never hits a limit reads exactly as today. It
  adds under 50 characters, far inside `JobRun.error_summary`'s 500. It is the sentence the stopped
  change `an-unstaffed-review-names-its-holders` rewrites, so whichever is built second carries the
  hold's ground into the other's wording. The pre-existing gap beside it, a runnerless agent
  excluded but not named, is that change's D1, not this one's. Task 3.4d.
- **A loop's work moves to a free agent during a hold, as F128 records for a running one**
  *(Round 3; the reach corrected in Round 4 — REV)*. `_loop_flow_busy_reason` lets a firing through
  when anyone is free, and the default branch now passes over a held job agent. So in a project with
  a free agent, a loop whose job names the held agent is staffed with the free one. That is F128's
  substitution, which the operator has open (*"either the free list becomes loop-scoped … or the UI
  and the API stop presenting `job.agent` as who runs this loop"*).

  **How much of it is new.** R3 argued that the substitution used to last only as long as a turn,
  and a hold now makes it last hours. That premise is false. `decide_firing` gives width to a loop
  that declares no document too: `_loop_candidates` (`scheduler.py:704-721`) does not filter on
  `spec_document_id`, and the walk's only check on it is the review arm's (`:1492`). So in any
  documentless loop with two startable tasks, the first goes to the default agent (`:1445`), and the
  second falls to `else` and recruits from `free` (`:1459`), **whether or not the job's agent is
  busy**. Today's wall reaches it that way too: tick 2 re-selects the refused agent's T1
  (`:1421-1435`) and adds it to `taken` (`:1467`), and T2 goes to `free`. Code-read, not driven.

  So D6 adds exactly one case: a **single** startable unassigned task while the job agent is held.
  It neither widens nor narrows the rule; it applies it to one more reason an agent cannot take a
  turn. Whatever the operator decides for F128 applies to held and running agents alike. The
  alternative, leaving the default branch blind to the hold, is the cross-task pile-up above.
- **What the board shows.** `api/v1/jobs.py:339, 1232` read the same `decide_firing`. A held
  agent's task with queued input is in the firing's cannot-staff collection, and
  `task_attribution.attribute` renders it `held` (*"staffed, and nothing is running"*,
  `task_attribution.py:55-58`, `:186-188`), which is true. `firing_active` joins a **running**
  `Run` (`jobs.py:405-413`), so a held loop does not read as firing. The queue status (D9) says why
  nothing moves. *(Round 3: R2 said the task reads in flight "as a running agent's does". A running
  agent's task renders `working` only where a run is bound to it.)*

  **But a stalled answer on the board was false** *(Round 4 — REV)*. R3 said *"this change adds no
  word for it on the board"*. That misses a case. Take a single-agent loop whose agent is held, with
  one pending unassigned task and no input naming it (the refused turn was a peer message). The
  default branch skips the held agent, `free` is empty, and the walk reaches `continue` (`:1464`).
  So `_batch_loop_summaries` (`jobs.py:339-340`) reads `DECISION_STALLED`, with *"loop queue is
  stalled: no claimable task among 1 open (1 pending)"* (`scheduler.py:1802`), for the length of
  the hold. The firing never records it, because the busy guard refuses first. Only the board shows
  it. The UI's contract for that field is *"set exactly when the next firing would be refused, by
  the same computation that would refuse it"* (`hub/ui/src/components/spec/loopCounts.ts:21-22`),
  and the computation that refuses the next firing is the guard.

  **Repair:** when `decide_firing` answers `DECISION_STALLED` for a loop, and
  `_loop_flow_busy_reason(job.agent)` refuses, the summary's `stall_reason` is the guard's reason.
  It applies only to a stalled decision. An in-flight decision keeps `stall_reason = None`, so a
  single-agent loop whose agent is working its task keeps reading `running`, not `stalled`. REV
  proposed asking the guard first for every loop, and that would have labelled every working
  single-agent loop `stalled` for the length of each turn. The same repair fixes the running
  variant, which exists today while a turn lasts (the agent running a chat, with one pending task).
  No UI change: the field is already rendered. Task 3.4e.
- **What pressing Run says is not presentation** *(Round 3)*. `run_job` (`jobs.py:1287-1321`)
  turns a declined firing into an HTTP answer, and D6 changes which answer it reaches. See D11.
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
- **Not severable, and not an operator question** *(Round 4 — REV; R1 to R3 called it the one
  severable choice)*. The shipped position settles it. `_loop_agent_busy_reason`'s docstring
  (`scheduler.py:236-240`) calls a plain job's message *"a standing instruction still true when the
  agent frees up"*. One queued copy satisfies that, and no reading of it asks for sixty. The
  argument R1 to R3 never made is the decisive one. A job that does not resume gets a **new
  conversation per firing** (`scheduler.py:2837-2843`). So a `*/5` job held for five hours would
  deliver about sixty separate turns back to back into the freshly reset allowance, and exhaust it
  again. Queuing every tick is therefore self-defeating, not merely wasteful. Skipping instead would
  lose the instruction until the next firing after the reset. D7 is the only choice that keeps the
  shipped position's reason.

  It is not severable in practice either. Without D7, D4's `terminal_failure=False` keeps every held
  firing of a *resuming* job `in_progress` on one conversation. The inbound batch cap of ten
  (`inbound_queue.py:17`) then delivers them in one turn whose end finalizes one row, and the rest
  wait for a restart to mark them `failed` (D10's last bullet). Calling it severable also invited
  exactly what the F352-free precedent forbids: removing an operator question to avoid a stop.

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

**Every other reader of a `JobRun`'s status, against a row that stays `in_progress` for hours or
days** *(Round 3)*. Read at each site; none is misled:
- **`firing_active`** (`jobs.py:404-415`) joins a `Run` in `running` on the firing's conversation.
  A held firing has none, so the loop does not read as firing, which is true. That flag also
  decides whether an edit stages or applies, so an edit made during a hold applies at once, as it
  would for an idle loop.
- **`_stall_run_to_increment`** (`scheduler.py:885-925`) counts only when the most recent row is
  a `skipped` row with the same reason. A held `in_progress` row is the most recent, so the first
  stall after it writes its own row. That is D7's first-coalesce behaviour, already pinned by 3.5.
- **`_prune_job_history`** (`:2436-2460`) keeps the newest 100 rows. A held row can be pruned
  only if 100 rows are written above it during the hold. Loops record nothing while held, and D7
  collapses a plain job's skips into one row, so this needs a flow firing 100 times with other
  agents working, which is 8 h 20 m at `*/5`. If it happens, the delivering run's finalize finds no
  row and does nothing (`:1825-1827`). Nothing is corrupted; the firing loses its history row.
- **`_pending_loop_request`** (`:350-390`) reads the newest earlier firing's `conversation_id`,
  whatever its status.
- **`finalize_job_run_for_conversation`'s own invariant** (`:1812-1816`): *"at most one
  `JobRun` should be in progress for a given `conversation_id`"*, because a resuming job's earlier
  firings are terminal before the next is created. *(Round 4 — REV corrected R3's attribution.)*
  The invariant is **already false today**. A plain job is not busy-guarded, so a resuming job that
  fires during its own running turn creates a second `in_progress` row on the same conversation,
  and the two are flipped newest-first (`:1823`). What would amplify it is D4 plus the inbound
  batch, not D10. D4's `terminal_failure=False` keeps every held firing `in_progress`, and the batch
  cap of ten (`inbound_queue.py:17`) delivers them in one turn whose end flips one row. D7 prevents
  that **during a hold**: the later firing finds the first one's queued entry and coalesces. With D7
  and D10 together, two `in_progress` rows on one conversation still arise only when a firing lands
  during the refused turn's own 6–10 s, before any hold exists. That is today's shape. At a restart,
  `reconcile_stale_job_runs` (`run_reconciliation.py:210-223`) marks the leftover row `failed` once
  its entry has been delivered, so nothing stays open for ever.

### D11 — pressing Run on a loop that declines says why (Round 3; retires F127)

`run_job` (`api/v1/jobs.py:1236-1330`) turns a firing that returned `False` into an HTTP answer.
Today it reads the newest `JobRun` (`:1278-1281`). If that row is `skipped`, it answers 409 with the
row's reason. Otherwise it re-derives the decision (`_loop_work_is_all_in_flight`, `:1215-1233`),
answering 409 *"Every task on this loop's queue is already being worked. Nothing was started, and
nothing is wrong"* when it is `DECISION_IN_FLIGHT`, and **500** with the row's `error_summary` or
*"Failed to fire job"* when it is not.

**What D6 does to that route, traced for a single-agent loop whose agent is held** (the LoopEngine
case, and the one an operator reaches by pressing Run to see why nothing moves):
1. The busy guard refuses (`_loop_agent_busy_reason` answers the hold, and `_agents_that_are_free`
   is empty after D6's free half). It records nothing (`scheduler.py:2544-2558`).
2. The newest `JobRun` is the refused firing's own, `in_progress` by D10. It is not `skipped`.
3. `_loop_work_is_all_in_flight` re-decides. If the refused briefing named a task (the usual case),
   that task has queued input, so D6 reports it in flight and the route answers *"already being
   worked … nothing is wrong"*. That is false: the provider is refusing the agent until 02:10. If
   the loop's queue held no task, the decision is not in flight, and the route answers **500
   "Failed to fire job"**, because an `in_progress` row has no `error_summary`.

Under R1's and R2's D6 the route is therefore wrong both ways. The second case is exactly **F127**
(*"pressing Run on a healthy loop whose agent is busy answers 500"*, open since 2026-08-29), made
reachable for the length of a hold instead of the length of a turn. F127's own write-up names the
honest fix: *"make the re-derivation ask the same question the firing asked"*.

**The rule** *(restructured in Round 4 — REV)*:
- **Did this firing write a row?** `run_job` reads the newest `JobRun` id for the job **before**
  `_fire_job_internal`, and again after. If they differ, the firing wrote a row, and the route
  answers from it exactly as today: 409 with a `skipped` row's reason, and otherwise today's
  branches. *(R3's rule re-asked the guard before the `skipped` check, so a firing that recorded a
  real `skipped` row, for example *"loop stop time reached"*, was answered with the busy reason if
  the agent became busy in between. Comparing ids asks which firing wrote the row, which is the
  question, and not when.)*
- **Only a new row is stamped.** `latest_run.requested_by_run_id = run_identity` (`:1283-1285`)
  today stamps whatever row is newest. When the firing wrote nothing, that is an earlier firing's
  row, and `run_identity` is `None` for an operator, so an agent's attribution is erased. Under D10,
  that earlier row is usually the held firing. So the stamp moves under the same *"the firing wrote
  a row"* condition. This is F369, which D10 makes reachable for the length of a hold, and which the
  change retires at archive.
- **Otherwise, for a job with a `Loop`,** the route asks `_loop_flow_busy_reason(session,
  project_id, job.agent)`. It is the first question `_do_fire_job` asks (`:2538-2558`), before any
  row is written. A refusal answers 409, naming the guard's reason and that no other agent is free,
  and saying nothing was started. For a running agent that is *"gamma is already running a turn"*.
  For a held one it is `hold_busy_reason`.
- When the route answers from `DECISION_IN_FLIGHT`, it reads who the in-flight tasks are staffed
  to through `task_attribution.staffing_from_decision` (the one sanctioned reader of
  `_cannot_staff`, `task_attribution.py:145-154`). If any of them is in `agents_held`, the detail
  names each held agent with `hold_busy_reason`, and drops both *"already being worked"* and
  *"nothing is wrong"*. A held agent's task is staffed and queued, not worked. *(Round 4 — REV:
  R3 dropped only the second phrase.)* Otherwise it is unchanged, which keeps F48's test
  (`test_board_agent_role.py:291-319`) passing as written. That test's guard passes because its
  author agent is free.

**Why this is in the change and not filed.** The hold half is this change's own regression, since D6
decides which branch of the route is reached. Restricting the rule to the hold would need a test for
*"is this reason the hold's"*, which is a second predicate for the one fact the guard already
answers. The running half comes free with the unrestricted rule, and it retires F127. **REV may
narrow it to the hold** if it judges F127 outside the build-day row. The narrowing is one condition,
and F127 then stays open.

**REV's verdict: keep it, and retire F127** *(Round 4)*.
- F127's own *shape of the fix* (`FINDINGS.md`, F127) is the rule D11 implements.
- The release roadmap already lists F127 as *decided, queued*.
- Narrowing needs a second predicate on the one guard's answer. The route would then answer 409
  for a held agent and 500 for a running one, which reads as two products.

The build-day row covers what LoopEngine showed, and a Run press on a held loop is that
observation's own surface.

A race remains, as it does for F48's re-derivation. If the agent's turn ends between the firing and
the re-ask, the guard passes and the route falls through to today's branches. That cannot produce a
false hold sentence, only today's answer.

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
  quietly (`:95`). Named so that nobody reads it as a hole in the hold. *(Round 4 — REV.)* The
  author's handover (`consider_handover_from_run_end`, `agent_trigger.py:2373`) is the same kind of
  spawn, about 19 s of CLI. It is reached for 2.6's shape, a `completed` run with a refusal reading,
  because nothing was returned. It self-declines for anything but a flow agent handing over with
  notes recorded. Checkpoint generation may spawn as well (unverified). None of these is a turn, so
  none meets the hold.
- It does not repair F368, the general form of D6's pile-up. *(Round 3.)* D6's resumption rule,
  `task.id in on_it`, is F368's repair restricted to held agents. Unrestricted, it would also stop
  a token-budget firing from recording `failed` every tick. Some operators read that record, so it
  is a behaviour change beyond this finding, and it stays F368's.
- It does not decide F128 (D6). During a hold, a loop in a project with a free agent is staffed
  with that agent, as it is today while its own agent is running a turn. *(Round 4 — REV.)* F128's
  substitution already reaches every documentless loop with two startable tasks, busy agent or not.
  D6 adds only the single-task case during a hold.

## Risks

- **The harness renames `status` or `resetsAt`.** Recognition then returns `None` and the Hub falls
  back to today's counted path. That is a degradation to known behaviour, not a new failure. The
  parser test pins the measured shape.
- **A hold that outlives the operator's patience.** A `seven_day` refusal holds autonomous input
  for days. The queue status says until when, and the operator can withdraw input or probe.
- **The re-arm at start reads every queued agent's latest `TurnUsage`.** That is one indexed query
  per queued agent (`ix_turn_usage_project_observed`, `models.py:1243`), run once per start.
- **The hold reads one clock, and tests patch it** *(Round 3)*. `provider_hold` and
  `agents_held` default `now` to `provider_allowance._utcnow()`, one module function. The
  scheduler, the status route and `run_job` never pass `now`, so a test that has to end a hold
  without waiting for it patches that function (tasks 1.2, 2.5, 3.1). A `now` default computed at
  each call site would give a test nothing to patch.
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

## Round 3 — re-derived again (2026-09-14, `f355-r3`)

R3 re-derived the change from the code R2's repairs touch, without starting from R2's reasoning.
It read `decide_firing` and every consumer of its answer, including the board, `task_attribution`,
`run_job` and the review arm. It also read every `JobRun` status reader, `_execute_run`'s end from
`:2277` to `:2460`, the Codex app-server end, every `schedule_agent` caller, and the shipped
`agent-flows` and `agent-loops` requirements that D6 lands on. Nothing was driven. Every claim is
read from code, with its line.

**The OPERATOR QUESTION check.** `next_action` asked whether R2's `_agents_that_are_free` repair is
really not F352-free's. **R3 agrees with R2, and there is still no OPERATOR QUESTION.** F352-free
asks which *holdings* make an agent unavailable, and its five options (`an-unstaffed-review-names-
its-holders/proposal.md:162-181`) differ only in that half. The running half's stated reason is
*"`schedule_agent` would refuse the second start"* (`scheduler.py:983-984`), and after D4 that is
equally true of a held agent. What R2 missed is that the rule is written into a shipped
requirement, so it has to be MODIFIED there (below). Editing a requirement's wording to carry a
reason its own design gave is not a new policy. R3 also checked F128, the one open operator call
that D6 reaches. D6 applies the existing running rule to one more reason, and leaves that call
exactly as open as it was.

**What R3 changed, in order of weight:**
1. **R2's D6 breached a shipped requirement.** Putting held agents into `running` made a held
   assignee's task read in flight on its assignment alone. `agent-loops` *A task reported as in
   flight is one an agent is actually working* forbids that (*"A name written in the task's
   assignee SHALL NOT by itself be sufficient"*). The running arm's agent-level reading is a
   commented exception for runs with no `task_id` (`scheduler.py:1285-1290`), and a held agent has
   no run for it to reach. Repair: a held assignee is in flight only while input naming the task is
   queued (`on_it`, already computed at `:1310`). Otherwise it is briefed once. The default branch
   and the free half still read the hold unconditionally. The `agent-flows` ADDED requirement was
   rewritten, with two scenarios where it had one; tasks 3.4b.
2. **Pressing Run went wrong both ways under D6** (new D11). The route either said *"already being
   worked … nothing is wrong"* while the provider was refusing the agent, or returned 500 *"Failed
   to fire job"*, which is F127 lasting as long as the hold. The route now re-asks the busy guard
   first, which is the question the firing asked first, and names held agents on its in-flight
   answer. That retires F127, and REV may narrow it to the hold. New `agent-loops` ADDED
   requirement; task 4.4.
3. **The ADDED `agent-flows` requirement contradicted a shipped one.** *A flow resolves a reviewer
   by declaration, then by availability* says the Hub *"SHALL select any agent that is not running a
   turn and holds no task"*, and R2 added *"SHALL NOT be selected as a reviewer by availability"*
   for an agent that satisfies it. That requirement is now MODIFIED, copied whole, with the hold in
   its availability sentence and two scenarios.
4. **Rung 3's sentence became false** once the free half read the hold (*"Every agent … is either
   running a turn, already holding active work, or …"*). It now names the hold whenever a
   non-excluded agent was passed over for one. That wording is conditional and adds under 50
   characters. Task 3.4d.
5. **Smaller:**
   - D5: the arm is conditioned on the reading being *recorded* (`if run:`, `:2298`). Its first
     neighbour after the commit is `evaluate_run_end`, reached only for 2.6's shape.
   - D4: every caller listed. An answered question is `operator`-origin, so it probes, and that is
     right.
   - D10: the other `JobRun` readers were read, and none is misled. D10 depends on D7 for
     `finalize`'s one-row-per-conversation invariant, so severing D7 needs a replacement.
   - The board renders a held agent's queued task as `held`, not as in flight like a running
     agent's.
6. **Test construction:**
   - 3.1's fourth test, and 2.5's served run, need the hold to end without waiting an hour.
     `_attempt_turn` passes no `now`, so R2's `now=None` parameter gave them nothing to hold. There
     is now one module clock, `provider_allowance._utcnow`, which tests patch.
   - 1.2b named no mutation. It now has one.
   - 3.4c's second test could not tell its mutation from the pass unless the held agents hold no
     task. Its fixture now says so.
   - 3.4b's first test needs the queued entry to *name* the task. Its new second test pins the
     single briefing.

**Checked and found sound:**
- 2.5, 2.6, 3.7 and 4.3 can be built as written, given the clock seam, and each fails under its
  mutation. For 4.3, the route's fallback reads `entry.waiting_reason` only when nothing above it
  answered (`api/v1/inbound_queue.py:177-183`), so a stored sentence does reach the answer once the
  hold has ended.
- The review wedge does stop by itself. `tasks_with_a_turn_pending_or_running` counts a `queued`
  entry by `task_id` and by `review_task_id` (`run_task_binding.py:295-309`), and a refused entry
  is requeued with both kept.
- `trigger_agent_directly` still has one caller, so every turn meets D4.

## Round 4 — REV (2026-09-14, `f355-rev`)

The operator's standing pre-approval step: one Opus subagent, asked to reject the change's
arguments rather than re-read them. It read the change, DIRECTION.md 2026-09-14, the decisions it
rests on (F96, F127, F128, loop D4, flow D12, F352-free), and the cited code. It edited nothing.
The window re-read each finding against the code before applying it. The one it did not verify
(the checkpoint spawn) is labelled so. Nothing was driven.

**Verdict: PROCEED**, once the fixes below are in the change files, which they now are. The
subagent tested every leg of the no-OPERATOR-QUESTION argument and found no choice that is the
operator's:
- **Hold vs drop** is F96's (`turn_scheduler.py:533-540`). A refusal that stops the agent running
  at all must not drop input, because nothing for that agent could run either way.
- **`_agents_that_are_free`**: only the running half moves. F352-free's options (a) to (e) differ
  only in the holdings half.
- **F128** stays exactly as open as it was. R3's premise that the hold extends its reach was false:
  the substitution already reaches any documentless loop with two startable tasks. D6 adds one case.
- **D7** is settled by the shipped docstring, plus the self-defeat argument the change never made.
  Calling it severable was both untrue and the move the F352-free precedent forbids.
- **D11** retires F127, which the roadmap already lists as *decided, queued*.

**What REV changed, in order of weight:**
1. **The MODIFIED `agent-loops` SHALL was false under the change's own code** (defect). It said a
   firing whose loop agent is held is refused. But `_loop_flow_busy_reason` (`scheduler.py:295-300`)
   lets it through whenever anyone is free, and the change's own `agent-flows` scenario then staffs
   the free agent. A flow is a loop (`agent-flows`), so the two deltas disagreed for every flow.
   That is the class of defect R3 fixed for the reviewer requirement. The shipped running sentence
   is now restored verbatim. The hold gets its own paragraph, conditioned on *no other agent in the
   project is free*, and a sentence leaves staffing to `agent-flows`. Proposal item 6 is corrected.
2. **The board said "no claimable task" for the whole hold** (defect). A single-agent loop, agent
   held, one pending task that no queued input names: `decide_firing` stalls at `:1464`, and
   `_batch_loop_summaries` shows *"no claimable task among 1 open (1 pending)"*. The firing never
   records it, since the guard refuses first. Repair: when the decision is stalled and the guard
   refuses, `stall_reason` is the guard's reason (D6, task 3.4e, a new `agent-loops` sentence and
   scenario). **The window narrowed REV's proposal.** REV said to ask the guard first for every
   loop, and that would have labelled every working single-agent loop `stalled` for each turn,
   because the UI buckets on `stall_reason` before `firing_active` (`loopCounts.ts:23`).
3. **D7 is not severable** (defect in the argument). The proposal, D7 and the D10 note are
   rewritten.
4. **D11 answered from the wrong row in a race, and stamped an earlier row** (defect).
   - Re-asking the guard before the `skipped` check could answer a real `skipped` row with the
     busy reason.
   - The route stamps `requested_by_run_id` onto whatever row is newest (`jobs.py:1283-1285`).
     Under D10 that is usually the held firing.

   Repair: compare the newest `JobRun` id before and after the firing, answer from a row only if
   the firing wrote it, and stamp only that row. The stamp is filed as **F369**, retired by this
   change. The in-flight answer with a held agent now also drops *"already being worked"*.
5. **Smaller, each read at its line:**
   - D6's resumption rule is now `on_it.get(task.id) == agent`, not `task.id in on_it`
     (`run_task_binding.py:302-309` maps a task to *any* agent);
   - D2's refusal needs a recorded reading (`if run:`), or an uncounted requeue with no hold
     loops;
   - a refusal whose `resetsAt` is not after the run's end is counted, so the shipped limits end
     it (new `agent-conversation-workspace` paragraph and scenario);
   - D3 uses the Python informative check, not SQLite's `json_type`;
   - the D10 invariant note is re-attributed: it is already false today, and D4 plus batching is
     what would amplify it;
   - the handover spawn is named beside the titler;
   - test 2.4's mutation named an outcome that cannot occur.

**Checked and found sound by REV:**
- All four MODIFIED requirements diff clean against the shipped text. The reviewer requirement
  (`openspec/specs/agent-flows/spec.md:231-342`) differs in exactly three hunks.
- The migration head is `0102` (`test_migrations.py:40`, `test_project_persistence.py:227`), and
  `0103` is unclaimed.
- No task edits `mcp_server.py` or the UI.
- `trigger_agent_directly` has one caller (`turn_scheduler.py:392`).
- The finalize → commit → `evaluate_run_end` order at `agent_trigger.py:2348-2365` matches D5.
- R3's *briefed once* trace holds: the brief carries `task_id` (`scheduler.py:2870-2874`), and a
  refused probe or wake requeues it with `task_id` kept.
