# Tasks — a spent allowance holds the queue

Finding: F355 (retired by this change at archive). R1 2026-09-14.
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
      - `None` unless `now < hold_until`.

      Tests:
      - a refused row an hour ahead holds;
      - a later `measured` row with `allowed` releases;
      - a later `measured` row with **no** reading also releases;
      - a later `unavailable` row with no reading does **not** release (the pre-spawn and crash
        rows);
      - a refused row whose `resetsAt` is 5 minutes past, observed 10 s ago, holds until
        `observed_at + 60 s`;
      - another agent's refusal does not hold this agent.

      Mutations:
      - the newest row of any kind (the fourth test fails);
      - drop the floor (the fifth fails).
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
        `allowance_refusals` is 1 and `waiting_reason` is the hold sentence;
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

## 3. The scheduler, the wake, loops and jobs (design D4–D7)

- [ ] 3.1 The hold check in `_attempt_turn`, placed per D4, returning `terminal_failure=False`.
      Tests in `hub/tests/test_turn_scheduler.py`:
      - an agent-origin entry queued during a hold starts no turn (the spawn mock is not called),
        and the result's `waiting_reason` is the hold sentence;
      - an operator entry arriving after the refusal starts exactly one turn, **even when it sits
        in a conversation behind an autonomous head**;
      - after that turn is refused, a further `schedule_agent` starts nothing;
      - after the hold's end (`now` past `hold_until`), `schedule_agent` starts a turn.

      Mutations:
      - key the probe on `selected` (the second test fails);
      - drop the `arrived_at > observed_at` condition (the third fails, because the probe
        re-fires).
- [ ] 3.2 `arm_allowance_wake(project_id, agent, when)` (D5), and make
      `run_reconciliation._schedule_or_defer` public as `schedule_or_defer`. Keep the old name as
      an alias only if a test imports it.

      Arm the wake in `_execute_run` after the finalize commit, when a refusal was recognised.
      Emit `queue_agent_held` there too (4.2).

      Tests:
      - the job is added with id `allowance-wake:{project}:{agent}` and run date
        `max(hold_until, now + 1 s)`;
      - a second refusal replaces the job rather than adding one;
      - with `HOLD_FLOOR` monkeypatched to 1 s and `resetsAt` 2 s ahead, the wake fires and a turn
        starts with no other call (a real `JobScheduler`, not a mock, for this one).

      Mutation: do not arm. The last test times out.
- [ ] 3.3 A start-up re-arm, `arm_held_queues()`, called from `lifespan()` after
      `init_scheduler()`. Tests:
      - an agent with queued input and a future hold is armed;
      - one whose hold passed while the Hub was down reaches `schedule_or_defer`;
      - an agent with no queued input is not armed.
- [ ] 3.4 `_loop_agent_busy_reason` returns `hold_busy_reason` when held (D6). Tests in
      `hub/tests/test_scheduler.py`:
      - a loop's job firing while its agent is held creates no `JobRun` and no queue entry (the
        existing *records nothing* shape);
      - after the hold, the firing proceeds.

      Mutation: drop the hold branch. The first test fails.
- [ ] 3.5 Plain-job coalescing in `_do_fire_job` (D7). Tests:
      - during a hold, the first firing queues;
      - three more firings queue nothing and leave one `skipped` `JobRun` whose `tick_count` is 3,
        with the coalesce reason as its `error_summary`;
      - with no hold, four firings queue four entries, which is today's behaviour, pinned.

      Mutation: drop the coalesce branch. The second test fails.
- [ ] 3.6 A job firing whose `schedule_agent` meets the hold leaves its `JobRun` `in_progress`.
      Test through `_do_fire_job` with a held agent.

      Mutation: return the hold with the default `terminal_failure`. The `JobRun` reads `failed`
      and the test fails.

## 4. Visibility (design D9)

- [ ] 4.1 The queue status route names the hold after the running and hop-budget checks and
      before the token budget, unless a queued operator entry would probe. Tests in
      `hub/tests/test_inbound_queue.py`:
      - an entry queued during a hold with no `waiting_reason` of its own reports the hold
        sentence;
      - with a newer operator entry queued, the route does not report the hold.
- [ ] 4.2 `queue_agent_held` is persisted at `warn` and broadcast at each refused run's end, with
      `agent`, `run_id`, `hold_until`, `resets_at`, `limit_type` and `entry_ids`. Test the
      persisted row through the 2.4 fixture.

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
- [ ] 6.4 Re-raise the flag and send an operator message. Observe one probe, refused, and no
      second spawn until the new reset.
- [ ] 6.5 A loop with a `*/1` cron on a held agent: no `JobRun` and no entry while held.
- [ ] 6.6 Leave no job enabled. Record the drive's evidence in `scripts/drive/FINDINGS.md` under
      F355.

## 7. Archive

- [ ] 7.1 `openspec-sync-specs`, then archive. Retire F355 in `FINDINGS.md` with `fixed <sha>`, in
      the archive commit.
