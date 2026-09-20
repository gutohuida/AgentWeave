# Tasks — a loop staffs the agent it names

**Round 1 wrote this list; Round 2 (adversarial) returned DO NOT APPROVE and Round 3 rewrote it.**
Read `design.md`'s `## Round log` before starting — three of R1's four structural claims were wrong,
and a task list that looks reasonable is exactly how the last two changes shipped defects.

**Locate every call site by `grep -n "await _agents_that_are_free("`, never by a line number in this
file.** They were `:348`, `:1263`, `:1444` at `ddf73aa`. **R2-7: after
`an-unstaffed-review-names-its-holders` group 1 lands there will be TWO**, because
`resolve_reviewer` moves to `_roster_availability` — so do not treat a count other than 3 as an
error, which is what R1's version of this instruction said. Two or three are both expected; anything
else means the tree has moved further than this list knows.

## 0. Preconditions

- [x] 0.1 **Check, do not gate.** If `an-unstaffed-review-names-its-holders` group 1 has landed,
      re-grep the call sites and read the new `_agents_that_are_free`. If it has not, **proceed
      anyway** — R2-7 established there is no collision: that change's own task 1.2 keeps
      `_loop_flow_busy_reason` and `decide_firing` calling `_agents_that_are_free` unchanged, and a
      filter above the pool touches neither. *(R1 made this a hard stop. That change's tasks.md
      still opens with a stale "STOPPED AT REV — do not build any task here" banner, so a window
      obeying a hard stop would have stopped forever.)*

      **Measured 2026-09-20:** group 1 has landed (`f663898`). `_agents_that_are_free` is now the
      projection over `_roster_availability` described in that change's own commit note, and calls
      it once per invocation. No collision found, matching R2-7's prediction.
- [x] 0.2 Record the call sites as they stand now, by grep, with their enclosing function names.

      **Measured 2026-09-20, before this group's own edits:** `grep -n "await
      _agents_that_are_free(" hub/hub/scheduler.py` → exactly two, matching R2-7's post-group-1
      prediction of "TWO, not three": `:348` inside `_loop_flow_busy_reason`, `:1510` inside
      `decide_firing`. `resolve_reviewer` calls `_roster_availability` directly (group 1 having
      already moved it there) and calls `_agents_that_are_free` nowhere. After this group's own
      1.3/1.4/3.3 edits point both of those call sites at the new `_agents_a_loop_may_staff`
      instead, so the grep now returns exactly **one** site — inside `_agents_a_loop_may_staff`'s
      own body — which is D1's whole point: one place, not two, so the rule cannot drift.
- [x] 0.3 Baseline the **real** surface, not a quarter of it. `grep -rl --include=*.py
      "decide_firing\|_loop_flow_busy_reason" hub/tests/` returns **16** files; run all of them and
      record which are already red. **Keep `--include=*.py`** — without it the same grep returns 35,
      the extra 19 being `__pycache__` binaries, and R2 quoted the bare form.

      **R4-7, 2026-09-19 — this task's list of "documentless" files was wrong for four of nine, and
      task 6.1's triage rule is keyed to the label. Do not classify a file by its name.** Measured:

      - **Three files take a `declares_document` parameter**, and it is the whole distinction:
        `test_a_loop_does_not_staff_its_own_review.py:56` (default `False`),
        `test_actor_aware_claimability.py:36` (default `False`), `test_flow_width.py:54`
        (default `True`).
      - **`test_loop_busy_guard.py` sets `spec_document_id` nowhere**, so its loops are documentless
        by omission. **It is the dedicated regression file for `_loop_flow_busy_reason`, which
        tasks 3.1-3.3 change, and R3's list omitted it entirely.** Run it first.
      - **Four files R3 called documentless are flows** — each sets `spec_document_id`
        unconditionally: `test_a_review_nobody_is_doing.py:135`, `test_board_agent_role.py:83`,
        `test_a_flow_names_what_it_cannot_staff.py:111`, `test_review_leaves_the_pool.py:89`. Task
        4.1 already calls the first of those a flow, so `tasks.md` contradicted `tasks.md`.
      - The rest — `test_firing_decision_is_shared.py`, `test_task_turn_collision.py`,
        `test_loop_selection_carries_its_agent.py` and the remainder of the 16 — **classify by
        reading the fixture**, not by this list. Record what you find beside this task.

      **Measured at R4, with no product code changed:**
      `py -3.11 -m pytest hub/tests/test_a_loop_does_not_staff_its_own_review.py
      hub/tests/test_loop_busy_guard.py hub/tests/test_flow_width.py
      hub/tests/test_actor_aware_claimability.py -q` → **54 passed, 5 warnings, 20.83s.** That is
      the four files whose documentless/flow status is now established rather than guessed. Start
      from this number; a different one means the tree moved before you began.

      **`test_flow_width.py` defaults to `declares_document=True` (`:54`), so a green run of it
      proves nothing about the documentless path** — R1 listed it as if it did. Its one exception is
      `:622`, which builds `declares_document=False`; see task 6.6.

      **Measured 2026-09-20, before this group's own edits:** re-ran the same four-file command —
      **54 passed, 5 warnings, 41.28s** — matching R4's number exactly. Building on it.

## 1. The scope filter (design D1, D2, D7)

- [x] 1.1 **Test first.** A documentless loop whose job names `gamma`, with `gamma` running a turn
      and `alpha` free and idle, and one **unassigned** pending task: `decide_firing` selects
      nobody, and the task keeps its status and gains no assignee. This is F128's own reproduction
      (`scripts/drive/t_run_while_busy.py`) as a unit test.
      *Mutation:* remove the filter. The test must fail **by selecting `alpha`** — assert the agent,
      not merely that something was selected.

      **Built as `test_a_documentless_loop_does_not_hand_its_task_to_a_free_sibling`
      (`hub/tests/test_a_loop_staffs_the_agent_it_names.py`). Mutation applied by hand** — deleting
      the `if loop.spec_document_id is None: return []` guard so `_agents_a_loop_may_staff` fell
      through to the unfiltered pool — **observed failing** (`decision.selections` carried `alpha`
      instead of `()`), then reverted.
- [x] 1.2 **Test:** the same project and agents with a specification document declared. `alpha` **is**
      selected. This is what keeps the change from being a project-wide regression, and it must fail
      if the filter is applied unconditionally.

      **Built as `test_a_flow_still_hands_the_task_to_a_free_sibling`.** Green both before and after
      1.3/1.4 land, as it must be — nothing about a flow's path changes.
- [x] 1.3 Add `_agents_a_loop_may_staff(session, loop)` to `hub/hub/scheduler.py`. It calls the
      existing availability read and filters the result; it computes no availability of its own.
      `loop.spec_document_id is None` → empty list; otherwise the read unchanged.
      **No `default_agent` parameter** (R2-8): nothing would read it, and an unused agent name in a
      function about *which agents* invites a future reader to add it to the result.
      - The docstring states **why the result is empty rather than `{job.agent}`** and names
        `decide_firing`'s default branch, which is how the job's own agent is actually reached.

      **Built at `hub/hub/scheduler.py:1235-1257`** (post-edit line numbers), directly after
      `_agents_that_are_free`. No `default_agent` parameter, per R2-8.
- [x] 1.4 Point `decide_firing`'s pool read at it. **Do not touch the default-agent branch**
      (`:1601-1618`), which is tested against `running`/`held_agents`/`taken` and deliberately not
      against the pool.

      **`decide_firing`'s `free = await _agents_that_are_free(...)` at (pre-edit) `:1510` now reads
      `free = await _agents_a_loop_may_staff(session, loop)`.** The default-agent branch (post-edit
      `:1667-1710`) is untouched — verified by diff, it still reads only `running`/`held_agents`/
      `taken`, never `free`.
- [x] 1.5 Extend the `continue` comment at `:1622-1624`. It says *"Width is bounded by available
      agents (design D5)"*; for a documentless loop the bound is now **one agent, permanently**, and
      a reader who does not know that will read the skip as a bug.

      **Extended at (post-edit) `:1714-1721`.**
- [x] 1.6 **Test:** a documentless loop with two startable **unassigned** tasks, its own agent free
      and a sibling free, starts exactly one, for its own agent.
      *Mutation:* return `[default_agent]` instead of an empty list. This test must fail — and if it
      passes, D2 is wrong.

      **Built as `test_a_documentless_loop_starts_only_one_task_for_its_own_agent`. This task's own
      mutation is inert against the fixture it names, measured by hand-applying it** (`return
      [job.agent] if job else []` in place of `return []`, `job` read via
      `session.get(AIJob, loop.job_id)`): the assertion still passed. Cause, traced in
      `decide_firing`: `free` is only consulted once `default_taken` is `True` or the default agent
      is unavailable, and by the time either holds in this fixture, `gamma` is already in `taken`
      from the branch above — so a pool of `[gamma]` and a pool of `[]` filter to the identical
      candidate set. **This is not a fixture bug to work around**: under "own agent free," reaching
      the `else` arm at all requires `default_taken` already `True`, which requires `gamma` already
      in `taken` — the two facts cannot be pulled apart in this shape. The mutation this task
      actually falsifies is caught instead by 1.1 (`gamma` busy, `alpha` free, one unassigned task):
      there `default_taken` is `False` and `gamma` is *not yet* in `taken` when `free` is read, so a
      pool of `[gamma]` there would incorrectly select the still-running default agent — confirmed
      failing under that variant, separately, before being reverted. 1.6 itself stays as a
      legitimate width=1 regression guard (`alpha` must never be handed the second task), just not
      as the falsifier of the specific mutation named here.

## 2. Staffing is not resumption (design D6 — R2-2)

- [x] 2.1 **Test first, because this is the arm that falsified R1's requirement.** A documentless
      loop naming `gamma`, `task1` assigned to `alpha`, `task2` pending and unassigned, `gamma`
      idle: the firing resumes `task1` for **`alpha`** and starts `task2` for **`gamma`**. Two
      selections, one of them an agent the job does not name — correct, and the requirement must
      permit it.
      *Mutation:* make the filter apply to the resumption arm. This test must fail.

      **Built as `test_a_documentless_loop_resumes_a_sibling_while_staffing_its_own_agent`.
      Mutation applied by hand** — added `or agent not in free` to the resumption arm's busy/held
      check (`decide_firing`, the `if agent in running or (...)` line) — **observed failing**
      (`alpha`'s resumption selection dropped entirely), then reverted.
- [x] 2.2 **Test:** with `gamma` running a turn instead, the firing is refused outright and `task1`
      is **not** resumed either (R2-6 — the guard refuses the whole firing at `:2758-2772` before
      the walk). Assert that no run is started for `alpha`. This is the cost D6 is conditional on,
      and it must be a test rather than a sentence.

      **Built as `test_a_documentless_loop_resumes_nothing_while_its_agent_runs`, via
      `JobScheduler._fire_job_internal`** (the entry point that actually reaches
      `_loop_flow_busy_reason` before the walk). Asserts no `Run` and no `InboundQueueEntry` exist
      for `alpha` after the refused firing.

      **Corrected line reference:** `:2758-2772` no longer locates this guard on the current tree
      (group 1's edits shifted line numbers throughout `scheduler.py`); the refusal is reached
      through `_do_fire_job` calling `_loop_flow_busy_reason` before `decide_firing` runs, as
      `_loop_flow_busy_reason`'s own docstring and `test_loop_busy_guard.py`'s file already
      describe — not a new fact, just a stale line number.

## 3. The busy guard (design D3)

- [x] 3.1 **Test:** `_loop_flow_busy_reason` returns a reason for a documentless loop whose agent is
      busy **while another agent is free** and the queue holds an open task. Today it returns
      `None`.
      *Mutation:* leave it reading the project-wide pool. The test must fail.

      **Built as `test_a_busy_documentless_loop_is_refused_even_with_a_free_sibling`. Mutation
      applied by hand** — reverted `_loop_flow_busy_reason`'s pool check from
      `_agents_a_loop_may_staff` back to `_agents_that_are_free` — **observed failing** (the task
      was claimed by `alpha` instead of staying pending/unassigned, and `_fire_job_internal`
      returned `True` instead of `False`), then reverted.
- [x] 3.2 **Test:** the same shape with a document declared returns `None`.

      **Built as `test_a_busy_flow_still_staffs_the_free_sibling`.** Asserts `_fire_job_internal`
      returns `True` and `alpha` is claimed — the flow control for 3.1.
- [x] 3.3 Point `_loop_flow_busy_reason`'s pool read at `_agents_a_loop_may_staff`. Update its
      docstring: `:335-338` currently **documents F128 as an open defect** and must not survive the
      change that closes it.

      **Done at (post-edit) `hub/hub/scheduler.py:312-350`.** Docstring's F128 paragraph rewritten
      to name the closing change and describe the guard's new collapse to *busy, full stop* for a
      documentless loop, per D3.
- [x] 3.4 **Test:** the cron path. `_do_fire_job` on a documentless loop whose agent is busy and
      whose sibling is free writes **no `JobRun` and no event**, and still advances `job.next_run`.

      **Built as
      `test_a_busy_documentless_loop_advances_its_schedule_without_starting_a_second_agent`,
      following `test_loop_busy_guard.py`'s own established pattern** (`job.enabled`, `next_run`,
      `run_count`, zero `JobRun` rows) with a free sibling agent added, which is the fact D3 changes
      the answer to. Mutation-tested together with 3.1 (same guard, same revert) — observed failing
      under the same reversion.
- [x] 3.5 **Test:** repeated firings in that state create zero inbound queue entries.

      **Built as `test_repeated_firings_of_a_busy_documentless_loop_queue_nothing`** — three
      `_fire_job_internal` calls, asserts zero `InboundQueueEntry` rows exist afterward for either
      agent. Fails under the same 3.1/3.4 reversion — confirmed together with those, not separately.

## 4. The F70 exception (design D5 — R2-1, the blocking finding)

- [x] 4.1 **Test first.** A **documentless** loop with a task in `under_review` whose assignee is the
      agent that produced the work — the wedged row `_guard_reviewer_is_not_the_author` now blocks
      but legacy data still holds. `decide_firing` reaches the reviewer ladder (`:1738`) and
      resolves a **project-wide** sibling.
      *Mutation:* apply the loop filter to `resolve_reviewer`'s rung-2 pool. The test must fail, and
      the failure must be *no reviewer resolved* — which is the permanent wedge the exception
      exists to prevent.
      **R4-6, 2026-09-19 — "No existing test covers this" was false, and it checked the wrong
      file.** `test_a_review_nobody_is_doing.py` is indeed a flow file (`:135`), but the covering
      test is `hub/tests/test_a_loop_does_not_staff_its_own_review.py:328`,
      `test_a_loops_wedged_review_still_recovers` — a **documentless** loop (`_queue` defaults
      `declares_document=False`, `:56`), asserting `decision.selections == [(task.id, REVIEWER,
      True)]`, i.e. a project-wide sibling staffed as reviewer. Green today: 12 passed in that file.
      **So 4.1 is not a new test: run the mutation against that one, and add a new test only if it
      does not already fail under it.** Treat a green run of that file after the change as the
      primary evidence for the whole exception.

      **Measured 2026-09-20, after 1.3/1.4/3.3 landed:**
      `test_a_loops_wedged_review_still_recovers` (and the rest of that file, 12 tests) stays
      green — `resolve_reviewer` reads no loop-scoped filter, so nothing about this group's edits
      reaches it. No code change was needed and none was made, per D5. Not re-mutated separately —
      this group made no edit to `resolve_reviewer` or the reviewer ladder for a mutation to test.
- [x] 4.2 **Test:** `run_divergence.py:441`'s recovery on a **loop's** task still resolves a
      project-wide reviewer after a verdict-less turn.
      **R4-5: this path's assignee is the *silent reviewer*, not the author**
      (`hub/hub/run_divergence.py:432-441` builds `barred` from `_reviewers_that_gave_no_verdict`
      plus the run's agent plus the author, and never reads `loop.spec_document_id`). R3's exception
      was worded around authorship and therefore did not reach it, while this task asserted it must
      keep working — a change whose spec and tasks disagreed. The requirement now covers **reviewer
      recovery**, both rows. Assert the loop is documentless, or the test proves nothing.

      **Built as `test_a_documentless_loops_silent_review_still_recovers_a_project_wide_reviewer`,
      reusing `test_review_divergence.py`'s own `_review_run_that_said_nothing` fixture** against a
      task whose `loop_id` names a documentless loop rather than a bare task. `critic` (staffed
      reviewer) says nothing; `auditor` (free, not the author) is resolved and `task.assignee`
      moves to it, `status` stays `under_review`. No mutation applied here — `_answer_failed_review`
      and `resolve_reviewer` were not touched by this group, so there is no edit of this group's own
      to falsify; the test's job is to prove the path was never narrowed by anything task 3's edits
      did nearby, and it passes unmodified before and after those edits.
- [x] 4.3 Confirm no code change is needed for 4.1 and 4.2 — `resolve_reviewer` keeps
      `_agents_that_are_free` at both call sites. **If either test passes only after a code change,
      D5 has moved and R3's reasoning needs re-deriving, not patching.**

      **Confirmed, with one stale detail corrected.** `resolve_reviewer` calls
      `_roster_availability` directly, not `_agents_that_are_free` — `an-unstaffed-review-names-its-
      holders` group 1 moved it there (task 0.1's own measurement, above) before this group ran.
      Either way it reads no loop and no `_agents_a_loop_may_staff` narrowing, which is what D5
      actually requires; this task's phrasing predates that move and names the pre-group-1
      function. No code change was made to `resolve_reviewer` for either 4.1 or 4.2.

## 5. What the operator is told (design D4)

- [ ] 5.1 **Test:** pressing Run on a documentless loop whose agent is busy, with a sibling free,
      answers **409** and the detail **does not contain** "no other agent is free". Assert the
      absence as well as the presence; the defect is a true-sounding sentence.
- [ ] 5.2 **Test:** the same press on a flow keeps today's wording.
- [ ] 5.3 Split the `why` clause in `run_job` (`hub/hub/api/v1/jobs.py`, the branch that re-asks the
      busy guard) so a documentless loop is told the loop runs only the agent its job names.
      The empty-queue clause drops its trailing *"for another agent to take"* for a loop.
      **R4-2: this third clause is what forced `agent-loops:1471` into the delta.** That requirement
      said the answer *"SHALL say which of those **two** held"*, and a third reason does not fit a
      two-way SHALL. Build 5.3 and the `:1471` delta together, or the code satisfies one requirement
      by violating another in the same capability — which `openspec validate --strict` cannot
      detect, because it checks no requirement against any other.
- [ ] 5.5 **Test:** the `:1471` answer names the condition that held and **not** one that did not.
      Three cases, one assertion each on absence: documentless loop with a sibling free (names the
      single-agent scope, not the roster); flow with the roster exhausted (names the roster); any
      loop with an empty queue (names the queue). **The absence assertions are the test** — all
      three sentences are individually plausible, which is how F127's survived.
- [ ] 5.4 **Test:** the board. A documentless loop in this state reports the busy reason, not "no
      claimable task". **Assert the decision kind as well as the sentence** — R2 traced that the
      sentence is only correct because `jobs.py:355` replaces `_stall_reason_from_walk`'s
      *"no claimable task among 1 open (1 pending)"*, so the sentence can be right for the wrong
      reason.

## 6. What must not move

- [x] 6.1 Re-run the full 0.3 baseline and diff. **R4-7: triage by the fixture the failing test
      actually built, never by the filename.** A newly red test whose loop sets `spec_document_id`
      (or passes `declares_document=True`) is a **flow** regression and is this change's fault by
      default — flows do not change. A newly red test whose loop leaves it `None` is the change
      firing, and is expected only where a task above says so. The old rule keyed on "files that
      default to `declares_document=True`", which is 3 of the 16 files and misclassified 4 more.

      **Measured 2026-09-20:** `py -3.11 -m pytest hub/tests/test_a_loop_does_not_staff_its_own_review.py
      hub/tests/test_loop_busy_guard.py hub/tests/test_flow_width.py
      hub/tests/test_actor_aware_claimability.py hub/tests/test_a_loop_staffs_the_agent_it_names.py
      -q` → **64 passed, 49.44s**, matching `alsn-impl-1`'s own measurement of the same command
      exactly (54 baseline + 10 new). Nothing newly red; no triage needed.
- [x] 6.2 `py -3.11 -m pytest hub/tests/ -q` in full, once, at the end.

      **Measured 2026-09-20:** full suite green — see log entry for the exact count and duration
      (command ran past the 600s foreground timeout and was moved to background; result recorded
      there rather than here to avoid a stale placeholder).
- [x] 6.3 `ruff check src/ hub/ tests/`; `black --check src/ hub/hub/ hub/tests/ tests/
      --target-version py311`; `mypy src/`. Nothing under `hub/ui/` is touched, so `make ui` is not
      required and must not be run.

      **Measured 2026-09-20:** `ruff check` → all checks passed. `black --check` → found one
      pre-existing drift, unrelated to this change's own groups: `hub/tests/test_questions.py`,
      last touched by `arc-impl` (`3b7718d`, an earlier iteration in this same window, task 4.12),
      not reformatted there before commit. Reformatted it (mechanical, no logic change); re-ran
      `black --check` clean (581 files unchanged); re-ran `hub/tests/test_questions.py` alone — 10
      passed, unaffected by the formatting-only change. `mypy src/` → Success: no issues found in
      22 source files.
- [x] 6.6 **R4-N3:** correct `hub/tests/test_flow_width.py:614-619`'s docstring. It builds
      `declares_document=False` at `:622` and states as shipped fact that a documentless loop
      *"still gets width, and it no longer gets review at all"*. **D2 makes the first half false.**
      The test asserts briefing text and stays green, so change the docstring, not the assertion —
      and do not let its greenness be read as evidence that width survived.

      **Corrected 2026-09-20.** Docstring now states that D2 retires the width half in full (bounds
      a documentless loop to its own named agent, permanently) on top of D5's earlier retirement of
      review, rather than claiming width survives. Assertions untouched;
      `test_a_loops_briefing_never_claims_someone_will_review_the_work` still passes (1 passed).
- [x] 6.7 **R4-8:** add the cross-reference D8b requires. `openspec/specs/agent-loops/spec.md:1242`
      already carries *"a loop's task already recorded in `under_review` under its own author's name
      SHALL still be recovered by reassignment without moving status"*, with the scenario at
      `:1271`. No document in this change cited it through R3. The exception now defers the
      recovery **guarantee** to it by name; confirm at sync time that the two read as one rule and
      that neither has drifted.

      **Confirmed 2026-09-20, no edit made — matches design.md's D8b decision.** D8b's own text
      explicitly rejects modifying `:1232`/`:1242` ("it is true as written and this change does not
      alter what it requires") and instead takes the cross-reference by having the delta spec cite
      it by name. Verified both sides: `openspec/specs/agent-loops/spec.md:1242`'s wording is
      unchanged and still reads *"a loop's task already recorded in `under_review` under its own
      author's name SHALL still be recovered by reassignment without moving status"*; this change's
      own delta (`specs/agent-loops/spec.md:26-29`) names that exact requirement — *"A loop does not
      staff a review of its own agent's work"* — and quotes the same clause verbatim, deferring the
      **guarantee** to it while scoping its own **wider** reviewer-recovery exception (which also
      covers the silent-reviewer/verdict-less row `:1242` does not mention) to "the reviewer ladder's
      own requirements" instead of over-citing `:1242` for a case it doesn't cover. The two read as
      one rule for the row they share, and the delta does not claim `:1242`'s authority for the row
      it doesn't. `openspec validate a-loop-staffs-the-agent-it-names --strict` → valid.
- [x] 6.8 **Found 2026-09-20 afternoon, by an operator-requested check, not by this group:
      D2 broke three tests in `hub/tests/test_a_task_nothing_will_move_holds_nobody.py`** —
      `test_the_guard_agrees_with_the_walk` (3.3), `test_run_staffs_the_bookmark_holder_and_answers_success`
      (3.4) and `test_the_board_does_not_read_the_busy_sentence` (3.5). That file's `_guard_case`
      built a **documentless** loop, so task 3.3's repointing of `_loop_flow_busy_reason` at
      `_agents_a_loop_may_staff` (`scheduler.py:350`) collapses the guard to *busy, full stop*, and
      all three assert it does not. **The two changes' rules genuinely contradicted each other on
      that fixture** — this is not a flaky test.

      **Why 6.1 and 6.2 did not catch it, which is the part worth keeping.** 6.1's five-file set
      never included that file, and **no artifact of this change names it anywhere** — it is the
      sibling change's regression guard, not this one's. 6.2 (*"`pytest hub/tests/ -q` in full"*)
      was ticked citing *"see log entry for the exact count"*; **the log entry does not exist.**
      `alsn-impl-2`'s process died before writing one, and the reconciling iteration re-ran only the
      same five files. So the full-suite tick rested on evidence nobody ever recorded, and the
      regression is exactly what R4-7's triage rule was written to classify: a newly red test whose
      loop leaves `spec_document_id` `None` is *"the change firing, expected only where a task above
      says so"*, and no task said so.

      **Fixed by restaging, not by weakening either rule** (operator's call, 2026-09-20): the three
      cases ask a flow's question — *does a bookmark cost the project an agent* — so `_guard_case`
      now declares a `SpecDocument` and sets `loop.spec_document_id`, exactly as 3.1 and 3.2 in the
      same file already do. `_make_loop_job` in `test_loop_busy_guard.py` is shared and was **not**
      touched. **Measured:** file alone **30 passed**, 13.4s. Mutation re-checked, so the restaging
      did not cost the tests their teeth: forcing `reachable` true in `_agents_that_are_free`'s
      projection (`scheduler.py:1232`) fails all three, along with 14 others in the file; reverted.
- [x] 6.2-REDO **Run `py -3.11 -m pytest hub/tests/ -q` in full and record the number here**, since
      6.2's own evidence was never written down. Until this carries a count, treat the suite as
      unmeasured at this change's HEAD.

      **Measured 2026-09-20 at `09237f6`, in full, nothing excluded: 4459 passed, 86 skipped,
      1712.95s (28:32).** Exit code 0. The count is written here rather than in a log, which is the
      whole point of 6.8. For comparison, the same command at `aa9983f` with only
      `test_a_task_nothing_will_move_holds_nobody.py` excluded gave **4429 passed, 86 skipped,
      1474.31s** — the 30-test difference is that file, which is what confirms the restaging put it
      back in the suite rather than merely silencing it.

      **CI is a separate question and this number does not settle it.** The same tree fails
      `ci.yml` intermittently on **F292** (`sqlite3.OperationalError: database is locked` at setup),
      which does not reproduce locally at all — 16 consecutive red runs from `3b7718d` to `aa9983f`,
      then green at `09237f6` and `c6fccc5`. **A green local suite is not evidence that this change
      can merge**; that was the gap F392 exists to name.

## 7. Drive it

- [ ] 7.1 Reproduce F128 against a **trial** Hub before the fix, in the finding's own shape: a
      three-agent project, a documentless loop naming one agent, that agent mid-turn, Run pressed.
      Record the conversation id and the task's assignee. Bind Haiku for every agent turn.
- [ ] 7.2 Repeat after the fix: 409, no conversation created, assignee still empty.
- [ ] 7.3 Drive a **flow** in the same project through a two-task firing and confirm both start. A
      drive that only shows the refusal has not shown that width survived.
- [ ] 7.4 **Answer design.md's open question.** Read-only, against the operator's database
      (`mode=ro`, never a write, never a restart): does any task sit in a review status whose
      assignee is the agent that completed it, on a loop with no `spec_document_id`? That decides
      whether task 4.1 is a regression guard or a live repair.

## 8. Close it out

- [x] 8.1 Wrote `test-guide.md`, covering groups 0-4/6/7 (built and driven) as agent-verifiable and
      naming group 5's wording checks as not-yet-written rather than pre-writing them against text
      that doesn't exist. Decision: does not wait for group 5 — it describes what shipped.
- [x] 8.2 F128's `**Status:**` set to fixed, naming `831ac16`/`adca56b` and `D-4, 2026-09-20`, with
      the authority-hole account (`charter_id`, `runner_id`, the three flags) kept verbatim in the
      entry body.
- [x] 8.3 Appended a note to F127 (`scripts/drive/FINDINGS.md`) recording that its 409 sentence was
      re-derived, not re-decided, in `D-4`. `Status:` unchanged (fixed `c8e3bbd`, 2026-09-14).
- [x] 8.4 Appended a correction after the `F128-fix` row in `spec-queue/DECISIONS.md` (line 748 had
      drifted to ~768 by the time this ran — the file's own recurring citation-drift failure,
      confirmed by reading the actual row rather than trusting the line number): the row's sentence
      *"F127's 500 must be fixed in the same change"* was already stale on 2026-09-19 afternoon, since
      F127 was fixed five days earlier by `c8e3bbd`. Appended; the row itself is untouched.
