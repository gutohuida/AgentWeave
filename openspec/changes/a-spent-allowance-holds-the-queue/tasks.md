# Tasks — a spent allowance holds the queue

Finding: F355 (retired by this change at archive). R1 2026-09-14. R2 the same day; its additions
are marked **(Round 2)**: 1.2b, 2.5, 2.6, 3.4b, 3.4c, 3.7 and 4.3, with edits to 1.2, 2.2, 3.2,
3.3, 3.5 and 6.4. R3 the same day; its additions are marked **(Round 3)**: 3.4d and 4.4, with
edits to 1.2, 1.2b, 2.5, 3.1, 3.4b, 3.4c and 6.5.
Build day 2026-09-14. Day rules:
- no `hub/hub/mcp_server.py` (nothing here needs it);
- no UI and no bundle;
- **one migration, `0103`**, named on the review page.

Tests run under `py -3.11`. `black` needs `--target-version py311`.

Each test named below must **fail with its mutation applied** before it counts. Record the mutation
and the observed failure beside the task when ticking it.

The reading used in tests is the measured one (`design.md`, *Context*):

```json
{"status": "rejected", "resetsAt": <epoch>, "rateLimitType": "five_hour",
 "overageStatus": "rejected", "overageDisabledReason": "out_of_credits", "isUsingOverage": false,
 "unifiedWindows": {"five_hour": {"utilization": 1.02, "resetsAt": <epoch>}}}
```

## 1. Recognition and the derived hold (design D1, D3, D9)

- [ ] 1.1 New `hub/hub/provider_allowance.py`:
      - `AllowanceRefusal(resets_at, limit_type)`;
      - `allowance_refusal(allowance)`, per D1: `status == "rejected"` and a numeric, non-`bool`
        `resetsAt`, converted to an aware UTC `datetime`.

      Tests in `hub/tests/test_provider_allowance.py`:
      - the measured reading is recognised with `resets_at` 02:10 UTC for `1789351800`;
      - `allowed`, `allowed_warning`, a missing `resetsAt`, `resetsAt: true`, `None` and a
        non-dict all return `None`;
      - a reading with `overageStatus: "rejected"` and `status: "allowed"` returns `None`.

      Mutation: recognise on `overageStatus`. The last test fails.
- [ ] 1.2 `ProviderHold` and `provider_hold(db, project_id, agent, *, now=None)` per D3:
      - the newest *informative* `TurnUsage` row (its allowance is a JSON object, or its status is
        `measured`);
      - `hold_until = max(resets_at, observed_at + HOLD_FLOOR)`, with `HOLD_FLOOR` a module
        constant of 60 s;
      - `None` unless `now < hold_until`;
      - **(Round 3)** `now` defaults to `provider_allowance._utcnow()`, one module function, and
        never to a `datetime.now` written at a call site. `_attempt_turn`, the status route and
        `run_job` pass no `now`, so this function is the only thing a test can patch to end a hold
        (2.5, 3.1).

      Tests:
      - a refused row an hour ahead holds;
      - a later `measured` row with `allowed` releases;
      - a later `measured` row with **no** reading also releases;
      - a later `unavailable` row with no reading does **not** release (the pre-spawn and crash
        rows);
      - **(Round 2)** a refusal followed by 60 `unavailable` rows still holds. This fails a fixed
        window of 50;
      - a refused row whose `resetsAt` is 5 minutes past, observed 10 s ago, holds until
        `observed_at + 60 s`;
      - another agent's refusal does not hold this agent.

      Mutations:
      - the newest row of any kind (the fourth test fails);
      - read only the newest 50 rows (the fifth fails);
      - drop the floor (the sixth fails).
- [ ] 1.2b **(Round 2)** `agents_held(db, project_id, *, now=None) -> Set[str]`, the set-valued
      form of `provider_hold` at one `now` (design D6). Test: two agents refused and one served,
      read in one call, give exactly the two. Also test that it agrees with `provider_hold` agent
      by agent over the 1.2 fixtures.

      **(Round 3)** One of the two refused agents has a crash-reconciled `unavailable` row after
      its refusal. Mutation: read each agent's newest row of any kind. That agent drops out and the
      test fails.
- [ ] 1.3 The informative filter treats a JSON-`null` allowance as no reading. Test: write the
      row through `record_turn_usage(..., sample=None)` (the real writer, not a hand-built row)
      after a refusal, and assert that the hold survives. Then assert, in the same test, that the
      stored column is not SQL `NULL` (`select allowance is null` is false). That second assertion
      is what shows the test exercises the trap.

      Mutation: filter with `TurnUsage.allowance.is_not(None)`. The hold assertion fails.
- [ ] 1.4 `hold_sentence(agent, hold)`, `hold_busy_reason(agent, hold)` and
      `hold_coalesce_reason(agent, hold)`, worded as in D6, D7 and D9.
      - Test the lengths at a 32-character agent name and a `seven_day` type. Measured shapes: 285,
        86 and 161 characters. The coalesce reason must be at most 500
        (`JobRun.error_summary`, `models.py:1349`).
      - Test that each names the agent and the `HH:MM UTC` of `hold_until`.
      - Test that the limit word is omitted, not rendered `None`, when `limit_type` is absent.

## 2. The queue (design D2, D8)

- [ ] 2.1 `InboundQueueEntry.allowance_refusals`: integer, not null, default 0, with a server
      default. Migration `0103_allowance_refusals.py`, guarded for a missing table as `0033`/`0034`
      are. Bump the head assertions in `hub/tests/test_migrations.py` **and**
      `hub/tests/test_project_persistence.py`. Expose it on the queue entry response schema beside
      `delivery_attempts` (`api/v1/inbound_queue.py:40`).
- [ ] 2.2 `return_run_entries(db, run_id, *, refusal=None)` per D2. Tests in
      `hub/tests/test_delivery_attempts.py`:
      - with a refusal, the entry is `queued` and `delivery_attempts` is unchanged, while
        `allowance_refusals` is 1 and `waiting_reason` is `None` (Round 2: the status route
        derives the sentence; D2);
      - three consecutive refusals leave the conversation's `provider_session_id` set and the entry
        `queued`;
      - without a refusal, every existing test in the file still passes unchanged.

      Mutation: ignore `refusal`. The first two fail.
- [ ] 2.3 `format_turn_prompt` names attempt `delivery_attempts + allowance_refusals + 1`, and
      states the note when that sum is positive. Test: an entry with one refusal and no failed
      delivery carries *"delivery attempt 2"*.

      Mutation: read `delivery_attempts` alone. The test fails.
- [ ] 2.4 `_execute_run` computes the refusal from `accounting_sample` when
      `final_status == "failed"` and `binding_conflict is None`, and passes it. Test with the
      `_fake_pty` pattern (`hub/tests/test_agent_trigger.py:147`), scripted as the harness emits a
      refusal:
      - a `system` init line with a session id;
      - a `rate_limit_event` carrying the measured reading with `resetsAt` an hour ahead;
      - an `assistant` text line;
      - a `result` line with `is_error: true`, then exit code 1.

      Assert that the spawn mock was called **once** in total (no re-spawn within the hold), that
      the entry is `queued` with `delivery_attempts == 0` and `allowance_refusals == 1`, and that
      the conversation's `provider_session_id` is the init line's.

      Mutation: pass no refusal. The spawn count rises and the entry is withdrawn.

      The test runs with no `JobScheduler` (`get_scheduler()` is `None`). So it also shows that
      arming the wake with no scheduler neither raises nor stops the run's end (design D5).
- [ ] 2.5 **(Round 2, design D10)** The refused turn's own firing stays `in_progress`. Through the
      2.4 fixture, with the entry queued by `_do_fire_job` for a plain job:
      - after the refused run, the firing's `JobRun` reads `in_progress`, not `failed`;
      - after a served run delivers the same entry, it reads `completed`.

      **(Round 3)** Between the two runs, keep `resetsAt` an hour ahead so the refused run's end
      starts nothing, then patch `provider_allowance._utcnow` past `hold_until` and call
      `schedule_agent`. Script the fake pty with two turns, refused and then served.

      Mutation: keep the finalize call on a refusal. The first assertion fails, and so does the
      second, because the row already reads `failed` and the finalize selects only `in_progress`
      rows.
- [ ] 2.6 **(Round 2, design D5)** A run that ends `completed` with a `rejected` reading arms the
      wake and emits `queue_agent_held` with empty `entry_ids`. Script the 2.4 lines with exit
      code 0 and a `result` line that is not an error. Assert that its input is **not** returned
      (it completed), and that the wake-arming function was called with `hold_until`. Patch it to
      record its calls.

      Mutation: arm only when `final_status == "failed"`. The test fails.

## 3. The scheduler, the wake, loops and jobs (design D4–D7)

- [ ] 3.1 The hold check in `_attempt_turn`, placed per D4, returning `terminal_failure=False`.
      Tests in `hub/tests/test_turn_scheduler.py`:
      - an agent-origin entry queued during a hold starts no turn (the spawn mock is not called),
        and the result's `waiting_reason` is the hold sentence;
      - an operator entry arriving after the refusal starts exactly one turn, **even when it sits
        in a conversation behind an autonomous head**;
      - after that turn is refused, a further `schedule_agent` starts nothing;
      - after the hold's end, `schedule_agent` starts a turn. **(Round 3)** End it by patching
        `provider_allowance._utcnow` past `hold_until`, since `_attempt_turn` passes no `now`.

      Mutations:
      - key the probe on `selected` (the second test fails);
      - drop the `arrived_at > observed_at` condition (the third fails, because the probe
        re-fires).
- [ ] 3.2 `arm_allowance_wake(project_id, agent, when)` (D5), and make
      `run_reconciliation._schedule_or_defer` public as `schedule_or_defer`. Keep the old name as
      an alias only if a test imports it.

      Arm the wake in `_execute_run` **immediately after the finalize commit** (`:2354`), for any
      run whose recorded reading is a refusal, whatever its final status (design D5, Round 2).
      Emit `queue_agent_held` there too (4.2). With no scheduler, arming is a debug-logged no-op,
      and it never raises.

      Tests:
      - the job is added with id `allowance-wake:{project}:{agent}` and run date
        `max(hold_until, now + 1 s)`;
      - a second refusal replaces the job rather than adding one;
      - with `HOLD_FLOOR` monkeypatched to 1 s and `resetsAt` 2 s ahead, the wake fires and a turn
        starts with no other call (a real `JobScheduler`, not a mock, for this one).
        **Make the bound address known first** (`bound_address.observe`, or one request through
        the app) (Round 2). Otherwise `schedule_or_defer` defers the wake
        (`run_reconciliation.py:152-155`) and the test times out whether or not the wake was
        armed. So also assert that the scheduler holds the wake job before the date passes. The
        mutation must fail on that assertion, not on the timeout.

      Mutation: do not arm. The pre-date assertion fails.
- [ ] 3.3 A start-up re-arm, `arm_held_queues()`, called from `lifespan()` after
      `init_scheduler()`. It reads the newest **informative** row (D3), not the newest row
      (Round 2). Tests:
      - an agent with queued input and a future hold is armed;
      - one whose hold passed while the Hub was down reaches `schedule_or_defer`;
      - an agent with no queued input is not armed;
      - an agent whose refusal is followed by a crash-reconciled `unavailable` row is still armed.

      Mutation: read the newest row. The last test fails.
- [ ] 3.4 `_loop_agent_busy_reason` returns `hold_busy_reason` when held (D6). Tests in
      `hub/tests/test_scheduler.py`:
      - a loop's job firing while its agent is held creates no `JobRun` and no queue entry (the
        existing *records nothing* shape);
      - after the hold, the firing proceeds.

      Mutation: drop the hold branch. The first test fails.

      **The project in these tests has no other agent.** With a second free agent,
      `_loop_flow_busy_reason` lets the firing through. What stops it then is 3.4b, not this
      branch.
- [ ] 3.4b **(Round 2, rewritten in Round 3; design D6)** `decide_firing` reads
      `held_agents = agents_held(...)` once, beside `running`. The resumption arm records in
      flight for `agent in running or (agent in held_agents and task.id in on_it)`. The default
      branch requires `default_agent not in held_agents` as well as `not in running`. `running`
      itself is unchanged. Tests in `hub/tests/test_scheduler.py`, on a flow whose project has a
      **second, free** agent `other`. That agent is what lets the firing past the busy guard;
      without it the test cannot tell 3.4 from 3.4b.
      - `dev` is held, and holds an `assigned` task with a queued entry whose **`task_id` names
        it**. Three firings add **no** entry for `dev`, and the decision reports the task in
        flight;
      - **(Round 3)** `dev` is held and holds an `assigned` task with **no** queued entry naming it
        (its queued input is a peer message). Three firings add **exactly one** entry for `dev`,
        naming the task, on the first firing. The decision reports the task in flight on the second
        and third;
      - `dev` is the job's own agent and is held, and one unassigned task is startable. The
        firing staffs `other`, not `dev`.

      Mutations:
      - ignore `held_agents` in the resumption arm (R1's form). The first test gains three entries;
      - read `agent in held_agents` alone, without `on_it` (R2's form). The second test gains no
        entry, and it reports the task in flight on the first firing;
      - drop `held_agents` from the default branch. The third test staffs `dev`.
- [ ] 3.4c **(Round 2, design D6)** `_agents_that_are_free`'s running half reads
      `running | agents_held`. The holdings half is untouched. Tests:
      - a held agent holding no task is not in the free list;
      - with every agent held, **each holding no task** (Round 3: otherwise the holdings half
        already excludes them, and the mutation passes too), a flow's firing whose job agent is
        held is refused and records nothing (the `_loop_flow_busy_reason` path);
      - an existing free-list test, unchanged, still passes. This pins that the holdings half did
        not move.

      Mutation: leave the running half as it is. The first two tests fail.
- [ ] 3.4d **(Round 3, design D6)** Rung 3's reason names the hold. `resolve_reviewer` reads
      `agents_held` at rung 3 only. When a roster agent that is not excluded is held, the
      enumeration gains *"waiting for its provider's usage limit to reset"*. Tests:
      - a completed task with no declared reviewer, whose only non-author agent is held and holds
        nothing. The firing surfaces rung 3, and the reason names the provider's usage limit and
        does not read *"either running a turn, already holding active work, or"* without it;
      - with no agent held, rung 3's reason is byte-identical to today's;
      - the reason at a 64-character task id and 32-character agent names is at most 500
        characters.

      Mutation: leave rung 3's sentence as it is. The first test fails.

      Update the stopped change's D2 length budget in the same commit only if it is built first.
      Otherwise record in the review page that its rung-3 rewrite must carry this ground.
- [ ] 3.5 Plain-job coalescing in `_do_fire_job` (D7). Tests:
      - during a hold that came from a refusal on **another conversation**, the first firing
        queues;
      - three more firings queue nothing and leave one `skipped` `JobRun` whose `tick_count` is 3,
        with the coalesce reason as its `error_summary`. The first of the three writes the row with
        `tick_count` 1 (`models.py:1379`), because the newest row is still the first firing's
        `in_progress` one (`_stall_run_to_increment`, `scheduler.py:909-925`). The next two
        increment it;
      - **(Round 2)** the LoopEngine shape: the job's own firing is the refused turn. Its entry is
        requeued on its conversation, and its `JobRun` is `in_progress` (D10). So the **very next**
        firing coalesces and queues nothing;
      - with no hold, four firings queue four entries, which is today's behaviour, pinned.

      Mutation: drop the coalesce branch. The second and third tests fail.
- [ ] 3.6 A job firing whose `schedule_agent` meets the hold leaves its `JobRun` `in_progress`.
      Test through `_do_fire_job` with a held agent.

      Mutation: return the hold with the default `terminal_failure`. The `JobRun` reads `failed`
      and the test fails.
- [ ] 3.7 **(Round 2, design D10)** `reconcile_stale_job_runs` leaves a held firing `in_progress`.
      Tests in `hub/tests/test_run_reconciliation.py` (or wherever the existing A4.5 tests are):
      - an `in_progress` `JobRun` whose conversation has a queued entry, for an agent whose newest
        informative row is a refusal with the reset ahead, stays `in_progress`;
      - the same with the reset already past stays `in_progress`. D5's start-up re-arm delivers
        it;
      - an `in_progress` `JobRun` queued for an agent with **no runner bound** and no refusal
        still reads `failed`. That is the docstring's decided case, pinned unchanged.

      Mutation: drop the refusal exemption. The first two fail.

## 4. Visibility (design D9)

- [ ] 4.1 The queue status route names the hold after the running and hop-budget checks and
      before the token budget, unless a queued operator entry would probe. Tests in
      `hub/tests/test_inbound_queue.py`:
      - an entry queued during a hold with no `waiting_reason` of its own reports the hold
        sentence;
      - with a newer operator entry queued, the route does not report the hold.
- [ ] 4.2 `queue_agent_held` is persisted at `warn` and broadcast at the end of every run whose
      reading is a refusal, with `agent`, `run_id`, `hold_until`, `resets_at`, `limit_type` and
      `entry_ids`. Test the persisted row through the 2.4 fixture (and through 2.6's, with empty
      `entry_ids`).
- [ ] 4.3 **(Round 2)** Once the hold has ended, the status route reports no hold sentence, even
      for an entry the refusal returned. Test: an entry returned by `return_run_entries(...,
      refusal=...)`, left `queued`, with the agent not running and `now` past `hold_until`. The
      route's `waiting_reason` is not the hold sentence.

      Mutation: store the hold sentence on the returned entries (R1's D2). The route's
      `waiting_reason` fallback (`api/v1/inbound_queue.py:183`) then reports the ended hold, and
      the test fails.

- [ ] 4.4 **(Round 3, design D11; retires F127)** `run_job` asks `_loop_flow_busy_reason`
      first for a loop job, before the `skipped` check. A refusal answers 409 with the guard's
      reason, that no other agent is free, and that nothing was started. On
      `DECISION_IN_FLIGHT`, the answer names each held agent among the in-flight tasks' staffing,
      read through `task_attribution.staffing_from_decision`, and drops *"nothing is wrong"*.
      Tests in `hub/tests/test_board_agent_role.py`, beside F48's:
      - a single-agent loop whose agent is running a turn on no loop task, with a pending task.
        `POST …/run` answers 409 naming the agent, not 500 *"Failed to fire job"*. This is F127's
        own reproduction (`t_run_while_busy2.py`'s shape);
      - the same loop with its agent held, its refused firing's `JobRun` `in_progress` (D10) and
        its briefing queued. 409 names the hold's `HH:MM UTC`, and does not contain *"already being
        worked"* or *"nothing is wrong"*;
      - a two-agent flow, job agent free with nothing startable, and the in-flight task staffed to
        a held agent with its briefing queued. 409 names that agent's hold, and does not contain
        *"nothing is wrong"*;
      - F48's test (`:291-319`), unchanged, still passes.

      Mutations:
      - drop the busy-guard re-ask. The first test reads 500, and the second reads *"already being
        worked"*;
      - drop the held clause on the in-flight answer. The third test reads *"nothing is wrong"*.

      A source-scanning test already pins `task_attribution` as the only reader of
      `_cannot_staff`, and the new route code must not read it directly.

## 5. The gate

- [ ] 5.1 `py -3.11 -m pytest hub/tests/ -q`, then the full `tests/`. Both green, with the counts
      recorded.
- [ ] 5.2 The CI lint set: `ruff check src/ hub/ tests/`,
      `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`, `mypy src/`.
- [ ] 5.3 `openspec validate --strict a-spent-allowance-holds-the-queue`.

## 6. Drive (night-window.md *Driving*)

The provider's real allowance cannot be spent on demand, so the refusal comes from a stub. Say so
in the log and on the review page.

- [ ] 6.1 Put a `claude.cmd` stub in a directory **first** on the drive Hub's `PATH`, and have it
      log its argv. While a flag file exists, it prints the four scripted lines from 2.4 and exits
      1:
      - `resetsAt` is two minutes ahead;
      - the init line's session id **echoes the `--resume` argument**. A different id is a binding
        conflict (`agent_trigger.py:2164-2171`), and an invented one could not be resumed by the
        real CLI after the reset.

      Otherwise it execs the real `claude` with its arguments. Start a drive Hub from source on a
      free port with a fresh `profiles/drive0914/` database, as night-window.md says, and bind
      every agent to Haiku.
- [ ] 6.1b With the flag absent, give the agent one real Haiku turn, so that its conversation has
      a real provider session. Every refusal below is on that conversation.
- [ ] 6.2 With the flag present, send an operator message on that conversation. That is the
      refused turn; no hold exists yet, so it is not a probe. Then, while held, have a peer message
      and a plain job's firing reach the agent. They queue on conversations of their own, and
      neither may spawn. Observe:
      - exactly one refused run;
      - the entries `queued` with `allowance_refusals == 1` and `delivery_attempts == 0`;
      - `GET …/queue/{agent}/status` naming the hold and its time;
      - a `queue_agent_held` event.
- [ ] 6.3 Remove the flag before the reset. Observe that at the reset one real Haiku turn starts
      without any request, resumes the **same** provider session, and carries *"delivery attempt
      2"*.
- [ ] 6.4 Re-raise the flag and send an operator message. That one is a fresh refusal, not a
      probe: 6.3 ended the hold (Round 2 found R1's version of this step could not observe a
      probe). Then send a **second** operator message while held. Observe:
      - exactly one probe spawn, refused;
      - no further spawn until the new reset;
      - the queue status naming the renewed hold's time.
- [ ] 6.5 A loop with a `*/1` cron on a held agent: no `JobRun` and no entry while held. Record
      whether the drive project had a second, free agent. With one, the firing passes the busy
      guard and it is 3.4b's rule that holds: the held agent's assigned task reads in flight, and
      nothing is queued for it. Without one, the busy guard refuses it (3.4).
      **(Round 3)** Press Run on that loop while held. Record the status code and the detail. It
      must be a 409 naming the hold's time, not *"already being worked"* and not a 500 (4.4).
- [ ] 6.6 Leave no job enabled. Record the drive's evidence in `scripts/drive/FINDINGS.md` under
      F355.

## 7. Archive

- [ ] 7.1 `openspec-sync-specs`, then archive. Retire F355 in `FINDINGS.md` with `fixed <sha>`, in
      the archive commit. **(Round 3)** Retire F127 the same way, unless REV narrowed D11 to the
      hold. In that case add a dated note to F127 saying the hold half is fixed and the running
      half is not. Add a dated note to F128 saying a hold now reaches its substitution (design D6).
