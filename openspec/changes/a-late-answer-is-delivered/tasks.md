# Tasks — a late answer is delivered

Finding: F356, retired by this change at archive. R1 2026-09-14.

Day rules (2026-09-14):
- no `hub/hub/mcp_server.py` edit (F354). None is needed: the tool's report already lists exactly
  what it did not receive.
- no migration.
- no UI code and no bundle.

Tests run under `py -3.11`. `black` needs `--target-version py311`.

Each test named below must **fail with its mutation applied** before it counts. Record the mutation
and the observed failure beside the task when ticking it.

## 1. One predicate for "still waiting" (design D1, D2)

- [ ] 1.1 In `hub/hub/api/v1/questions.py`, add `_asker_still_waiting(session, question)`: blocking,
      and `wait_ended_at IS NULL`, and not `_asking_run_has_ended`. Check `wait_ended_at` before
      the run lookup. Its docstring names both arms and why `wait_expires_at` is not the test
      (the tool polls past the Hub's deadline).
- [ ] 1.2 `answer_question` and `decline_question` call it **after** their commit and refresh
      (D4), replacing the expression at `:346` and `:453`.
      Test: a blocking question whose run is `running` and whose `wait_ended_at` is set is
      answered → one queue entry, one `queue_entry_queued` event, and `schedule_agent` is called.
      **Mutation:** drop the `wait_ended_at` arm → no entry.
- [ ] 1.3 The shortcut still holds. Test: a blocking question, run `running`, `wait_expires_at`
      **passed**, `wait_ended_at` NULL, answered → no entry. This is the tool's grace window.
      **Mutation:** use `wait_has_expired` in place of `wait_ended_at` → an entry appears.
- [ ] 1.4 A decline completing a batch whose wait ended while its run lives delivers the batch's
      answers. **Mutation:** leave `decline_question` on the old expression.
- [ ] 1.5 `_with_asker_state` and `_with_asker_state_one` both give `asker_waiting = False` for a
      row with `wait_ended_at` set and a live run. Extend
      `hub/tests/test_asker_waiting_is_the_same_on_every_route.py` with that row, on both the list
      route and the detail route. **Mutation:** add the arm to only one of the two → the agreement
      test fails.

## 2. The expiry report delivers what the tool never received (design D3, D4)

- [ ] 2.1 In `report_wait_ended` (`agent_actions.py:642`), a question asked by the calling run that
      is **answered** with `wait_ended_at` NULL gets `wait_ended_at = now`. It is counted as
      accepted, and no release function is called. There is no `wait_has_expired` check on this
      branch. A **declined** one is accepted with no write (D3: the invariant at
      `models.py:1003-1007`). Update the docstring's list of refusals: *"already answered or
      declined"* is no longer a refusal, and the docstring says why.
      **Mutation:** also set `wait_ended_at` on the declined one → 2.7's
      `proceeded_without_answer_reason` assertion fails.
      **(Round 3)** Implement this as design D4 *One decision point*: after the ownership checks,
      the only load-time branch left is "unanswered and not `wait_has_expired` → refuse". Everything
      else goes through 2.8's guarded `UPDATE`, and `rowcount` decides. The *already recorded*
      (`:683`) and *declined* branches stop being separate code. The mutation above cannot be
      applied through a `WHERE … declined IS FALSE`. Its applicable form is: **drop the
      `declined IS FALSE` arm** → 2.7 fails.
- [ ] 2.2 After the loop, deliver once per batch key, through `_deliver_batch_if_complete`. The
      keys are the ones 2.9 collects (Round 2), not those read at load time. Announce and wake through the helper that 2.4
      extracts. Test: a batch of 4, 2 answered in time, 2 reported expired **after** being
      answered, all in one report → exactly one entry carrying all four, in ask order. Assert the
      event and the wake. **Mutations:** (a) deliver per question → two entries; (b) keep the old
      `continue` → no entry.
- [ ] 2.3 **The identity-map trap (D4).** Test: within one report request, a sibling of the batch is
      answered, and committed through a second session, after the route loaded it. Drive this with
      a hook on the release, or by answering between the load and the delivery. The batch must be
      judged against committed state and delivered. **Mutation:** remove `populate_existing` or the
      refresh → no entry.
- [ ] 2.4 Extract the post-delivery tail (`queue_entry_queued` persist and broadcast, then
      `schedule_agent`) from `answer_question` (`:377-399`) and `decline_question` (`:488-504`)
      into one helper in `questions.py`. All three routes call it. The existing tests in
      `test_question_batch_delivery.py`, `test_question_declined.py` and
      `test_blocking_questions.py` stay green unchanged.
- [ ] 2.5 An entry queued for an agent with a live run waits behind that run and does not start a
      second concurrent run. R1 read it at `turn_scheduler.py:327-334`, with the re-drain at run
      end at `agent_trigger.py:2514`. Test: 1.2's fixture with the asking run still `running` → no
      new `Run` row, and `schedule_agent` answers *"agent is already running"*. If this fails,
      **stop and record a finding**. Do not patch the scheduler inside this change.
- [ ] 2.6 A second report of the same ids is accepted and delivers nothing more. **Mutation:**
      skip the `wait_ended_at` write on the resolved branch → a second entry.
      **(Round 3)** That mutation is stale under 2.9. Skipping the write means the first report
      stamps nothing, keys nothing, and delivers nothing, so 2.2 fails and 2.6 sees no second entry.
      The applicable mutation is: **drop the `wait_ended_at IS NULL` arm** of 2.8's `WHERE` → the
      second report's `rowcount` is 1, it re-keys, and a second entry appears. 2.9's mutation (c)
      stays as a separate check.
- [ ] 2.7 A lone question declined after the tool's last poll, then reported: accepted, no entry,
      `wait_ended_at` still NULL, and the bound task's `proceeded_without_answer_reason` still
      null.
- [ ] 2.8 **(Round 2) The stamp is a guarded `UPDATE`** (design D4, *The invariant D3 leans on*).
      Both branches of `report_wait_ended` write `wait_ended_at` with
      `UPDATE question SET wait_ended_at = :now WHERE id = :id AND wait_ended_at IS NULL AND
      declined IS FALSE`, in place of the ORM attribute write, and read `rowcount`.
      `release_block_for_expired_wait` runs only on the expired branch, and only when `rowcount` is
      1. A `rowcount` of 0 is accepted, with no key and no release.
      Test: the report loads Q unresolved, then a decline is committed through a second session
      before the report writes (a hook on `wait_has_expired`, or a patched `session.get` that
      commits the decline after returning the row) → Q's `wait_ended_at` still NULL, and the bound
      task's `proceeded_without_answer_reason` null. **Mutation:** restore the ORM write →
      `wait_ended_at` set on a declined row.
      **(Round 3)** The statement lives in one helper,
      `record_wait_ended(session, question_id, now) -> bool`, in `run_task_binding.py` beside
      `wait_has_expired`. 2.10 is its second caller. It carries
      `.execution_options(synchronize_session=False)`, as `inbound_queue.py:350` and
      `turn_scheduler.py:627` do. Measured in design D4 *Measured*: with the default sync, a
      `rowcount` of 0 still sets `wait_ended_at` on the loaded object. No route test can see that
      today, so it is a code rule stated in the helper's docstring, not a mutation.
- [ ] 2.9 **(Round 2) Keys come from committed state, after the report's own commit** (design D4,
      *The report half*). After the loop, re-read every row whose `rowcount` was 1, with
      `populate_existing`, and take a batch key from each that is `answered`. This replaces 2.2's
      key collection from the load-time answered branch. Test: the report loads Q unanswered, then
      an answer is committed through a second session before the report writes, using the same hook
      as 2.8. Drive the answer through the real `answer_question`, so its own predicate reads
      `wait_ended_at` NULL and queues nothing → after the report, exactly one entry carrying Q's
      answer. **Mutations:** (a) key from the load-time branch, which is round 1's design → no
      entry; (b) re-read without `populate_existing` → no entry; (c) key rows accepted through the
      *already recorded* branch too → 2.6 gets a second entry.
      **(Round 3)** Under *One decision point* the "already recorded branch" in (c) is a
      `rowcount` of 0. Mutation (c) reads: key every accepted row, not only those whose `rowcount`
      was 1. Mutation (b) was observed in design D4 *Measured*: a plain re-read returned
      `answered = False` for rows answered in a second session.
- [ ] 2.10 **(Round 3) The run-end sweep uses the same guarded write** (design D4, *The sweep is the
      second writer*). In `evaluate_run_end` (`run_divergence.py:730-733`), replace
      `question.wait_ended_at = question.wait_ended_at or now` with `record_wait_ended`, and call
      `release_block_for_expired_wait` only when it returns True. Test: a bound run has ended,
      holding an unanswered blocking question whose wait has expired. A decline is committed through
      a second session after `unanswered_blocking_question` has loaded the row (patch it to commit
      the decline before returning) → the question's `wait_ended_at` stays NULL, and the task's
      `proceeded_without_answer_reason` is null. **Mutation:** restore the attribute write →
      `wait_ended_at` set on a declined row. The existing sweep tests
      (`grep -rl wait_ended_at hub/tests/`) stay green unchanged.

## 3. Races (design D4)

- [ ] 3.1 Test both orders on committed state: answer-then-report, and report-then-answer. Each
      ends with exactly one entry.
- [ ] 3.2 Interleaved: the answer route decides its predicate from a fresh read while the report
      has already committed `wait_ended_at` → an entry. Pin this by asserting the predicate is
      evaluated after `session.refresh`. **Mutation:** move 1.2's call back before the commit, and
      use a row loaded before the report committed → no entry.

## 4. Gate

- [ ] 4.1 `py -3.11 -m pytest hub/tests/ -q` whole and green. Record the counts.
- [ ] 4.2 The CI lint set: `ruff check src/ hub/ tests/`,
      `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`, and `mypy src/`.
- [ ] 4.3 `openspec validate a-late-answer-is-delivered --strict`.

## 5. Drive (night-window.md; a drive Hub on a free port with a fresh profile, Haiku)

- [ ] 5.1 Start a drive Hub from source on a free port in 8011–8019. Use a fresh
      `profiles/drive<date>/` profile, and set the agent's `question_timeout_seconds` to the
      smallest the setting allows. Use one Haiku runner and one agent.
- [ ] 5.2 Ask the agent to call `ask_user` with two questions, then after it returns run a shell
      `sleep` long enough to outlive the wait by a minute. Do not answer in time. Observe
      `wait_ended_at` set on both, and the run still `running`. Then check that the
      `GET /questions` list and the detail route both read `asker_waiting: false`.
- [ ] 5.3 Answer both while the run lives. Observe one `inbound_queue_entries` row carrying both
      answers. After the run ends, observe one new turn whose prompt carries both, and nothing
      else queued.
- [ ] 5.4 Control: answer a fresh question **inside** the wait. The tool returns it, and no entry
      is queued.
- [ ] 5.5 Only if the grace window can be hit by hand within the poll interval: answer 1–2 s after
      `wait_expires_at`. Record whether the tool returned it and whether an entry appeared. If it
      cannot be hit, say so. Do not claim it.
- [ ] 5.6 The 2.2 window (an answer after the tool's last poll and before its report, about a
      second) is not reliably hittable live. It is covered by 2.2 and 2.3. The drive report says
      so, rather than implying the drive exercised it.
- [ ] 5.7 Stop the drive Hub. Leave no run `running`.

## 6. Archive

- [ ] 6.1 Archive and sync `run-task-binding`. Retire F356 as `fixed <sha>` in
      `scripts/drive/FINDINGS.md`.
- [ ] 6.2 Record D5's residual (report lost, answer inside the run's remaining life) as an open
      note on F356's retirement line, so that it is not mistaken for closed.
