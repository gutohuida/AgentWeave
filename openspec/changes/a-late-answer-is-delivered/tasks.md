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

- [x] 1.1 In `hub/hub/api/v1/questions.py`, add `_asker_still_waiting(session, question)`: blocking,
      and `wait_ended_at IS NULL`, and not `_asking_run_has_ended`. Check `wait_ended_at` before
      the run lookup. Its docstring names both arms and why `wait_expires_at` is not the test
      (the tool polls past the Hub's deadline).
      *Done, iteration 7:* `questions.py::_asker_still_waiting`, `wait_ended_at` checked before the run lookup; docstring names both arms and why not `wait_expires_at`. Tested through 1.2/1.3.
- [x] 1.2 `answer_question` and `decline_question` call it **after** their commit and refresh
      (D4), replacing the expression at `:346` and `:453`.
      Test: a blocking question whose run is `running` and whose `wait_ended_at` is set is
      answered → one queue entry, one `queue_entry_queued` event, and `schedule_agent` is called.
      **Mutation:** drop the `wait_ended_at` arm → no entry.
      *Done, iteration 7:* both routes call it after `commit` + `refresh`. `test_a_late_answer_is_delivered.py::test_an_answer_after_the_wait_ended_is_queued_while_the_run_lives` (entry, `queue_entry_queued` naming it, one wake, body `asker_waiting: false`). Mutation (drop the `wait_ended_at` arm) -> fails, `ValueError: not enough values to unpack (expected 1, got 0)` (no entry).
- [x] 1.3 The shortcut still holds. Test: a blocking question, run `running`, `wait_expires_at`
      **passed**, `wait_ended_at` NULL, answered → no entry. This is the tool's grace window.
      **Mutation:** use `wait_has_expired` in place of `wait_ended_at` → an entry appears.
      *Done, iteration 7:* `test_a_late_answer_is_delivered.py::test_an_answer_in_the_tools_grace_window_is_not_duplicated`. Mutation (`not wait_has_expired(question)` in place of the arm) -> fails, `assert [<InboundQueueEntry>] == []`.
- [x] 1.4 A decline completing a batch whose wait ended while its run lives delivers the batch's
      answers. **Mutation:** leave `decline_question` on the old expression.
      *Done, iteration 7:* `test_a_late_answer_is_delivered.py::test_a_decline_that_completes_a_batch_after_the_wait_ended_delivers_its_answers`. Mutation (decline on the old `blocking and not _asking_run_has_ended` expression) -> fails, no entry.
- [x] 1.5 `_with_asker_state` and `_with_asker_state_one` both give `asker_waiting = False` for a
      row with `wait_ended_at` set and a live run. Extend
      `hub/tests/test_asker_waiting_is_the_same_on_every_route.py` with that row, on both the list
      route and the detail route. **Mutation:** add the arm to only one of the two → the agreement
      test fails.
      *Done, iteration 7:* `test_asker_waiting_is_the_same_on_every_route.py::test_the_list_and_the_detail_route_agree_once_the_wait_has_ended` (an ended-wait row and an open-wait control on one live run, both routes). Mutations (arm dropped from the bulk only; from the detail only) -> each fails the dict equality.
- [x] 1.6 **(Round 4 — REV, F-C) Correct two comments that state a false invariant.**
      `models.py:1003-1007` and `tasks.py:447-449` say a declined question never carries
      `wait_ended_at`. Shipped code breaks that without any race: the report stamps Q, then the
      operator declines Q, and `decline_question` (`questions.py:444-446`) never reads
      `wait_ended_at`. Reword both to *"not stamped on a question declined **before** its wait was
      recorded as ended; a decline after the record leaves it, and the task then reads 'Proceeded
      without your answer', which is true: the run did proceed without it."* Comments only, no
      behaviour change. No test.
      *Done, iteration 7:* both comments reworded as specified (models.py adds that an answer after the last poll is also stamped, D3). Comments only. The report's own docstring was checked for the same claim and corrected too.

## 2. The expiry report delivers what the tool never received (design D3, D4)

- [x] 2.1 In `report_wait_ended` (`agent_actions.py:642`), a question asked by the calling run that
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
      *Done, iteration 7:* one load-time refusal (unanswered and not expired), everything else through `record_wait_ended`; docstring rewritten. `test_a_late_answer_is_delivered.py::test_a_question_declined_before_the_report_is_accepted_and_not_called_an_absence` (2.7). Mutation (drop `declined IS FALSE`) -> fails, `wait_ended_at` is a datetime. **Also, not in the task text:** a question with no `wait_expires_at` is refused on every branch. Without it the answered branch (which skips `wait_has_expired`) would stamp and re-deliver a non-blocking note a report named. `test_a_late_answer_is_delivered.py::test_a_question_nobody_waited_on_cannot_be_reported_even_once_answered`; mutation (drop the check) -> fails, accepted `['q-…']`. **Sweep:** three tests in `test_a_task_waits_while_its_run_waits.py` encoded the old skip, and each failed on the new code. They were inverted in place with a docstring saying so: `test_an_answered_question_never_expired` became `…_the_tool_never_received_is_recorded_as_gone_ahead_without` (accepted, stamped); `test_a_declined_question_never_expired` is now accepted, still unstamped; and `test_a_batch_reports_only_the_waits_that_expired` was re-staged so its per-question refusal is an unexpired question. No other existing test changed.
- [x] 2.2 After the loop, deliver once per batch key, through `_deliver_batch_if_complete`. The
      keys are the ones 2.9 collects (Round 2), not those read at load time. Announce and wake through the helper that 2.4
      extracts. Test: a batch of 4, 2 answered in time, 2 reported expired **after** being
      answered, all in one report → exactly one entry carrying all four, in ask order. Assert the
      event and the wake. **Mutations:** (a) deliver per question → two entries; (b) keep the old
      `continue` → no entry.
      *Done, iteration 7:* `_deliver_what_the_report_found_answered`. `test_a_late_answer_is_delivered.py::test_late_answers_reported_together_are_delivered_once_with_the_whole_batch`. Mutations: (a) key per question -> fails, `too many values to unpack` (two entries); (b) the old `continue` -> fails, `accepted [] == [q3, q4]`; (c) delivery without `announce_queued_answer` -> fails, no event.
- [x] 2.3 **The identity-map trap (D4).** Test: within one report request, a sibling of the batch is
      answered, and committed through a second session, after the route loaded it. Drive this with
      a hook on the release, or by answering between the load and the delivery. The batch must be
      judged against committed state and delivered. **Mutation:** remove `populate_existing` or the
      refresh → no entry.
      **(Round 4 — REV)** Re-aimed. As written, the sibling is answered by a raw second-session write,
      a state the product never produces: the real `answer_question` would see the report's
      committed stamp and deliver by itself. Test instead the interleave that loses an answer
      (design, *Round 4*, F-A). In a batch of Q1 and Q2, Q1 is answered after the tool's last poll.
      The report stamps Q1 (`rowcount` 1). Then Q2 is declined through the **real**
      `decline_question`, in a second session, after the report loaded Q2 and before its guarded
      `UPDATE` on Q2 (`rowcount` 0) → exactly one entry carrying Q1's answer. **Mutation:** drop
      `populate_existing` from `_completed_batch` (2.11) → no entry, because the decline route also
      reads `wait_ended_at` NULL and declines to deliver.
      *Done, iteration 7:* as re-aimed. `test_a_late_answer_is_delivered.py::test_a_sibling_declined_mid_report_does_not_strand_the_batchs_answer`. The decline goes through the real route inside the report, via a patched `AsyncSession.get` that fires right after the report loads Q2. Mutation (drop `populate_existing` from `_completed_batch`) -> fails, no entry.
- [x] 2.4 Extract the post-delivery tail (`queue_entry_queued` persist and broadcast, then
      `schedule_agent`) from `answer_question` (`:377-399`) and `decline_question` (`:488-504`)
      into one helper in `questions.py`. All three routes call it. The existing tests in
      `test_question_batch_delivery.py`, `test_question_declined.py` and
      `test_blocking_questions.py` stay green unchanged.
      *Done, iteration 7:* `questions.announce_queued_answer(session, project_id, question, entry, conversation)`, called by the answer, the decline and the report. `_deliver_batch_if_complete` became public `deliver_batch_if_complete` (it has a caller in `agent_actions` now). One ordering change: the answer route's persisted `question_answered` event now precedes `queue_entry_queued` (grep: no test reads that order). `test_question_batch_delivery.py`, `test_question_declined.py` and `test_blocking_questions.py` pass unchanged.
- [x] 2.5 An entry queued for an agent with a live run waits behind that run and does not start a
      second concurrent run. R1 read it at `turn_scheduler.py:327-334`, with the re-drain at run
      end at `agent_trigger.py:2514`. Test: 1.2's fixture with the asking run still `running` → no
      new `Run` row, and `schedule_agent` answers *"agent is already running"*. If this fails,
      **stop and record a finding**. Do not patch the scheduler inside this change.
      **(Round 4 — REV, F-G)** The scenario's second half, *"delivered as a new turn once the agent
      is free"*, had only drive step 5.3. Extend the test: move the asking run out of `running`,
      re-drain (`agent_trigger.py:2514`'s call, or `schedule_agent` directly) → one turn starts,
      and its input is the entry. **Mutation:** drop the run-end re-drain (`agent_trigger.py:2514`)
      and drive the run's end through the real finalize → no turn.
      *Done, iteration 7:* `test_a_late_answer_is_delivered.py::test_a_turn_queued_behind_a_live_run_waits_for_it_and_then_runs`. The asking run is a real trigger whose scripted PTY blocks its first read, so it is `running` while the operator answers: one entry `queued`, no second `Run`, and the answer's wake answered `agent is already running`. It then ends through the real `_execute_run` finalize, which re-drains and starts a turn delivered that entry; the spawned argv carries `Answer: blue`. Mutation (drop the re-drain at `agent_trigger.py:2514`) -> fails, `the asking run's end started no turn`. No finding: the scheduler holds.
- [x] 2.6 A second report of the same ids is accepted and delivers nothing more. **Mutation:**
      skip the `wait_ended_at` write on the resolved branch → a second entry.
      **(Round 3)** That mutation is stale under 2.9. Skipping the write means the first report
      stamps nothing, keys nothing, and delivers nothing, so 2.2 fails and 2.6 sees no second entry.
      The applicable mutation is: **drop the `wait_ended_at IS NULL` arm** of 2.8's `WHERE` → the
      second report's `rowcount` is 1, it re-keys, and a second entry appears. 2.9's mutation (c)
      stays as a separate check.
      *Done, iteration 7:* `test_a_late_answer_is_delivered.py::test_a_second_report_of_the_same_ids_delivers_nothing_more`. Mutation (drop `wait_ended_at IS NULL`) -> fails, `assert 2 == 1`.
- [x] 2.7 A lone question declined after the tool's last poll, then reported: accepted, no entry,
      `wait_ended_at` still NULL, and the bound task's `proceeded_without_answer_reason` still
      null.
      *Done, iteration 7:* `test_a_late_answer_is_delivered.py::test_a_question_declined_before_the_report_is_accepted_and_not_called_an_absence` (accepted, no entry, `wait_ended_at` NULL, task `proceeded_without_answer_reason` null). It is the test for 2.1's mutation.
- [x] 2.8 **(Round 2) The stamp is a guarded `UPDATE`** (design D4, *The invariant D3 leans on*).
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
      *Done, iteration 7:* `run_task_binding.record_wait_ended`, `synchronize_session=False`, with the rule in its docstring. `test_a_late_answer_is_delivered.py::test_a_decline_committed_mid_report_is_not_recorded_as_a_wait_that_ended` (a real decline route via the patched `get`). Mutation (restore `question.wait_ended_at = now`) -> fails, `wait_ended_at` is a datetime.
- [x] 2.9 **(Round 2) Keys come from committed state, after the report's own commit** (design D4,
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
      *Done, iteration 7:* `test_a_late_answer_is_delivered.py::test_an_answer_committed_mid_report_is_delivered_by_the_report` (real answer route inside the report, asserting it queued nothing itself). Mutations: (a) key from the load-time branch -> fails, no entry; (b) re-read without `populate_existing` -> fails, no entry; (c) key every accepted row -> 2.6 fails, `assert 2 == 1`.
- [x] 2.10 **(Round 3) The run-end sweep uses the same guarded write** (design D4, *The sweep is the
      second writer*). In `evaluate_run_end` (`run_divergence.py:730-733`), replace
      `question.wait_ended_at = question.wait_ended_at or now` with `record_wait_ended`, and call
      `release_block_for_expired_wait` only when it returns True. Test: a bound run has ended,
      holding an unanswered blocking question whose wait has expired. A decline is committed through
      a second session after `unanswered_blocking_question` has loaded the row (patch it to commit
      the decline before returning) → the question's `wait_ended_at` stays NULL, and the task's
      `proceeded_without_answer_reason` is null. **Mutation:** restore the attribute write →
      `wait_ended_at` set on a declined row. The existing sweep tests
      (`grep -rl wait_ended_at hub/tests/`) stay green unchanged.
      **(Round 4 — REV, F-B)** Only the release depends on the helper's result. `question = None`
      and the commit happen **whatever it returns**, because `question = None` is what keeps the
      park at `:738` from firing. Written as `if … and await record_wait_ended(...)`, a False return
      leaves `question` set, and `block_task_for_question` parks the task on the question the
      operator just declined. That is the *decline undone* defect that
      `unanswered_blocking_question`'s docstring warns about (`run_task_binding.py:649-652`). The
      shape is:
      `if question is not None and wait_has_expired(question): if await record_wait_ended(...):
      release; commit; question = None`.
      The test also asserts that the task's status, **re-read from the database** (not from the
      sweep's `task` loaded at `:702`), is not `blocked`. **Mutation:** move `question = None` under
      the helper's True branch → the task reads `blocked`.
      *Done, iteration 7:* `run_divergence.py` in the F-B shape. `test_a_late_answer_is_delivered.py::test_a_decline_committed_mid_sweep_is_not_recorded_and_parks_nothing`. The task is released by hand while the run waits, so it is `in_progress` at the sweep and a park would move it. Mutations: (a) restore the attribute write -> fails, `wait_ended_at` set; (b) `question = None` under the True branch -> fails, `assert 'blocked' != 'blocked'`. Existing sweep tests pass unchanged.
- [x] 2.11 **(Round 4 — REV, F-A) Completeness is judged on fresh rows.** Add
      `.execution_options(populate_existing=True)` to `_completed_batch`'s `select`
      (`questions.py:71-77`). This is safe, because it already flushes the caller's pending write
      first (`:69`). It covers the report, and the answer and decline routes too. 2.9's re-read
      still chooses the **keys**, and this re-read judges **completeness**. Each is needed: a sibling
      whose guarded `UPDATE` returned 0 is not re-read by 2.9, and `synchronize_session=False`
      leaves it stale in the identity map. Test: 2.3 as re-aimed. The existing batch tests in
      `test_question_batch_delivery.py` stay green unchanged.
      *Done, iteration 7:* `_completed_batch`'s `select` has `.execution_options(populate_existing=True)`. The test and mutation are 2.3's. `test_question_batch_delivery.py` passes unchanged.

## 3. Races (design D4)

- [x] 3.1 Test both orders on committed state: answer-then-report, and report-then-answer. Each
      ends with exactly one entry.
      *Done, iteration 7:* `test_a_late_answer_is_delivered.py::test_either_order_on_committed_state_delivers_exactly_once[answer-then-report|report-then-answer]`, each exactly one entry.
- [x] 3.2 Interleaved: the answer route decides its predicate from a fresh read while the report
      has already committed `wait_ended_at` → an entry. Pin this by asserting the predicate is
      evaluated after `session.refresh`. **Mutation:** move 1.2's call back before the commit, and
      use a row loaded before the report committed → no entry.
      *Done, iteration 7:* `test_a_late_answer_is_delivered.py::test_the_answer_decides_on_a_fresh_read_after_the_report_committed` (the real report route runs inside the answer route, right after its load). Mutation (predicate computed before the commit, from the loaded row) -> fails, no entry.

## 4. Gate

- [x] 4.1 `py -3.11 -m pytest hub/tests/ -q` whole and green. Record the counts.
      *Done, iteration 8:* one run, whole: **4361 passed, 86 skipped, 16 xfailed, 0 failed** in
      28 min 18 s. The last gate (4b59ee0) was 4345/86/16, and the +16 is exactly this change's new
      tests (14 functions in `test_a_late_answer_is_delivered.py`, one of them parametrized twice,
      plus one in `test_asker_waiting_is_the_same_on_every_route.py`). Taken before the F-H test
      below existed. After it: the six question files, 122 passed.
      **Verified on resume:** three of iteration 7's recorded mutations re-applied byte-exact
      (1.2's `wait_ended_at` arm, 2.1's `declined IS FALSE`, 2.11's `populate_existing`), and each
      failed its named test with the recorded failure.
      **Round 4 F-H, completed here (iteration 8).** Iteration 7 read `run.id` into a local before
      the report's loop, as the design asked. But `release_block_for_expired_wait` still reads
      `run.id` and `run.agent`, and after one question's rollback `run` is expired. A probe
      measured it: the next question's release raised `MissingGreenlet`, was caught, rolled back,
      and was not accepted. So one failed release took every later one down with it. Fixed by
      re-loading `run` after the rollback. Test:
      `test_a_late_answer_is_delivered.py::test_one_failed_release_in_a_report_does_not_fail_the_next`,
      which reports the failing question first and the real release second. Mutation (drop the
      re-load) → fails, `assert [] == ['q-…']`.
- [x] 4.2 The CI lint set: `ruff check src/ hub/ tests/`,
      `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`, and `mypy src/`.
      *Done, iteration 8:* all three green, each run as `py -3.11 -m`, before and after the F-H edit.
- [x] 4.3 `openspec validate a-late-answer-is-delivered --strict`.
      *Done, iteration 8:* valid.

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
      **(Round 4 — REV, F-F)** The note carries D5's route table as REV corrected it: route 1
      includes a report whose write was rolled back, and a candidate route 4 (the MCP client
      abandons the tool call before its deadline) is read, not measured.
