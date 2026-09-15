# Tasks — a refusal names a remedy that works

Split from `an-unstaffed-review-names-its-holders` on 2026-09-15 (proposal.md, *Provenance*).
**Not built. Takes one verification round before it is built (REV's recommendation, approved by
the operator).** Groups 2–4 below carry their parent tasks' text **verbatim**, renumbered only;
each keeps a `(was N.N)` marker so a verifier can diff against the parent's `tasks.md` at
`fb469e2`/`82b58df` directly. **Group 1 is new** — the parent bundled building `own_review_remedy`
inside its own task 2.3, mixed with rung-3 clause logic that does not move. Group 1 extracts the
buildable part; its mutation is this split's own, not carried, and deserves the closest look in
the verification round.

Findings: F353, F334, F365, F367 (retired by this change). F352 stays open (its visibility half
is the sibling directory's); F366 stays open (this change stops relying on its hole, does not
close it).

Day rules, if built on a day window: no `hub/hub/mcp_server.py`, no migration, no UI (this change
touches none). Tests run under `py -3.11`. `black` needs `--target-version py311`.

Each test named below must **fail with its mutation applied** before it counts. Record the
mutation and the observed failure beside the task when ticking it.

## 1. The remedy a refused actor can act on (design D1) — new for this split

- [x] 1.1 Add `own_review_remedy(task)` to `hub/hub/scheduler.py`, public (no leading underscore,
      so `agent_trigger` can import it at module level — it already imports four names from
      `scheduler`, and `scheduler` imports nothing from `agent_trigger`, so there is no cycle).
      Returns the status-only sentence (D1), asserting the task's status is one of the two below:
      - `completed`: *"Land it, on the task, to review it yourself."* No promise of approval.
      - `under_review`: *"decide it yourself: approve, reject, or send it back with
        revision_needed."* Never Land it.

      Landed at `scheduler.py`, beside `_wedged_review_reason`. Group 4 (`4.2`) is what actually
      wires `agent_trigger` to import it — not built yet in this firing.
- [x] 1.2 Test: the helper returns the right sentence for each of the two statuses.
      *Mutation:* swap the two branches. The test must fail.

      This helper's assertion on any other status is exercised by the sibling directory's own
      task once it re-derives the divergence restaff's screening logic against `F352-free` — do
      not duplicate that test here; it belongs where the screening that triggers it lives.

      `hub/tests/test_a_refusal_names_a_remedy_that_works.py::test_completed_names_land_it` and
      `::test_under_review_names_the_three_exits_never_land_it`. Mutation applied (swapped the
      `if task.status == "completed"` branch to `"under_review"`): both tests failed —
      `test_completed_names_land_it` on `'Land it...' == 'decide it yourself...'` and
      `test_under_review_names_the_three_exits_never_land_it` on the reverse. Reverted; both pass
      clean.

## 2. The stall reason fits within its column (design D2)

- [x] 2.1 (was 2.5) Fit `JobRun.error_summary` at the model (design D2):
      - `JOB_RUN_ERROR_SUMMARY_CHARS = 500` beside `JobRun`, read by `String(...)` and by
        `JobRunResponse.error_summary`'s `max_length`;
      - `fit_error_summary(text)`, which leaves text that fits unchanged and cuts longer text to
        499 characters plus `…`;
      - `@validates("error_summary")` on `JobRun`, applying it;
      - `_stall_run_to_increment` (`:961`) comparing against `fit_error_summary(stall_reason)`.

      Landed in `hub/hub/db/models.py` (constant, helper, column, validator),
      `hub/hub/schemas/jobs.py` (`JobRunResponse.error_summary` now reads the constant), and
      `hub/hub/scheduler.py:961` (`_stall_run_to_increment`'s comparison). Re-grepped
      `error_summary\s*=` across `hub/hub` first: still the nine sites D2 names, all covered by
      the model-level validator, no new site since the round.
- [x] 2.2 (was 2.5b) `_wedged_review_reason` (`scheduler.py:1893-1897`) shortens the quoted title
      so the whole sentence fits 500 characters and its remedy survives.

      Implemented as an inner `_sentence(title)` closure plus a trim loop that shortens the raw
      title one character at a time (re-`repr`ing each attempt, since `!r`'s escapes can regrow
      the string non-monotonically) until the assembled sentence fits
      `JOB_RUN_ERROR_SUMMARY_CHARS`, appending `…` to the trimmed title.
- [x] 2.3 (was 2.12) Test: a `JobRun` constructed or assigned with 600 characters of
      `error_summary` stores exactly 500, ending `…`. A 500-character value is stored unchanged,
      and `None` stays `None` (the column is nullable).
      *Mutation:* remove the `@validates`. The test must fail.

      `hub/tests/test_a_refusal_names_a_remedy_that_works.py::test_a_600_character_error_summary_is_stored_at_500_ending_ellipsis`,
      `::test_a_500_character_error_summary_is_stored_unchanged`,
      `::test_none_error_summary_stays_none`. Mutation applied (renamed the `@validates`-decorated
      method to `_validate_error_summary_DISABLED` without the decorator): the 600-character test
      failed on `assert 600 == 500` (the raw, unfitted string was stored). Reverted; all three
      pass clean.
- [x] 2.4 **New — the verification round found 2.2 shipped with no test of its own.** REV's list
      of what moves named `own_review_remedy`, 2.5, 2.12 and 2.13 — not 2.5b; its only coverage in
      the parent was task 2.11, a through-a-real-firing test that depends on rung-3's own
      wedged-review detection (F154's shape), which is not built here and is not re-derived yet.
      Test `_wedged_review_reason` (2.2) directly instead, as a unit: a wedged review whose
      reviewer has a 32-character name and whose task has a 256-character title. Assert the
      returned sentence is at most 500 characters and still ends with the remedy
      (`revision_needed.`). The parent's task 2.11 (through-a-real-firing) stays in the sibling
      directory once it is re-derived, and re-verifies this at the integration level; it is not
      duplicated here.
      *Mutation:* remove 2.2's title-shortening. The test must fail.

      `hub/tests/test_a_refusal_names_a_remedy_that_works.py::test_wedged_review_reason_fits_500_at_a_32_char_reviewer_and_256_char_title`.
      Unmutated, at a 32-char reviewer and a 256-char title, the sentence measures 552 characters
      (the exact wording drifted slightly from D2's 551-character measurement, same shape).
      Mutation applied (returned `_sentence(task.title)` directly, skipping the trim loop): the
      test failed on `assert 552 <= 500`. Reverted; passes clean.

## 3. Once per task (design D3)

- [x] 3.1 (was 3.1) `_review_unstaffed_already_stands` filters on
      `EventLog.data["task_id"].as_string() == task_id`, against real SQLite. **Carries REV item
      10, missed in the first split pass:** the docstring at `scheduler.py:2067-2069` still
      claims a condition that cleared and returned *"is news again"*, which stays untrue after
      this fix for a loop with two stuck tasks whose reasons happen to repeat exactly (the same
      gap REV noted, left open, and this task must not leave open silently). Amend the docstring
      to state the narrower rule this task actually implements: newest-for-this-task, not
      newest-for-any-change.

      Landed at `scheduler.py:2120-2148` (line numbers moved from groups 1-2's ~40 added lines,
      re-grepped before editing). Added `.where(EventLog.data["task_id"].as_string() == task_id)`
      to the query and dropped the now-redundant `data.get("task_id") == task_id` from the
      Python-side check (`reason` alone, since the query already scopes to this task). Docstring
      rewritten: states the query is scoped to this task's own newest record, not the loop's
      (F365), and explicitly disclaims the "cleared and returned is news again" property — there
      is no "cleared" event, so a task whose newest record still reads the same reason looks
      unbroken-standing whether the condition was continuous or recurred; names this as REV item
      10, left open.
- [x] 3.2 (was 3.2) Test: one loop, **two** unstaffable tasks, five firings through the real
      route. Exactly one `review_unstaffed` per task.
      *Mutation:* revert to the loop-newest query. The test must fail, while the existing
      single-task test still passes against the mutant, which shows why it never caught this.

      `hub/tests/test_a_refusal_names_a_remedy_that_works.py::test_two_unstaffable_tasks_each_get_exactly_one_review_unstaffed`.
      Two operator-completed, single-agent-roster tasks (both excluded via
      `agents_that_may_have_authored`, evidenced from setup so both reach the exclusion branch
      immediately), five firings through `POST /jobs/{id}/run`. Mutation applied (dropped the
      `task_id` filter, restored the old `data.get("task_id") == task_id` check): task a recorded
      5 events instead of 1 (one new row every firing, since each firing's freshly-written row for
      the *other* task always shadows the next check). `test_an_unchanged_wedge_is_recorded_once_not_once_per_tick`
      (`test_a_review_nobody_is_doing.py`, one task, five firings) was re-run against the same
      mutant and still passed, confirming why a single-task fixture never caught this. Reverted;
      both pass clean, 1 event per task.
- [x] 3.3 (was 3.3, **staging corrected in this split — verification round found the original
      staging no longer produces a reason change**) Test: two tasks; between firings, change one
      task's reason only. **Not** by freeing a holding: since `4b59ee0` (2026-09-15,
      `_agents_that_are_free`, `scheduler.py:1125-1138`), a bare holding no longer changes
      availability or today's fixed rung-3 sentence — only a `loop_id`-reachable holding or a
      queued turn does, and today's sentence (`scheduler.py:1297-1301`) varies only by
      `excluded_because` and a project-wide provider-hold clause, not by named holdings at all
      (that naming is rung-3's own D2, not built here). Stage the reason change instead by
      varying one task's `excluded_because` — e.g. record evidence for a non-author agent on one
      task between firings, which changes that task's exclusion clause without touching the
      other's. One more record for the changed task, and none for the other. Note (was 2.11 in
      the parent, R2): this changes one task's reason only if the agent whose exclusion changes
      is not the other task's own excluded agent — keep the fixture's two tasks' exclusions
      independent.
      *Mutation:* drop the task filter. The test must fail.

      `hub/tests/test_a_refusal_names_a_remedy_that_works.py::test_a_changed_reason_is_recorded_again_for_only_the_task_that_changed`.
      Task `a` starts with no evidence at all (refused before `resolve_reviewer` at the
      `commit_for_task_review` gate, a different sentence entirely); task `b` is worked by the
      same author and never gets evidence. Between firings, evidence for `a` is recorded by a
      second roster agent that did not work `a` -- resolving the commit gate and (via
      `agents_that_recorded_evidence_for`) adding that agent to `a`'s exclusion, so the now-full
      two-agent roster still can't staff it, with the exclusion-branch reason instead. Mutation
      applied (same as 3.2's): task `b` recorded 2 events instead of 1 (its unchanged "no commit"
      reason no longer suppressed, because the loop-newest check now compares against `a`'s
      just-written row). Reverted; `a` records 2 events with different reasons, `b` records 1.

## 4. The refusals (design D4)

- [x] 4.1 (was 4.1) `_guard_reviewer_is_not_the_author`, both branches:
      - word it true for a staged or a committed assignee, as *"Cannot move task T to
        'under_review' with 'dev' as its holder: …"*, with no "is assigned to", no "still
        assigned", no "holding it" and no "held by";
      - choose the remedy by `actor.is_operator`:
        - operator: Land it with no promise of approval, or dispatching another agent's review
          turn (`POST /agent/trigger` with `review_task_id`). **Not** the PATCH that sets
          assignee and status together, which queues no turn and wedges;
        - agent: "None of the task tools you are offered reassigns a task" and who can move it
          on, never "no agent can" and never "none of your tools changes who holds a task"
          (`create_task` takes an assignee);
      - the operator branch fits 500 characters at a 64-character id and a 32-character name, in
        both branches (see 4.10);
      - drop "Left as is…";
      - amend the docstring's *"`actor` is deliberately unread"* paragraph.

      The decision is unchanged.

      Landed at `task_transition_service.py:443-465`, both raise sites (completer and evidence
      branches share one `remedy` string, chosen once by `actor.is_operator` before either
      branch). Message shape: *"Cannot move task {id} to 'under_review' with {assignee!r} as
      its holder: …"*; operator remedy *"Land it, on the task, to review it yourself, or
      dispatch a different agent's review turn (POST /agent/trigger with review_task_id)."*;
      agent remedy *"None of the task tools you are offered reassigns a task; the operator can
      move it on."* Neither remedy suggests the PATCH that sets assignee and status together.
      Measured at a 64-char id and 32-char name (both raise sites, both actor kinds): 392,
      346, 468, 422 characters — all under 500 (4.10's own test, group 4b, is the one that
      pins this at the real call sites). Docstring's *"actor is deliberately unread"* paragraph
      rewritten to state actor now drives the remedy, not the refusal.
- [x] 4.2 (was 4.2) `review_dispatch_refusal`: the author branch drops "clear the assignee", and
      both branches end with `own_review_remedy(task)` (1.1). That gives Land it for a `completed`
      task and the three exits for an `under_review` one, **without** rung 3's freeing clause.
      - Add `own_review_remedy` to the existing module-level import from `...scheduler`
        (`agent_trigger.py:133-138`). There is no cycle: `scheduler` imports nothing from
        `agent_trigger`.

      Landed: import added (`agent_trigger.py:133-138`); both `return` statements
      (`:504-511`, `:512-521`) now end with `{own_review_remedy(task)}` in place of their old
      "Dispatch a different reviewer, or …" sentences, and the completer branch's "clear the
      assignee" clause is gone. `task.status` is always `"completed"` or `"under_review"` at
      both call sites — `review_dispatch_refusal`'s own status guard (`:487-493`) filters to
      exactly `REVIEWABLE_LOOP_TASK_STATUSES + WITH_REVIEWER_LOOP_TASK_STATUSES` before either
      branch is reachable — so `own_review_remedy`'s assertion cannot fire here.
- [x] 4.3 (was 4.3) Test, operator PATCH on a completed task held by its author: 403, names Land
      it and `review_task_id`, and contains none of "clear the assignee", "approves" or "name
      that agent as the assignee".
      *Mutation:* restore the old sentence. The test must fail.

      `hub/tests/test_a_refusal_names_a_remedy_that_works.py::test_the_operator_refusal_names_land_it_and_review_task_id`.
      *Mutation applied* (swapped the `if actor.is_operator` condition so the operator gets the
      agent-shaped remedy): failed on `'Land it' in detail` — the response instead read "None of
      the task tools you are offered reassigns a task; the operator can move it on." Reverted;
      passes clean.
- [x] 4.4 (was 4.4) Test, agent PATCH through `/agent-actions/tasks/{id}` with a run token, by a
      non-author on a completed task held by its author. Expect 403, with "none of the task tools
      you are offered", and none of "clear the assignee", "assign a different reviewer", "no
      agent can", "changes who holds" or "API".
      *Mutation:* ignore `actor`. The test must fail.

      `hub/tests/test_a_refusal_names_a_remedy_that_works.py::test_the_agent_refusal_names_no_tool_that_reassigns`.
      *Mutation applied* (same swap as 4.3 — the agent branch's own remedy selection is what
      "ignoring `actor`" collapses to, since the guard reads `actor` for nothing else): failed on
      `'None of the task tools you are offered reassigns a task' in detail` — the response
      instead named Land it and `review_task_id`. Reverted; passes clean.
- [x] 4.5 (was 4.5) Test, F334's shape: a queued review for an agent that recorded evidence
      during its own turn, delivered and refused. The entry's `waiting_reason` and
      `abandoned_reason` do not say the task "is assigned to" that agent, and the task's assignee
      is unchanged.
      *Mutation:* restore "it is assigned to {assignee!r}" in the evidence branch. The test must
      fail.

      `hub/tests/test_a_refusal_names_a_remedy_that_works.py::test_a_changed_evidence_authors_refusal_never_claims_an_assignment_the_rollback_discarded`.
      Reuses `test_a_refused_review_leaves_nothing_behind.py`'s `_leg_a` (§1.4 of that change),
      which already reproduces F334's exact shape — a review queued behind the reviewer's own
      running turn, evidence recorded for the task by that same agent before its turn ends, then
      `DELIVERY_ATTEMPT_LIMIT` delivery attempts through `schedule_agent`. `enter_selected_task`
      always calls `apply_transition` with `operator()` (unchanged, `scheduler.py:878` — staffing
      is a Hub-internal act, not the reviewer's own), so every pass reads the operator remedy;
      the test only pins the absence of "is assigned to" and that the task's assignee stays
      `None` through every pass (the staged assignee is rolled back with the refused
      transition — `turn_scheduler`'s rollback runs before it records `entry.waiting_reason`).
      *Mutation applied* (restored `f"it is assigned to {task.assignee!r}, which recorded
      evidence…"` in the evidence branch): failed on `"is assigned to" not in waiting_reason` —
      every one of the five recorded passes read *"it is assigned to 'rr-reviewer'"*. Reverted;
      passes clean, `entry.abandoned_reason` and `task.assignee` (`None`) both clean too.
- [x] 4.6 (was 4.6) Update any existing test asserting the old sentences, and list each one here
      when ticking. D1's and D4's wording keeps every fragment below, so each should pass
      unchanged. Confirm it:
      - `test_flow_fires_a_review_turn.py:357`, `test_reviewer_ladder.py:174` and
        `test_the_evidence_names_the_author.py:692`: `could not staff this step`;
      - `test_the_evidence_names_the_author.py:693` and
        `test_a_flow_names_what_it_cannot_staff.py:719`: `has worked on this task`;
      - `test_a_flow_names_what_it_cannot_staff.py:733`: `is the one that completed this task`;
      - `test_reviewer_is_not_the_author.py:82, 340`: `review it yourself`, as operator;
      - **two absence assertions:** `"completed" not in reason` at
        `test_a_flow_names_what_it_cannot_staff.py:720` and
        `test_the_evidence_names_the_author.py:694`. They constrain the wording. Neither remedy
        nor the freeing clause may contain the word "completed", and a holds clause never does,
        because `completed` is not in `LIVE_STATUSES`.

      **Amend three comments that state the old remedy in the present tense.** After D4 each
      would be false about the guard:
      - `api/v1/tasks.py:1259-1268`;
      - `schemas/tasks.py:124-127`;
      - the docstring of
        `test_reviewer_is_not_the_author.py::test_clearing_the_assignee_lets_the_operator_review_it_themselves`
        (`:377-378`);
      - `api/v1/agent_trigger.py:854-858` (*"already names both remedies and the cost of doing
        nothing"*) and `task_transition_service.py:405-406` (*"they clear or reassign
        `assignee` first, which is what the refusal asks for"*).

      **Confirmed unchanged** (re-grepped, still passing, current line numbers matched what was
      cited): all six assertions above, at the same lines.

      **One test not on this list was broken by group 4a and only surfaced running the broader
      suite for this task**: `test_the_evidence_names_the_author.py:434`
      (`test_the_evidence_author_cannot_be_entered_as_the_reviewer`) asserted the evidence branch's
      *pre*-D4 wording, `"No agent is recorded as completing it"`, which 4.1's rewording dropped in
      favour of `"with no completer recorded"`. Not named at split time because the split's list
      was built from the design's own before/after wording rather than a fresh grep of every test
      touching this guard's message — noted here rather than silently fixed, since the same gap
      could recur. Fixed to assert the new fragment; the rest of that test (which checks
      `"completed" not in detail`) needed no change, since `"completer"` does not contain
      `"completed"` as a substring.

      **Amended all five comments**: the
      "assign a different reviewer" / "clear the assignee to review it yourself" wording in
      `api/v1/tasks.py:1261-1272`, `schemas/tasks.py:123-128` and
      `test_reviewer_is_not_the_author.py:374-378`'s docstring now describes the mechanism (PATCH
      reassigning, or clearing to `None`) rather than quoting a sentence the guard no longer says;
      `api/v1/agent_trigger.py:853-859`'s "already names both remedies" became "already names the
      remedy for whichever actor is asking (design D4)"; `task_transition_service.py:401-406`'s
      "they clear or reassign `assignee` first" became "the refusal's own remedy (design D4,
      below) names how".
- [x] 4.7 (was 4.7) Test: the dispatch route's author refusal (`POST /agent/trigger` with
      `review_task_id`) on a `completed` task names Land it and does not contain "clear the
      assignee".
      *Mutation:* restore "or clear the assignee to review it yourself". The test must fail.

      Done: `test_the_dispatch_routes_author_refusal_names_land_it`
      (`hub/tests/test_a_refusal_names_a_remedy_that_works.py`). *Mutation applied* (appended the
      old clause to `own_review_remedy`'s `completed` branch): failed on
      `"clear the assignee" not in detail`. Reverted.
- [x] 4.8 (was 4.8) Test: the same refusal on an `under_review` task that nobody holds,
      dispatched to its completer. It names approve, reject and revision_needed, and does
      **not** name Land it.
      *Mutation:* always emit the `completed` remedy. The test must fail.

      Done: `test_the_dispatch_routes_completer_refusal_never_names_land_it`. *Mutation applied*
      (`own_review_remedy` always returns the `completed` sentence): failed on
      `"approve" in detail` (got the Land-it sentence instead). Reverted.
- [x] 4.9 (was 4.9, **fixed in this split — verification round found a duplication defect in the
      original wording**) The D9 refusal, *"Reassign the task if …"*, at `agent_trigger.py:501`
      and `:847`, becomes *"… Let the review in flight finish."* as its own complete sentence,
      followed by `own_review_remedy(task)`'s `under_review` sentence (1.1) as a **new** sentence
      — do **not** repeat "decide it yourself" in the D9 prefix itself; `own_review_remedy`'s
      `under_review` branch already opens with it (1.1), and concatenating the two as originally
      drafted (*"…or decide it yourself" plus "decide it yourself: approve, …"*) doubles the
      phrase. Test both sites: dispatch a second reviewer to a task under review by another.
      Expect 409, naming approve, reject and revision_needed, containing "decide it yourself"
      **exactly once** (not "yourself decide" and not the phrase twice), and not "Reassign".
      *Mutations:* (a) restore one site's old sentence — the test must fail; (b) restore the
      duplicated *"or decide it yourself" + own_review_remedy* concatenation — the "exactly once"
      assertion must fail, which is what a looser assertion (approve/reject/revision_needed
      present, "Reassign" absent) would miss.

      Done. Both sites dropped the "Reassign the task if..." clause entirely (it named an action
      neither site actually offers a path to from this response) and now read
      `f"Task {id} is already under review by {assignee!r}. Let the review in flight finish. "
      f"{own_review_remedy(task)}"`. Two tests:
      `test_the_precheck_names_the_remedy_exactly_once` (site 1, `review_dispatch_refusal`, via
      `POST /agent/trigger`'s route-level precheck) and
      `test_the_dispatch_itself_names_the_remedy_exactly_once` (site 2, `trigger_agent_directly`'s
      own D9 check, reached by calling it directly so the precheck above does not intercept
      first). *Mutation (a) applied* at site 1 (restored the old sentence, no `own_review_remedy`
      appended): failed on `"approve" in detail`. *Mutation (b) applied* at site 1 (restored
      `"...or decide it yourself. " + own_review_remedy(task)`): failed on
      `detail.count("decide it yourself") == 1` (got 2) — exactly the duplication this task
      predicted, and exactly what a looser assertion would have missed. Both reverted.
- [x] 4.10 (was 2.13) Test: the guard's operator sentence, both branches, at a 64-character task
      id and a 32-character agent name, is at most 500 characters. So is the queue entry's
      `waiting_reason` after a flow staging is refused on it, read **before** the model fit, from
      the event or the entry and not from `JobRun`, or the validator hides the overflow. The
      remedy survives whole.
      *Mutation:* restore the earlier, unfitted evidence-branch explanation (583 characters at
      those ids). The test must fail.

      Done. `test_the_guards_sentence_fits_at_worst_case_ids` calls
      `_guard_reviewer_is_not_the_author` directly for all four combinations (F70 completer /
      F306 evidence-author branch, × operator / agent actor) at a 64-char task id and 32-char
      agent name, asserting `len(message) <= 500` and that the actor's remedy fragment survives
      whole. `test_the_dispatched_refusal_at_worst_case_ids_also_fits` reaches the same guard
      through the real dispatch route (`enter_selected_task` -> `TransitionRefusedError`,
      `agent_trigger.py`'s `except TransitionRefusedError` site) at the same worst-case ids,
      reading the length off the route's own 403 response rather than `JobRun.error_summary` (D2
      already fits that column separately, which is exactly what would hide this bug if the test
      read it from there instead). *Mutation applied* (lengthened the evidence branch's f-string
      to restore something in the shape of the pre-fit wording, measured 681 chars at these ids):
      the direct test failed on `len(message) <= 500`. Reverted.

## 5. Verify

- [ ] 5.1 CI's lint set:
      - `ruff check src/ hub/ tests/`;
      - `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`;
      - `mypy src/`.
- [ ] 5.2 `py -3.11 -m pytest hub/tests/ -q`, full. Record pass and fail counts. Classify any
      failure against DEAD-ENDS (F292 and F314 signatures) before calling it unrelated.
- [ ] 5.3 Drive (night-window.md, *Driving*): a drive Hub on a free port with a fresh
      `profiles/` database; runners bound to `claude-haiku-4-5-20251001`; a flow with a document.
      Read:
      - `GET …/jobs/{id}/history` → 200 after a wedged review with a long title;
      - the drawer's status menu → `under_review` on the author-held task, with the refusal
        rendered beside Land it (Chromium);
      - one real Haiku agent turn asked to move that task to `under_review`, and the refusal
        text it received, read from its tool result.

      Leave no job enabled.
- [ ] 5.4 Archive:
      - sync `agent-loops` and `task-lifecycle-governance` deltas into `openspec/specs/`;
      - move the change to `archive/<date>-a-refusal-names-a-remedy-that-works`;
      - in FINDINGS, mark F353, F334, F365 and F367 `fixed <sha>`.
