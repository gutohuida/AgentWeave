# Tasks — a task nothing will move holds nobody

Findings: F352's definition half (F352 stays open for its visibility half). R1, night of 2026-09-14.
*Round 3* adds F372, which is fixed here by design D8 and group 3b.

Rules for this change:
- No `hub/hub/mcp_server.py` edit: `:8000` spawns it fresh from this tree per agent turn (F354).
  Nothing here needs it.
- No migration, no API shape change, no UI code, no bundle.

Tests run under `py -3.11`. `black` needs `--target-version py311`.

Each test named below must **fail with its mutation applied** before its task is ticked. Record the
mutation and the observed failure beside the tick.

New tests go in `hub/tests/test_a_task_nothing_will_move_holds_nobody.py` unless a task says
otherwise. Stage agents through the same roster and runner fixtures `test_reviewer_ladder.py` uses
(`_roster`, `bind_runner`), so "has a runner bound" is real, not assumed.

## 1. The predicate (design D1, D2, D4, D6)

- [x] 1.1a *(Round 2.)* Add `task_agent_pairs_with_a_turn_queued(session, project_id) ->
      Set[Tuple[str, str]]` to `hub/hub/run_task_binding.py`, beside
      `tasks_with_a_turn_pending_or_running`. It returns `(task_id, agent)` and
      `(review_task_id, agent)` for every `InboundQueueEntry` that meets all of these:
      - in the project;
      - `state == "queued"`;
      - `agent` not NULL;
      - `hop_depth <= hop_budget`, with the budget read through `inbound_queue.project_limits`,
        the reader `_attempt_turn` uses.

      The docstring must say why this is not the F154 helper (design D4): the helper answers
      *is anybody on this task* per task with one agent, and the pool asks *will input queued for
      this agent move it onto this task*, per pair and within budget. It must also name F370 and
      F371. Do **not** change `tasks_with_a_turn_pending_or_running` or its reader at `:1454`, and
      do not change the held-resume arm at `:1506` (F370 is not this change's).
      *Done, iteration 5:* `run_task_binding.task_agent_pairs_with_a_turn_queued`, budget via `inbound_queue.project_limits`; docstring names D4, F370, F371. The F154 helper, `:1454` and `:1506` untouched. Mutation M8 (drop the `hop_depth <= hop_budget` filter) fails 1.6b only.
- [x] 1.1 In `_agents_that_are_free` (`hub/hub/scheduler.py:1022`), replace the project-wide
      `holding` query with D6's shape:
      - `live`, the ids of this project's loops with `ending_state IS NULL` **and `archived_at IS
        NULL`** (Round 2);
      - `queued`, from task 1.1a's function (Round 2, in place of R1's `on_it`);
      - the live-status assigned tasks with their `loop_id`;
      - `holding`, the assignees whose task has `loop_id in live` or `(task.id, assignee) in
        queued`.

      The signature, return type and name order do not change. `running` and `roster` are not
      touched.
      *Done, iteration 5:* `live` / `queued` / `holdings` / `holding` exactly as D6. Signature, return type and name order unchanged. Pinned by 1.2-1.7b below.
- [x] 1.2 **A task outside every loop holds nobody, in every live status.** Parametrise over
      `sorted(LIVE_STATUSES)`. Stage an agent assigned one task with `loop_id` NULL and no queued
      entry, then assert the agent is in `_agents_that_are_free`.
      **Mutation:** make the comprehension's condition `True`, which restores the old rule → all
      five cases fail.
      *Done, iteration 5:* `test_a_task_outside_every_loop_holds_nobody[*]`, 5 cases. Mutation M1 (condition `if True`) -> all 5 fail, `assert 'dev' in []`.
- [x] 1.3 **A task in a live loop holds its assignee.** The same agent, with the task's `loop_id`
      naming a loop whose `ending_state` is NULL and whose job is enabled. Assert the agent is not
      free. **Mutation:** drop the `loop_id in live` arm → the test fails.
      *Done, iteration 5:* `test_a_task_in_a_live_loop_holds_its_assignee`. Mutation M2 (drop the `loop_id in live` arm) -> fails, `assert 'dev' not in ['dev']`.
- [x] 1.4 **A paused loop still holds** (design D2, the position flagged to the operator). The same,
      with the loop's `AIJob.enabled = False` and `ending_state` NULL. Assert the agent is not free.
      **Mutation:** build `live` with an extra `AIJob.enabled IS TRUE` join → the test fails.
      *Done, iteration 5:* `test_a_paused_loop_still_holds`. Mutation M3 (`live` joins `AIJob` with `AIJob.enabled IS TRUE`) -> this test alone fails.
- [x] 1.5 **An ended or archived loop holds nobody, and neither does a `loop_id` naming no loop.**
      Four cases:
      - `ending_state = "stopped"`;
      - `ending_state = "completed"`;
      - *(Round 2)* a loop archived through the operator's `POST /jobs/{id}/archive`, driven
        through the route rather than written into the row, so that `ending_state` is still NULL.
        Assert that it is, before asserting the agent is free, so the test fails loudly if the
        route ever starts ending the loop;
      - a `loop_id` that names no `Loop` row.

      Assert the agent is free in each.
      **Mutation A:** replace the membership test with `loop_id is not None` → all four fail.
      **Mutation B:** outer-join `Loop` and test `Loop.ending_state IS NULL` instead of membership
      → the dangling case fails.
      **Mutation C** *(Round 2)*: drop the `archived_at IS NULL` clause → the archived case fails.
      *Done, iteration 5:* `test_an_ended_loop_holds_nobody[stopped|completed]`, `test_a_loop_archived_through_the_job_route_holds_nobody` (route answered 200; `ending_state` asserted None and `archived_at` set before the pool is asked), `test_a_loop_id_naming_no_loop_holds_nobody`. M4 (`loop_id is not None`) -> all four fail. M5 (outer join, test `ending_state`/`archived_at`) -> the dangling case alone fails. M6 (drop `archived_at IS NULL`) -> the archived case alone fails.
- [x] 1.6 **A turn queued for the assignee holds its task, outside every loop.** Two cases:
      - an `InboundQueueEntry` in `state="queued"` for the assignee with `task_id` naming the task;
      - one with `review_task_id` naming it.

      Both at `hop_depth=0`. Assert the agent is not free in both. **Mutation:** drop the `queued`
      arm → both fail.
      *Done, iteration 5:* `test_a_turn_queued_for_the_assignee_holds_its_task[task_id|review_task_id]`. Mutation M7 (drop the `queued` arm) -> both fail (and 1.6b's second assertion, and 1.7b).
- [x] 1.6b *(Round 2)* **Input past the hop budget does not hold.** The same entry, with
      `task_id` naming the task, at `hop_depth = hop_budget + 1`, which is what `create_message`
      writes for a chain past the budget. Assert the agent is free. Then re-base it with
      `inbound_queue.release_entry`, the operator's release, and assert the agent is not free.
      **Mutation:** drop the `hop_depth <= hop_budget` filter from task 1.1a's function → the first
      assertion fails.
      *Done, iteration 5:* `test_input_past_the_hop_budget_does_not_hold_until_released`: at budget+1 free, after `release_entry` (refusal None) not free. Mutation M8 -> fails on the first assertion, *input nothing will deliver must not hold its assignee*.
- [x] 1.7 **A turn queued for somebody else does not hold the assignee.** The entry names the task
      but is for a different agent. Assert the assignee is free. **Mutation:** test `task.id in
      {t for t, _ in queued}` in place of the pair → the test fails.
      *Done, iteration 5:* `test_a_turn_queued_for_somebody_else_does_not_hold_the_assignee`. Mutation M9 (`task_id in {t for t, _ in queued}`) -> this test alone fails.
- [x] 1.7b *(Round 2; re-staged in Round 3)* **Input for somebody else does not hide the
      assignee's own.** Queue three entries naming the task, all within budget: one for `architect`
      (sorts before the assignee), then one for the assignee `dev`, then one for `zeta` (sorts
      after). The assignee's entry goes **between** the other two. Assert `dev` is not free.
      **Mutation:** R1's shape, `tasks_with_a_turn_pending_or_running(...).get(task.id) ==
      assignee` → the test fails. *Round 3:* R2's two-agent staging relied on the helper's rows
      coming back in agent-name order. That order comes from the query planner using
      `ix_inbound_queue_project_agent_state_arrival`, and nothing guarantees it. With the assignee
      neither first nor last by name, and neither first nor last by insertion, the helper's
      `setdefault` keeps a non-assignee under name order, reverse name order, insertion order and
      reverse insertion order. So the mutation fires whichever of those the planner picks. Record
      the helper's actual answer beside the tick. Do not tick on a mutation that cannot fire.
      *Done, iteration 5:* `test_input_for_somebody_else_does_not_hide_the_assignees_own`. **The helper's actual answer: `{'task-held': 'architect'}`** (measured by replacing the premise assertion with `assert False, helper`). The test asserts that premise before its real assertion. Mutation M10 (R1's shape, `tasks_with_a_turn_pending_or_running(...).get(task_id) == assignee`) -> fails.
- [x] 1.8 **Correct the three statements of the old rule.** No test.
      - `_agents_that_are_free`'s docstring: state D1's rule. Replace the *"third opinion … cannot
        appear here"* sentence (`:1031-1033`) with D5's account of why the roster and the pool
        differ.
      - `resolve_reviewer`'s ladder, line 2 (`:1107`): *"any agent not running and holding no
        active task"* becomes *"… holding no work anything will move"*.
      - The comment at `:1363-1367`: the same correction.

      *Round 3:* two other passages mention the pool counting an assignee busy, and both stay:
      - `task_transition_service.py:397` narrates F70's discovery in the past tense;
      - `scheduler.py:1419` is about a task the walk reached, which is in a live loop and still
        holds.

      Leave both alone.
      *Done, iteration 5:* Pool docstring states D1/D2 and D5's roster-vs-pool account in place of the *third opinion* sentence; its held-agent paragraph's *which tasks ... is unchanged* re-scoped to that change. Ladder line 2 and the `:1363` comment corrected. `task_transition_service.py:397` and `scheduler.py:1419` left alone.

## 2. Tests that encode the old rule (design D7)

- [x] 2.1 **Re-stage `test_reviewer_ladder.py::test_an_agent_holding_an_active_task_is_not_selected`**
      inside a live loop. Give `task-held` a `loop_id` naming a loop whose `ending_state` is NULL.
      Keep its assertion (`zz-free` is chosen). Update its docstring: D4's pile-up applies to a queue
      something will serve.
      **Mutation:** drop the `loop_id in live` arm → it fails, because `aa-loaded` sorts first.
      *Done, iteration 5:* Re-staged in a live loop (`job-held`/`loop-held`), assertion kept (`zz-free`), docstring says the pile-up is a queue something will serve. Mutation M2 -> fails, `assert 'aa-loaded' == 'zz-free'`.
- [x] 2.2 **Its sibling:** `test_an_agent_holding_only_a_task_outside_every_loop_is_selected`, in the
      same file. It stages the same task with no `loop_id` and asserts `aa-loaded` is chosen.
      **Mutation:** make the condition `True` → it fails.
      *Done, iteration 5:* `test_an_agent_holding_only_a_task_outside_every_loop_is_selected`. Mutation M1 -> fails, `assert 'zz-free' == 'aa-loaded'`.
- [x] 2.3 **Sweep.** Run the files listed in 4.1. Any other test that now fails because it staged a
      holding with no `loop_id` is re-staged the way 2.1 is. Name each one in the log, with one line
      on why re-staging keeps its point. **No assertion is weakened to pass.** If a failure is *not*
      of that shape, stop and write it down: it is a consumer R1 to R3 did not find.

      *Round 3.* Some tests will fail for a second, **intended** reason: design D8 now refuses a
      firing whose job agent is busy and whose loop holds no open task, even when another agent is
      free.
      - Where such a test asserted that the firing proceeds, and the assertion is about queuing a
        briefing for the busy agent, it asserted F372's pile-up. Flip it and name it in the log.
      - Where it needed the firing to proceed for some other reason, it most likely needs its
        agent idle. Give it that, and name it.
      - Where neither fits, stop, as above.
      *Done, iteration 5:* Sweep of every 4.1 file against the new code before 2.1: **one** failure, `test_an_agent_holding_an_active_task_is_not_selected`, which is D7's own (464 passed, 3 skipped). No test of D8's shape failed, no other consumer surfaced, and the whole suite (4.3) is green. Nothing else re-staged, nothing weakened.

## 3. The callers, through the real functions (design D3)

- [x] 3.1 **The LoopEngine shape, through `decide_firing`.** Stage the following:
      - a flow with a document;
      - one `completed` task whose completion is recorded by agent `A`, and whose evidence names a
        commit;
      - agent `B` assigned an `in_progress` task and agent `C` a `pending` task, both with `loop_id`
        NULL;
      - no declared reviewer.

      Assert the decision selects a review for `B` (first in name order), and `unstaffed` is empty.
      Reuse the fixture of an existing test that staffs a rung-2 review through `decide_firing`
      (find it in `test_flow_*.py` or `test_a_loop_does_not_staff_its_own_review.py`) rather than
      building a second one.
      **Mutation:** make the condition `True` → `unstaffed` carries the rung-3 sentence and nothing
      is selected.
      *Done, iteration 5:* `test_the_loopengine_shape_staffs_its_review`, reusing `test_a_loop_does_not_staff_its_own_review`'s `_queue(declares_document=True)`, `_task`, `_completed_by` and `record_review_evidence`. Selections `[(task, 'bb-bookmark', True)]`, `unstaffed == ()`. Mutation M1 -> `assert [] == [...]`.
- [x] 3.2 **New work, through `decide_firing`.** A flow with two startable unassigned tasks. The job's
      agent is `running`. The only other roster agent is assigned one `in_progress` task with
      `loop_id` NULL. Assert one selection pairs a task with the other agent.
      **Mutation:** make the condition `True` → no selection.
      *Done, iteration 5:* `test_new_work_is_given_to_a_bookmark_holder`. Mutation M1 -> `assert [] == ['bb-bookmark']`.
- [x] 3.3 **The guard agrees with the walk.** `_loop_flow_busy_reason(session, loop, agent)` (the
      signature from task 3b.1) returns `None` when all of these hold:
      - the job's agent is running;
      - the only other agent holds only a task outside every loop;
      - *(Round 3)* the guard's loop holds a startable unassigned task. Under D8 an empty loop is
        refused whoever is free, so without this task the case tests D8 instead.

      It returns the busy reason when that other agent's task is in a live loop.
      **Mutation:** give the guard its own copy of the old holding query → the first case fails.
      *Done, iteration 5:* `test_the_guard_agrees_with_the_walk`, the guard's loop holding its pending task. Mutation M11 (the guard filters the pool through its own copy of the old holding query) -> fails, `assert 'guard-owner is already running a turn' is None`. M2 fails its second case.
- [x] 3.4 **What the Run route returns (the F108 question).** Use the `live_scheduler` fixture that
      `test_board_agent_role.py` defines. *Round 3:* without it the route answers **503** *"Job
      scheduler not available"* before it reaches the firing (measured), which is how F48 survived.
      Stage 3.3's first case on a real loop, then `POST` the job's `/run`. The answer is **200**
      with `"success": true` (`jobs.py:1414`), not the guard's 409 (*"… and no other agent is free
      to take this loop's work. Nothing was started."*), and one input naming the task is queued
      for the other agent. Then stage the second case: the answer is that 409.
      **Mutation:** make the condition `True` → the first case answers 409.
      *Done, iteration 5:* **Split into two tests** (a deviation, found by mutation): with both cases in one database, M2 left the second case answering 409 anyway, because the first case's firing had itself staffed `B` onto a live-loop task, so the second case's staging tested nothing. `test_run_staffs_the_bookmark_holder_and_answers_success`: 200 `success: true`, one entry for `B` naming the task, none for the owner. M1 -> 409 *"... and no other agent is free to take this loop's work. Nothing was started."*; M11 -> the same. `test_run_still_answers_409_when_the_holding_is_in_a_live_loop`: M2 -> `200 == 409`. `schedule_agent` is patched inert so no process starts; the queued entry is what is asserted.
- [x] 3.5 **The board says the same.** For 3.3's first case, the loops board's `stall_reason`
      (`api/v1/jobs.py:355`) is not the guard's busy sentence.
      **Mutation:** as in 3.4 → the busy sentence appears.
      *Done, iteration 5:* `test_the_board_does_not_read_the_busy_sentence`. Mutation M1 -> the busy sentence appears.
- [x] 3.6 **The roster is unchanged.** `GET` the project's agents. The agent holding a task outside
      every loop still shows it in its active-task count. **Mutation:** filter the roster's
      `active_task_counts_q` (`api/v1/agents.py:439`) to `Task.loop_id IS NOT NULL` → the test fails.
      This pins a spec scenario that this change must not break, not code that it writes.
      *Done, iteration 5:* `test_the_roster_still_counts_a_bookmark`: `active_task_count == 1`, and the pool frees the agent. Mutation M12 (roster's `active_task_counts_q` filtered to `Task.loop_id IS NOT NULL`) -> fails.

## 3b. The guard's queue half (design D8, finding F372; Round 3)

Reuse `test_loop_busy_guard.py`'s `_make_loop_job` and `_running_turn`. Delete the staged task to
get an empty loop. Stage the free agent through `_roster`, so that it has a runner bound. R3's probe
did exactly this against the current code: three firings queued three entries for the busy agent and
wrote three `JobRun`s, and Run answered 200.

- [x] 3b.1 Add `_loop_has_open_task(session, loop) -> bool` to `hub/hub/scheduler.py`. It tests
      whether any task has `Task.loop_id == loop.id` and `Task.status NOT IN
      TERMINAL_FOR_BINDING`, which is the predicate `_stall_reason_from_walk` reads (`:1863-1871`).
      Its docstring must say that this is the question which decides `DECISION_PROCEED_EMPTY`.
      Change `_loop_flow_busy_reason` to `(session, loop, agent)`. It returns the busy reason when
      the job's agent is busy **and** either no agent is free or `_loop_has_open_task` is false.
      Update the three callers:
      - the firing, `scheduler.py:2629`, which already holds `loop`;
      - the board, `jobs.py:355`, which already holds `loop`;
      - the Run route, `jobs.py:1350`, which loads the `Loop` where it now calls `_job_has_loop`.

      Rewrite the guard's docstring, whose *"a single-agent loop … exactly as strict as before for
      every loop that exists today"* F128 already showed false, to state both halves and why.
      *Done, iteration 5:* `_loop_has_open_task` beside the guard; the guard is `(session, loop, agent)`, its queue half asked before the pool. Callers: the firing (`loop`), the board (`loop`), the Run route (`_job_has_loop` became `_job_loop`, returning the row). The route's clause is chosen by `_loop_has_open_task`. Guard docstring rewritten: the false *exactly as strict as before* sentence is replaced by both halves and F128.
- [x] 3b.2 **A busy agent's empty loop queues nothing, whoever is free.** The staging: the job agent
      is running, the loop holds no task, and one roster agent with a runner holds nothing. Fire
      three times. Assert, in this order, that zero entries are queued for the busy agent, zero
      `JobRun`s exist, and every firing returned `False`.
      **Mutation:** drop the queue half → 3 entries, 3 `JobRun`s, three `True`s (measured by R3
      against the current code).
      *Done, iteration 5:* `test_a_busy_agents_empty_loop_queues_nothing_whoever_is_free`. Mutation M13 (drop the queue half) -> `assert 3 == 0` on entries: R3's measurement, reproduced.
- [x] 3b.3 **The same, when the free agent holds only a bookmark.** This is the case the change itself
      would otherwise have opened. The staging is 3b.2's, with the other agent assigned one
      `pending` task that has `loop_id` NULL. Assert zero and zero.
      **Mutation:** drop the queue half → 3 and 3. *(Before this change, the old holding rule
      refused it. That is why this test belongs to this change and not only to F372.)*
      *Done, iteration 5:* `test_the_same_when_the_free_agent_holds_only_a_bookmark`. M13 -> `assert 3 == 0`.
- [x] 3b.4 **The held form.** The same as 3b.2, but the job agent is **held**, with no run, through
      `test_a_held_agent_is_busy.py`'s `_hold`. Assert that no entry is queued for it.
      **Mutation:** drop the queue half → entries appear.
      *Done, iteration 5:* `test_a_held_agents_empty_loop_queues_nothing` (two firings). M13 -> `assert 2 == 0`.
- [x] 3b.5 **The queue half is conjunctive with busy.** An idle job agent, an empty loop, and a free
      other agent. Fire once: exactly one entry is queued for the job agent. *(A never-filled loop
      still fires its agent to fill it.)*
      **Mutation:** refuse on `not _loop_has_open_task` alone, without asking whether the agent is
      busy → zero entries.
      *Done, iteration 5:* `test_an_idle_agents_empty_loop_still_fires_its_agent`: one entry, `[True]`. Mutation M14 (queue half asked before, and without, busy) -> fails.
- [x] 3b.6 **What Run says (the F108 question for D8).** Take 3b.2's staging with `live_scheduler`,
      and `POST` the job's `/run`. The answer is **409**:
      - its detail names the running agent;
      - it contains *"Nothing was started"*;
      - it does **not** contain *"no other agent is free"*.

      No entry is queued for the busy agent. The existing
      `test_board_agent_role.py::test_running_a_loop_whose_agent_is_mid_turn_answers_409_not_500`
      still passes unchanged, and its loop holds a pending task, so it pins the other clause.
      **Mutation A:** drop the queue half → **200** `{"success": true}` (measured by R3).
      **Mutation B:** keep the route's old single clause → the *"no other agent is free"* assertion
      fails.
      *Done, iteration 5:* `test_run_on_a_busy_agents_empty_loop_names_the_empty_queue`: 409, names `busy-agent`, *Nothing was started*, not *no other agent is free*, no entry. M13 -> `200 == 409` with `{"success":true,...}` (R3's measurement). M15 (route keeps the single clause) -> fails. `test_running_a_loop_whose_agent_is_mid_turn_answers_409_not_500` passes unchanged.

## 4. Verification

- [x] 4.1 Under `py -3.11`, run these files:
      - the new file;
      - `test_reviewer_ladder.py`, `test_a_held_agent_is_busy.py`, `test_scheduler.py`,
        `test_loop_busy_guard.py`, `test_flow_*.py`, `test_board_agent_role.py`,
        `test_turn_scheduler.py`;
      - `test_a_task_waits_while_its_run_waits.py`, `test_a_loop_does_not_staff_its_own_review.py`,
        `test_reviewer_is_not_the_author.py`, `test_the_evidence_names_the_author.py`,
        `test_task_turn_collision.py`, `test_run_divergence*.py`;
      - *(Round 3, for D8's three call sites)* `test_a_review_nobody_is_doing.py`, `test_jobs.py`,
        `test_jobs_crud.py`, and every `test_loop*.py`.

      Record the counts.
      *Done, iteration 5:* 30 files (the new one and the list above): **491 passed, 3 skipped, 0 failed**, read from the whole run's junit XML.
- [x] 4.2 Run CI's lint set exactly:
      - `ruff check src/ hub/ tests/`
      - `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`
      - `mypy src/`
      *Done, iteration 5:* `py -3.11 -m ruff check src/ hub/ tests/`: all checks passed. `py -3.11 -m black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`: 575 unchanged. `py -3.11 -m mypy src/`: no issues in 22 files.
- [x] 4.3 Run the whole hub suite once, per `night-window.md` *Implementing*. Record passed, skipped
      and xfailed, and compare them with the last gated count (4316 / 86 / 16 at `c8e3bbd`).
      *Done, iteration 5:* Whole hub suite, as 10 size-balanced chunks plus `tests/browser`: **4345 passed, 86 skipped, 16 xfailed, 0 failed**. Against 4316 / 86 / 16 at `c8e3bbd`, +29 passed = the 28 new tests + 2.2's sibling.

## 5. Drive and archive (design, *Test plan*)

- [ ] 5.1 Start a drive Hub on a free port against a **fresh** `profiles/drive0915/` database, from
      `hub/`, from source. Every runner binds `claude-haiku-4-5`. Never use `:8000`,
      `proj-5e960453` or `proj-18e5d4e0`.
- [ ] 5.2 **The LoopEngine shape, live.** Stage 3.1's board through the real routes: agents, a
      document, approval, a flow, tasks, evidence. Give `B` and `C` their out-of-loop tasks through
      `POST /tasks`, with an assignee and no `loop_id`, which is the route the Architect used. Fire
      the flow. The review is staffed and a real Haiku turn runs it, with no `review_unstaffed`
      recorded for the task.
- [ ] 5.3 **The control.** Put `B`'s and `C`'s tasks in a second live loop, or stage them there
      fresh. Fire. The review is `review_unstaffed`, and the sentence is today's.
- [ ] 5.4 **Paused and ended.** Pause that second loop: still unstaffed. End it: staffed.
      *(Round 2)* **Archived.** Stage a third loop with the tasks again. Archive its job through
      `POST /jobs/{id}/archive` without stopping it first, confirm with `GET /loops/{id}` that
      `ending_state` is null, and fire: the review is staffed.
- [ ] 5.4b *(Round 2)* **Past the hop budget.** With `B`'s task outside every loop, send `B` a peer
      message naming that task through `POST /messages` with a `task_id` and no run, which
      `create_message` queues at `hop_budget + 1`. Fire the flow: `B` is still staffed. That is the
      LoopEngine Q6 shape.
- [ ] 5.4c *(Round 3)* **A busy agent's empty loop (D8).** Create a plain loop on `A` with no
      tasks. While `A` has a real turn running, press Run on that loop. The staging:
      - `B` holds only its out-of-loop task;
      - `A`'s turn is long enough to hold open, for example a Haiku turn asked to list and summarise
        a directory.

      The answer is 409 naming `A`, and `GET` on `A`'s queue shows no new job entry. If a turn cannot
      be held open long enough to press Run inside it, say so in the log. Task 3b.6 is then this
      step's only evidence. Do not report the step as driven.
- [ ] 5.5 Confirm every job the drive created is disabled, and stop the drive Hub.
- [ ] 5.6 Archive:
      - sync the `agent-flows` delta into `openspec/specs/`;
      - move the change to `openspec/changes/archive/`;
      - in the same commit, set F352's Status line to record its definition half fixed at the
        implementation's sha, leaving it open for the visibility half;
      - correct `FINDINGS.md`'s index note for F352;
      - *(Round 2)* add a dated note to F128: this change widened where its substitution fires
        (design D3). Its decision stays open. F370 and F371 stay open, because this change
        deliberately does not touch `:1506` or `:1454`.
      - *(Round 3)* sync the `agent-loops` delta as well;
      - *(Round 3)* set F372's Status line to *fixed* at the implementation's sha;
      - *(Round 3)* add a dated note to F373 saying this change widened its reach (design D3,
        Round 3). It stays open.
