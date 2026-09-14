# Tasks — an unstaffed review names its holders

> **STOPPED AT REV, 2026-09-14. Do not build any task here** until the operator answers
> `F352-free` and the split question (proposal.md, top). If the operator approves REV's split, the
> F353 half (groups 3 and 4, 2.5, 2.5b, 2.12 and 2.13) moves to its own change directory and takes
> one verification round there before it is built. REV (2026-09-14) revised 2.6, 4.1, 4.3, 4.4, 4.5,
> 4.6 and 4.7, and added 2.13, 2.14 and 4.9. 2.14 belongs to the rung-3 half.

Findings: F353, F334, F365, F367 (retired by this change); F352 (the visibility half only; stays
open); F366 (stays open; D5 stops relying on it). R2 (2026-09-14) revised 1.2, 2.1-2.5, 2.7, 2.10,
4.1, 4.2, 4.4 and 4.7, and added 1.4, 2.5b, 2.11, 2.12 and 4.8. R3 (2026-09-14) revised 2.3, 2.4,
2.6, 2.12, 4.2 and 4.6, and added 2.9b.
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
      - Its three callers keep the projection: `scheduler.py:298`, `:1137` and `:1298`.
      - `resolve_reviewer` instead reads `_roster_availability` **once**, and derives both rung 2's
        pool and rung 3's records from that one read.

      The existing pool tests pass unchanged: `test_reviewer_ladder.py`, `test_flow_width.py`,
      `test_a_task_waits_while_its_run_waits.py::…3.4`, and the busy guard.
- [ ] 1.3 Test: an agent with no runner, one running with nothing held, one holding two tasks, and
      one free each get the right record, and the pool is exactly the free one.
      *Mutation:* drop `Task.status` from the holdings select (or the `LIVE_STATUSES` filter). The
      test must fail.
- [ ] 1.4 Test: `resolve_reviewer` reads the roster once per call. Count the executed `Task.assignee`
      selects with a SQLAlchemy `before_cursor_execute` listener on the real test engine.
      *Mutation:* call `_agents_that_are_free` for rung 2 and `_roster_availability` for rung 3. The
      test must fail.

## 2. What rung 3 says (design D2, D3)

- [ ] 2.1 Change `resolve_reviewer`'s `exclude` to `Mapping[str, str]` (agent → clause) and remove
      `excluded_because`. Rung 1b reads `exclude[resolution.agent]`.
      - `decide_firing` (`scheduler.py:1550-1584`) builds the mapping from exactly the clauses it
        passes today.
      - Update every call site. A missed one fails only where it reaches a named exclusion, and CI
        runs no mypy over `hub/`, so grep `exclude=` before ticking. The sites are:
        - `test_reviewer_ladder.py:97, 121, 146, 159, 170, 189, 213, 239, 278, 303, 328, 339`;
        - `test_a_flow_names_what_it_cannot_staff.py:472, 482`;
        - `scheduler.py:1577` and `run_divergence.py:440`.
- [ ] 2.2 `run_divergence` (`:430-446`) builds the mapping in three layers, each overwriting the
      one before:
      1. on the operator-completed branch, `agents_that_may_have_authored` → "has worked on this
         task";
      2. the silent reviewers and `run.agent` → "reviewed this task and recorded no verdict";
      3. on the agent-completed branch, the recorded completer → "is the one that completed this
         task".
- [ ] 2.3 Rung 3 builds its reason from the same `_roster_availability` read (1.2):
      - clause precedence is excluded, then no runner, then holds (three, then "and N more"), then
        running;
      - clauses in name order, leading with `could not staff this step: nobody is free.`;
      - with no record at all, "the project has no agent on its roster" in the clauses' place;
      - the remedy from `own_review_remedy(task)` (public, in `scheduler.py`), in D2's wording. The
        helper returns the status sentence only (R3):
        - `completed`: "Land it, on the task, to review it yourself", with **no** promise of
          approval;
        - `under_review`: the three exits, and **not** Land it;
      - after the helper's sentence, rung 3 itself appends "; rejecting a held task that is no
        longer wanted frees its agent." The dispatch refusal (4.2) does not.
- [ ] 2.4 Bound the reason to 500 characters. If the whole sentence fits, use it. Otherwise add
      clauses in name order while the prefix, the clauses, the tail
      "; and N more agents are excluded, busy or unbound" and the remedy still fit.
      - A holds clause that would not fit is retried with two named tasks, then one, counting the
        rest as "and N more". Only then is its agent left to the tail (R3).
- [ ] 2.5 Fit `JobRun.error_summary` at the model (design D2):
      - `JOB_RUN_ERROR_SUMMARY_CHARS = 500` beside `JobRun`, read by `String(...)` and by
        `JobRunResponse.error_summary`'s `max_length`;
      - `fit_error_summary(text)`, which leaves text that fits unchanged and cuts longer text to
        499 characters plus `…`;
      - `@validates("error_summary")` on `JobRun`, applying it;
      - `_stall_run_to_increment` (`:923`) comparing against `fit_error_summary(stall_reason)`.
- [ ] 2.5b `_wedged_review_reason` (`scheduler.py:1744-1748`) shortens the quoted title so the whole
      sentence fits 500 characters and its remedy survives.
- [ ] 2.6 Test, LoopEngine-shaped, through a real firing (`POST …/jobs/{id}/run`), reading the
      `review_unstaffed` event **and** `LoopSummary.stall_reason`. Four agents: the author; one
      holding an `under_review` task; one holding five `pending` tasks; one holding an
      `in_progress` task with no turn.

      **Every held task has `loop_id` NULL**, as LoopEngine's backlog did (R3). A held task in the
      loop's own queue is walked: an idle assignee's `in_progress` task is resumed as a selection,
      so the firing claims work and never stalls, and a non-author's `under_review` task with no
      turn surfaces F154's sentence, which F64 may promote instead (design, *Round 3* item 6).
      Assert:
      - every non-author's name, each named task id and its status, and "2 more" for the five;
      - the author's exclusion clause, and **not** the author's holdings;
      - Land it, and no "approves".

      **REV: the author also holds one live task outside the loop**, as `dev` did on LoopEngine.
      Without it, mutation (b) cannot fail, because an author holding nothing reads the same under
      either order.

      *Mutations:* (a) drop the holdings clause; (b) put holds before excluded; (c) use
      `excluded_because` for every agent. Each must fail.
- [ ] 2.7 Test, divergence restaff with nobody left, on **both** branches:
      - agent-completed: the silent reviewer's clause says it recorded no verdict, and nowhere says
        it completed the task;
      - operator-completed: the silent reviewer, which `agents_that_may_have_authored` also
        contains, still reads "recorded no verdict" and not "has worked on this task".

      *Mutations:* (a) map silent reviewers to the author clause; (b) R1's order, where the author
      layer is laid last. Each must fail, (b) on the operator-completed case.
- [ ] 2.8 Test, an `under_review` row (the F70 recovery or the divergence restaff) reaching rung 3:
      the reason names approve, reject and revision_needed, and not Land it.
      *Mutation:* always emit the `completed` remedy. The test must fail.
- [ ] 2.9 Test, twelve agents each holding three tasks:
      - the reason is at most 500 characters, counts the unnamed agents, and still names the
        remedy;
      - `GET …/jobs/{id}/history` answers **200** with the stall row in it.

      *Mutation:* remove the bound (2.4) and the fit (2.5). The history route must fail, which
      proves the test reaches `JobRunResponse`.
- [ ] 2.9b Test (R3): the first agent in name order holds three tasks with 64-character
      caller-chosen ids (created through `POST …/tasks` with `id`), and its name is 32 characters.
      Assert:
      - the reason is at most 500 characters, as an `under_review` row, which has the smaller
        budget;
      - it names that agent with fewer than three of its tasks, plus "and N more";
      - it still names the remedy.

      *Mutation:* drop 2.4's per-clause fallback. The agent must then be missing from the reason,
      so the test fails.
- [ ] 2.10 Test: two consecutive stalled firings with an unchanged reason over 500 characters leave
      **one** stall row with `tick_count == 2`.
      *Mutation:* compare the raw `stall_reason` at `:923`. The test must fail.
- [ ] 2.11 Test, F367 through a real firing: a wedged review (F154's shape) whose reviewer has a
      32-character name and whose task has a 256-character title. Assert:
      - `GET …/jobs/{id}/history` answers 200;
      - the stall row's reason is at most 500 characters and still ends with the remedy
        (`revision_needed.`).

      *Mutations:* (a) remove 2.5b, so the history still answers 200 but the remedy is cut; (b)
      remove the `@validates` as well, so the route answers 500.
- [ ] 2.12 Test: a `JobRun` constructed or assigned with 600 characters of `error_summary` stores
      exactly 500, ending `…`. A 500-character value is stored unchanged, and `None` stays `None`
      (R3: the column is nullable).
      *Mutation:* remove the `@validates`. The test must fail.
- [ ] 2.13 (REV) Test: the guard's operator sentence, both branches, at a 64-character task id and
      a 32-character agent name, is at most 500 characters. So is the queue entry's
      `waiting_reason` after a flow staging is refused on it, read **before** the model fit, from
      the event or the entry and not from `JobRun`, or the validator hides the overflow. The remedy
      survives whole.
      *Mutation:* restore R2's D5 evidence-branch explanation (583 characters at those ids). The
      test must fail.
- [ ] 2.14 (REV) The divergence restaff returns `None` for a task whose status is no longer
      `completed` or `under_review`, at the same screen as `blocked` (`run_divergence.py:746`).
      `own_review_remedy` asserts one of the two statuses. Test: the operator moves a task to
      `revision_needed` while its review run is live, and the run then ends without a verdict. No
      `review_unstaffed` is recorded and no reviewer is staffed.
      *Mutation:* drop the new screen. The test must fail.

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
      - word it true for a staged or a committed assignee, as *"Cannot move task T to
        'under_review' with 'dev' as its holder: …"* (REV), with no "is assigned to", no "still
        assigned", no "holding it" and no "held by";
      - choose the remedy by `actor.is_operator`, in D5's REV wording:
        - operator: Land it with no promise of approval, or dispatching another agent's review
          turn (`POST /agent/trigger` with `review_task_id`). **Not** the PATCH that sets assignee
          and status together, which queues no turn and wedges (REV);
        - agent: "None of the task tools you are offered reassigns a task" and who can move it on,
          never "no agent can" and never "none of your tools changes who holds a task" (REV:
          `create_task` takes an assignee);
      - the operator branch fits 500 characters at a 64-character id and a 32-character name, in
        both branches (see 2.13);
      - drop "Left as is…";
      - amend the docstring's *"`actor` is deliberately unread"* paragraph.

      The decision is unchanged.
- [ ] 4.2 `review_dispatch_refusal`: the author branch drops "clear the assignee", and both
      branches end with `own_review_remedy(task)`. That gives Land it for a `completed` task and the
      three exits for an `under_review` one, **without** rung 3's freeing clause (R3).
      - Add `own_review_remedy` to the existing module-level import from `...scheduler`
        (`agent_trigger.py:126`). There is no cycle: `scheduler` imports nothing from
        `agent_trigger`.
- [ ] 4.3 Test, operator PATCH on a completed task held by its author: 403, names Land it and
      `review_task_id`, and contains none of "clear the assignee", "approves" or "name that agent as
      the assignee" (REV).
      *Mutation:* restore the old sentence. The test must fail.
- [ ] 4.4 Test, agent PATCH through `/agent-actions/tasks/{id}` with a run token, by a non-author on
      a completed task held by its author. Expect 403, with "none of the task tools you are
      offered", and none of "clear the assignee", "assign a different reviewer", "no agent can",
      "changes who holds" or "API".
      *Mutation:* ignore `actor`. The test must fail.
- [ ] 4.5 Test, F334's shape: a queued review for an agent that recorded evidence during its own
      turn, delivered and refused. The entry's `waiting_reason` and `abandoned_reason` do not say
      the task "is assigned to" that agent, and the task's assignee is unchanged.
      *Mutation (REV):* restore "it is assigned to {assignee!r}" in the evidence branch. The test
      must fail.
- [ ] 4.6 Update any existing test asserting the old sentences, and list each one here when ticking.
      R3's grep found these fragment assertions, and D2's and D5's wording keeps every fragment, so
      each should pass unchanged. Confirm it:
      - `test_flow_fires_a_review_turn.py:357`, `test_reviewer_ladder.py:174` and
        `test_the_evidence_names_the_author.py:692`: `could not staff this step`;
      - `test_the_evidence_names_the_author.py:693` and
        `test_a_flow_names_what_it_cannot_staff.py:719`: `has worked on this task`;
      - `test_a_flow_names_what_it_cannot_staff.py:733`: `is the one that completed this task`;
      - `test_reviewer_is_not_the_author.py:82, 340`: `review it yourself`, as operator;
      - **two absence assertions:** `"completed" not in reason` at
        `test_a_flow_names_what_it_cannot_staff.py:720` and
        `test_the_evidence_names_the_author.py:694`. They constrain the wording. Neither remedy nor
        the freeing clause may contain the word "completed", and a holds clause never does,
        because `completed` is not in `LIVE_STATUSES`. On the second test's fixture, `WORKER` is in
        the author set through its bound run and reads "has worked on this task". `SILENT` reads
        "recorded no verdict". Both fragments still hold.

      **Amend three comments that state the old remedy in the present tense** (R3). After D5 each
      would be false about the guard. F78's behaviour, clearing then entering review, stays:
      - `api/v1/tasks.py:1259-1268`;
      - `schemas/tasks.py:124-127`;
      - the docstring of `test_reviewer_is_not_the_author.py::test_clearing_the_assignee_lets_the_operator_review_it_themselves`
        (`:377-378`);
      - **REV, two more:** `api/v1/agent_trigger.py:847-849` (*"already names both remedies and the
        cost of doing nothing"*) and `task_transition_service.py:405-406` (*"they clear or
        reassign `assignee` first, which is what the refusal asks for"*).
- [ ] 4.7 Test: the dispatch route's author refusal (`POST /agent/trigger` with `review_task_id`) on
      a `completed` task names Land it and does not contain "clear the assignee".
      *Mutation (REV):* restore "or clear the assignee to review it yourself". The test must fail.
- [ ] 4.8 Test: the same refusal on an `under_review` task that nobody holds, dispatched to its
      completer. It names approve, reject and revision_needed, and does **not** name Land it.
      *Mutation:* always emit the `completed` remedy. The test must fail.
- [ ] 4.9 (REV) The D9 refusal, *"Reassign the task if …"*, at `agent_trigger.py:494` and `:840`,
      becomes *"… Let the review in flight finish, or decide it yourself"* plus the `under_review`
      sentence of `own_review_remedy`. Test both sites: dispatch a second reviewer to a task under
      review by another. Expect 409, naming approve, reject and revision_needed, and not
      "Reassign".
      *Mutation:* restore one site's old sentence. The test must fail.

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
      - in FINDINGS, mark F353, F334, F365 and F367 `fixed <sha>`, and add a dated note to F352 that
        its visibility half shipped and its definition half waits on the operator.
