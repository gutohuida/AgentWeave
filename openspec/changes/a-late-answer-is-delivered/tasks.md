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
- [ ] 2.2 After the loop, deliver once per batch key over the questions resolved before their
      report, through `_deliver_batch_if_complete`. Announce and wake through the helper that 2.4
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
- [ ] 2.7 A lone question declined after the tool's last poll, then reported: accepted, no entry,
      `wait_ended_at` still NULL, and the bound task's `proceeded_without_answer_reason` still
      null.

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
