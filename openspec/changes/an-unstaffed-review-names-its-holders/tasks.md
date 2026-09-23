# Tasks — an unstaffed review names its holders

> **SUPERSEDED BANNER (R8, 2026-09-21).** The block quoted below is kept as provenance and is **no
> longer the status of this file.** The re-derivation it demands ran (R5, 2026-09-19), was reviewed
> (R6, R6-measured, R6-8), group 1 was built (`f663898`), and R8 (2026-09-21) re-verified groups 2,
> 5 and 6 against the tree — see `proposal.md`'s `RESOLVED 2026-09-19` banner and `design.md`
> `## Round 8`. Whether a night may build groups 2/5/6 is decided by an operator token in
> `spec-queue/APPROVALS.md`, not by this banner. **Build order inside group 2 is fixed: 2.14
> before 2.3** (the ordering note at the top of group 2).
>
> ~~**STOPPED AT REV, 2026-09-14. Do not build any task here.**~~ The operator decided both questions
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

- [x] 2.1 Change `resolve_reviewer`'s `exclude` to `Mapping[str, str]` (agent → clause) and remove
      `excluded_because`. Rung 1b reads `exclude[resolution.agent]`.

      **Built 2026-09-23.** `grep -n "await _agents_that_are_free("` at build time still returned
      exactly `:348`, `:1263`, `:1444` (1.2's own re-verification, unaffected by this task) and
      `grep -rn "exclude=" hub/ --include=*.py` returned **25 lines**, matching R9's count exactly
      -- the tree had not moved since R9. All 21 `resolve_reviewer` call sites updated: the 13 in
      `test_reviewer_ladder.py` and 3 in `test_a_held_agent_is_busy.py` mechanically (a script
      replacing `exclude={NAME}` with `exclude={NAME: "is the one that completed this task"}`), the
      1 in `test_a_task_nothing_will_move_holds_nobody.py` the same way, the 2 in
      `test_a_flow_names_what_it_cannot_staff.py` by hand (`exclude=set()` → `exclude={}`,
      `exclude=await agents_that_worked(...)` → `exclude=dict.fromkeys(await
      agents_that_worked(...), "has worked on this task")`), and the 2 runtime sites
      (`decide_firing`, `_answer_failed_review`) per 2.2 below.
      - `decide_firing` (`scheduler.py:1550-1584`; **R8: now `:1808-1843`**) builds the mapping
        from exactly the clauses it passes today.
      - Update every call site. A missed one fails only where it reaches a named exclusion, and CI
        runs no mypy over `hub/`, so grep `exclude=` before ticking. The sites are:
        - `test_reviewer_ladder.py:97, 121, 146, 159, 170, 189, 242, 257, 283, 322, 347, 372, 383`
          — **thirteen** sites. R6 corrected six of the numbers R1 gave and found a thirteenth the
          list never had;
        - `test_a_flow_names_what_it_cannot_staff.py:471, 478` — **R8: `:472` and `:482`**; `:482`
          passes `agents_that_worked(...)`, a set, and reaches rung 3 (`guarded.rung ==
          "unstaffed"`), so it raises `TypeError` under a `Mapping`;
        - **`test_a_held_agent_is_busy.py:377, 388, 401` (R6) — missing from every earlier round.**
          All three pass `exclude={AUTHOR}`, a set, and all three reach rung 3, so a `Mapping`
          signature makes them raise `TypeError` at `exclude[name]`;
        - **`test_a_task_nothing_will_move_holds_nobody.py:684` (R8) — missing from R6's list.** It
          is group 1's own task-1.4 test, `test_resolve_reviewer_reads_the_roster_once`, added
          after R6 ran; it passes `exclude={author}` and reaches rung 3 by design (a single-agent
          project), so it raises `TypeError` too. The fourth consecutive round at which this list
          was incomplete;
        - `scheduler.py:1738-1745` and `run_divergence.py:441-447` — **R8: `scheduler.py:1836-1843`
          and `run_divergence.py:441-447`** (the latter held).
        - R8 count, `grep -rn "exclude=" hub/ --include=*.py`: **21 `resolve_reviewer` call sites**
          — 13 + 2 + 3 + 1 in tests, 2 at runtime (plus three docstring/comment hits: `scheduler.py:1826`, `test_a_flow_names_what_it_cannot_staff.py:459, 546`). A different count means the tree moved.
          **R9: that grep returns 25 lines, not 24, at `7e2f663` and today** — the fourth non-call
          hit is `main.py:245`, `_git_last_commit_iso(ui_src, exclude=("__tests__",))`, unrelated
          (dated 2026-08-14). 21 `resolve_reviewer` call sites is still right; the tree has not moved.
      - **R6: re-verify every line above before editing.** This list has been wrong at three
        consecutive rounds. Grep for `exclude=` and count; do not trust the numbers.
- [x] 2.2 `run_divergence` (`:430-446`) builds the mapping in three layers, each overwriting the
      one before:
      1. on the operator-completed branch, `agents_that_may_have_authored` → "has worked on this
         task";
      2. the silent reviewers and `run.agent` → "reviewed this task and recorded no verdict";
      3. on the agent-completed branch, the recorded completer → "is the one that completed this
         task".

      **Built 2026-09-23.** `_answer_failed_review` now builds one `dict[str, str]`, applying layer
      1 only `if attribution.agent is None`, then layer 2 unconditionally (`_reviewers_that_gave_no
      _verdict` then `run.agent`, each `dict.update`/assignment overwriting layer 1's entry for the
      same agent), then layer 3 only `if attribution.agent is not None`. A dedicated test proving
      the overwrite order on an agent that is both a silent reviewer and the recorded completer is
      task 2.7's, not built here -- this task is the mapping construction, not its own regression
      test. The full relevant suite (130 tests, listed at 2.4's own note) passed unchanged, which
      exercises `_answer_failed_review` end to end without asserting the layering directly.
- [x] 2.3 Rung 3 builds its reason from the same `_roster_availability` read (1.2).

      > **R8, 2026-09-21 — this block supersedes every earlier bullet of 2.3 where they disagree.
      > Build from this block.** The bullets below it are kept for their reasoning.
      >
      > - **Prefix: `could not staff this step: no reviewer is free. `** (48 characters). The bullet
      >   below still said *"nobody is free."* — the pre-REV prefix REV replaced as false (D2,
      >   *"The sentence leads with the names"*). R6-measured's table already used the REV prefix;
      >   this task never received it.
      > - **Clause precedence: excluded, no runner, HELD, booked, running** — the usage hold now
      >   comes *before* the holdings clause (R8-1). An agent that is both usage-held and booked is
      >   named by the hold only. R6's order (holds before held) silently reverts shipped
      >   behaviour: today `roster_held` (`scheduler.py:1394-1396`) names the hold for any held,
      >   bound, non-excluded agent **whatever it holds**, and `agent-flows`' shipped SHALL
      >   (*"an agent was passed over because its queue is held … SHALL name the hold among the
      >   grounds"*) requires that. Under R6's order a held agent with one reachable task reads
      >   `"X holds …"` and the hold is named nowhere — and rejecting its task would not free it,
      >   because it is still held, so the remedy would be false for that agent.
      > - **Clause wording:**
      >   - excluded: `"{name} {exclude[name]}"`;
      >   - no runner: `"{name} has no runner bound"`;
      >   - held: `"{name} is waiting for its provider's usage limit to reset"`;
      >   - booked: `"{name} is booked for {id} ({status}), {id} ({status}), {id} ({status}) and N
      >     more"` — reachable holdings only, by task id, three named then counted (R8-2: **not**
      >     `holds` — see below);
      >   - running: `"{name} is running a turn"`.
      > - **The join, written out, because R6-8 found the last join nobody concatenated:**
      >   `PREFIX + "; ".join(clauses [+ tail]) + ". " + capitalize_first(own_review_remedy(task)) +
      >   (REJECT if any record took the booked clause else "")`, where `capitalize_first(s)` is
      >   `s[:1].upper() + s[1:]` and `REJECT = " Rejecting booked tasks that are no longer wanted
      >   can free their agents."`
      >   - **`capitalize_first` is required (R8-3).** `own_review_remedy` returns
      >     `"decide it yourself: approve, …"` for `under_review` — **lowercase**
      >     (`scheduler.py:2020`). Placed after `". "` it starts a sentence in lowercase, the same
      >     class of defect as R6-8's `.;`, on the other status. Every earlier round measured only
      >     the `completed` join. The helper is not changed (`agent_trigger.py:503, 511, 521, 848`
      >     share it).
      >   - **The REJECT sentence is conditional (R8-4).** It is appended only if at least one record
      >     took the booked clause (before fitting). With no booked agent — every other agent held,
      >     running or unbound, or a one-agent project — rejecting a task frees nobody, and the
      >     delta's *"that way SHALL have the stated effect for every agent the reason named"*
      >     forbids offering it.
      >   - The empty roster: `PREFIX + "The project has no agent on its roster. " +
      >     capitalize_first(remedy)`, no REJECT. **(R9: capital `T` — R8 wrote `"the project…"`
      >     after the prefix's `". "`, R8-3's lowercase-after-a-period on the one join R8 itself
      >     added. Tested exactly by 2.18.)**
      > - **Why `booked` and not `holds` (R8-2).** D2's R5 paragraph decided that the sentence and the
      >   roster disagree on purpose (the roster counts every live task, the reason names only
      >   reachable ones) and that *"the remedy sentence says the list is what something will still
      >   move"*. No task ever carried that wording, and the delta's SHALL (*"worded so that a reader
      >   is not told the two disagree about the same fact"*) had no implementing task. `holds` is
      >   the roster's own word for the roster's own set (`agents.py` "active task"); using it for a
      >   subset is exactly the contradiction. `is booked for` says *something will bring this agent
      >   back to this task*, which is (f)'s definition, and costs 8 characters per booked agent
      >   rather than a 44-character gloss sentence (R8 measured both).
      >
      > **Assert the joined string exactly, for both statuses** (the R6-8 rule). One test per
      > status, `==` against a literal.

      **Built 2026-09-23, from the R8 block above.** `scheduler.py` gained `_rung_3_clause_kind`
      (the five-way precedence), `_rung_3_clause_text`, `_rung_3_booked_clause`, `_rung_3_tail`,
      `_rung_3_join` and `_rung_3_reason`, all pure functions over `_roster_availability`'s one read
      -- `resolve_reviewer`'s fallback now returns
      `ReviewerChoice(rung="unstaffed", reason=_rung_3_reason(task, availability, exclude))` in
      place of the old static-sentence `f"..."`.

      **Build-time correction to the R8 block's own premise.** R8-3 says `own_review_remedy`
      returns *"decide it yourself: approve, …"* lowercase for `under_review`
      (`scheduler.py:2020`). At the tree this was built against (`scheduler.py:2142`) it returns
      `"Decide it yourself: …"`, **already capitalized** -- the tree moved since R8 wrote that note,
      the fourth such drift this file records (R7 on the caller list, R8/R9 on the `exclude=`
      count). `capitalize_first` is still applied unconditionally, per the R8 rule, and is a no-op
      on the tree as it stands; the two literal tests below assert the actual capitalized string,
      not R8's predicted lowercase one, so a future regression that *does* lowercase the sentence
      would still be caught by the join, just not by a case change this task's tests do not exist to
      detect.

      **`test_rung_3_reason_is_this_exact_string_for_a_completed_task` and
      `..._for_an_under_review_task`** (`test_reviewer_ladder.py`) are the R6-8/R8 pair this block
      calls for: a single-agent (author-excluded) roster, `==` against a literal, one per status.
      *Mutation:* changed the join's `". "` before the remedy to `"; "` (the exact defect class
      R6-8 found the last round missed). Both tests failed, on the literal `==`. Reverted;
      `git diff --stat` confirmed the file was back to the one-line change.

      - clause precedence is excluded, then no runner, then holds (three, then "and N more"), then
        running; **(R8: superseded — see the block above)**
      - clauses in name order, leading with `could not staff this step: nobody is free.`
        **(R8: wrong prefix — `no reviewer is free.`; see above)**;
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
      - **R6: clause precedence is excluded, no runner, holds, HELD, running** — five clauses.
        **(R8: order superseded — HELD now precedes booked; see the R8 block.)** The
        held clause is `"{name} is waiting for its provider's usage limit to reset"`. It is
        required by a shipped SHALL in `openspec/specs/agent-flows/spec.md`, and without it a held
        agent is reported as running a turn, which is false.
      - after the helper's sentence, rung 3 itself appends " Rejecting held tasks that are no
        longer wanted can free their agents." **(R8: now " Rejecting booked tasks …", and only when
        a record took the booked clause — see the R8 block)** — **a new sentence, space and capital, not a `;`**
        (R6-8). `own_review_remedy` already ends in a period, so the `;` every round wrote
        produces `…yourself.; rejecting…`. Assert the joined string in the test, not the two
        halves separately: that is why five rounds missed it.
        The dispatch refusal (4.2 — **R8: moved to the archived sibling; the code is
        `review_dispatch_refusal`, `api/v1/agent_trigger.py:495-521`**) does not append this clause
        at all.
      - **R6: the remedy names rejecting, and nothing else.** It must never suggest pausing (a
        paused loop still holds, `scheduler.py:1084-1085`) and must never claim that ending or
        archiving a loop frees an agent (reachability is an OR; the queued arm survives an
        archive). Both would be fresh instances of F353.
- [x] 2.4 Bound the reason to 500 characters. If the whole sentence fits, use it. Otherwise add
      clauses in name order while the prefix, the clauses, the tail
      "; and N more agents are excluded, busy or unbound" and the remedy still fit.

      **Built 2026-09-23.** `_rung_3_reason` tries the full join first (2.3's happy path); over
      budget, it walks `availability` in name order, retrying a booked clause at `limit=3, 2, 1`
      (recomputing the trial join, including the tail's *actual* remaining count and held-variant
      wording, at each retry) before leaving that agent and everyone after it to the tail. Sanity-
      checked directly against `_rung_3_reason` (not through a real firing -- that fixture is 2.6's
      and the twelve-agent length tests are 2.9/2.9b's, not duplicated here): a 20-agent roster each
      booked for three 24-character task ids stayed under 500 at both statuses (480/492) with the
      fit visibly shrinking a later agent's booked clause from three named tasks to two before
      falling to the tail's "N more agents are excluded, busy or unbound"; a held agent pushed past
      the fit cutoff produced the tail's held variant ("waiting for a usage limit or unbound"); the
      empty-roster branch and a small roster with one held agent (2.3's own R8 concern) both checked
      separately. These are mechanism checks, not the shipped regression tests -- 2.9's twelve-agent
      fixture and 2.9b's fallback fixture are still open and still need their own `==`-against-a-
      literal assertions once built.
      - **R8: the tail names the hold when it counts a held agent.** If any agent left to the tail
        took the held clause, the tail is `"; and N more agents are excluded, busy, waiting for a
        usage limit or unbound"` (77 characters at N=12, 78 at N=999). Otherwise it is R3's. The
        fit is **in name order**, so a held agent late in the alphabet on a large roster is counted,
        not named; with R3's tail the hold would then be named nowhere, which is the shipped
        `agent-flows` SHALL (*"SHALL name the hold among the grounds"*) broken by the fit rather
        than by the clause list. The fit must reserve the tail's actual length, not 50.
      - **R8: "the remedy" in the fit means the whole ending** — `". " + capitalize_first(remedy)`
        plus the REJECT sentence where 2.3 appends it. R8 measured (`%TEMP%` scratchpad
        `r8len2.py`, the 2.3 R8 strings): fixed overhead at `under_review` with the long tail is
        **274**, leaving **226** for clauses (**256** at `completed`). The widest single clause is
        **143** at one named task (a 32-character name, 64-character ids, `revision_needed`,
        "and 1002 more"), 227 at two and 311 at three; a held clause at a 32-character name is 83
        and an excluded one 75. So the first clause always fits at one task, and R3's "at least one
        agent is always named" still holds.
      - **R8 totals** (17-character ids): LoopEngine shape **432 / 462** (`completed` /
        `under_review`); the same plus one usage-held agent **488 / 518 — over at `under_review`**;
        five agents 408 / 438; six 458 / 488; **seven 508 / 538 — over**. The `booked` verb costs 8
        characters per booked agent over `holds`; the fit fires one roster size earlier than
        R6-measured's table, and at the flagship shape plus a single hold.
      - A holds clause that would not fit is retried with two named tasks, then one, counting the
        rest as "and N more". Only then is its agent left to the tail (R3).
      - **R6: there is no loop id to drop any more.** The fallback is the pre-R5 one: three named
        tasks, then two, then one, then the agent falls to the tail.
      - **R6, do this FIRST: re-measure D2's character budget table.** R5 lengthened clause 3 and
        the remedy without recomputing it, and the review measured the flagship shape at 559/589
        against a 500 bound. R6 removed both additions, which should restore it — but clause 4 adds
        a per-agent string that never existed, and "shorter than before" is not a measurement. The 500 bound is enforced at the
        model since `fit_error_summary` shipped (`models.py:1336-1348`; **R8: now `:1367-1379`, the
        `@validates` at `:1413`**), so an over-long reason is
        now silently truncated rather than loudly wrong — which is exactly the failure mode a stale
        budget table produces.
~~- [ ] 2.5~~ **MOVED 2026-09-15** to `a-refusal-names-a-remedy-that-works/tasks.md` task 2.1
      (Fit `JobRun.error_summary` at the model). Built there, not here.
~~- [ ] 2.5b~~ **MOVED 2026-09-15** to the same directory's task 2.2 (`_wedged_review_reason`'s
      title fit). Built there, not here. **This half's own tasks (2.6, 2.9, 2.9b, 2.11) still
      depend on that fit existing** — it is a model-level `@validates`, so it applies to every
      write regardless of which change added it, and the sibling directory builds first.
> **Night iteration 9, 2026-09-23 — split note.** The queue's own `unstaffed-group2-task2.6to2.11`
> item named all six of 2.6-2.11 as one build. 2.10 and 2.11 were built this firing (above): both
> are regression cover for the sibling directory's already-shipped code, with no new fixture design
> and no ambiguity about what they test. The remaining four — 2.6, 2.7, 2.9, 2.9b — were not: they
> all depend on R8's one open fixture decision (every non-author holding, and the author's own
> extra task, must live in a *second* live loop this firing never fires, per 2.6's own R8 block —
> a shape no test in this file has built yet) and 2.6 in particular is a real-firing test with a
> 409/detail/event three-surface assertion, sized on its own to what iteration 7's split treated as
> one whole item. Rushing four fixture-heavy tests after two already-verified ones risked exactly
> the failure this project's history warns about (a plan that reads right and an implementation
> that does not match it) — so they stay queued as their own item, `unstaffed-group2-task2.6to2.9b`,
> for the next firing. **2.8 is not carried forward as a separate task.** Re-reading it against 2.3's
> own build: `test_rung_3_reason_is_this_exact_string_for_an_under_review_task` (built with 2.3,
> `test_reviewer_ladder.py`) already asserts the whole `under_review` reason with `==`, already
> contains `". Decide it yourself:"` capitalised, and names the same fixture (a single-agent,
> author-excluded roster) 2.8 would need. **Checked live, not assumed:** applied 2.8's own R8
> mutation (drop `capitalize_first` from `_rung_3_reason`'s `remedy = ...` line) and re-ran both of
> 2.3's exact-string tests — both still passed. `own_review_remedy` returns an already-capitalized
> sentence for both statuses on this tree (2.3's own build-time correction note says so), so
> `capitalize_first` is a genuine no-op here and *no* test reached through the real function can
> observe that mutation — 2.8 as R8 specified it is unfalsifiable on this tree, the same vacuous-test
> shape (F190) this file has flagged twice already (2.6's R6 note, 2.10's R8 rewrite). Reverted;
> `git diff --stat` showed no change. Recorded here rather than silently dropped, so a future round
> does not re-open it without reading this note and re-checking the premise (own_review_remedy's
> capitalization) first, since a change there would make the mutation live again.
- [x] 2.6 Test, LoopEngine-shaped, through a real firing (`POST …/jobs/{id}/run`), reading the
      `review_unstaffed` event **and** `LoopSummary.stall_reason`. Four agents: the author; one
      holding an `under_review` task; one holding five `pending` tasks; one holding an
      `in_progress` task with no turn.

      **Built 2026-09-23, night iteration 10, from the R8 block below.** Added
      `test_a_loopengine_shaped_firing_names_every_reachable_holder` to
      `test_a_task_nothing_will_move_holds_nobody.py`, next to the file's own `_loop`/`_holding`
      helpers it depends on. Fixture: `_flow_queue(declares_document=True)` + `_flow_task` +
      `_completed_by` + `record_review_evidence` for the reviewable task (the job's own agent is
      the author, per R8); a **second** live loop (`_loop(db, suffix="2.6-elsewhere")`) holding the
      author's own extra `in_progress` task (REV) plus B's `under_review` task, C's five `pending`
      tasks, and D's `in_progress` task, all carrying that second loop's id so each is reachable
      without the firing under test ever walking it; a sixth, unreachable task for C
      (`loop_id=None`, nothing queued) for the delta's own "a task nothing will move is not named"
      scenario. Fired through `POST …/jobs/{id}/run` (`live_scheduler` + `_no_spawn()`), asserted
      the whole reason `==` a literal, and cross-read it on all three surfaces: the 409 `detail`,
      the `review_unstaffed` `EventLog` row's `data["reason"]`, and `LoopSummary.stall_reason`
      (`_batch_loop_summaries`) — all three equal. Also asserted the unreachable sixth task's id is
      absent and every non-author clause reads "is booked for", never "holds".

      *Mutations, all applied live to `scheduler.py` and reverted, `git diff --stat` clean after
      each:* (a) dropped the booked branch from `_rung_3_clause_kind` (falls to "running") — failed
      on the `==` literal, every booked agent read "is running a turn" instead. (b) moved the
      booked check ahead of the excluded check — failed: the author's own reachable holding (REV's
      addition) made *it* read "is booked for task-2.6-author (in_progress)" instead of "is the one
      that completed this task", exactly the fixture-dependent bite R8 predicted; without that
      holding this mutation could not have failed. (c) `_rung_3_clause_text`'s excluded branch
      returns a fixed `"{name} is excluded"` instead of the `exclude` mapping's own per-agent
      reason — failed on the literal. *Fixture check (R6):* temporarily set every non-C holding's
      `loop_id` to `None` (three of the four `_holding` calls — the loop over C's five tasks kept
      its indentation and was not touched by the same edit, so C's five stayed reachable) — the
      firing then answered 200, not 409 (B or D, now free, got staffed), proving the fixture's
      reachability is what makes the stall happen at all, not an assertion artifact. Reverted;
      `git diff --stat` clean.

      Full relevant suite: `pytest hub/tests/test_reviewer_ladder.py
      hub/tests/test_a_held_agent_is_busy.py hub/tests/test_a_flow_names_what_it_cannot_staff.py
      hub/tests/test_a_task_nothing_will_move_holds_nobody.py hub/tests/test_review_divergence.py
      hub/tests/test_run_divergence.py -q` → **133 passed** (130 + this task's 1 new test; matches
      the file-level count of 32, up from 31). `ruff check src/ hub/ tests/`,
      `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` (one reformat needed,
      applied and re-checked clean), `mypy src/` (CI's exact paths) — all clean.

      **2.7, 2.9 and 2.9b split off to their own queue item** (`unstaffed-group2-task2.7to2.9b`) —
      each needs its own fixture design on top of this task's one (2.7 the divergence path's
      restaff-with-nobody-left on both branches; 2.9 the twelve-agent 500-char fit; 2.9b the
      64-character-id fallback), and this task alone — the real-firing, three-surface test the R8
      block itself sized as one whole item's worth of work — took the room a firing has today.

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

      > **R8, 2026-09-21 — the fixture, decided rather than left as "re-check".**
      > - **Every non-author holding, and the author's extra task, lives in a SECOND live loop**
      >   that this test never fires — `_loop(db, suffix=…)` and `_holding(db, loop_id=…)` in
      >   `test_a_task_nothing_will_move_holds_nobody.py:76, 102`. That makes each one reachable
      >   (`loop_id in live`) without being walked by the firing under test, so R3's caveat (an idle
      >   assignee's in-loop task is resumed as a selection and the firing claims instead of
      >   stalling) cannot arise, and no agent needs staging as `running`.
      > - **REV's "the author holds one live task outside the loop" must be in that second live
      >   loop too.** With `loop_id` NULL it is unreachable, rung 3 prints nothing for it, and
      >   mutation (b) (holds before excluded) reads identically — the exact reason REV added the
      >   task, defeated by (f). R6 said *"stays as it is"*; it does not.
      > - Base the flow on `test_the_loopengine_shape_staffs_its_review`'s fixture
      >   (`_flow_queue(db, suffix=…, declares_document=True)`, same file `:318-333`), which already
      >   reaches the ladder with evidence naming a commit. **The job's agent is the author** and is
      >   neither running nor held — otherwise `_loop_flow_busy_reason` (`scheduler.py:312-352`)
      >   refuses the firing before `decide_firing` runs and no `review_unstaffed` is recorded.
      > - **`POST …/jobs/{id}/run` answers 409 on this stall, not 200**: the firing writes a
      >   `skipped` row and returns `False` (`scheduler.py:3114-3135`), and the route turns a
      >   `skipped` newest row into 409 with `detail = error_summary` (`api/v1/jobs.py:1363-1367`).
      >   Assert the 409 **and** that `detail` equals the event's reason — the three surfaces
      >   carry one string.
      > - Assert the whole reason with `==` against a literal (2.3's R8 block), and that it contains
      >   `is booked for` for each non-author, and not `holds`.
      > - *Mutation (R8):* put the author's extra task back at `loop_id=None`. Mutation (b) must then
      >   stop failing — run it once to prove the fixture is what makes (b) bite, then restore.
      > - **The delta's scenario *"A task nothing will move is not named as a reason"* had no test
      >   in group 2** (1.3 tests the record, not the sentence). Give the five-task agent one more
      >   task with `loop_id=None` and nothing queued, and assert its id is absent from the reason
      >   and the count still reads "2 more". *Mutation:* build the booked clause from every
      >   holding, ignoring `reachable`. The test must fail (the id appears, the count reads "3
      >   more").

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
      **R8:** the divergence path surfaces its reason on the `run_diverged` event's `reason`
      (`run_divergence.py:813-821`), never on `review_unstaffed` — read it there, as
      `test_the_evidence_names_the_author.py:663-694` does. Every other agent must be unavailable
      through a **reachable** holding (second live loop), a hold, or a running turn; an agent
      holding only an unreachable task is free and the restaff succeeds instead.
~~- [ ] 2.8~~ **SUBSUMED BY 2.3, 2026-09-23 (night iteration 9) — see the split note above 2.6.**
      `test_rung_3_reason_is_this_exact_string_for_an_under_review_task` already builds this task's
      fixture and assertion in full, and its own R8 mutation is checked, live, to be unfalsifiable
      on this tree (see the note). Not built as its own test; the reasoning is recorded, not the
      task silently dropped.
- [ ] 2.9 Test, twelve agents each holding three tasks:
      - the reason is at most 500 characters, counts the unnamed agents, and still names the
        remedy;
      - `GET …/jobs/{id}/history` answers **200** with the stall row in it.

      *Mutation:* remove the bound (2.4) and the fit (sibling directory's 2.1, once built). The
      history route must fail, which proves the test reaches `JobRunResponse`.
      **R8:** (i) the fit shipped (`models.py:1367-1379, 1413`), so "once built" is now. (ii) A
      second mutation: remove **only** 2.4's bound. The model fit then cuts the sentence to 499 +
      `…`, the route still answers 200, and the test must fail on *"still names the remedy"* —
      that is the mutation that proves 2.4 itself; the first one proves only the sibling's fit.
      (iii) Every holding in a second live loop (2.6's R8 fixture); with `loop_id` NULL none is
      reachable, all twelve agents are free, and rung 3 is never reached. (iv) Make one agent
      late in name order usage-held and assert `"waiting for a usage limit"` appears in the
      tail — *mutation:* always use R3's tail. The test must fail (R8-5).
- [ ] 2.9b Test (R3): the first agent in name order holds three tasks with 64-character
      caller-chosen ids (created through `POST …/tasks` with `id`), and its name is 32 characters.
      Assert:
      - the reason is at most 500 characters, as an `under_review` row, which has the smaller
        budget;
      - it names that agent with fewer than three of its tasks, plus "and N more";
      - it still names the remedy.

      *Mutation:* drop 2.4's per-clause fallback. The agent must then be missing from the reason,
      so the test fails.
      **R8:** the three 64-character-id tasks must carry the second live loop's id (2.6's R8
      fixture) — created through `POST …/tasks` if that route takes a `loop_id`, else with
      `_holding(db, task_id=…, loop_id=…)`; the route is not the point, the 64-character id is.
      With `loop_id` NULL they are unreachable, the agent is free, and the test never reaches
      rung 3. R8 measured the widest clause as **143** at one task under the `booked` verb, inside
      the **226** `under_review` clause budget (2.4).
- [x] 2.10 Test: two consecutive stalled firings with an unchanged reason over 500 characters leave
      **one** stall row with `tick_count == 2`.
      *Mutation:* compare the raw `stall_reason` at `:923`. The test must fail.

      > **R8 — as written this test cannot fail (F190's shape), and is rewritten.** Once 2.4 bounds
      > rung 3 to 500 characters, no rung-3 reason is over 500, `fit_error_summary` returns it
      > unchanged, and comparing the raw reason is identical to comparing the fitted one — the
      > mutation is a no-op. The comparison it guards also **shipped** with the sibling
      > (`_stall_run_to_increment` already compares `fit_error_summary(stall_reason)`, at
      > `scheduler.py:975`; `:923` is stale), and no test covers it (grep `hub/tests` for
      > `_stall_run_to_increment`: none).
      >
      > **Rewritten:** a direct test of `_stall_run_to_increment` — write a `skipped` `JobRun` whose
      > `error_summary` is set to a 600-character reason (the `@validates` stores 499 + `…`), then
      > call `_stall_run_to_increment(session, job_id, that_600_char_reason, exclude_run_id="x")`
      > and assert it returns that row. *Mutation:* compare the raw `stall_reason` at `:975`. The
      > test must fail (it returns `None`). It is regression cover for the sibling's shipped code,
      > not for this change's; it stays here because this change is what makes long stall reasons
      > ordinary.

      **Built 2026-09-23, night iteration 9.** Added
      `test_a_stall_reason_over_budget_still_matches_the_fitted_row` (the positive case, R8's
      rewrite exactly) and `test_a_stall_reason_that_actually_changed_does_not_match` (the negative
      case — a genuinely different reason must not coalesce) to `test_reviewer_ladder.py`, direct
      unit tests of `_stall_run_to_increment` against a real `AIJob`/`JobRun` pair. *Mutation:*
      replaced `fit_error_summary(stall_reason)` with the bare `stall_reason` at `scheduler.py:978`
      — the positive test failed (`assert None is not None`, since the stored row's own
      `@validates` fit it to 500 chars but the raw 600-char argument no longer matched). Reverted;
      `git diff --stat` on `scheduler.py` showed no change. 2 passed both before and after.
- [x] 2.11 Test, F367 through a real firing: a wedged review (F154's shape) whose reviewer has a
      32-character name and whose task has a 256-character title. Assert:
      - `GET …/jobs/{id}/history` answers 200;
      - the stall row's reason is at most 500 characters and still ends with the remedy
        (`revision_needed.`).

      *Mutations:* (a) remove the sibling directory's title fit (its task 2.2), so the history
      still answers 200 but the remedy is cut; (b) remove the `@validates` as well (its task
      2.1), so the route answers 500.
      **R8:** both halves shipped (`_wedged_review_reason`'s title fit, unit-tested at
      `test_a_refusal_names_a_remedy_that_works.py:119`; the `@validates`). This test touches no
      code this change writes — F154's wedged-review sentence is not rung 3 — so it is route-level
      regression cover for the sibling. Its mutations can fail; keep it, but do not count it as
      evidence for any of this change's decisions.

      **Built 2026-09-23, night iteration 9.** Added
      `test_f367_a_wedged_review_with_a_long_name_and_title_still_fits_the_column` to
      `test_a_review_nobody_is_doing.py` (F154's own file), through a real
      `POST …/jobs/{id}/run` against a 32-character-name reviewer and a 256-character task title
      (`_wedged` there widened with an optional `title=` kwarg, default unchanged for its other 20
      callers). Both mutations applied live and reverted: (a) stripped `_wedged_review_reason`'s
      title-shortening loop down to `text = _sentence(title)` — the test failed on the `endswith`
      assertion (the remedy itself was truncated: `"...review i�"`, matching the task's own
      prediction of what the mutation does); (b) with (a) still applied, also disabled `JobRun`'s
      `@validates` — the route raised `fastapi.exceptions.ResponseValidationError` (`string_too_long`
      on `error_summary`), which is the 500 the task predicts. Both reverted; `git diff --stat` on
      `scheduler.py` and `hub/hub/db/models.py` showed no change after. 1 passed before and after.
~~- [ ] 2.12~~ **MOVED 2026-09-15** to `a-refusal-names-a-remedy-that-works/tasks.md` task 2.3.
      Built there, not here.
~~- [ ] 2.13~~ **MOVED 2026-09-15** to the same directory's task 4.10 (it tests D5's guard
      sentence, which moved with group 4). Built there, not here.
- [x] 2.14 (REV) The divergence restaff returns `None` for a task whose status is no longer
      `completed` or `under_review`, at the same screen as `blocked` (`run_divergence.py:746`).

      > **R8, 2026-09-21 — placement and test corrected; build from this block.**
      > - **Not at the `blocked` screen.** That screen (`run_divergence.py:753-754`) runs for
      >   **every** run. A status screen there returns `None` for every ordinary work run whose
      >   task is `assigned`/`in_progress` — it would silently disable divergence handling for all
      >   non-review work. The screen belongs **inside the review branch**: in `evaluate_run_end`,
      >   under `if await review_task_for_run(session, run) is not None:` (`:769`), before
      >   `_answer_failed_review` is called (`:771-773`), return `None` when
      >   `task.status not in ("completed", "under_review")`. `review_task_for_run`
      >   (`run_task_binding.py:226-248`) reads the queue entries and never looks at status, which
      >   is why the operator's mid-run move reaches `_answer_failed_review` today.
      > - **"No `review_unstaffed` is recorded" cannot fail.** The divergence path never emits
      >   `review_unstaffed` — only a firing does (`scheduler.py:3053`, `_emit_review_unstaffed`);
      >   divergence emits `run_diverged` (`run_divergence.py:835-842`). Replace it with: stage a
      >   **free, non-excluded** agent; after the run ends, assert `evaluate_run_end` returned
      >   `None`, no `RunDivergence` row and no `run_diverged` event exist for the run, the task's
      >   assignee is unchanged, and nothing is queued for the free agent. *Mutation:* drop the
      >   screen — the review is restaffed onto the free agent and the test fails. This fails
      >   **before** 2.3 lands, which is what lets 2.14 be built first.
      > - **Second case, after 2.3:** nobody free. *Mutation:* drop the screen — rung 3 calls
      >   `own_review_remedy` on a `revision_needed` task and its `assert` raises. Assert no
      >   exception escapes `evaluate_run_end`.
      > - **What the raise would do, and why the order matters (R8-7).** `evaluate_run_end` is
      >   awaited bare after the run row commits (`api/v1/agent_trigger.py:2420, 3006`) and in
      >   `run_reconciliation.py:126`'s loop at Hub start. An `AssertionError` there skips the F43
      >   handover at the run boundary, and at start aborts the remaining divergence evaluations
      >   and the `schedule_or_defer` after them. Unattended, that is a silent failure.
      `own_review_remedy` (built by the sibling directory's task 1.1 — depends on it landing
      first) asserts one of the two statuses. Test: the operator moves a task to `revision_needed`
      while its review run is live, and the run then ends without a verdict. No `review_unstaffed`
      is recorded and no reviewer is staffed.
      *Mutation:* drop the new screen. The test must fail.
      **R6: this task runs BEFORE 2.3** — see the ordering note at the top of this group. Its
      citation has drifted: the `blocked` screen is at `run_divergence.py:753-754`, not `:746`.

      **Built 2026-09-23, night iteration 7.** Screen added in `evaluate_run_end`, inside the
      review branch, before `_answer_failed_review` — exactly the R8 placement. Test added:
      `hub/tests/test_review_divergence.py::test_a_review_run_ending_after_its_task_left_review_restaffs_nobody`
      (the first case only — a free agent on the roster is genuinely restaffed onto the moved task
      without the screen). Mutation: replaced the screen's condition with `False and …`; test failed
      (`assert 'div-...' is None` — a divergence was recorded and the free agent would have been
      restaffed). Reverted; `git diff --stat` back to the one-line addition only.
      **The second case (nobody free, `AssertionError` from `own_review_remedy`) is deferred to
      when 2.3 lands** — today's `resolve_reviewer` rung 3 does not yet call `own_review_remedy`
      (that call arrives with 2.3), so the assert this screen protects against cannot fire yet and
      a test for it would have no mutation that bites. Added as a follow-up note rather than a
      test asserting nothing.
      Full relevant suite: `pytest hub/tests/test_review_divergence.py
      hub/tests/test_run_divergence.py hub/tests/test_a_task_nothing_will_move_holds_nobody.py
      hub/tests/test_reviewer_ladder.py -q` → 77 passed. CI's exact ruff/black/mypy clean.
- [ ] 2.15 (R6) Test: an agent whose queue is held, running no turn and holding nothing, is named
      by the **held** clause and **not** by the **running** clause. **(R9: this line said "clause
      4 … not clause 5", R6's numbering; under the delta's R8 numbering clause 4 is *booked*, so
      read literally it asked for the wrong clause. The delta numbers held 3, booked 4, running 5.)**
      **R8: a second case — a held agent that is also booked** (one task in a second live loop) is
      named by the hold, and its task id does **not** appear. *Mutation:* R6's order (booked
      before held). The test must fail. This is the shipped behaviour `roster_held`
      (`scheduler.py:1394-1396`) has today, which R6's order reverted (R8-1). If staged through a
      firing rather than `resolve_reviewer`, the held agent must not be the job's agent, or
      `_loop_flow_busy_reason` refuses the firing first. Assert the reason contains "waiting for its provider's
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
      **R8:** also assert that with **no** booked agent (the only other agent held), the reason does
      not contain `"Rejecting"`. *Mutation:* append REJECT unconditionally. The test must fail
      (R8-4).
- [ ] 2.18 (R9) Test: the empty roster, through `resolve_reviewer` on a project whose every agent
      is archived, for a `completed` task. Assert the whole reason with `==` against
      `"could not staff this step: no reviewer is free. The project has no agent on its roster.
      Land it, on the task, to review it yourself."` (one line, one space after each period). The
      delta's scenario *"An empty roster is stated"* had no task behind it at any round.
      *Mutation:* lowercase the `T`. The test must fail; a substring check on `"no agent on its
      roster"` would not.

## 3. ~~Once per task (design D4)~~ MOVED 2026-09-15

Groups 3 and 4 (all of `own_review_remedy`'s once-per-task and refusal-wording tasks) moved
wholesale to `a-refusal-names-a-remedy-that-works/tasks.md` groups 3 and 4, renumbered 3.1-3.3 and
4.1-4.10. Built there, not here. See that directory for the full text.

## 5. The board line (design D6), under the day's bundle rule

- [ ] 5.1 `title={loop.stall_reason}` on the stall `<p>` in `LoopsIndexTab.tsx`, and a unit test
      asserting the attribute carries the full reason.

      > **R8 — this group edits `hub/ui/` and ships a bundle. The bundle reaches the operator's live
      > `:8000` app on their next reload** (`.claude/rules/hub-ui.md`). Checked 2026-09-21: the
      > committed bundle's stamp (`hub/hub/static/ui/ui-build-stamp.json`, `src_commit 46dd58e`,
      > built 2026-09-13) and the last `hub/ui/src` commit (`1731522`, 2026-09-13) agree, so a
      > rebuild tonight carries only this attribute — re-check that before 5.2; if `hub/ui/src`
      > has moved since, the bundle carries those changes too.
      > - The stall `<p>` is `LoopsIndexTab.tsx:237-244` (unchanged). Its text strips a leading
      >   `"loop queue is "`; the `title` carries `loop.stall_reason` **unstripped**.
      > - The unit test goes in the existing `hub/ui/src/__tests__/loopsIndexTab.test.tsx` (the
      >   stall line's test is at `:144`), with a reason longer than 200 characters that starts with
      >   `"loop queue is "`, asserting `title` equals it exactly. *Mutation:* remove the attribute,
      >   or set it to the stripped text. Each must fail.
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

        > **R8 — this bullet is stale and self-defeating; drive the replacement below instead.**
        > (1) *"Archive the holding loop … the remedy the sentence now prints"*: R6 removed the
        > archive remedy (R6-3) and the delta now forbids claiming it; the sentence prints
        > **rejecting**. (2) An unreachable-only holder that *is* in the pool is staffed by rung 2,
        > so no rung-3 reason exists in which to see it *not named* — the same contradiction R6-5
        > found in 2.6. **Drive instead:** (a) stage a holder whose only task is unreachable; the
        > next firing staffs **it** as the reviewer — that is the observable proof it holds nobody
        > (its not-being-named is 2.6's R8 assertion); (b) with the LoopEngine shape stalled, reject
        > one booked task through the operator's own control (`PATCH` the task to `rejected`, or
        > the drawer's status menu) and confirm the reason on the next firing no longer names it —
        > and, where that was the agent's only booked task, that the next firing staffs that agent.
        > That is the remedy the sentence prints, watched working.
        >
        > **Also R8:** the two bullets above about the drawer's status menu refusal and *"one real
        > Haiku agent turn asked to move that task to `under_review`"* drive D5's refusals, which
        > moved to `a-refusal-names-a-remedy-that-works` (archived 2026-09-16). They are not this
        > change's to drive; skip them. *"Two firings with two unstaffed tasks → one event each"*
        > is D4 (F365), also the sibling's — harmless to observe, not a gate here.

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
