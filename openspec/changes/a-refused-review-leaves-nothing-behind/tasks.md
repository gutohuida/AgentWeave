# Tasks — a refused review leaves nothing behind

Implementation belongs to a night window. No task here is complete because this plan exists. Only
verified implementation closes one.

**This change is Python-only.** No `hub/ui` file changes, so the committed bundle in
`hub/hub/static/ui` is **not** rebuilt. The Python lint set **is** required (§7).

**File isolation.** This change must not touch `hub/hub/mcp_server.py`,
`hub/tests/test_permission_approver.py` or `docs/reference/permission-postures.md`. Those belong to
`a-url-is-not-a-path`, which the same night builds. The two changes share only
`scripts/drive/FINDINGS.md`, each in its own findings' sections.

**The tests are written first, and the tree stays green at every commit.** §1 writes the new tests
against the **unmodified** tree. It marks every assertion that must move with
`xfail(strict=True, reason="a-refused-review-leaves-nothing-behind §2")` or `§3`. §2 and §3
remove those markers as the code lands. A strict xfail that starts passing early is a failure: a leg
may not change answer before its mechanism exists.

**An xfail marks a whole test, never one assertion (R2).** A test that asserts what holds today and
what must move, under one strict xfail, stops at the first failing assertion, so whatever follows it
is never run and whatever precedes it is pinned by nothing. Where a task below says a part *passes
today* and a part is *xfail*, write **two tests**: a pin that asserts only what holds today, and an
xfail that asserts only what must move.

## 1. Pin the defect before the fix

All in a new `hub/tests/test_a_refused_review_leaves_nothing_behind.py`. The module docstring cites
F319, F320 and this change's `design.md` D1 and D4. Each test's docstring names the mutation in §4
that must fail it.

- [x] 1.1 **Fixtures.** Reuse `_roster` (`test_a_flow_names_what_it_cannot_staff.py`) and
  `_init_repo` (`test_agent_trigger.py`). Capture the real `worktrees.ensure_review_checkout` at
  import time, as `test_review_turn.py:35` does, and restore it with `monkeypatch` where a leg needs
  the real one. Patch `hub.launchability.shutil.which` so the probe finds `claude`.
  - The task is **operator-completed**: `pending` is created, then `in_progress` and `completed` are
    applied through `apply_transition` as `operator()`.
  - One evidence row carries a footprint naming a commit. It is operator-kind for the B and T legs
    and agent-kind (the reviewer) for leg A.
  - A `_snapshot(task_id)` helper returns `(status, assignee, transition count)`.
  - **Every leg asserts the snapshot after equals the snapshot taken before the dispatch**, not a
    hard-coded `("completed", None)`. The requirement is *as it was*, and a fixture change must not
    turn this into a test of a constant.
- [x] 1.2 **B0, B1, B2 on the scheduler path**, parametrized. Queue an operator review entry
  (`review_task_id` set) for a reviewer that recorded nothing, then `schedule_agent` once.
  - B0: `tmp_path` is not a repository.
  - B1: a repository whose evidence names `"e" * 40`, with the real `ensure_review_checkout`.
  - B2: a repository at `HEAD`, with `.agentweave/reviews/<reviewer>/x.txt` a plain directory, and
    the real `ensure_review_checkout`.

  Assert all of these. The snapshot is unchanged. There is no `Run`. The entry is `queued` with
  `delivery_attempts == 1`. Its `waiting_reason` equals `ScheduleResult.waiting_reason` and contains
  the refusal's distinguishing words (*"not a git repository"*, *"is not present in this
  repository"*, *"refusing existing path"*). `ScheduleResult.refusal.status_code == 409`. Two tests
  per leg: `…_records_the_refusal` holds everything but the snapshot and passes today (measured,
  `design.md` D0); `…_leaves_the_task_as_it_was` holds the snapshot and the absence of a `Run`, and
  is xfail(§2).
- [x] 1.3 **B1 through the route.** `POST /agent/trigger` names the reviewer and `review_task_id`.
  Assert all of these:
  - The answer is `409`, and its `detail` names the commit.
  - The snapshot is unchanged (xfail §2).
  - The entry is `withdrawn`.
  - An `EventLog` row `queue_entry_withdrawn` exists.

  Then `POST` again, naming a **different** reviewer. Its `detail` must not contain
  `"already under review"` (xfail §2). It may still be refused for the commit.

  As two tests: the `409`, its `detail` and the withdrawn entry with its event are a pin; the
  snapshot and the second reviewer's answer are xfail(§2).
- [x] 1.4 **Leg A, the timing gap, through the route.**
  1. Register agent X with a runner.
  2. Insert a `Run(status="running")` row for X.
  3. `POST /agent/trigger` naming X as reviewer. It answers `200` and `queued`, because the
     route's check passes: X has recorded nothing yet.
  4. Add an **agent-kind** evidence row by X for the task, with `review_state="awaiting"`.
  5. Set the run `completed`.
  6. Call `schedule_agent` `DELIVERY_ATTEMPT_LIMIT` times.

  After **each** pass the snapshot is unchanged (xfail §2), and the entry's `waiting_reason`
  contains *"recorded evidence for this task"*. After the last pass the entry is `withdrawn`, its
  `abandoned_reason` contains the guard's sentence, and a `queue_entry_abandoned` row exists. The
  §3.4 guard is **not** patched. It is what refuses.

  As two tests sharing one fixture: the `waiting_reason` after each pass, the withdrawal and the
  event are a pin; the snapshot after each pass is xfail(§2).
- [x] 1.5 **Leg T, a deferral after the staging.** Delete `HUB_URL` from the environment and make
  `agent_trigger.bound_address.get` return `None`. The default `ensure_review_checkout` stub is
  fine. Queue the review and call `schedule_agent` once. The snapshot is unchanged (xfail §2). The
  entry is `queued` with `delivery_attempts == 0`. `terminal_failure is False`, and `refusal is None`
  (a pin: these pass today).
- [x] 1.6 **F320 at the scheduler**, with `trigger_agent_directly` patched (as
  `test_a_delivery_attempt_means_a_delivery.py:29` does). The mock records the entry ids it is
  called with. **It raises `RuntimeError("test guard")` on any call past the number the case
  expects**, so a loop that fails to stop fails the test instead of hanging it: `pytest-timeout` is
  not installed (DEAD-ENDS). Head H is a review entry at `DELIVERY_ATTEMPT_LIMIT - 1` attempts, in
  conversation C1.
  - (a) Entry B waits in C2. The mock refuses H request-level and returns a `TriggerAgentResponse`
    for B. Expect two calls, the second carrying B. H is `withdrawn`, and the result's `response` is
    B's (xfail §3).
  - (b) Like (a), except the mock refuses B too. Expect two calls. B is `queued` at 1 attempt, not
    3 (xfail §3).
  - (c) The mock raises a **transient** refusal. Expect one call, and H's attempts unchanged. This
    passes today, and it is a pin, not an xfail.
  - (d) Three entries, each at `LIMIT - 1`, in three conversations. The mock refuses all three.
    Expect three calls, all three `withdrawn`, and a result whose `waiting_reason` is the refusal and
    not `"queue is empty"` (xfail §3).
  - (e) H alone at `LIMIT - 1`, refused. The result's `waiting_reason` is the refusal and
    `terminal_failure` is `True`. This passes today, and it is a pin: it keeps §3's result rule from
    regressing the ordinary case.
  - (f) **The rider (R2, `design.md` D4).** Set the project's `turn_delivery_cap` to 2. In one
    conversation, in this order: H1, a review entry at `LIMIT - 1`; M, a plain message at 0; H6, a
    review entry at `LIMIT - 1`. The mock refuses every call, request-level, and allows three. Assert
    only that H1 is `withdrawn` and M is `queued` at **1** attempt. This passes today (one call,
    `[H1, M]`; H6 is not reached and stays at `LIMIT - 1`), and it is a pin. With the loop H6 is
    reached and withdrawn too, which (d) already covers, so (f) does not assert H6. Against R1's
    loop without the once-per-pass rule (f) fails: R2 measured M carried
    by `[H1, M]`, `[M, H6]` and `[M]` and `withdrawn` at 3 in one pass.
  - (g) **The pass stops at a rider refused alone (R3, `design.md` D13).** Default cap. In C1: H1, a
    review entry at `LIMIT - 1`, then M, a plain message at 0. In C2: N, a plain message at 0. The
    mock refuses any call that carries H1 or M, request-level, and returns a started response for a
    call carrying only N; it allows two calls. Expect exactly two calls, `[H1, M]` then `[M]`; H1
    `withdrawn`; M `queued` at **1**; N `queued` at **0** with no turn (xfail §3: today the pass makes
    one call). This is the case the requirement's stop list names as *"refused and gave up on
    nothing"*: N waits behind M as it waits behind any refused head below its limit. Measured on R2's
    prototype: calls `[['H1', 'M'], ['M']]`, rows `H1 ('withdrawn', 3)`, `M ('queued', 1)`,
    `N ('queued', 0)`.
- [x] 1.7 **F320 through the route.** Seed H as in 1.6. Then `POST /agent/trigger` a plain message
  to the same agent, which opens a new conversation. The mock refuses H and returns a started
  response for the route's own entry. The answer reports that conversation as started, with
  `status == "running"` (xfail §3). Today it answers `queued`, *"queued behind other input"*.
- [x] 1.8 **The one-caller pin.** Parse every `hub/hub/**/*.py` with `ast` and collect each `Name`
  node, `Attribute` node and import `alias` spelled `trigger_agent_directly`. That covers a call, a
  module-qualified call, an import under another name, and a reference passed as a callable, and it
  ignores the docstrings and comments that name the function. Outside `agent_trigger.py` (the `def`
  itself), the only file may be `turn_scheduler.py`. A text search for `trigger_agent_directly(`
  misses `partial(trigger_agent_directly, …)` and anything imported `as` another name. The test's
  docstring says why: `design.md` D2(e), where the rollback lives in the one caller. This passes
  today.
- [x] 1.8a **An open divergence is not closed by a refused review (R2, `design.md` D8).** Give the
  B1 task an open `RunDivergence` row before the dispatch, **built through the product, not
  inserted** (R3 measured this recipe, `design.md` D13): create the task `pending` and a
  `Run(status="running")` for a third agent, call `bind_run_to_task` (it moves the task to
  `in_progress`, origin `runtime`), apply `completed` as `operator()` while the run is still
  running, set the run `completed`, and call `evaluate_run_end(run_id)`. That returns a divergence
  with `task_status_at_end == "completed"`, `outcome == "surfaced"` and `resolved_at` NULL. Take the
  snapshot after that. After the refused
  `schedule_agent`, the row's `resolved_at` is still `NULL` and no `run_divergence_resolved`
  `EventLog` row exists (xfail §2: today the committed staging closes it). Capture
  `sse_manager.broadcast` and record in the docstring, without asserting it, that the broadcast
  still escapes. That is D8's accepted residual, and §8.5 files it.
- [x] 1.8b **Input withdrawn while its turn is dispatched is not counted (R3, F328, `design.md`
  D13).** One plain entry at `LIMIT - 1`. The patched trigger withdraws it through
  `inbound_queue.withdraw_entry` in a session of its own, then raises a request-level refusal; it
  allows one call. Assert the entry is `withdrawn` with `delivery_attempts == LIMIT - 1`, an empty
  `abandoned_reason`, and no `queue_entry_abandoned` row (xfail §2). Measured today and on R2's
  prototype: `attempts=3`, `abandoned_reason` *"delivery failed 3 times (refused); the Hub stopped
  retrying"*, one `queue_entry_abandoned`. With 2.1's `state == "queued"` filter: `attempts=2`, no
  reason, no event. **The docstring must say this covers only a dispatch that holds no database
  lock.** A real review dispatch holds the write lock while it records the reviewer, so a
  withdrawal lands after the re-read and is still counted (pre-approval review, test O2). F328 is
  narrowed, not closed (8.5a).
- [x] 1.9 Run §1 against the unmodified tree. Every xfail must xfail and every pin must pass.
  **Any other outcome means the test is wrong, not the code.** Stop, re-measure with
  `testbed/scratch/r1f319/test_zz_r1f319_scratch.py`, and record what differed here. Commit §1 alone,
  green.

  **Actual (night r1-pin, 2026-09-13, Windows, `py -3.11`, on `ab49909`'s product code).** The file
  is 11 pins and 13 strict xfails: 11 passed, 13 xfailed, 20 s. With the baseline chunk: 298
  passed, 1 skipped, 13 xfailed, 1m38s. Under `--runxfail` every xfail fails on the value the
  design measured and on nothing else:
  - B0, B1, B2, 1.3 and T: `('under_review', 'rr-reviewer', 3)` against `('completed', None, 2)`;
  - A: `('completed', 'rr-reviewer', 2)` after each of the three passes;
  - 1.6(a), (b), (d) and (g): one call where two or three are expected;
  - 1.7: `status == "queued"`;
  - 1.8a: `resolved_at` set;
  - 1.8b: `('withdrawn', 3)` against `('withdrawn', 2)`.

  Nothing differed from the scratch measurements, so the scratch was not re-run. Departures, all
  additive:
  - Every marker carries `raises=AssertionError`, so a fixture that fails to build, or a guard
    `RuntimeError`, is a failure and not the expected one.
  - 1.8a's fixture has its own pin, `test_the_divergence_fixture_is_built_through_the_product`, so
    the xfail can fail only on what it asserts. `RunDivergence` is read by `id` with a `select`,
    because its primary key is `sequence`.
  - 1.8's scanner is checked first against an import `as`, a `partial(...)` and an attribute
    call, and against a docstring and a comment, so that the pin is not vacuous.
  - 1.1 read: leg A's commit-naming evidence row is operator-kind, as for B and T. The route's
    `commit_for_task_review` needs it at step 3. The agent-kind row by the reviewer is the one 1.4
    adds at step 4.
  - B1, B2, T and 1.8a use `_init_repo(tmp_path / "repo")` with `bind_project_workspace`, as
    `test_review_turn.py` does. B0 keeps the default `tmp_path` root, which is not a repository.

## 2. The rollback (F319)

- [x] 2.1 In `hub/hub/turn_scheduler.py`, capture `selected_ids` and `conversation_id` immediately
  before the `trigger_agent_directly` call. Make `await db.rollback()` the **first** statement of
  `except TriggerAgentError`. Then:
  - re-read `selected` with `InboundQueueEntry.id.in_(selected_ids)` **and
    `InboundQueueEntry.state == "queued"`**, in the captured order (R3). An entry the operator
    withdrew while the dispatch ran is then neither counted nor given up on, and the branch records
    a refusal only on input that is still waiting (F328, 1.8b). Without the filter the re-read is
    not load-bearing at all: R3 dropped it from R2's prototype and no test changed (`design.md` D13);
  - re-read `entries` with `queued_entries(db, project_id, agent)`;
  - pass `conversation_id` wherever `conversation.id` was read in the branch.

  Everything after that is unchanged: the `waiting_reason` write, both commits, the events, and
  `TurnRefusal` (`design.md` D1, D3).
- [x] 2.2 Rewrite the comment that opens the branch (today `:340-346`). It should say that the
  dispatch's staging is discarded **before** anything is recorded, and why: F319. It should also say
  that the refusal's words are written after the rollback, so F97's reason for this commit still
  holds. Keep F97's paragraph and add to it. Do not replace it.
- [x] 2.3 Correct the comment at `hub/hub/api/v1/agent_trigger.py:788-793`. A refusal abandons the
  staging because `turn_scheduler.schedule_agent`, the one caller, rolls back before it records the
  refusal. Name this change, and name the one-caller test (§1.8). **Comment only. No code in this
  file changes.**
- [x] 2.4 Remove the §2 xfail markers from 1.2 to 1.5, 1.8a and 1.8b.
- [x] 2.5 Update the docstrings of `test_dispatching_the_evidence_author_as_reviewer_is_refused_before_the_turn`
  (`test_the_evidence_names_the_author.py:474-480`) and
  `test_the_direct_dispatch_refuses_the_evidence_author_before_the_checkout` (`:517-520`). Each
  should stop saying the product path commits the staging, and should name §1.4 as the test that
  shows it no longer does. Change no assertions.

  **Actual (night r2-rollback, 2026-09-13, Windows, `py -3.11`).** Six `@MOVES_IN_2` decorators
  cover eight tests, because 1.2 is parametrized three ways. All six are removed, along with the
  marker's now-unused definition. The new file gives 19 passed and 5 xfailed. The five xfails are
  the `MOVES_IN_3` tests.

  **2.5 needed one more sentence than the task names, and it was measured.** The first docstring
  said the §3.5 test's *holder* assertion is what fails when §3.5 is removed. On the fixed tree that
  is no longer true. It was measured in a throwaway worktree carrying this section's diff with the
  route's `review_dispatch_refusal` call deleted. The task reads back `("completed", None)`, because
  the rollback now discards the staged assignee. The test still fails, but at `:505`, on the queue
  (`['entry-…'] == []`): the request left an entry behind, and the route's refusal never creates one.
  So §3.5 is still load-bearing for that test, on a different assertion, and the docstring now says
  which. No assertion changed.

## 3. The pass goes on (F320)

- [x] 3.1 Split `schedule_agent`'s body into one attempt, `_attempt_turn(db, project_id, agent)`. It
  returns a small frozen dataclass with four fields:
  - `result`, the `ScheduleResult`;
  - `attempted`, whether `trigger_agent_directly` was called;
  - `gave_up`, the entries set `withdrawn` by this attempt;
  - `nothing_queued`, set only by the empty-queue early return.

  `schedule_agent` keeps the lock and the session and loops. It stops unless `gave_up` is
  non-empty. Bound the loop at `len(initial queued entries) + 1` attempts, counted once when the
  pass begins, and state D4's argument that the bound is never reached in the comment beside it.
- [x] 3.1a **Count each entry at most once per pass (R2, `design.md` D4).** `schedule_agent` holds a
  set of the entry ids counted in this pass and hands it to every attempt. The counting loop skips
  an entry already in the set: it still gets the refusal's words as its `waiting_reason`, and it is
  neither counted nor given up on again. So an attempt can give up only on entries it counted, and
  one pass raises an entry's `delivery_attempts` by at most one, which is what a single pass does
  today. The comment names F114 and the measured rider case. 1.6(f) must still pass.
- [x] 3.2 The result rule of D5, keyed on `nothing_queued`, **not** on the string
  `"queue is empty"`. Where the last attempt has `nothing_queued` and an earlier attempt gave up,
  return that earlier attempt's result.
- [x] 3.3 Rewrite the comment at `:493-497` (*"the next tick tries again"*). No tick exists. A
  transient refusal waits for the run-end re-drain (`agent_trigger.py:2422-2451`) or an operator
  action. At the abandonment paragraph (`:407-413`), add that the pass then goes on to the input
  behind, and why: F320.
- [x] 3.4 `hub/tests/test_a_blocked_workspace_counts_where_input_could_run.py:227`: change the
  expectation to `[("withdrawn", DELIVERY_ATTEMPT_LIMIT), ("queued", 1)]`. Add one sentence to its
  docstring: the pass that gives up on the head now attempts the entry behind it, and the mock
  refuses that one too (`design.md` D6). **This is the only existing assertion that changes.** If a
  second one fails, stop and record it in `design.md` D6 before changing it.
- [x] 3.5 Remove the §3 xfail markers from 1.6 and 1.7.

  **Actual (night r4-loop, 2026-09-13, Windows, `py -3.11`).**
  - **3.1.** `_attempt_turn(db, project_id, agent, counted)` returns `_Attempt(result, attempted,
    gave_up, nothing_queued)`, a frozen dataclass. `schedule_agent` keeps the lock and the session,
    reads `len(queued_entries(...)) + 1` once when the pass begins, and repeats only while the last
    attempt's `gave_up` is non-empty. D4's argument that the bound is never reached is the comment
    beside it. The signature has a fourth parameter the task's text does not name, because 3.1a
    hands the set to every attempt.
  - **3.1a.** The counting loop skips an id already in `counted`, after the `waiting_reason` write,
    so a skipped entry keeps the refusal's words and is neither counted nor given up on again. The
    comment names F114 and R2's measured `[H1, M]`, `[M, H6]`, `[M]` rider. 1.6(f) passes.
  - **3.2.** `schedule_agent` returns the last attempt's result, unless that attempt has
    `nothing_queued` and an earlier attempt gave up. Then it returns the result of the last attempt
    that gave up. The rule never compares the string.
  - **3.3.** The line numbers the task cites had drifted to `:539-543` and `:453-459` after §2. The
    transient paragraph now says the pass ends and that there is no tick. It names the run-end
    re-drain in `agent_trigger` (F90) by name, not by line: that block is at `:2431-2460` today,
    not `:2422-2451`. The abandonment paragraph gains the F320 paragraph.
  - **3.4.** `:227` now expects `[("withdrawn", LIMIT), ("queued", 1)]`, and its docstring has D6's
    sentence. No second existing assertion failed in the ten files below. The whole suite is §7.2.
  - **3.5.** The five `@MOVES_IN_3` decorators and the marker definition are removed.

  Measured:
  - The new file: 24 passed.
  - The baseline chunk, plus the new file and `test_a_blocked_agent_workspace_holds_its_input.py`:
    **314 passed, 1 skipped, in 81.7s and then 78.3s.** That is 309 + the 5 flipped.
  - The first run of that set **stalled**. It was killed after 10m16s at test 253,
    `test_failed_run_returns_input.py::test_giving_up_lets_the_agent_accept_new_input`, with no
    traceback. That file then passed 8 of 8 alone (about 9s each), and the whole set passed twice.
  - By reading, the loop cannot repeat in that test. It never raises `TriggerAgentError`: its
    failures happen in the background run, so `gave_up` stays empty. What it sees of this change is
    one extra `SELECT` per pass. The shape matches F292's unbounded-hang mode, a background
    `_execute_run` and a dead aiosqlite worker, but without a signature that is not classified.
    §7.2 is where it would show again.
  - ruff and black (py311) are clean. `validate --strict` is valid.

## 4. Mutation checks — every line must be load-bearing

No existing test fails for F319's absence (`design.md` D6), so each mechanism is mutated once. A
named test must fail. Record which test failed, then restore.

- [x] 4.1 Delete the rollback line. The snapshot tests of 1.2, 1.3, 1.4 and 1.5 must fail, and so
  must 1.8a.
- [x] 4.2 Move the rollback **below** the first `await db.commit()` of the branch. 1.2 must fail,
  because the first commit lands the staging.
- [x] 4.3 Keep the rollback, and do the `waiting_reason` write **before** it. The `waiting_reason`
  assertions of 1.2 and 1.4 must fail, because the write is rolled back with the staging.
- [x] 4.4 Keep the rollback and drop the re-read of `entries` (keep the `selected` re-read and the
  captured `conversation_id`, so the mutation isolates the one row set only the workspace branch
  reads). **Three** tests must fail with `MissingGreenlet` (R3 ran this mutation on R2's
  prototype, `design.md` D13):
  - `test_a_binding_inherited_from_the_thread_spends_the_heads_attempts`
  - `test_a_second_unbound_conversation_does_not_make_the_head_expendable`
  - `test_a_task_bound_entry_waiting_elsewhere_spends_the_heads_attempts`

  `test_a_blocked_agent_workspace_holds_the_operators_message` and
  `test_an_entry_in_the_refused_batch_naming_a_vanished_task_does_not_count` **pass** under it:
  they fail only when the captured conversation id is not used (4.4c). R1's five came from a
  rollback that re-read nothing, which is 4.4 and 4.4c at once.
  - [x] **4.4b** Drop 2.1's `state == "queued"` filter, keeping the re-read by id. 1.8b must fail, with
    the entry counted to `LIMIT` and `queue_entry_abandoned` emitted.
  - [x] **4.4c** Keep both re-reads and read `conversation.id` in the branch instead of the captured
    `conversation_id`. All five tests named in `design.md` D3 must fail with `MissingGreenlet`
    (measured by R3 on R2's prototype: those five, plus D6's test, which already fails there before
    3.4 changes its expectation).

  **Actual (night 2026-09-13, `r3-mut-a`, against `6ebcd9f`).** Each mutation was a single scripted
  edit to `hub/hub/turn_scheduler.py`, each `old` asserted to occur exactly once, using
  `testbed/scratch/night0913/r3/mutate.py`. The run covered four files, from `hub/` under
  `py -3.11`: this change's file, `test_a_blocked_workspace_counts_where_input_could_run.py`,
  `test_a_blocked_agent_workspace_holds_its_input.py` and `test_the_evidence_names_the_author.py`.
  Unmutated they gave 50 passed and 5 xfailed. After every mutation the file was restored with
  `git checkout`, and `git status --short` was empty. **Every named test failed. No named test
  passed. No test was changed.**

  | Mutation | Result | Failed (the named ones in bold) | Message |
  |---|---|---|---|
  | 4.1 rollback deleted | 7 failed | **1.2 `…leaves_the_task_as_it_was[B0,B1,B2]`**, **1.3 `…does_not_stop_another_reviewer`**, **1.5 `test_leg_t_leaves_the_task_as_it_was`** | `('under_review','rr-reviewer',3) == ('completed',None,2)` |
  | | | **1.4 `test_leg_a_leaves_the_task_as_it_was_after_every_pass`** | `('completed','rr-reviewer',2) != ('completed',None,2)` |
  | | | **1.8a `test_a_refused_review_does_not_close_an_open_divergence`** | `resolved_at` is a datetime, not `None` |
  | 4.2 rollback below the first commit | 7 failed | **1.2 (B0, B1, B2)**, plus the same four as 4.1 | identical to 4.1: the first commit lands the staging, and the late rollback has nothing left to discard |
  | 4.3 `waiting_reason` written before the rollback | 6 failed | **1.2 `…records_the_refusal[B0,B1,B2]`** | `None == <the refusal's words>` |
  | | | **1.4 `test_leg_a_records_the_guards_refusal_and_gives_up_at_the_limit`** | `'recorded evidence for this task' in ''` (its per-pass `waiting_reason` assertion) |
  | | | also: 1.8a's fixture pin `test_the_divergence_fixture_is_built_through_the_product`, and D3's `test_a_blocked_agent_workspace_holds_the_operators_message` | both on `waiting_reason` `None` |
  | 4.4 `entries` re-read dropped | **exactly 3** failed | **`…inherited_from_the_thread…`**, **`…second_unbound_conversation…`**, **`…task_bound_entry_waiting_elsewhere…`** | `sqlalchemy.exc.MissingGreenlet` |
  | | | `…holds_the_operators_message` and `…vanished_task_does_not_count` **pass**, as 4.4 says | |
  | 4.4b `state == "queued"` filter dropped | 1 failed | **1.8b `test_input_withdrawn_during_its_dispatch_is_not_counted`** | `('withdrawn', 3) == ('withdrawn', 2)` |
  | 4.4c `conversation.id` read in the branch | **exactly 5** failed | **the five of D3**: `…holds_the_operators_message`, `…inherited_from_the_thread…`, `…second_unbound_conversation…`, `…task_bound_entry_waiting_elsewhere…`, `…vanished_task_does_not_count` | `sqlalchemy.exc.MissingGreenlet` |

  - **4.4b, the rest of its claim.** The test's first assertion stops it before its event
    assertion. So the 1.8b scenario was re-run as an untracked probe that observes and asserts
    nothing (`hub/tests/test__r3_probe_4_4b.py`, deleted afterwards).
    - Under the mutation: `('withdrawn', 3)`, `abandoned_reason` *"delivery failed 3 times (refused
      entry-…); the Hub stopped retrying"*, and one `queue_entry_abandoned`.
    - On HEAD: `('withdrawn', 2)`, no reason, and no event.
  - **4.4c, D6's test.** It **passes** under 4.4c on this tree. It is
    `test_a_blocked_task_checkout_still_counts_with_nothing_waiting`, the `:227` assertion. R3's
    sixth failure came from the prototype's loop, which D6 attributes to §3, and §3 is not applied
    here. So 4.4c is exactly the five of D3.
- [ ] 4.5 Make the loop continue after **any** non-transient refusal, not only after giving up.
  1.6(b) and 1.6(g) must fail **on their guard `RuntimeError`** (R3). The reason R1 gave, *"because
  B is counted more than once"*, cannot be the failure once 3.1a is in place: 3.1a stops any entry
  being counted twice in a pass, so this mutation's cost is the same refusal repeated until the loop
  bound, and the guard is what catches it.
- [ ] 4.6 Also continue after a transient refusal. 1.6(c) must fail, on its guard `RuntimeError`.
- [ ] 4.7 Remove the loop. 1.6(a), 1.6(b), 1.6(d) and 1.7 must fail.
- [ ] 4.8 Return the last attempt's result unconditionally. 1.6(d) must fail, because it reports
  `"queue is empty"`.
- [ ] 4.9 With the loop in place, restore §3.4's old expectation `("queued", 0)`. That test must
  fail. This confirms that D6's change is caused by the loop and by nothing else.
- [ ] 4.10 Remove 3.1a's once-per-pass guard, keeping the loop. 1.6(f) must fail, with M
  `withdrawn` at 3 (R2 measured exactly this against R1's prototype). 1.6(g) must fail too, with M
  `queued` at 2 instead of 1 (inferred from the prototype's counting loop, not run).

## 5. Drive it — the tests are an argument, and a drive is the product

Every real agent turn binds `claude-haiku-4-5-20251001`. No job is left enabled. The drive Hub runs
on a port chosen that night after `netstat -ano | grep LISTENING` shows it free, **never 8000 or
8010**. It uses a fresh `profiles/drive<MMDD>` with `AW_BOOTSTRAP_API_KEY` set, and is started from
`hub/` with `py -3.11 -m uvicorn` **from source**. No `.py` under `hub/hub` or `src` may be newer than
the process. Export `AW_HUB` and `AW_KEY` before every harness run.

- [ ] 5.1 **The harness.** Extend `scripts/drive/t_d1_0912_f319_reach.py`.
  - `AW_EXPECT=prefix` (the default) keeps today's "REACHED" assertions. `AW_EXPECT=fixed` asserts,
    for every leg, that the task row and its transition count equal a snapshot taken
    **immediately before** the dispatch, and that the refused reviewer has no run.
  - **The D9 check is asserted, not just noted**: the second reviewer's answer on B1 does not say
    *"already under review"*.
  - **Add leg F, for F320, through operator routes only:**
    1. Start agent X's turn with the `sleep 60` then `record_evidence` instruction that leg A uses.
    2. While it runs, dispatch a review of task TA naming X. It is answered `200 queued` (H).
    3. Also `POST /agent/trigger` a plain one-line message M to X, in a new conversation. It is
       answered `200 queued`.
    4. Wait for X's turn to end. The run-end re-drain makes attempt 1 on H.
    5. `POST /conversations/<H's conversation>/continue` twice, for attempts 2 and 3.
    6. Read `inbound_queue_entries` and `runs`.
- [ ] 5.2 **Pre-fix, first.** Run `git worktree add ../aw-f319-prefix <sha>` at §1's commit.
  **Never `git stash`.** Start the drive Hub from that worktree, on a fresh git fixture project, and
  run legs B, A and F with `AW_EXPECT=prefix`. These must reproduce:
  - B1 and B2: `under_review`, held by the refused reviewer, with a new transition row.
  - The D9 refusal of a second reviewer.
  - A: `("completed", X)`.
  - F: H `withdrawn`, and M still `queued` at 0 attempts with no run.

  **If any of these does not hold, this is not a reproduction.** Say so and stop. Stop the Hub and
  remove the worktree afterwards.
- [ ] 5.3 **Fixed tree.** Use a fresh project and fresh agents, and run the same legs with
  `AW_EXPECT=fixed`.
  - Every task equals its before-dispatch snapshot, and no refused reviewer has a run.
  - The route's `409` sentences for B1 and B2 are unchanged.
  - The second reviewer on B1 is not refused as *"already under review"*.
  - A's entry carries the guard's sentence as `waiting_reason`, and after attempt 3, a
    `queue_entry_abandoned` row exists.
  - F: M is delivered by the pass of the second `continue`. A run exists whose delivered entry is M,
    and no other event came between.
- [ ] 5.4 **Where the operator saw it.** Run `scripts/drive/t_d1_0912_f319_ui.py` (Chromium,
  against the served bundle) on the fixed-tree Hub. The B1 and B2 cards are not in **Under
  Review**. A's card does not name X. The bundle is unchanged by this change. This checks the
  symptom F319 recorded on the board.
- [ ] 5.5 Confirm that every run in the profile joined to a Haiku runner (`model LIKE
  'claude-haiku-4-5%'`), and that
  `GET /jobs` is empty or every job is disabled. Stop the Hub. Remove any worktree the drive made.

## 6. Verification only a human can do

- [ ] 6.1 **Dispatch a review from the UI** on a task whose commit you pruned (test guide, check
  1). F319 never captured what the UI's own dispatch control shows for the `409`. Does the reason
  reach you, and does the board still show the task as untouched?
- [ ] 6.2 **Leg A tells you late.** The request was answered *queued*, and the refusal arrives as
  the waiting input's reason, then as a notice that the input was given up on. This change keeps
  that and adds nothing. Decide whether it is enough, and write the answer down, or leave it open in
  writing.
- [ ] 6.3 **The operator question at the top of `proposal.md` (F327, `design.md` D7).** Its answer
  must be written in `DECISIONS.md` by the operator before approval. If it is not there, this change
  is not approved, and nothing here decides it on the operator's behalf.

## 7. The gate

- [ ] 7.1 `ruff check src/ hub/ tests/`, `black --check src/ hub/hub/ hub/tests/ tests/
  --target-version py311`, and `mypy src/`. Use CI's path list, not a narrower one.
- [ ] 7.2 The whole Hub suite, `py -3.11 -m pytest tests/ -q` from `hub/`, in chunks or in the
  background (it exceeds the 600 s command cap). Use `py -3.11`, never bare `python`.
- [ ] 7.3 `openspec validate --strict a-refused-review-leaves-nothing-behind` after every delta
  edit.
- [ ] 7.4 `git diff <base>.. -- hub/hub/migrations hub/ui hub/hub/mcp_server.py
  hub/hub/task_transition_service.py hub/hub/scheduler.py hub/hub/run_divergence.py` is empty (the
  last three make the non-goals mechanical: no guard weakened, no flow staging moved), and
  `git diff <base>.. -- hub/hub/api` is the comment hunk of §2.3 only.

## 8. Close it out

- [ ] 8.1 Set F319's `**Status:**` line to `fixed <sha>`, naming §2 and quoting §5.3's legs.
- [ ] 8.2 Set F320's `**Status:**` line to `fixed <sha>`, separately, naming §3 and quoting §5.3's
  leg F.
- [ ] 8.3 F326 stays **open**. Say so in the close-out commit, so nobody reads this change as
  closing it.
- [ ] 8.4 F327 stays **open** unless the operator's answer brought it into this change. Say which in
  the close-out commit.
- [ ] 8.5 File the escaped `run_divergence_resolved` broadcast (`design.md` D8, 1.8a) as a finding,
  severity D, with 1.8a as its reproduction. It exists only once §2 has landed, which is why it is
  filed here and not earlier.
- [ ] 8.5a **F328 stays open. Do not set it `fixed`.** 2.1's `state == "queued"` filter narrows it,
  and a withdrawal that waits on a real review dispatch's write lock still lands after the re-read
  (pre-approval review, test O2 in `testbed/scratch/opusf319/test_zz_opusf319.py`). Append one
  dated line to F328's section naming the commit that narrowed it, and say in the close-out commit
  that F328 stays open.
- [ ] 8.6 `openspec validate --strict a-refused-review-leaves-nothing-behind`, then archive with the
  `openspec-archive-change` skill. After syncing, confirm that the main requirement *"Dispatching a
  review staffs the task, whichever path dispatched it"* is **byte-identical** to before. This
  change adds requirements beside it and does not modify it (`design.md` D9).

## 9. User test guide

- [ ] 9.1 `test-guide.md` in this change is the operator's walkthrough. Keep it true to what
  shipped.
