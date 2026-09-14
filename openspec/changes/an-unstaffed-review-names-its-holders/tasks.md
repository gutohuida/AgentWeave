# Tasks — an unstaffed review names its holders

Findings: F353, F334, F365 (retired by this change); F352 (the visibility half only; stays open).
Build day 2026-09-14. Day rules: no `hub/hub/mcp_server.py`, no migration, and the UI bundle only
under group 5's condition. Tests run under `py -3.11`. `black` needs `--target-version py311`.

Each test named below must **fail with its mutation applied** before it counts. Record the
mutation and the observed failure beside the task when ticking it.

## 1. One availability read (design D1)

- [ ] 1.1 Add `AgentAvailability` and `_roster_availability(session, project_id)` to
      `hub/hub/scheduler.py`:
      - one record per non-archived agent, in name order;
      - `has_runner`, `running`, and `holdings` as `(task_id, status)` pairs over `LIVE_STATUSES`,
        ordered by task id.
- [ ] 1.2 Re-express `_agents_that_are_free` as the projection
      `has_runner and not running and not holdings`, and keep its docstring's argument.
      The existing pool tests pass unchanged: `test_reviewer_ladder.py`, `test_flow_width.py`,
      `test_a_task_waits_while_its_run_waits.py::…3.4`, and the busy guard.
- [ ] 1.3 Test: an agent with no runner, one running with nothing held, one holding two tasks, and
      one free each get the right record, and the pool is exactly the free one.
      *Mutation:* drop `Task.status` from the holdings select (or the `LIVE_STATUSES` filter). The
      test must fail.

## 2. What rung 3 says (design D2, D3)

- [ ] 2.1 Change `resolve_reviewer`'s `exclude` to `Mapping[str, str]` (agent → clause) and remove
      `excluded_because`. Rung 1b reads `exclude[resolution.agent]`.
      - `decide_firing` builds the mapping from exactly the clauses it passes today.
      - Update the 14 test call sites.
- [ ] 2.2 `run_divergence` (`:430-446`) maps silent reviewers to "reviewed this task and recorded no
      verdict", then lays the author clause over any agent that is also the author.
- [ ] 2.3 Rung 3 builds its reason from `_roster_availability`:
      - clause precedence is excluded, then no runner, then holds (three, then "and N more"), then
        running;
      - clauses in name order, leading with `could not staff this step: nobody is free.`;
      - the remedy by `task.status`: `completed` names Land it, `under_review` names the three
        exits and **not** Land it; both name rejecting a held task that is no longer wanted.
- [ ] 2.4 Bound the reason to 500 characters: reserve the remedy, add clauses while they fit, and
      collapse the rest into "and N more agents are excluded, busy or unbound".
- [ ] 2.5 Add one helper that fits `error_summary` to the column, used at the stall write
      (`scheduler.py:2762`) and in `_stall_run_to_increment`'s comparison (`:923`).
      **R2 to decide** whether it also covers the other `error_summary` writes (`:2580`, `:2609`,
      `:2923`, `:3062`).
- [ ] 2.6 Test, LoopEngine-shaped, through a real firing (`POST …/jobs/{id}/run`), reading the
      `review_unstaffed` event **and** `LoopSummary.stall_reason`. Four agents: the author; one
      holding an `under_review` task; one holding five `pending` tasks; one holding an
      `in_progress` task with no turn. Assert:
      - every non-author's name, each named task id and its status, and "2 more" for the five;
      - the author's exclusion clause, and **not** the author's holdings;
      - Land it.

      *Mutations:* (a) drop the holdings clause; (b) put holds before excluded; (c) use
      `excluded_because` for every agent. Each must fail.
- [ ] 2.7 Test, divergence restaff with nobody left: the silent reviewer's clause says it recorded no
      verdict, and nowhere says it completed the task.
      *Mutation:* map silent reviewers to the author clause. The test must fail.
- [ ] 2.8 Test, an `under_review` row (the F70 recovery or the divergence restaff) reaching rung 3:
      the reason names approve, reject and revision_needed, and not Land it.
      *Mutation:* always emit the `completed` remedy. The test must fail.
- [ ] 2.9 Test, twelve agents each holding three tasks:
      - the reason is at most 500 characters, counts the unnamed agents, and still names the
        remedy;
      - `GET …/jobs/{id}/history` answers **200** with the stall row in it.

      *Mutation:* remove the bound (2.4) and the fit (2.5). The history route must fail, which
      proves the test reaches `JobRunResponse`.
- [ ] 2.10 Test: two consecutive stalled firings with an unchanged long reason leave **one** stall
      row with `tick_count == 2`.
      *Mutation:* fit only the write and not the comparison. The test must fail.

## 3. Once per task (design D4)

- [ ] 3.1 `_review_unstaffed_already_stands` filters on
      `EventLog.data["task_id"].as_string() == task_id`, against real SQLite.
- [ ] 3.2 Test: one loop, **two** unstaffable tasks, five firings through the real route. Exactly
      one `review_unstaffed` per task.
      *Mutation:* revert to the loop-newest query. The test must fail, while the existing
      single-task test still passes against the mutant, which shows why it never caught this.
- [ ] 3.3 Test: two tasks; between firings, change one task's reason only, by freeing an agent's
      holding so its clause changes. One more record for that task, and none for the other.
      *Mutation:* drop the task filter. The test must fail.

## 4. The refusals (design D5)

- [ ] 4.1 `_guard_reviewer_is_not_the_author`, both branches:
      - word it true for a staged or a committed assignee, with no "is assigned to" and no
        "still assigned";
      - choose the remedy by `actor.is_operator`;
      - drop "Left as is…";
      - amend the docstring's *"`actor` is deliberately unread"* paragraph.

      The decision is unchanged.
- [ ] 4.2 `review_dispatch_refusal`: the author branch drops "clear the assignee" and names Land it;
      the evidence-author branch names Land it too.
- [ ] 4.3 Test, operator PATCH on a completed task held by its author: 403, names Land it, and does
      not contain "clear the assignee".
      *Mutation:* restore the old sentence. The test must fail.
- [ ] 4.4 Test, agent PATCH through `/agent-actions/tasks/{id}` with a run token, by a non-author on
      a completed task held by its author: 403, states an agent cannot change who holds a task, and
      contains neither "clear the assignee" nor "assign a different reviewer".
      *Mutation:* ignore `actor`. The test must fail.
- [ ] 4.5 Test, F334's shape: a queued review for an agent that recorded evidence during its own
      turn, delivered and refused. The entry's `waiting_reason` and `abandoned_reason` do not say
      the task "is assigned to" that agent, and the task's assignee is unchanged.
- [ ] 4.6 Update any existing test asserting the old sentences, and list each one here when ticking.
- [ ] 4.7 Test: the dispatch route's author refusal (`POST /agent/trigger` with `review_task_id`)
      names Land it and does not contain "clear the assignee".

## 5. The board line (design D6), under the day's bundle rule

- [ ] 5.1 `title={loop.stall_reason}` on the stall `<p>` in `LoopsIndexTab.tsx`, and a unit test
      asserting the attribute carries the full reason.
- [ ] 5.2 `cd hub/ui && npm run lint && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`.
- [ ] 5.3 Drive the served bundle in Chromium on the drive Hub. Hover the stall line and read the
      full reason from `title`. Take a screenshot.
- [ ] 5.4 Commit the bundle only if 5.3 passed **and** nothing the bundle calls is newer than the
      `:8000` process start. It calls nothing new. Otherwise revert `hub/hub/static/ui` and record
      why.

## 6. Verify

- [ ] 6.1 CI's lint set:
      - `ruff check src/ hub/ tests/`;
      - `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`;
      - `mypy src/`;
      - `cd hub/ui && npm run lint`.
- [ ] 6.2 `py -3.11 -m pytest hub/tests/ -q`, full. Record pass and fail counts. Classify any
      failure against DEAD-ENDS (F292 and F314 signatures) before calling it unrelated.
- [ ] 6.3 Drive (night-window.md, *Driving*): a drive Hub on a free port with a fresh
      `profiles/drive0914/` database; runners bound to `claude-haiku-4-5`; a flow with a document;
      the LoopEngine shape staged. Read:
      - the `review_unstaffed` event and the board's stall line;
      - two firings with two unstaffed tasks → one event each;
      - `GET …/jobs/{id}/history` → 200;
      - the drawer's status menu → `under_review` on the author-held task, with the refusal
        rendered beside Land it (Chromium);
      - one real Haiku agent turn asked to move that task to `under_review`, and the refusal text
        it received, read from its tool result.

      Leave no job enabled.
- [ ] 6.4 Archive:
      - sync the three deltas into `openspec/specs/`;
      - move the change to `archive/2026-09-14-an-unstaffed-review-names-its-holders`;
      - in FINDINGS, mark F353, F334 and F365 `fixed <sha>`, and add a dated note to F352 that its
        visibility half shipped and its definition half waits on the operator.
