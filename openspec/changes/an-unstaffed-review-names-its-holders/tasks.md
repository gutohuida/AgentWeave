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

**R5, 2026-09-19 — every task in this group was rewritten. The originals specified the pool as
*"holds no live task"*, which has been wrong since `4b59ee0` and would have reverted it. Read
`design.md` `## Round 5`, finding `R5-0`, before starting.**

- [x] 1.1 Add `AgentAvailability`, `Holding` and `_roster_availability(session, project_id)` to
      `hub/hub/scheduler.py`:
      - one record per non-archived agent, in name order;
      - `has_runner`, `running`, **`held`**, and `holdings` as
        `Holding(task_id, status, loop_id, reachable)`, ordered by task id;
      - **R6: `held` is `agents_held(session, project_id)`** (`hub/hub/provider_allowance.py`),
        which `_agents_that_are_free` ORs into its `running` set at `scheduler.py:1122`. It is a
        separate field, never folded into `running`, because clause 4 must tell them apart.
        Omitting it reverts `a-spent-allowance-holds-the-queue` D6 exactly as the pre-R5 D1
        reverted `4b59ee0`.
      - `LIVE_STATUSES` is the **band** a holding must be in, not the test. `reachable` is
        `loop_id in live or (task_id, assignee) in queued`, computed from the same two reads
        `_agents_that_are_free` does today (`scheduler.py:1123-1150`) — **not** a second opinion
        about reachability, which is the thing D1 exists to prevent.
      - Unreachable holdings stay on the record and are printed by nothing (D1's R5 note).
- [x] 1.2 Re-express `_agents_that_are_free` as the projection
      `has_runner and not running and not held and not any(h.reachable for h in holdings)`, and
      keep its docstring's argument **including its reachability paragraph and its D6 paragraph**.
      - **R7, 2026-09-19 — this bullet's caller list was wrong in every particular and is
        replaced.** It read *"Its three callers keep the projection: `scheduler.py:298`, `:1262`
        and `:1298` (R5-7: `:1137` in the original is stale)"*. Measured at `2f0ef0d`,
        `grep -n "await _agents_that_are_free("` returns **`:348`, `:1263`, `:1444`** and nothing
        else. Of the three numbers given, `:298` is a docstring line inside `_loop_has_open_task`,
        `:1298` is a `where` clause inside `resolve_reviewer`'s `roster_held` query, and only
        `:1262` is within a line of a real call. R5-7 corrected four citations elsewhere and closed
        with *"re-verify the whole list at implementation time rather than trusting this round's
        four"* — this is that re-verification, and the list did not survive it.
      - **It was also self-contradictory.** `:1262` is `resolve_reviewer`'s pool walk, which the
        next bullet says does **not** keep the projection. The count is two, not three:
      - **`_loop_flow_busy_reason` (`scheduler.py:348`) and `decide_firing` (`scheduler.py:1444`)
        keep the projection**, unchanged, calling `_agents_that_are_free` exactly as they do today.
      - `resolve_reviewer` (`scheduler.py:1263`) instead reads `_roster_availability` **once**, and
        derives both rung 2's pool and rung 3's records from that one read.
      - Line numbers move. **Locate all three by `grep -n "await _agents_that_are_free("` rather
        than by the numbers above**, and treat a count other than 3 as a signal that the tree has
        moved further than this task knows.

      The existing pool tests pass unchanged: `test_reviewer_ladder.py`, `test_flow_width.py`,
      `test_a_task_waits_while_its_run_waits.py::…3.4`, the busy guard, **and every test in
      `test_a_task_nothing_will_move_holds_nobody.py`**. That last file is the regression guard for
      this group: if `test_the_loopengine_shape_staffs_its_review` goes red, the projection has
      reverted (f) and the fix is here, not in the test.

      **Build note, 2026-09-19 night.** `grep -n "await _agents_that_are_free("` at the tree this
      was built against returned exactly `:348`, `:1263`, `:1444` — R7's prediction held, not the
      four-numbers-earlier text. `resolve_reviewer` now calls `_roster_availability` once and
      derives both the rung 2 walk and the roster-held check from that one read; `_loop_flow_busy_reason`
      and `decide_firing` are untouched. Full regression named above plus
      `test_actor_aware_claimability.py` and `test_a_loop_does_not_staff_its_own_review.py`:
      124 passed.
- [x] 1.3 Test: an agent with no runner, one running with nothing held, one holding two **reachable**
      tasks, one holding only **unreachable** tasks, and one free each get the right record; the
      pool is exactly the free one **and the unreachable-holder**.
      *Mutation:* drop `Task.status` from the holdings select (or the `LIVE_STATUSES` filter). The
      test must fail.
      *Mutation:* make `reachable` always `True` — i.e. the pre-`4b59ee0` rule. The test must fail,
      and so must `test_the_loopengine_shape_staffs_its_review`.
      *Mutation (R6):* drop `held` from the projection. The test must fail, and so must
      `hub/tests/test_a_held_agent_is_busy.py::test_a_held_agent_is_not_free`.

      **Observed, 2026-09-19 night.** Named test is
      `test_the_roster_read_gives_each_agent_the_right_record`
      (`hub/tests/test_a_task_nothing_will_move_holds_nobody.py`). The described fixture alone did
      not catch the `Task.status` mutation — every fixture task already used a `LIVE_STATUSES`
      member, so dropping the filter changed nothing observable. Added a sixth agent (`NONLIVE`)
      holding a `completed` task inside the same live loop as the reachable-holder, so dropping the
      filter pulls it into `holdings` and the pool. All three mutations applied and reverted by
      hand: (1) dropped the `Task.status.in_(...)` clause — this test failed on `records[NONLIVE]
      .holdings == ()`; (2) set `reachable=True` unconditionally — this test failed on
      `UNREACHABLE`'s holdings, and `test_the_loopengine_shape_staffs_its_review` failed too; (3)
      dropped `and not record.held` from `_agents_that_are_free`'s projection — this test failed on
      the pool set, and `test_a_held_agent_holding_no_task_is_not_free` failed too (the exact name;
      `test_a_held_agent_is_not_free` above is stale). Reverted each mutation before moving on;
      final state is green (124 passed, see 1.2's note).
- [x] 1.4 Test: `resolve_reviewer` reads the roster once per call. Count the executed `Task.assignee`
      selects with a SQLAlchemy `before_cursor_execute` listener on the real test engine.
      *Mutation:* call `_agents_that_are_free` for rung 2 and `_roster_availability` for rung 3. The
      test must fail.

      **Observed, 2026-09-19 night.** Named test is `test_resolve_reviewer_reads_the_roster_once`.
      A two-agent fixture where the second agent is genuinely free does not reach the roster-held
      read at all -- rung 2 returns before it. Staged instead as a single-agent project (the
      author, excluded), which reaches rung 3 by the general rule `resolve_reviewer`'s own
      docstring names as D4's test of the ladder. Mutation applied by hand (rung 2 walking
      `_agents_that_are_free` and a second, independent `_roster_availability` call for the
      roster-held check): this test failed, two selects naming `tasks.assignee` instead of one.
      Reverted; final state green.

## 2. What rung 3 says (design D2, D3)

> **R6 — ORDERING CONSTRAINT, and it is real. Do task 2.14 FIRST, before 2.3.**
> `own_review_remedy` ships with a bare `assert task.status in ("completed", "under_review")`
> (`scheduler.py:1916-1919`). The screen that keeps a diverged non-review task away from it is
> **2.14**, and it has **not** shipped — `run_divergence.py` carries no `under_review` guard and
> calls `resolve_reviewer` at `:441-447` with no status check. So the moment 2.3 makes rung 3 call
> the helper, an operator who moves a task to `revision_needed` while its review run is live turns
> a surfaced reason into an unhandled `AssertionError` inside the scheduler. In an unattended
> window that is the failure to expect. The list below is otherwise in its original order.

- [ ] 2.1 Change `resolve_reviewer`'s `exclude` to `Mapping[str, str]` (agent → clause) and remove
      `excluded_because`. Rung 1b reads `exclude[resolution.agent]`.
      - `decide_firing` (`scheduler.py:1550-1584`) builds the mapping from exactly the clauses it
        passes today.
      - Update every call site. A missed one fails only where it reaches a named exclusion, and CI
        runs no mypy over `hub/`, so grep `exclude=` before ticking. The sites are:
        - `test_reviewer_ladder.py:97, 121, 146, 159, 170, 189, 242, 257, 283, 322, 347, 372, 383`
          — **thirteen** sites. R6 corrected six of the numbers R1 gave and found a thirteenth the
          list never had;
        - `test_a_flow_names_what_it_cannot_staff.py:471, 478`;
        - **`test_a_held_agent_is_busy.py:377, 388, 401` (R6) — missing from every earlier round.**
          All three pass `exclude={AUTHOR}`, a set, and all three reach rung 3, so a `Mapping`
          signature makes them raise `TypeError` at `exclude[name]`;
        - `scheduler.py:1738-1745` and `run_divergence.py:441-447`.
      - **R6: re-verify every line above before editing.** This list has been wrong at three
        consecutive rounds. Grep for `exclude=` and count; do not trust the numbers.
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
      - **R5:** the holds clause prints only **reachable** holdings, and each as
        `"{name} holds {id} ({status})"`. A holding that is not reachable is not a reason and must
        not be named. **R6 removed the loop id** — it existed only to aim the archive remedy, which
        R6 removes, and it printed `in None` for a holding reachable only through the queued arm.
      - **R6: clause precedence is excluded, no runner, holds, HELD, running** — five clauses. The
        held clause is `"{name} is waiting for its provider's usage limit to reset"`. It is
        required by a shipped SHALL in `openspec/specs/agent-flows/spec.md`, and without it a held
        agent is reported as running a turn, which is false.
      - after the helper's sentence, rung 3 itself appends " Rejecting held tasks that are no
        longer wanted can free their agents." — **a new sentence, space and capital, not a `;`**
        (R6-8). `own_review_remedy` already ends in a period, so the `;` every round wrote
        produces `…yourself.; rejecting…`. Assert the joined string in the test, not the two
        halves separately: that is why five rounds missed it.
        The dispatch refusal (4.2) does not append this clause at all.
      - **R6: the remedy names rejecting, and nothing else.** It must never suggest pausing (a
        paused loop still holds, `scheduler.py:1084-1085`) and must never claim that ending or
        archiving a loop frees an agent (reachability is an OR; the queued arm survives an
        archive). Both would be fresh instances of F353.
- [ ] 2.4 Bound the reason to 500 characters. If the whole sentence fits, use it. Otherwise add
      clauses in name order while the prefix, the clauses, the tail
      "; and N more agents are excluded, busy or unbound" and the remedy still fit.
      - A holds clause that would not fit is retried with two named tasks, then one, counting the
        rest as "and N more". Only then is its agent left to the tail (R3).
      - **R6: there is no loop id to drop any more.** The fallback is the pre-R5 one: three named
        tasks, then two, then one, then the agent falls to the tail.
      - **R6, do this FIRST: re-measure D2's character budget table.** R5 lengthened clause 3 and
        the remedy without recomputing it, and the review measured the flagship shape at 559/589
        against a 500 bound. R6 removed both additions, which should restore it — but clause 4 adds
        a per-agent string that never existed, and "shorter than before" is not a measurement. The 500 bound is enforced at the
        model since `fit_error_summary` shipped (`models.py:1336-1348`), so an over-long reason is
        now silently truncated rather than loudly wrong — which is exactly the failure mode a stale
        budget table produces.
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

      > **R6 — R3's `loop_id` NULL fixture is now self-defeating and must be replaced.** Under (f)
      > a holding with a NULL `loop_id` and no queued turn is **unreachable**: it holds nobody, so
      > R5-3 forbids naming it *and* the firing never reaches rung 3 at all —
      > `test_a_task_nothing_will_move_holds_nobody.py:307-322` stages exactly this shape and
      > asserts `decision.unstaffed == ()`. As written this test asserts three mutually exclusive
      > things and its three mutations cannot fail, because the code under test is never entered.
      >
      > **Replace the fixture:** every non-author's held task is **reachable** — carry the loop's
      > own `loop_id`, or have a queued turn naming `(task, assignee)`. The author's extra live
      > task (REV's addition, below) stays as it is. Then re-check R3's own caveat in the next
      > paragraph against the new fixture: an idle assignee's in-loop `in_progress` task is
      > *walked*, so it may be claimed as a selection rather than stalling. If it is, stage that
      > agent as `running` instead and say so — the point of the test is the sentence, not the
      > route to it.
      >
      > The same question is unanswered for **2.9, 2.9b, 2.10 and 2.11**, which never state whether
      > their holdings are reachable. Answer it in each before writing them: an unreachable holding
      > names nobody, which makes the twelve-agent length test vacuous.

      A held task in the
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
      *Mutation (R6):* make every held task unreachable. The test must fail — and if it does not,
      the fixture is still the one R6 replaced.
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
      **R6: this task runs BEFORE 2.3** — see the ordering note at the top of this group. Its
      citation has drifted: the `blocked` screen is at `run_divergence.py:753-754`, not `:746`.
- [ ] 2.15 (R6) Test: an agent whose queue is held, running no turn and holding nothing, is named
      by clause 4 and **not** by clause 5. Assert the reason contains "waiting for its provider's
      usage limit to reset" for that agent's name, and does not say it is running a turn.
      *Mutation:* fold `held` into `running` on the record. The test must fail.
      This is the shipped SHALL at `openspec/specs/agent-flows/spec.md` — *"the reason surfaced
      SHALL name the hold among the grounds"* — and it is the requirement D2's pre-R6 clause list
      silently dropped.
- [ ] 2.16 (R6) Update the three shipped tests in `hub/tests/test_a_held_agent_is_busy.py` that
      D2 and D3 necessarily break, and say in each commit why the old assertion no longer holds:
      - `:370-381` asserts the old blanket clause as a substring — rewrite against clause 4;
      - `:384-390` is `assert choice.reason == _TODAY`, **exact equality** with today's whole
        sentence. D2 replaces that sentence, so this assertion must be re-based on the new one.
        R3's claim that *"the existing tests assert fragments that D2's wording keep"* is false
        against today's tree, and `tasks.md`'s "existing pool tests pass unchanged" list never
        named this file;
      - the `error_summary` fit test — re-check it against the re-measured budget (2.4).
      **Do not weaken these to substring checks to make them pass.** An exact-equality test on the
      operator's only surface is deliberate; re-base it and keep it exact.
- [ ] 2.17 (R6) Test: the rung-3 reason never contains "pause", and never claims that ending or
      archiving a loop frees an agent. One test over a fixture with holdings in another live loop —
      the case R5 wrote the archive remedy for.
      *Mutation:* restore R5's archive clause. The test must fail.

## 3. ~~Once per task (design D4)~~ MOVED 2026-09-15

Groups 3 and 4 (all of `own_review_remedy`'s once-per-task and refusal-wording tasks) moved
wholesale to `a-refusal-names-a-remedy-that-works/tasks.md` groups 3 and 4, renumbered 3.1-3.3 and
4.1-4.10. Built there, not here. See that directory for the full text.

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

- [ ] 6.0 **R5 regression guard, run this before anything else and again at the end:**
      `py -3.11 -m pytest hub/tests/test_a_task_nothing_will_move_holds_nobody.py -q`.
      It must be green before you start and green when you finish. If
      `test_the_loopengine_shape_staffs_its_review` goes red, the availability projection has
      reverted `4b59ee0` (design R5-0) — fix the projection, never the test.
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
        it received, read from its tool result;
      - **R5, the two new claims, driven not asserted:** stage a holder whose only tasks are
        unreachable (no live loop, no queued turn) and confirm it is *not* named in the reason and
        *is* in the pool; then archive the holding loop through the operator's own control
        (`POST /jobs/{id}/archive`) and confirm the next firing staffs the review. The second is the
        remedy the sentence now prints, and a remedy this change has not watched work is the defect
        it exists to repair.

      Leave no job enabled.
- [ ] 6.5 (R6) Re-derive `test-guide.md`. It is untouched since R4: its own header says it needs
      re-deriving, it still calls the OPERATOR QUESTION open, and its A6 claim and human item 3 are
      written against option (e). Neither R5 nor R6 touched it. It must reflect the five clauses,
      the reachability filter, the removed archive remedy, and the hold clause.
- [ ] 6.4 Archive:
      - sync the `agent-flows` delta into `openspec/specs/` (the only one still owned by this
        directory — `agent-loops` and `task-lifecycle-governance` moved with the split and are
        synced by the sibling directory instead);
      - move the change to `archive/<date>-an-unstaffed-review-names-its-holders`;
      - in FINDINGS, add a dated note to F352 that its visibility half shipped (`F352-free`
        decided (f), and the rung-3 half here re-derived and built against it). F353, F334, F365
        and F367 are marked `fixed <sha>` by the sibling directory instead.
      - **R6: do not write that this change "leaves F352 open".** The pre-R6 `Impact` said so,
        justified by the operator question being open; it is closed.
