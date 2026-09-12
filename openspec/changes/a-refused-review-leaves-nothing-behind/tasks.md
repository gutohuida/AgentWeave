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

## 1. Pin the defect before the fix

All in a new `hub/tests/test_a_refused_review_leaves_nothing_behind.py`. The module docstring cites
F319, F320 and this change's `design.md` D1 and D4. Each test's docstring names the mutation in §4
that must fail it.

- [ ] 1.1 **Fixtures.** Reuse `_roster` (`test_a_flow_names_what_it_cannot_staff.py`) and
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
- [ ] 1.2 **B0, B1, B2 on the scheduler path**, parametrized. Queue an operator review entry
  (`review_task_id` set) for a reviewer that recorded nothing, then `schedule_agent` once.
  - B0: `tmp_path` is not a repository.
  - B1: a repository whose evidence names `"e" * 40`, with the real `ensure_review_checkout`.
  - B2: a repository at `HEAD`, with `.agentweave/reviews/<reviewer>/x.txt` a plain directory, and
    the real `ensure_review_checkout`.

  Assert all of these. The snapshot is unchanged. There is no `Run`. The entry is `queued` with
  `delivery_attempts == 1`. Its `waiting_reason` equals `ScheduleResult.waiting_reason` and contains
  the refusal's distinguishing words (*"not a git repository"*, *"is not present in this
  repository"*, *"refusing existing path"*). `ScheduleResult.refusal.status_code == 409`. **Only
  the snapshot assertion is xfail(§2).** The rest pass today (measured, `design.md` D0).
- [ ] 1.3 **B1 through the route.** `POST /agent/trigger` names the reviewer and `review_task_id`.
  Assert all of these:
  - The answer is `409`, and its `detail` names the commit.
  - The snapshot is unchanged (xfail §2).
  - The entry is `withdrawn`.
  - An `EventLog` row `queue_entry_withdrawn` exists.

  Then `POST` again, naming a **different** reviewer. Its `detail` must not contain
  `"already under review"` (xfail §2). It may still be refused for the commit.
- [ ] 1.4 **Leg A, the timing gap, through the route.**
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
- [ ] 1.5 **Leg T, a deferral after the staging.** Delete `HUB_URL` from the environment and make
  `agent_trigger.bound_address.get` return `None`. The default `ensure_review_checkout` stub is
  fine. Queue the review and call `schedule_agent` once. The snapshot is unchanged (xfail §2). The
  entry is `queued` with `delivery_attempts == 0`. `terminal_failure is False`, and `refusal is None`.
- [ ] 1.6 **F320 at the scheduler**, with `trigger_agent_directly` patched (as
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
- [ ] 1.7 **F320 through the route.** Seed H as in 1.6. Then `POST /agent/trigger` a plain message
  to the same agent, which opens a new conversation. The mock refuses H and returns a started
  response for the route's own entry. The answer reports that conversation as started, with
  `status == "running"` (xfail §3). Today it answers `queued`, *"queued behind other input"*.
- [ ] 1.8 **The one-caller pin.** Scan `hub/hub/**/*.py` for `trigger_agent_directly(` outside its
  own `def`. The only file must be `turn_scheduler.py`. The docstring says why: `design.md` D2(e),
  where the rollback lives in the one caller. This passes today.
- [ ] 1.9 Run §1 against the unmodified tree. Every xfail must xfail and every pin must pass.
  **Any other outcome means the test is wrong, not the code.** Stop, re-measure with
  `testbed/scratch/r1f319/test_zz_r1f319_scratch.py`, and record what differed here. Commit §1 alone,
  green.

## 2. The rollback (F319)

- [ ] 2.1 In `hub/hub/turn_scheduler.py`, capture `selected_ids` and `conversation_id` immediately
  before the `trigger_agent_directly` call. Make `await db.rollback()` the **first** statement of
  `except TriggerAgentError`. Then:
  - re-read `selected` with `InboundQueueEntry.id.in_(selected_ids)`, in the captured order;
  - re-read `entries` with `queued_entries(db, project_id, agent)`;
  - pass `conversation_id` wherever `conversation.id` was read in the branch.

  Everything after that is unchanged: the `waiting_reason` write, both commits, the events, and
  `TurnRefusal` (`design.md` D1, D3).
- [ ] 2.2 Rewrite the comment that opens the branch (today `:340-346`). It should say that the
  dispatch's staging is discarded **before** anything is recorded, and why: F319. It should also say
  that the refusal's words are written after the rollback, so F97's reason for this commit still
  holds. Keep F97's paragraph and add to it. Do not replace it.
- [ ] 2.3 Correct the comment at `hub/hub/api/v1/agent_trigger.py:788-793`. A refusal abandons the
  staging because `turn_scheduler.schedule_agent`, the one caller, rolls back before it records the
  refusal. Name this change, and name the one-caller test (§1.8). **Comment only. No code in this
  file changes.**
- [ ] 2.4 Remove the §2 xfail markers from 1.2 to 1.5.
- [ ] 2.5 Update the docstrings of `test_dispatching_the_evidence_author_as_reviewer_is_refused_before_the_turn`
  (`test_the_evidence_names_the_author.py:474-480`) and
  `test_the_direct_dispatch_refuses_the_evidence_author_before_the_checkout` (`:517-520`). Each
  should stop saying the product path commits the staging, and should name §1.4 as the test that
  shows it no longer does. Change no assertions.

## 3. The pass goes on (F320)

- [ ] 3.1 Split `schedule_agent`'s body into one attempt, `_attempt_turn(db, project_id, agent)`. It
  returns a small frozen dataclass with four fields:
  - `result`, the `ScheduleResult`;
  - `attempted`, whether `trigger_agent_directly` was called;
  - `gave_up`, the entries set `withdrawn` by this attempt;
  - `nothing_queued`, set only by the empty-queue early return.

  `schedule_agent` keeps the lock and the session and loops. It stops unless `gave_up` is
  non-empty. Bound the loop at `len(initial queued entries) + 1` attempts, counted once when the
  pass begins, and state D4's argument that the bound is never reached in the comment beside it.
- [ ] 3.2 The result rule of D5, keyed on `nothing_queued`, **not** on the string
  `"queue is empty"`. Where the last attempt has `nothing_queued` and an earlier attempt gave up,
  return that earlier attempt's result.
- [ ] 3.3 Rewrite the comment at `:493-497` (*"the next tick tries again"*). No tick exists. A
  transient refusal waits for the run-end re-drain (`agent_trigger.py:2422-2451`) or an operator
  action. At the abandonment paragraph (`:407-413`), add that the pass then goes on to the input
  behind, and why: F320.
- [ ] 3.4 `hub/tests/test_a_blocked_workspace_counts_where_input_could_run.py:227`: change the
  expectation to `[("withdrawn", DELIVERY_ATTEMPT_LIMIT), ("queued", 1)]`. Add one sentence to its
  docstring: the pass that gives up on the head now attempts the entry behind it, and the mock
  refuses that one too (`design.md` D6). **This is the only existing assertion that changes.** If a
  second one fails, stop and record it in `design.md` D6 before changing it.
- [ ] 3.5 Remove the §3 xfail markers from 1.6 and 1.7.

## 4. Mutation checks — every line must be load-bearing

No existing test fails for F319's absence (`design.md` D6), so each mechanism is mutated once. A
named test must fail. Record which test failed, then restore.

- [ ] 4.1 Delete the rollback line. 1.2, 1.3, 1.4 and 1.5 must fail on the snapshot.
- [ ] 4.2 Move the rollback **below** the first `await db.commit()` of the branch. 1.2 must fail,
  because the first commit lands the staging.
- [ ] 4.3 Keep the rollback, and do the `waiting_reason` write **before** it. The `waiting_reason`
  assertions of 1.2 and 1.4 must fail, because the write is rolled back with the staging.
- [ ] 4.4 Keep the rollback and drop the re-read. These five tests must fail with
  `MissingGreenlet`:
  - `test_a_blocked_agent_workspace_holds_the_operators_message`
  - `test_a_binding_inherited_from_the_thread_spends_the_heads_attempts`
  - `test_a_second_unbound_conversation_does_not_make_the_head_expendable`
  - `test_a_task_bound_entry_waiting_elsewhere_spends_the_heads_attempts`
  - `test_an_entry_in_the_refused_batch_naming_a_vanished_task_does_not_count`

  R1 measured exactly these five (D3).
- [ ] 4.5 Make the loop continue after **any** non-transient refusal, not only after giving up.
  1.6(b) must fail, because B is counted more than once.
- [ ] 4.6 Also continue after a transient refusal. 1.6(c) must fail, on its guard `RuntimeError`.
- [ ] 4.7 Remove the loop. 1.6(a), 1.6(b), 1.6(d) and 1.7 must fail.
- [ ] 4.8 Return the last attempt's result unconditionally. 1.6(d) must fail, because it reports
  `"queue is empty"`.
- [ ] 4.9 With the loop in place, restore §3.4's old expectation `("queued", 0)`. That test must
  fail. This confirms that D6's change is caused by the loop and by nothing else.

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
- [ ] 5.5 Confirm that every run in the profile joined to `claude-haiku-4-5-20251001`, and that
  `GET /jobs` is empty or every job is disabled. Stop the Hub. Remove any worktree the drive made.

## 6. Verification only a human can do

- [ ] 6.1 **Dispatch a review from the UI** on a task whose commit you pruned (test guide, check
  1). F319 never captured what the UI's own dispatch control shows for the `409`. Does the reason
  reach you, and does the board still show the task as untouched?
- [ ] 6.2 **Leg A tells you late.** The request was answered *queued*, and the refusal arrives as
  the waiting input's reason, then as a notice that the input was given up on. This change keeps
  that and adds nothing. Decide whether it is enough, and write the answer down, or leave it open in
  writing.
- [ ] 6.3 **`design.md` D7.** Confirm or overturn the reading that *"whichever path"* does not
  reach a flow's own committed staging. That is the operator's to decide. If the review page does
  not already carry it, put it in `decisions_for_user`.

## 7. The gate

- [ ] 7.1 `ruff check src/ hub/ tests/`, `black --check src/ hub/hub/ hub/tests/ tests/
  --target-version py311`, and `mypy src/`. Use CI's path list, not a narrower one.
- [ ] 7.2 The whole Hub suite, `py -3.11 -m pytest tests/ -q` from `hub/`, in chunks or in the
  background (it exceeds the 600 s command cap). Use `py -3.11`, never bare `python`.
- [ ] 7.3 `openspec validate --strict a-refused-review-leaves-nothing-behind` after every delta
  edit.
- [ ] 7.4 `git diff <base>.. -- hub/hub/migrations hub/ui hub/hub/mcp_server.py` is empty, and
  `git diff <base>.. -- hub/hub/api` is the comment hunk of §2.3 only.

## 8. Close it out

- [ ] 8.1 Set F319's `**Status:**` line to `fixed <sha>`, naming §2 and quoting §5.3's legs.
- [ ] 8.2 Set F320's `**Status:**` line to `fixed <sha>`, separately, naming §3 and quoting §5.3's
  leg F.
- [ ] 8.3 F326 stays **open**. Say so in the close-out commit, so nobody reads this change as
  closing it.
- [ ] 8.4 `openspec validate --strict a-refused-review-leaves-nothing-behind`, then archive with the
  `openspec-archive-change` skill. After syncing, confirm that the main requirement *"Dispatching a
  review staffs the task, whichever path dispatched it"* is **byte-identical** to before. This
  change adds requirements beside it and does not modify it (`design.md` D9).

## 9. User test guide

- [ ] 9.1 `test-guide.md` in this change is the operator's walkthrough. Keep it true to what
  shipped.
