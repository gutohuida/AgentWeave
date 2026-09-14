# Tasks — a task nothing will move holds nobody

Findings: F352's definition half (F352 stays open for its visibility half). R1, night of 2026-09-14.

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

- [ ] 1.1 In `_agents_that_are_free` (`hub/hub/scheduler.py:1022`), replace the project-wide
      `holding` query with D6's shape:
      - `live`, the ids of this project's loops with `ending_state IS NULL`;
      - `on_it`, from `run_task_binding.tasks_with_a_turn_pending_or_running`;
      - the live-status assigned tasks with their `loop_id`;
      - `holding`, the assignees whose task has `loop_id in live` or `on_it.get(task.id) ==
        assignee`.

      The signature, return type and name order do not change. `running` and `roster` are not
      touched.
- [ ] 1.2 **A task outside every loop holds nobody, in every live status.** Parametrise over
      `sorted(LIVE_STATUSES)`. Stage an agent assigned one task with `loop_id` NULL and no queued
      entry, then assert the agent is in `_agents_that_are_free`.
      **Mutation:** make the comprehension's condition `True`, which restores the old rule → all
      five cases fail.
- [ ] 1.3 **A task in a live loop holds its assignee.** The same agent, with the task's `loop_id`
      naming a loop whose `ending_state` is NULL and whose job is enabled. Assert the agent is not
      free. **Mutation:** drop the `loop_id in live` arm → the test fails.
- [ ] 1.4 **A paused loop still holds** (design D2, the position flagged to the operator). The same,
      with the loop's `AIJob.enabled = False` and `ending_state` NULL. Assert the agent is not free.
      **Mutation:** build `live` with an extra `AIJob.enabled IS TRUE` join → the test fails.
- [ ] 1.5 **An ended loop holds nobody, and neither does a `loop_id` naming no loop.** Three cases:
      - `ending_state = "stopped"`;
      - `ending_state = "completed"`;
      - a `loop_id` that names no `Loop` row.

      Assert the agent is free in each.
      **Mutation A:** replace the membership test with `loop_id is not None` → all three fail.
      **Mutation B:** outer-join `Loop` and test `Loop.ending_state IS NULL` instead of membership
      → the dangling case fails.
- [ ] 1.6 **A turn queued for the assignee holds its task, outside every loop.** Two cases:
      - an `InboundQueueEntry` in `state="queued"` for the assignee with `task_id` naming the task;
      - one with `review_task_id` naming it.

      Assert the agent is not free in both. **Mutation:** drop the `on_it` arm → both fail.
- [ ] 1.7 **A turn queued for somebody else does not hold the assignee.** The entry names the task
      but is for a different agent. Assert the assignee is free. **Mutation:** test `task.id in
      on_it` in place of `on_it.get(task.id) == assignee` → the test fails.
- [ ] 1.8 **Correct the three statements of the old rule.** No test.
      - `_agents_that_are_free`'s docstring: state D1's rule. Replace the *"third opinion … cannot
        appear here"* sentence (`:1031-1033`) with D5's account of why the roster and the pool
        differ.
      - `resolve_reviewer`'s ladder, line 2 (`:1107`): *"any agent not running and holding no
        active task"* becomes *"… holding no work anything will move"*.
      - The comment at `:1363-1367`: the same correction.

## 2. Tests that encode the old rule (design D7)

- [ ] 2.1 **Re-stage `test_reviewer_ladder.py::test_an_agent_holding_an_active_task_is_not_selected`**
      inside a live loop. Give `task-held` a `loop_id` naming a loop whose `ending_state` is NULL.
      Keep its assertion (`zz-free` is chosen). Update its docstring: D4's pile-up applies to a queue
      something will serve.
      **Mutation:** drop the `loop_id in live` arm → it fails, because `aa-loaded` sorts first.
- [ ] 2.2 **Its sibling:** `test_an_agent_holding_only_a_task_outside_every_loop_is_selected`, in the
      same file. It stages the same task with no `loop_id` and asserts `aa-loaded` is chosen.
      **Mutation:** make the condition `True` → it fails.
- [ ] 2.3 **Sweep.** Run the files listed in 4.1. Any other test that now fails because it staged a
      holding with no `loop_id` is re-staged the way 2.1 is. Name each one in the log, with one line
      on why re-staging keeps its point. **No assertion is weakened to pass.** If a failure is *not*
      of that shape, stop and write it down: it is a consumer R1 to R3 did not find.

## 3. The callers, through the real functions (design D3)

- [ ] 3.1 **The LoopEngine shape, through `decide_firing`.** Stage the following:
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
- [ ] 3.2 **New work, through `decide_firing`.** A flow with two startable unassigned tasks. The job's
      agent is `running`. The only other roster agent is assigned one `in_progress` task with
      `loop_id` NULL. Assert one selection pairs a task with the other agent.
      **Mutation:** make the condition `True` → no selection.
- [ ] 3.3 **The guard agrees with the walk.** `_loop_flow_busy_reason` returns `None` when:
      - the job's agent is running;
      - the only other agent holds only a task outside every loop.

      It returns the busy reason when that task is in a live loop.
      **Mutation:** give the guard its own copy of the old holding query → the first case fails.
- [ ] 3.4 **What the Run route returns (the F108 question).** Stage 3.3's first case on a real loop,
      then `POST` the job's `/run`. The answer is not the guard's 409 (*"… and no other agent is free
      to take this loop's work. Nothing was started."*), and one input is queued for the other agent.
      Then stage the second case: the answer is that 409.
      **Mutation:** make the condition `True` → the first case answers 409.
- [ ] 3.5 **The board says the same.** For 3.3's first case, the loops board's `stall_reason`
      (`api/v1/jobs.py:355`) is not the guard's busy sentence.
      **Mutation:** as in 3.4 → the busy sentence appears.
- [ ] 3.6 **The roster is unchanged.** `GET` the project's agents. The agent holding a task outside
      every loop still shows it in its active-task count. **Mutation:** filter the roster's
      `active_task_counts_q` (`api/v1/agents.py:439`) to `Task.loop_id IS NOT NULL` → the test fails.
      This pins a spec scenario that this change must not break, not code that it writes.

## 4. Verification

- [ ] 4.1 Under `py -3.11`, run these files:
      - the new file;
      - `test_reviewer_ladder.py`, `test_a_held_agent_is_busy.py`, `test_scheduler.py`,
        `test_loop_busy_guard.py`, `test_flow_*.py`, `test_board_agent_role.py`,
        `test_turn_scheduler.py`;
      - `test_a_task_waits_while_its_run_waits.py`, `test_a_loop_does_not_staff_its_own_review.py`,
        `test_reviewer_is_not_the_author.py`, `test_the_evidence_names_the_author.py`,
        `test_task_turn_collision.py`, `test_run_divergence*.py`.

      Record the counts.
- [ ] 4.2 Run CI's lint set exactly:
      - `ruff check src/ hub/ tests/`
      - `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`
      - `mypy src/`
- [ ] 4.3 Run the whole hub suite once, per `night-window.md` *Implementing*. Record passed, skipped
      and xfailed, and compare them with the last gated count (4316 / 86 / 16 at `c8e3bbd`).

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
- [ ] 5.5 Confirm every job the drive created is disabled, and stop the drive Hub.
- [ ] 5.6 Archive:
      - sync the `agent-flows` delta into `openspec/specs/`;
      - move the change to `openspec/changes/archive/`;
      - in the same commit, set F352's Status line to record its definition half fixed at the
        implementation's sha, leaving it open for the visibility half;
      - correct `FINDINGS.md`'s index note for F352.
