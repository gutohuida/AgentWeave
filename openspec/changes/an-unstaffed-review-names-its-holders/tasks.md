# Tasks — an unstaffed review names its holders

> **STOPPED AT REV, 2026-09-14. Do not build any task here.** The operator decided both questions
> on 2026-09-15 (`spec-queue/DECISIONS.md`, `### 2026-09-15, later` and the `F352-free` row):
> - **The split is approved and done.** Groups 3 and 4, 2.5, 2.5b, 2.12 and 2.13 moved to
>   `openspec/changes/a-refusal-names-a-remedy-that-works/`, renumbered there. **Do not build them
>   from this file — it is stale for them.** They are struck through below for that reason, not
>   removed, so a diff against `fb469e2`/`82b58df` still shows where they went.
> - **`F352-free` is decided: option (f), reachability, not (d) and not the (e) this file's
>   remaining tasks (1-2.4, 2.6-2.11, 2.14, 5) were written against.** (f) already shipped
>   (`4b59ee0`, archived `2026-09-15-a-task-nothing-will-move-holds-nobody`,
>   `hub/hub/scheduler.py:1138`). **Every remaining decision below (D1, D2's clause/prefix/budget
>   logic, D3, D6) needs re-deriving against (f) before any task here is built** — this file and
>   `design.md` still describe (e). That re-derivation is its own round, not done in this pass.
>
> 2.14 stays here (it always belonged to this half, REV 2026-09-14).

Findings: F352 (the visibility half only; stays open, now waiting on the re-derivation above, not
on an operator answer); F366 (stays open; D5's replacement in the sibling directory stops relying
on it, does not close it). R2 (2026-09-14) revised 1.2, 2.1-2.5, 2.7, 2.10, 4.1, 4.2, 4.4 and 4.7,
and added 1.4, 2.5b, 2.11, 2.12 and 4.8. R3 (2026-09-14) revised 2.3, 2.4, 2.6, 2.12, 4.2 and 4.6,
and added 2.9b. **F353, F334, F365 and F367 moved with groups 3-4/2.5/2.5b/2.12/2.13 to the
sibling directory** and are retired there, not here.

**Not a build day.** Tests, when this resumes, run under `py -3.11`. `black` needs
`--target-version py311`.

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
~~- [ ] 2.5~~ **MOVED 2026-09-15** to `a-refusal-names-a-remedy-that-works/tasks.md` task 2.1
      (Fit `JobRun.error_summary` at the model). Built there, not here.
~~- [ ] 2.5b~~ **MOVED 2026-09-15** to the same directory's task 2.2 (`_wedged_review_reason`'s
      title fit). Built there, not here. **This half's own tasks (2.6, 2.9, 2.9b, 2.11) still
      depend on that fit existing** — it is a model-level `@validates`, so it applies to every
      write regardless of which change added it, and the sibling directory builds first.
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

      *Mutation:* remove the bound (2.4) and the fit (sibling directory's 2.1, once built). The
      history route must fail, which proves the test reaches `JobRunResponse`.
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

      *Mutations:* (a) remove the sibling directory's title fit (its task 2.2), so the history
      still answers 200 but the remedy is cut; (b) remove the `@validates` as well (its task
      2.1), so the route answers 500.
~~- [ ] 2.12~~ **MOVED 2026-09-15** to `a-refusal-names-a-remedy-that-works/tasks.md` task 2.3.
      Built there, not here.
~~- [ ] 2.13~~ **MOVED 2026-09-15** to the same directory's task 4.10 (it tests D5's guard
      sentence, which moved with group 4). Built there, not here.
- [ ] 2.14 (REV) The divergence restaff returns `None` for a task whose status is no longer
      `completed` or `under_review`, at the same screen as `blocked` (`run_divergence.py:746`).
      `own_review_remedy` (built by the sibling directory's task 1.1 — depends on it landing
      first) asserts one of the two statuses. Test: the operator moves a task to `revision_needed`
      while its review run is live, and the run then ends without a verdict. No `review_unstaffed`
      is recorded and no reviewer is staffed.
      *Mutation:* drop the new screen. The test must fail.

## 3. ~~Once per task (design D4)~~ MOVED 2026-09-15

Groups 3 and 4 (all of `own_review_remedy`'s once-per-task and refusal-wording tasks) moved
wholesale to `a-refusal-names-a-remedy-that-works/tasks.md` groups 3 and 4, renumbered 3.1-3.3 and
4.1-4.10. Built there, not here. See that directory for the full text.

- [ ] 4.1 `_guard_reviewer_is_not_the_author`, both branches:
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
      - sync the `agent-flows` delta into `openspec/specs/` (the only one still owned by this
        directory — `agent-loops` and `task-lifecycle-governance` moved with the split and are
        synced by the sibling directory instead);
      - move the change to `archive/<date>-an-unstaffed-review-names-its-holders`;
      - in FINDINGS, add a dated note to F352 that its visibility half shipped (`F352-free`
        decided (f), and the rung-3 half here re-derived and built against it). F353, F334, F365
        and F367 are marked `fixed <sha>` by the sibling directory instead.
