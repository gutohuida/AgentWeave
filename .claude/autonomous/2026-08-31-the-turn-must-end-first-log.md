# The turn must end first — 2026-08-31, until 17:00

Newest entry at the **bottom**.

---

## Iteration 0 — 2026-08-31T11:35+01:00 — the prep

**What this run is.** One change, `approval-waits-for-the-turn-to-end`, taken from a finished round 1
through rounds 2 and 3, implementation, and two live drives. The operator's instruction, verbatim:
*"write them up and then prep a autonomous run to fix these. After fixing it another end to end run
to test the flow. Run untill 17. The aim again is to fix everything and make the flow work."*

**What happened before the run was armed, so it does not have to be rediscovered.**

The previous run (2026-08-31, until 08:00) closed cleanly at `stop_at` with all 19 queue items done
plus an unqueued F162 drive. It was reviewed and **merged to master at `f4f8ac6`**, CI green on all
nine jobs verified job-by-job. Four changes landed: `a-flow-briefing-names-its-contract`,
`a-review-a-flow-cannot-staff-is-named`, `approval-refuses-unaccepted-evidence`,
`a-loop-declares-whether-it-needs-evidence`. `F153` is the record it produced — the first time a
flow's work has been observed reaching a main branch in this project's history of drives.

It stopped rather than guessing on **D20** (which of three repairs closes F162) and **D21** (should a
loop staff reviews at all). Both were put to the operator this morning. **Both are answered**, and
the answers are in `decisions_for_user` as `D-ANSWERED-20` and `D-ANSWERED-21` so no round
re-litigates them:

- **D20 → refuse approval while the turn is live.** The deciding argument is an archived change
  named `2026-08-13-approved-means-it-is-in-the-product`: *"Approval merges… that is what the word
  will mean."* Deferring the merge to turn-end would retreat from that sentence. And the objection
  that made this look expensive — *"approval would depend on run state, which nothing else does"* —
  **is false**: `project_lifecycle.py:207` refuses project deletion, and `_guard_relocation` refuses
  relocation, on exactly that condition.
- **D21 → a loop should not staff reviews at all**, so the repair is at the selection site rather
  than inside `commit_for_task_review`.

**An openspec explore ran between those answers and this arming**, and round 1 was written from it
and committed at `fc0c661`. Three things the explore found that the previous run's exploration had
not:

1. **`pid_alive`'s own docstring warns the exact caller this change would add** — *"If a future
   caller checks liveness of a process this same Hub killed, it needs `waitpid(WNOHANG)` or a
   `/proc/<pid>/stat` state check — do not assume this function alone is enough there."*
   (`pty_runner.py:150-156`.) So the predicate asks the in-process registry first and treats absence
   as not-live, which fails in the safe direction.
2. **The evidence route has three defences against this same window; the branch-tip route inherited
   none.** `restamp_run_footprints` calls the window *structural* in so many words
   (`requirement_evidence.py:846`), a human acceptance step stands between `completed` and
   `approved`, and coverage can say `verified, not integrated`. Coverage **structurally cannot**
   describe a documentless loop's task: `requirement_coverage` selects from `SpecRequirement`
   (`:219`) and such a task serves none. That is why F162 is silent rather than merely wrong.
3. **`agent-flows` needs no delta.** Its review requirements are already written about a flow
   (`:134`, scenarios all beginning *"WHEN a flow fires"*). Nothing in the corpus says a loop staffs
   a review. The code applies the flow's arm to loops anyway — so the breach is code exceeding its
   spec, not a requirement needing amendment.

**Why F162, F161 and F163 are one change and not three.** The drive fired all three of F163's hops in
**640 milliseconds**, well inside F162's measured **10.5-second** window. Shortening the route
without closing the window makes the strand more likely, not less. F161's stall then disappears as a
consequence of D21 rather than as a patch.

**The queue, and why it is ordered this way.** A-R2 → A-R3 → A-IMPL-1 → **A-DRIVE-1** → A-IMPL-2 →
A-IMPL-3 → **A-DRIVE-2** → A-CLOSE → F155-R1. A drive sits after the first implementation group
deliberately: if time runs out, a run that closed F162 and *proved* it closed is worth more than one
that implemented all six groups and proved nothing. Stopping anywhere leaves complete work.

**The 15:30 rule** parks spec and implementation work at a clean boundary and hands the rest to
A-DRIVE-2 and A-CLOSE, because the operator asked for the fix **and** a drive. At 16:30 everything
stops and the branch is offered.

**What was checked at arming rather than assumed.**

| Checked | Result |
|---|---|
| CI on `f4f8ac6` (master) | green, **all nine jobs**, listed individually |
| `openspec validate approval-waits-for-the-turn-to-end --strict` | valid |
| `openspec status` for the change | 4/4 artifacts complete |
| Trial Hubs 8010 and 8011 | both `{"status":"ok","runtime":"native"}` at 11:25 |
| Scheduled Task `AgentWeaveAutonomousSession` | absent — the 08:00 run unregistered itself |
| Working tree | clean, `master` = `fc0c661`, pushed |

**What was NOT run:** the test suite, locally, by anyone this session. The green claim rests on CI at
`f4f8ac6` — which included `hub-test` — plus the observation that the only commit since is openspec
documents. `A-CLOSE` is where the suite actually runs.

**F154 stays filed** (`D6`). It is severity A and its repair shape is already written down, but it is
a different subject and pulling it in is how a reviewable change stops being reviewable. F155 is
queued last and **proposal only**.

**The branch is `autonomous/2026-08-31-the-turn-must-end-first`, cut from `master`.** This run does
not merge.

---

## Iteration 1 — 2026-08-31T11:48+01:00 — A-R2, round 2

**Branch reconciled first.** `autonomous/2026-08-31-the-turn-must-end-first` exists at `03bdd24`,
cut from master's tip carrying this run's STATE.json — which is what iteration 0's `next_action`
asked for. Tree clean at start. Nothing to reconcile.

### The five load-bearing claims, checked at the source

| Claim | Verdict |
|---|---|
| 1. `evaluate` (`:384`) is the single pre-transition question; repo-aware checks sit above the `if not enforced` early return | **CONFIRMED**, with a correction below |
| 2. `reconcile_interrupted_runs` runs only in `lifespan()` startup, so `Run.status` alone is insufficient | **CONFIRMED** — `main.py:350` is the only non-test call site in the tree |
| 3. `pid_alive`'s docstring warns precisely the caller this change adds | **CONFIRMED** verbatim at `pty_runner.py:152-156` |
| 4. `_active_ptys` (`:148`) / `_active_app_server_runs` (`:153`) hold a handle per live run in this process | **CONFIRMED**, and better than round 1 knew — see the ordering finding |
| 5. Nothing in the corpus says a LOOP staffs a review | **NARROWED** — one requirement comes close, and the proposal now says why it survives |

### The finding: this change, as round 1 wrote it, breaks every flow review

The predicate round 1 specifies is *"a `Run` bound to this task, `status == running`, process
alive"*. Round 2 asked who else that matches, and the answer is **the reviewer**.

Since migration `0092_review_divergence_regime`, a review run **is** bound to the task it inspects:
`run_task_binding.task_named_by` returns `entry.task_id or entry.review_task_id`
(`run_task_binding.py:170-189`) and `_bind` writes `run.task_id = task.id` (`:427`). The migration's
own note gives the reason — before it, *"no run records having caused"* those `under_review ->
approved` transitions. A reviewer approves from **inside its own turn**, so that turn is a live run
bound to the task being approved, and the gate would refuse it. Every flow review in the product
dies, including the only path ever observed carrying a flow's work to a main branch (F153, driven
this morning).

It is also **F155's failure mode exactly**, which design D4 already names as the standing warning:
the refusal's only remedy is *wait for the turn to end*, handed to the turn that would have to end.
No action clears it.

**Repair, written up as design D10:** `evaluate` takes the acting run and excludes it — *a turn is
never blocked by itself*. `task_transition_service` already holds `actor.run_id` at the call site
(`:571`), so this is one keyword-only argument with a `None` default; operator routes pass nothing
and exclude nothing. Rejected for scope: excluding review-bound runs *structurally*, which cannot be
done from the `Run` row at all — `review_task_id` lives on `InboundQueueEntry` (`models.py:618`)
and `Run` carries only the collapsed `task_id` (`:1102`). The residual it would have removed is
named rather than left implicit.

Task 3.8 now exists to catch this in the suite, and `t_drive1_flow_lands.py` (A-DRIVE-2) is what
proves it live. This is precisely the regression that queue item's *"the regression this whole
change most plausibly causes"* was pointing at, found before a line was written.

### Open question 1 answered — and round 1's argument for it was wrong

**Does the evidence route share the window? Yes.** Round 1 wrote that it *survives* the window
"because it has three defences". Re-derived, none of the three prevents the merge:

- `_targets` (`task_integration.py:219-266`) filters on `review_state`, `kind == "git"` and a
  non-empty `commit_sha`. It does **not** filter on `reachable_from_main`.
- A footprint recorded mid-turn names the pre-turn commit by construction — `restamp_run_footprints`
  says so itself (`requirement_evidence.py:856`).
- That restamp runs at turn **end**, in `_execute_run`'s finalize block
  (`agent_trigger.py:2041-2050`). It re-points rows and re-merges nothing, so an approval that
  landed earlier has already merged the stale sha.
- Nothing sequences acceptance after the turn: `decide_evidence` is callable at any moment. The
  "human acceptance step" is a step in the order of *states*, not of *time* — and time is what this
  window is made of.

The docstring states the consequence in the defect's own words: *"the pre-turn commit is usually
already on the main line... evidence for code that does not exist reads as already shipped."* That is
`ALREADY_INTEGRATED` by another name. The evidence route recovers its **record**; it never prevented
the **merge**.

This is the CLAUDE.md lesson working as designed: *an argument can be wrong while everything it
argues about is right.* Round 1's conclusion (refuse unconditionally) was correct; its reason for
believing one route was safe was not, and only re-deriving the argument found it.

### Open question 2 answered

**A new module, `hub/hub/run_liveness.py`, owning the two registries.** The import graph was checked
rather than assumed: `pty_runner` imports only stdlib and `subprocess_windows` (`:19-30`), and
`requirement_gate` already imports `db.models` — so `run_liveness` -> (`pty_runner`, `db.models`)
closes no cycle, and the function-local-import fallback of D1 is not needed. The registries are
referenced nowhere outside `agent_trigger` and four test files, whose references move with them.

`agent_lifecycle` rejected with a reason: `archivable` reads `Run.status == "running"` **alone**
(`:34-42`), which is the crash-wedge D3 exists to avoid. Putting a process-tested predicate beside a
column-read one, both about liveness, is how two answers to one question drift. (Filed, unqueued:
`archivable` carries that same exposure — an agent whose Hub crashed mid-run cannot be archived
until restart.)

**Not a fourth answer to "is this agent working".** `agent_status.heartbeat_is_stale` (`:15-25`)
tests an `AgentHeartbeat` row against a watchdog window and takes no run at all — a different
question. The answers genuinely about a run are two, and the predicate is the one place combining
them.

### Three smaller corrections

1. **The check must not nest under `if situation is not None`.** Round 1 said "the same place as the
   two repository-aware checks", which reads as *inside their block*. `_merge_situation` returns
   `None` for any project with no main branch, unresolvable workspace, non-repository directory or
   missing branch (`:255-283`) — so nested, the refusal would be silently absent from exactly the
   projects whose state is least understood. Liveness is not a question about the repository.
2. **The category needs adding in four places, not one.** The field, `refuses` (`:112`), `detail()`
   (`:120`) and `to_dict()` (`:193`). Round 1's tasks named only `detail()`. A field missing from
   `refuses` is a category that never refuses.
3. **Claim 5 narrowed.** `agent-loops:970` (*"An agent attributed to a task SHALL be attributed in a
   stated capacity"*) reasons from *"for a completed one awaiting review it is whichever agent the
   next firing would hand the review to"* and enumerates *"an agent a firing would select next"*. It
   survives — it constrains presentation **where a capacity exists**, and every scenario is
   conditioned on that existence — but the proposal's flat *"nothing in the corpus says a loop
   staffs a review"* was too strong, and a reader would have hit this and doubted the change.

### Checked and confirmed, needing no change

- The gate is evaluated **before** `task.status = to_status` and before the `TaskTransition` row
  (`task_transition_service.py:552-572`), so the delta's *"status unchanged, no integration
  recorded"* is a property of where the gate already sits.
- **Registry outlives the snapshot**, which round 1 asserted but did not evidence. `_active_ptys`
  registers at `agent_trigger.py:1855`, `snapshot_worktree` runs at `:1993`, the pop is at `:2262`;
  `run.status = final_status` is written at `:2035` — *after* the snapshot. Both liveness signals
  therefore cover the whole window with no gap at its far edge. This is what makes the predicate
  correct rather than merely plausible.
- `run_task_binding` performs no automatic `-> approved`, so its four `TransitionRefusedError`
  catches are not silently swallowing the new refusal.
- `stop_agent_run` exists (`agent_trigger.py:1515`), so the refusal is never a dead end for a long
  turn.

### Recorded for round 3 rather than answered

Task 5.4's populations. The discriminator already exists (`loop.spec_document_id`,
`scheduler.py:2043`). Reaching a *staffed* review today needs `completion_attribution.recorded`
(`:1444`), `commit_for_task_review(...).resolved` (`:1472`) and a resolvable non-author reviewer — so
the population that could lose anything is narrow: **a documentless loop, in a project with a second
eligible agent, whose agent recorded evidence naming a commit.** Written into design D5 as an
observation, explicitly *not* a clearance. Round 3 establishes whether it exists in the corpus's
terms and whether any test covers it.

### Also filed, not chased

`restamp_run_footprints`' docstring claims *"`task_integration.integration_targets` merges on exactly
this field"* of `reachable_from_main`. `_targets` does not read that field at all. The docstring is
stale about the code beneath it.

### Artifacts

`proposal.md`, `design.md` (new D10; D1, D3, D5, D9, risks and open questions rewritten), `tasks.md`
(2.2, 2.5, 3.2, 3.3, 3.8 new or rewritten; group 4 turned from a determination into a test) and the
`task-lifecycle-governance` delta (a paragraph on the acting run, a paragraph on both routes, two new
scenarios). `openspec validate --strict`: **valid**.

No code was touched. A-R3 is next and must not re-read this — it is to re-derive independently, with
task 5.4's population question as its named starting point.

---

## Iteration 2 — 2026-08-31T12:05+01:00 — A-R3, round 3

**Branch reconciled first.** `autonomous/2026-08-31-the-turn-must-end-first` at `f29277e`, tree
clean, `git log` matching STATE.json's `current`. Nothing to reconcile.

Round 3 was run against the **code and the shipped corpus**, not against round 2's log entry. Where
this entry names something round 2 also found, that is convergence, not a re-read.

### (a) Does a shipped requirement forbid a new approval precondition? — **No, and here is the proof**

`task-lifecycle-governance:720` *"An integration that cannot proceed does not block approval"* is the
place the queue item predicted a breach, and read alone it forbids this change: its scenarios say
flatly that approval succeeds with no configured main branch, and it closes with *"A project that is
not a repository SHALL be no less approvable than before this capability existed."*

It does not forbid it, and the evidence is inside the function this change edits. `evaluate`'s
enforced-requirements walk (`requirement_gate.py:399-410`) is **unconditional on `situation`** — so
`blocking` and `diagnostics` already refuse approval in projects `_merge_situation` cannot resolve,
and have since the gate shipped. The corpus therefore already tolerates non-integration refusals
there, which settles `:720`'s scope: it governs *integration* as a blocker of approval, and its
scenarios speak about their own cause. No delta against it.

**But there is a finding, and it is a principle stated in the code rather than in the corpus.**
`_MergeSituation`'s docstring (`requirement_gate.py:230-238`) says of its four preconditions: *"Each
is **a reason to not know, never a reason to refuse**, and they have to be the same four rather than
two lists that can drift, because a refusal that fired where the merge would have been skipped anyway
would block every task in such a project behind a remedy that changes nothing."* Round 2's D1
deliberately places the liveness check outside that block, so it fires in exactly those projects.
Round 2 was right to; it never noticed it was departing from a written rule. Design D1 now argues the
departure in three terms — liveness is not one of the four (it is answerable in a directory that is
not a repository at all), its remedy is not "a remedy that changes nothing" because it clears itself,
and `approved` is a judgement about work even where nothing merges. A scenario now pins it, and task
3.9 tests it.

### (b) Does removing the loop's review arm regress anything? — **four findings, one of them inverts the argument**

**1. The corpus does not merely permit this removal. It requires it.** Rounds 1 and 2 both argued from
silence: *"nothing in the corpus says a loop staffs a review."* `agent-flows:13` says the opposite of
silence — *"A loop that declares no document SHALL be unaffected by [this capability's requirements]
and SHALL behave exactly as it does today"* — and that capability's Purpose enumerates what it owns:
*"firing-time agent resolution, **reviewer resolution, review dispatch and its handover briefings**,
flow width, and the checkpoint lineage"* (`openspec/specs/agent-flows/spec.md:5-9`). Its scenario is
flatter still: *"A loop without a document is unchanged — every firing fires the job's own agent, as
before."* `decide_firing` resolves a **second** agent to review a documentless loop's task. So the arm
is a **breach of a shipped requirement**, and D5 restores the corpus. The proposal's weakest load-
bearing sentence is replaced by its strongest.

This is the round-3 shape CLAUDE.md describes: rounds 1 and 2 reached the right conclusion by an
argument that would not have survived a reader who knew `agent-flows:13`.

**2. Round 2's population estimate was right in its clauses and wrong in its scale.** Round 2 called
it *"narrow and specific: a documentless loop, in a project with a second eligible agent, whose agent
recorded evidence naming a commit"* and left it as an observation. That description is **the suite's
default fixture.** Measured, not assumed — `grep -c spec_document_id` is `0` in all five:

| File | Tests | Asserts |
|---|---|---|
| `test_actor_aware_claimability.py` | 14 | `:428` *"the ladder staffs a review, not the job's own agent"*, `is_review is True` |
| `test_a_flow_names_what_it_cannot_staff.py` | 24 | F142's three arms and the `unstaffed` sentences |
| `test_review_dispatch_staffs_the_task.py` | 12 | `:1481` staffing |
| `test_review_leaves_the_pool.py` | 9 | F45, review leaves the recruitment pool |
| `test_a_review_needs_something_to_review.py` | 5 | `commit_for_task_review` gating the arm |

Every loop in them is `Loop(id=..., project_id=..., job_id=..., purpose=...)` with no
`spec_document_id`. They are **flow requirements tested through loop fixtures**, which is precisely
why nobody noticed the arm running outside its capability. Task 5.5 moves the flow-subject fixtures
onto documents; the exclusion is not weakened to keep a fixture green.

**3. The arm serves two populations and only one may be excluded.** `scheduler.py:1440-1500` is
reached by a `completed` candidate (a fresh review) **and** by an `under_review` row whose assignee is
its own author, carried down by `wedged_review` from `:1299-1356` — the F70 recovery. An exclusion at
the top of the arm removes both, and the second failure is **silent**: that path deliberately skips
the `in_flight` record (`if not wedged_review: in_flight.append(...)`, `:1349`), so a loop's wedged row
would leave the walk having recorded nothing at all. F23's and F142's silence through a third door, in
a change whose purpose is to end a stall nobody can see. The exclusion goes on the fresh-review branch
only.

**4. `unstaffed` staying empty is right and not sufficient.** With the arm gone, a loop whose only open
task is `completed` falls to `_stall_reason_from_walk` and gets *"loop queue is stalled: no claimable
task among 1 open (1 completed)"* (`scheduler.py:1668`) — word for word the sentence the review arm's
own comment records as measured live on 2026-08-30 and wrong. This change would re-earn it for loops
on the day it removes it for flows. Here the cause is fully known and the remedy is D6, so the firing
must say so. New requirement text, a scenario, and task 5.4.

Also cleared, and now stated so it is not removed by accident (task 5.6): the operator's **by-hand**
review of a loop's completed task survives — `task-lifecycle-governance:1481` requires every dispatch
path to staff, and names the operator's first.

### (c) Does the composed landing action breach `:117` or `:168`? — **No, and one thing was missing**

`:117` is satisfied at the map: `TRANSITIONS["completed"]["under_review"]` and
`TRANSITIONS["under_review"]["approved"]` are both `_BOTH` (`task_transitions.py:134-141`), so the
composition travels declared operator edges and widens nothing. `:168` is satisfied because each step
goes through `apply_transition`, which writes its own row. `:264` — which *"binds every actor,
including the operator"* — is satisfied by ordering, since the hold is released first and
`_guard_reviewer_is_not_the_author` returns immediately for a task with no assignee (`:357`).

**What `:168` demanded and the delta did not say:** the recorded cause must *"distinguish a transition
an actor asked for from one the system made on that actor's behalf"*. The landing action is one intent
producing three records, so it has to choose. They are **actor-caused, all three** — nothing here is
observed by the runtime; the operator asked for every step, in one word instead of three. Delta text
and task 6.5.

**And a real gap in D7.** The delta already promises *"refused **for any reason** leaves nothing
half-applied"*; D7 delivered only a gate pre-check. The gate is one of several ways this composition
can refuse — `apply_transition`'s legality check, `_guard_reviewer_is_not_the_author` on
`-> under_review`, `_guard_run_holds_the_task`, `_guard_author_is_not_reviewer`. A landing that
pre-checked the gate and met one of those on step two would have released the author's hold already.
What guarantees the promise is the **transaction**: `apply_transition` and `transition_task` do not
commit — the routes in `api/v1/tasks.py` do (`:1173`, `:1397`, `:1564`) — so all three steps go in one
handler under one commit. The pre-check is kept and its purpose restated: it makes the *message* the
one approval would have given. Atomicity is the transaction's job. Delta paragraph, new scenario, task
6.3.

### D10, re-derived independently — right, necessary, and carrying a second residual

D10 is confirmed at the source: `_bind` writes `run.task_id = task.id` (`run_task_binding.py:427`) and
`task_named_by` resolves `entry.task_id or entry.review_task_id` (`:170-189`), so a reviewer's own turn
is bound to the task it approves and a naive predicate refuses every flow review. Also checked rather
than assumed: `requirement_gate.evaluate` has **exactly one caller**
(`task_transition_service.py:555`), so widening its signature keeps no second surface in step.

**The residual round 2 did not name.** The exclusion is unconditional on what the acting run is *for*,
and two facts make that reach further than intended:

- `_bind` sets `run.task_id` for a **working** turn exactly as for a review turn, so the `Run` row
  cannot tell them apart — the same fact that made the structural alternative expensive.
- `_guard_author_is_not_reviewer` refuses only where a completing agent is *recorded*
  (`task_transition_service.py:304-305`). An **unattributable** completion is permitted to act on, by
  the corpus's own *"refuse to offer, permit to act"* asymmetry — and an operator marking a card done
  is exactly that case, measured live in F142.

So: an agent mid-turn on task T, bound to T, whose `completed` the **operator** recorded and whose
assignee the operator cleared, may approve its own in-flight work from inside its own turn. The author
guard permits, D10 excludes its run, the gate says nothing, `task_branch_tip` resolves the pre-turn
commit. **That is F162 reached through the carve-out built to protect reviewers.**

Narrow — it needs the operator to complete *and* unassign a task an agent is still working — and not a
reason to drop D10, whose absence kills every flow review. Named in D10 with its price (the
`InboundQueueEntry.review_task_id` join round 2 rejected for scope; round 3 confirms the trade), and
task 2.6 pins the shape in a test so a later change knows what it would be closing.

### Artifacts

`proposal.md` (the `agent-flows:13` argument replaces the argument from silence; two bullets on what
D5 does *not* remove and on the stall sentence; an Impact paragraph costing the five test files),
`design.md` (D1, D5, D6, D7, D10 all extended; six new risks), `tasks.md` (2.6, 3.9, 5.4 rewritten,
5.5, 5.6, 6.3 rewritten, 6.5), and both deltas (a `:720`-interaction scenario; three new `agent-loops`
scenarios on the stall sentence, the by-hand review and the wedged recovery; a landing-action
rollback scenario and two new paragraphs). `openspec validate --strict`: **valid**.

No code was touched. The three rounds are complete and **A-IMPL-1 is next** — the reproduction first,
and it must be seen to fail for the stated reason before anything is fixed.

---

## Iteration 3 — 2026-08-31T12:28:51+01:00 — A-IMPL-1: groups 1, 2 and 3

Branch and `git log` matched STATE.json's `current` exactly (`3ad2fea`, tree clean, rounds 2 and 3
committed at `28d97c3` and `9b26344`). Nothing to reconcile.

**F162 is closed in code.** Three commits, each its own group, each verified before the next began.

### Group 1 — `9f9f18d`, the reproduction, written to fail first

`hub/tests/test_approval_waits_for_the_turn.py`. It reproduces the **window** and not merely a
state (design D8): the task's branch exists at the commit it was cut from, a `Run` row is recorded
`running` and bound to the task, **and** a session handle sits in this process's registry. Both
halves of "live" are read back before the transition, so a fixture that stopped producing either
fails there rather than passing for the wrong reason.

Task 1.3 was done by reading output, not by assuming. The flipped form was written and run first,
and it failed for exactly the stated reason:

```
expected a refusal, got 200: ... "status":"approved",
"latest_integration":{"outcome":"skipped",
"reason":"8471664b7ccf is already in main; there was nothing to merge", ...}
```

The committed form then asserted that wrong behaviour — a `200`, `approved`, `ALREADY_INTEGRATED`
against the **base** commit, the turn's real commit never reaching `main`, and
`is_retryable(...) is False` — following this repository's own precedent in
`test_loop_lands_its_work.py`, whose docstring names the commit its measurement lives at.

### Group 2 — `01100ad`, `hub/hub/run_liveness.py`

The module owns `active_ptys` and `active_app_server_runs`, taken out of `api/v1/agent_trigger`;
`agent_trigger` is still the only writer and the five test files that reach the registries moved
their references with them (design D3, open question 2). Import graph confirmed by running it, not
by reading it: `requirement_gate` → `run_liveness` → (`db.models`, `pty_runner`) closes no cycle,
so no function-local import was needed and D1's fallback went unused.

The predicate is registry-first, scoped to `Run.task_id == task.id`, excludes the acting run, and
does not call `pid_alive` — with a comment citing that function's own docstring warning about
precisely this caller.

**A FINDING, and a correction to design D3.** D3 named `PtySession.isalive()` as the test.
Implementing it showed **membership is the stricter and the correct signal**, and the difference is
exactly the window this predicate exists to close. `_execute_run` pops its registry entry in a
`finally` (`agent_trigger.py:2257`) that runs *after* the finalize block has taken the turn's
snapshot commit and restamped the evidence footprints (`:2036-2050`). `isalive()` goes false the
moment the process exits — which is **inside** the window, before the commit that holds the work
exists. An `isalive()`-based predicate would have permitted approval during the seconds the product
spends producing the very commit approval is waiting for, and F162 would have survived its own fix
in narrowed form. Membership covers the whole turn including that finalize block. Recorded in the
module docstring so the next reader does not re-derive it, and it is why `end_the_turn()` in the
tests pops the registry entry and deliberately leaves `Run.status` alone.

Seven tests: the three liveness arms, the task scoping, D10's carve-out **with a second live run
proving it is not too wide**, and task 2.6's residual — `Run` carries nothing distinguishing a
working turn from a review turn, so an agent on an operator-completed task can approve from inside
its own turn. Pinned so a later change that makes the `InboundQueueEntry.review_task_id` join cheap
knows exactly what it would be closing.

### Group 3 — `89429d5`, the gate refuses

The fifth `GateRefusal` category, `unfinished`, added in **all four** places. The check sits above
the `if not enforced` early return and beside the `if situation is not None` block, and
`_check_live_turn`'s docstring argues that departure from `_MergeSituation`'s *"a reason to not
know, never a reason to refuse"* in the three terms round 3 set out, plus why
`task-lifecycle-governance:720` is not breached. `evaluate` widens by a keyword-only
`acting_run_id`; `task_transition_service` passes `actor.run_id`.

The refusal sentence, measured live rather than quoted from the design:

> builder is still running the turn that produces this task's work, so what approving would merge
> is not knowable yet — the task's branch still points at the commit the turn started from. Nothing
> is wrong with the work. Approve once the turn has ended: this clears itself, with nothing for
> anyone to do. Stopping the agent's run ends the turn too.

The reproduction flipped, and the second half is what makes it a fix rather than a block: once the
turn ends the same task approves and merges the commit that actually holds the work. Five more
scenarios cover the crash case, no-run, `sketch` vs `gate` (with `blocking` empty in the sketch case,
proving it is the liveness check refusing), task 3.9's project with no configured main branch, and
task 3.8's **flow reviewer approving from inside its own review turn, driven through the agent
HTTP surface** — the change's largest regression risk.

Task 3.6 was verified at the source: `readableApiError` reads `detail.message`, which `to_dict`
composes, so the sentence renders as prose rather than a dict repr. A sixth case in
`taskIntegration.test.ts` pins the who, the still-running and the clears-itself. `hub/ui/src` is
excluded from the bundle fingerprint under `__tests__` (`main.ui_source_fingerprint`'s `exclude`),
so no rebuild was owed.

### Verification

| Run | Result |
|---|---|
| `test_approval_waits_for_the_turn.py` | 12 passed |
| `test_requirement_gate` + `test_task_integration` + `test_loop_lands_its_work` + `test_task_integration_retry` | 83 passed |
| `test_task_transitions` + `test_a_task_waits_while_its_run_waits` + `test_review_dispatch_staffs_the_task` + `test_actor_aware_claimability` | 150 passed |
| `test_agent_trigger` + `test_conversation_contract` | 52 passed |
| `test_agent_trigger_overrides` + `test_lifespan_shutdown` | 7 passed, 1 xpassed |
| `test_approval_refuses_unaccepted_evidence` + `test_task_rejected_evidence_signal` | 34 passed |
| `taskIntegration.test.ts` (vitest) | 6 passed |
| `ruff check src/ hub/ tests/`, `black --check` | clean |
| `openspec validate --strict` | valid |

**No drive yet.** Groups 1–3 are unit-level; nothing here has been seen against a running Hub. The
suite passing is not proof of behaviour and the operator asked for a drive. That is group 7, and it
must not be squeezed out.

Next: group 4 (one test — the evidence route through the same refusal, D9 having already answered
that it shares the window) then group 5 (the loop stops entering the review arm — the largest
remaining blast radius, five test files' fixtures).

---

## Iteration 4 — 2026-08-31T13:00 — A-IMPL-2: groups 4 and 5

Branch and `git log` matched STATE.json's `current` exactly (`cdd9c5a`, tree clean, groups 1–3 at
`9f9f18d`, `01100ad`, `89429d5`). Nothing to reconcile.

### Group 4 — `c3c23a4`, the evidence route through the same refusal

One test, as expected, and one correction that was not.

**Task 4.2.** A task whose work is named by accepted evidence, approved while a live run is bound to
it, is refused on exactly the same terms as one resolved from its own branch tip. Round 2 answered
*whether* the evidence route shares the window by reading the source (design D9); this measures it.

**The premise was verified by removal rather than assumed.** With `_check_live_turn`'s call
temporarily commented out of the gate, the new test's first approval returns `200` and records:

```
"latest_integration":{"outcome":"skipped",
"reason":"b04eea26d4f5 is already in main; there was nothing to merge", ...}
```

— F162 exactly, through the other door, against the pre-turn commit. Restored, it is a `409` whose
`unaccepted` and `unmergeable` are both empty, which is what proves the liveness check is the thing
refusing rather than the evidence being in some bad state.

The second half is the same as the branch-tip case: the work is committed, `restamp_run_footprints`
re-points the run's footprints at it the way the finalize block does, and the same task then approves
and merges the commit that holds the work.

**Task 4.3 asked whether the delta still reads true after implementation, and it did not quite.**
The evidence-route scenario said *"while the run that recorded that evidence is still live"*, which
is narrower than what the predicate does — it tests whether a live run is **bound to the task**, not
who authored each piece of evidence. The two coincide in the shape the product produces (the agent
working the task claims it, which binds its run, and records its evidence from that same turn) and
diverge where evidence recorded by another task's run against a **shared requirement** is a merge
target here — which `_targets` reaches through `TaskRequirementLink` by design. The scenario now
states the binding, and the routes paragraph carries that residual alongside the unbound-run one.

### Group 5 — `f468bf5`, a loop stops entering the review arm

Two lines of scheduler, and nine test files.

The exclusion sits at the selection site, above the finished-work arm, guarded by `not
wedged_review` — the fresh-review branch only, exactly as round 3 required. `awaiting_landing`
carries the excluded task ids out of the walk so the stall sentence can name them; `unstaffed` stays
empty because nothing was attempted.

**Verified by removal.** With the two-line exclusion commented out, five of the nine new tests fail,
and the sentence they fail with is F161 verbatim:

```
task task-f161-nocommit has no recorded evidence, so there is no commit to review.
Evidence naming a commit is what a review turn is given. Until the work that finished
this task is recorded as evidence naming a commit, no reviewer can be given anything
to look at.
```

**One of the nine passed against the defect, and that is a finding about the test rather than the
code.** `test_the_unstaffed_report_stays_empty_for_a_loops_completed_work` was written with evidence
recorded, so the old arm resolved a reviewer and *selected* — leaving `unstaffed` empty before the
change too. It was rewritten to the no-evidence shape, which is the shape that actually filled
`unstaffed`, and now fails without the fix. This is the reason the discipline says to read the
failure output rather than assume it: a green run of the reproduction is not the same as a
reproduction.

**Task 5.5 was larger than round 3 measured.** Round 3 named five files. Nine needed work:

| File | Which of the two |
|---|---|
| `test_a_flow_names_what_it_cannot_staff` | declares a document — `_flow` |
| `test_a_review_needs_something_to_review` | declares — `_loop_with_completed_task` → `_flow_with_completed_task` |
| `test_review_leaves_the_pool` | declares — `_loop_with_task` → `_flow_with_task` |
| `test_actor_aware_claimability` | declares, **one test only** — the file is about claimability, which is every queue's property |
| `test_flow_fires_a_review_turn` | declares — `_flow` (also fixes one in `test_scheduler`) |
| `test_flow_width` | declares, with a `declares_document=False` arm for the one test whose subject *is* a documentless loop |
| `test_reviewer_is_not_the_author` | declares — `_flow` |
| `test_board_agent_role` | declares — `_flow` |
| `test_scheduler` (all-completed spin) | **expectation changes** — genuinely a loop |
| `test_firing_decision_is_shared` (×2) | **expectation changes** — genuinely a loop |
| `test_loop_stall_ticks_in_place` (changed reason) | **expectation changes** — genuinely a loop |

Round 3's table also listed `test_review_dispatch_staffs_the_task`. It builds no `Loop` at all — it
drives the operator's by-hand dispatch — so it needed nothing, and its passing unchanged is itself
evidence for task 5.6.

`test_loop_stall_ticks_in_place`'s changed-reason mechanism has now moved twice: a second unclaimable
task originally, then recording an agent completion after F142, and now back to a second finished
task — because the landing sentence counts what it names, which is the property that makes the
original mechanism work again.

**A comment this change makes false, corrected rather than left.** `_compose_loop_briefing` asserted
that *"nothing in `decide_firing` or `resolve_reviewer` consults `spec_document_id` — width and
review by a non-author apply to every loop"*. Half of that is now wrong. The briefing wording it
justified is unchanged and is now true *of the scheduler* rather than merely safe for it, and the
documentless `is_review` arm stays reachable because the F70 recovery still staffs a reviewer for a
loop whatever it declares.

### Verification

| Run | Result |
|---|---|
| `test_approval_waits_for_the_turn` + `test_task_integration` | 39 passed |
| `test_scheduler` + `test_turn_scheduler` + `test_flow_fires_a_review_turn` + `test_flow_width` + `test_reviewer_ladder` + `test_reviewer_is_not_the_author` + `test_firing_decision_is_shared` + the new file | 144 passed |
| `test_flow_chain_end_to_end` + `test_flow_checkpoint_lineage` + `test_flow_holds_the_loop_requirements` + `test_handover_briefs_the_reviewer` + `test_briefing_names_its_contract` + 7 loop files | 86 passed |
| `test_a_decided_task_takes_no_new_work` … `test_dependency_gate` (12 files) | 215 passed |
| `test_failed_run_returns_input` … `test_review_divergence` (10 files) | 238 passed, 2 skipped |
| `test_run_reconciliation` … `test_agent_trigger` (12 files) | 223 passed |
| `test_actor_aware_claimability` + the other four of round 3's five | 66 passed |
| `ruff check src/ hub/ tests/`, `black --check` | clean |
| `openspec validate --strict` | valid |

**Still no drive.** Every scheduler-touching test file in the suite has been run and is green, and
that remains a statement about the tests. Groups 6 and 7 are next, and 7 is the one the operator
asked for.

---

## Iteration 5 — 2026-08-31T13:23+01:00 — A-IMPL-3: group 6, the landing action

**Reconciliation.** Branch and `git log` matched STATE.json exactly: `e50f0b2` on
`autonomous/2026-08-31-the-turn-must-end-first`, clean tree, five product commits behind the two
bookkeeping ones. Nothing to reconcile.

Group 6 landed at `80e5717`, one commit, source and bundle together. `POST /tasks/{id}/land`
composes the three moves the operator was making by hand: release the author's hold,
`-> under_review`, `-> approved`. Tasks 6.1–6.5 all ticked, 6.4 included — there was time for the
UI, so it was not dropped.

### The shape

The route is 60 lines and the map is untouched. `_commit_and_render` was extracted from
`update_task_for_actor`'s tail and both routes share it, which is load-bearing rather than tidy:
`apply_transition` stages and does not commit, so that one call **is** the transaction boundary both
callers depend on. A second copy would be a second place for "nothing half-applied" to stop being
true.

Refused on a task that is not `completed`, rather than adapted to it. A task already `under_review`
has a one-call approval that works, so landing would add nothing but a cleared assignee — which, on
a task a reviewer holds, is the review taken off them without saying so. Not restricted to a loop's
tasks: the composition grants no authority the operator lacks on any task, so a restriction would be
a rule about who may take a shortcut rather than about what is legal.

### Two findings, both measured

**1. The delta asked for a third transition row that cannot exist.** It said the history records
*"the release of its author's hold, the move into review, and the approval"*, and task 6.5 said to
record *all three* as actor-caused. `TaskTransition` records a move between **statuses**
(`db/models.py:768-799`) and `assignee` has no history table at all — the release is a column write
folded into the same handler, exactly as the ordinary PATCH route folds it into the same request
(F70's ordering, `tasks.py:1262`). Two rows are recorded, both `operator`, both `origin='actor'`.
The delta scenario and design D6 were corrected to say what the record can hold; the test asserts
the two rows **and** the cleared holder, so the release is still checked, just not claimed as
history.

**2. The gate pre-check is invisible from outside, and the code now says so.** Design D7 and round 3
both said the pre-check *"makes the message the one approval would have given"*. Measured by
deletion: with those three lines gone the landing still answers `409` with the **identical** body —
step three evaluates the same gate, raises the same `GateUnsatisfiedError`, and the transaction rolls
the staged `under_review` back. Eight of the nine backend tests passed with the pre-check removed;
only `test_the_gate_is_decided_before_anything_is_attempted`, added for exactly this and observing the
call sequence rather than the response, failed:

```
E       AssertionError: the landing action moved a task it was about to refuse
```

It is kept — ordering matters the moment a fourth step or a non-gate refusal joins the sequence —
but an unobserved line rots, so both the route comment and D7 now state what it buys and what it
does not.

**A third thing, smaller.** Task 6.3 asked for a test of a refusal raised by
`_guard_reviewer_is_not_the_author` on step two. Through the real route there is none: releasing the
hold first means that guard returns immediately, on its own first permitted case. The refusal is
therefore **forced** rather than provoked, and the test says so — which is the stronger reading of
what the delta claims anyway (*"refused for any reason"*, not for the reasons the composition can
foresee).

### Verified by removal, twice

| Removal | Result |
|---|---|
| Gate pre-check deleted | 8 passed, 1 failed — only the ordering test |
| `session.commit()` inserted after the assignee write | 8 passed, 1 failed — `assert None == 'builder'`, the author's hold gone on a task that never reached review |

Both restored, both green afterwards. This is what says the two tests discriminate rather than
merely pass.

### Verification

| Run | Result |
|---|---|
| `test_one_action_lands_the_work.py` (new) | 9 passed |
| `test_task_transitions_api` + `test_task_integration` + `test_loop_lands_its_work` + `test_approval_waits_for_the_turn` + the new file | 85 passed |
| `pytest hub/tests/ -k "task or tasks"` (rest) | 680 passed, 5 skipped |
| `taskLandingAction.test.tsx` (new) | 8 passed |
| `npm run lint`, `tsc --noEmit` | clean |
| `ruff check src/ hub/ tests/`, `black --check` | clean |
| `openspec validate --strict` | valid |

### Still no drive

Group 7 is untouched and is the operator's explicit ask. Every implementation group is now closed,
so the next firing has nothing standing between it and the three drives — which is why the branch is
released immediately below rather than at a heartbeat's distance.

---

## Iteration 6 — 2026-08-31T13:48+01:00 — A-DRIVE-1/2/3: the change is driven

**Reconciliation.** Branch and `git log` matched STATE.json exactly: `17d23b1` on
`autonomous/2026-08-31-the-turn-must-end-first`, clean tree, six product commits behind the
bookkeeping ones. Nothing to reconcile.

Group 7 is closed, and so is group 8 apart from the suite that was still running when this was
written. **The change has now been driven** — which, until this firing, nothing about it had been.

### The Hub was stale, again, and again the restart is how that was caught

PID 28704 on 8011, started **05:10**, serving the previous run's branch. Killed, restarted from
`hub/` with the beta-profile `DATABASE_URL`, and the new PID's start time checked against every
`.py` under `hub/hub` and `src`: none newer. **Third consecutive firing** where the state file's
warning about 8011 was load-bearing. It should stay in the state file for as long as this loop runs.

### The fixture

New project **`drive3-2026-08-31` = `proj-f44107415869`** at `C:\Users\huida\Documents\drive3-2026-08-31`
— `git init -b master`, one seed commit, `master` adopted by `POST /projects/open` with no settings
round trip. Runner `Haiku (cheap)`, agents `alpha` and `beta`, `allow_agent_jobs` on. Neither
forbidden project touched, every agent turn on Haiku.

### Four harnesses, six runs

| Run | Result |
|---|---|
| `t_f162_window.py` lane 1 | **17/17**, `OUTCOME: GUARDED` |
| `t_f162_window.py` lane 2 (`AW_WIDE=1`) | **6/6**, window 9.7s, 409 at every probe across it |
| `t_drive2_loop_lands.py` | **36/36** |
| `t_drive1_flow_lands.py` | **16/20** — the four are F155 and F154, both pre-filed |

Lanes 1 and 2 ran twice each. Each first outing failed exactly one assertion, and **both failures
belonged to the harness rather than to the product** — see below. A harness edit is not evidence
until it has been run, so both were re-run rather than reasoned about.

The full account with sentences, timings and commit shas is in `scripts/drive/FINDINGS.md` under
`DRIVE-3`. The three things worth carrying:

**1. F162 is closed, measured inside the window rather than around it.** At the instant the task
first read `completed`, the tip of its branch was still the commit it was cut from and `alpha` was
still busy — so the window was *entered*, not assumed. 130ms later the approval answered `409
gate_unsatisfied` with `unfinished: [{agent: alpha, run_id: …}]` and every other category empty.
**No integration row was written at all**, which is a stronger result than the design argued for:
the approval never reaches the point of resolving a merge target, so there is no
`ALREADY_INTEGRATED` skip left behind to be stranded by. Then the turn ended and the same three
hops answered 200/200/200 and put `def cube` on `master`. The refusal cleared itself exactly as its
sentence promises.

**2. The window did not narrow, and lane 2 is what says so.** A single refusal at one instant
cannot distinguish "refused throughout" from "refused at the moment we happened to ask", so lane 2
now probes `POST /land` every five seconds from `completed` to the tip moving. Two probes, both
`409`, both `unfinished`, across a **9.7-second** window. The width is unchanged and still
agent-sized — it runs to the end of the turn, which the product still does not constrain.

**3. The flow's review leg is untouched.** This is the regression the change most plausibly causes,
and it is absent: both reviewers non-author, and `modulo`'s integration row reads `actor_kind:
"run"`, `actor: "alpha"`, `outcome: "merged"`. That row **is** design D10 — *a turn is never blocked
by itself* — proven live rather than argued. Since migration `0092` a review run is bound to the
task it inspects, so a predicate without the acting-run exclusion would have refused this exact
approval. No refusal anywhere in that drive carried an `unfinished` entry.

### What the harnesses had to be told, and what that cost

- **Lane 1's pass condition is inverted.** `GUARDED` — the outcome the harness could only
  hypothesise when it was written — is now the pass, and `REPRODUCED` is a regression that fails
  the drive. Nine new assertions go with it: the refusal is the *approval* and not an earlier hop,
  it is 409 rather than 4xx-anything, the sentence names the agent and states the remedy, the
  `unfinished` entry names the live run, and we really were inside the window.
- **Lane 1 also drives `POST /land` inside the window**, first, because that is the only moment the
  task still reads `completed`. It answers the *identical* sentence, and afterwards the task still
  reads `completed` and is still held — the refused landing left nothing half-applied, which is
  `_commit_and_render`'s transaction boundary observed live rather than in a unit test.
- **`t_drive2_loop_lands`' `approve()` is one request instead of three.** What the three used to
  cost is kept in its docstring rather than deleted, because the three are the reason the route
  exists.
- **Three checks were added to LANE A for group 5's population** — one agent, one task, nobody else
  to ask. The loop's task rests at `completed`, still held by its author, with `beta` idle
  throughout.

### Two harness failures, both mine, both worth the paragraph

**A stale threshold is an assertion about the model.** Lane 2's `width >= 10` was calibrated on a
single sample (10.5s, this morning) and failed at **8.7s** on nothing but Haiku tidying up faster.
Three samples now read **10.5s, 8.7s, 9.7s**. The width is agent-sized *by construction*, so the
bound was an assertion about Haiku rather than about the product; loosened to `>= 5`, two orders
above the round trip that would land inside it, with the measured number printed either way because
the number is the finding.

**And a `NameError` in a branch no run had reached.** The LANE A review-arm check called
`busy_names()`, which that module does not define — it has `statuses()`. It survived a
`py_compile`, cost a full agent turn to discover, and the `finally` block is the only reason it left
no job enabled. An AST pass for unresolved globals was run over all three harnesses afterwards and
found nothing else. Worth doing *before* a run that costs ten minutes of Haiku, not after.

### One new observation, not a defect

Inside the window, hops 1 and 2 are permitted and only the approval refuses — right, because
clearing an assignee and moving to `under_review` assert nothing about whether the work is good. But
the operator is then left at `under_review`, and `POST /land` requires `completed`, so the
one-action route is no longer available *for that task*. Nothing is stranded (a single
`PATCH {"status": "approved"}` finishes it once the turn ends) and nothing is worse than before the
route existed. Recorded because the recommended route and the legacy one **degrade differently under
a refusal**, and that asymmetry is worth knowing before anyone documents either.

### F164's "intermittent is the wrong word" is corrected by this drive

F164 recorded two consecutive drives where a reviewer wrote a verdict in prose and never called
`update_task`, and concluded that *"two for two makes **intermittent** the wrong word"*. This drive
is the third, and the reviewer **did** call it — the transcript carries change C's 409 as prose,
followed by the agent reasoning about it. Two misses and one hit puts "intermittent" back in play,
and makes the harness's F152 assertions non-vacuous for the first time. The underlying diagnosis
(the spawned Claude CLI presents MCP tools as deferred and the model can loop on `ToolSearch`) is
unchanged and still not the Hub's.

### Verification

| Check | Result |
|---|---|
| `openspec validate approval-waits-for-the-turn-to-end --strict` | valid |
| `ruff check src/ hub/ tests/` | All checks passed |
| `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` | 533 files unchanged |
| `mypy src/` | no issues, 22 files |
| `pytest tests/` (the CLI suite) | 440 passed, 3 skipped |

**The whole Hub suite, all 239 files, in six interleaved chunks** — `awk 'NR%6==n'` rather than
contiguous blocks, so no chunk is a single subsystem and the per-chunk result means something:

| Chunk | Result |
|---|---|
| 0 (39 files) | 503 passed, 1 skipped |
| 1 (40 files) | 668 passed, 4 skipped |
| 2 (40 files) | 662 passed, 1 skipped |
| 3 (40 files) | 538 passed, 2 skipped, 1 xpassed |
| 4 (40 files) | 681 passed, 1 skipped |
| 5 (40 files) | 731 passed, 3 skipped |
| **total** | **3783 passed, 12 skipped, 1 xpassed, 0 failed** |

No product code moved this iteration — the diff is `scripts/drive/`, `FINDINGS.md` and `tasks.md`.
Nothing under `src/` has moved on this branch at all, so the CLI suite was never implicated; it was
run anyway (twice, by accident — see below) and is green.

**A chunking trap, for whoever splits the suite next.** The chunk lists were first written by a
Python heredoc to `/tmp/chunk0.txt` and read by bash from `/tmp/chunk0.txt`. Those are **different
directories** on this machine: Python resolves `/tmp` to `C:	mp`, Git Bash resolves it to
`%LOCALAPPDATA%\Temp`. `cat` failed, the shell substituted an empty argument list, and
`pytest` with no paths silently ran `tests/` — the CLI suite — three times over while reporting
`440 passed` and looking entirely legitimate. It was caught only because 440 is the wrong number for
a 40-file Hub chunk. Build the lists in the same shell that reads them.

Task 8.4's bundle was satisfied by iteration 5's commit and re-checked here rather than assumed:
`test_ui_build_stamp.py` passes, and so does the stricter bundle-matches-source assertion behind
`AW_CHECK_UI_BUNDLE=1` (13 passed). Nothing under `hub/ui/src` moved this iteration.

### Where the change stands

**Every task in `approval-waits-for-the-turn-to-end` is ticked** — groups 1 through 8. Three rounds
of spec discipline, six implementation groups, six drives, the whole Hub suite and all three gating
linters. The branch is ready to offer.

---

## Iteration 7 — 2026-08-31T14:18+01:00 — F155-R1: round 1 on the unfollowable refusal

**Position on arrival.** Branch `autonomous/2026-08-31-the-turn-must-end-first` at `6911702`, tree
clean, `git log` matching STATE.json exactly — iteration 6 recorded and the branch released.
`approval-waits-for-the-turn-to-end` is complete and driven; nothing about it is outstanding. Clock
read **14:09**, inside the 15:30 window, so `next_action` was startable as written.

**One unit of work, and only one.** `F155-R1` — explore the code and write the proposal for F155.
Proposal only. No implementation, and rounds 2 and 3 deliberately left for later firings.

### The change: `a-conflict-refusal-names-what-clears-it`

`openspec/changes/a-conflict-refusal-names-what-clears-it/` — `proposal.md`, `design.md`,
`tasks.md` (22 tasks in 6 groups), and one delta modifying `task-lifecycle-governance`'s
*Approval is refused when the work cannot be merged cleanly*. `openspec validate --strict`: valid.

**The defect, re-derived at the source rather than taken from the finding.** `_merge_detail`
(`hub/hub/requirement_gate.py:165-179`) says *"Resolve the conflict on the branch, then approve"*.
`_check_mergeable` (`:322-350`) iterates `situation.will_merge` and probes
`would_conflict(root, target.commit_sha, main_branch)` — `git merge-tree --write-tree` against **that
exact commit** (`task_integration.py:427-449`). Where evidence governs, those commits are the newest
**accepted** footprint per branch (`integration_targets`, `:270-287`). Resolving on the branch makes a
commit no evidence names; the gate re-reads the old one; the answer cannot change. Confirmed, and it
is the whole of F155.

### What round 1 found that the finding did not say

**The sentence is not wrong everywhere — it is wrong on one of two routes, and that is why it
survived review.** `merge_targets` (`task_integration.py:385-409`) has answered two ways since
`a-loop-declares-whether-it-needs-evidence` shipped:

| Route | Target commit | `Target.evidence_id` | Is "resolve on the branch" true? |
|---|---|---|---|
| evidence governs | newest accepted footprint per branch | the evidence row's id | **No** |
| documentless loop, no requirement link | `task_branch_tip` | `None`, by construction (`:405-409`) | **Yes** |

One sentence is emitted for both. It is true of the route the fixtures exercise and false of the
route the flow feature exists for. So the repair is **route-aware**, not a rewording — and the
discriminator is already carried, per target, on `Target.evidence_id`. That reframing is round 1's
main contribution; F155 filed the defect as "the sentence is wrong" and it is more precisely "one
sentence is emitted where the product has two answers".

**Nothing reads a key off `unmergeable`.** Checked rather than assumed, because D1 adds keys to it:
`to_dict` copies the list wholesale, `readableApiError` (`hub/ui/src/api/client.ts:74-108`) returns
`detail.message` and nothing else, and `mcp_server._readable_detail` (`:112-131`) does the same on the
agent's side. The `paths`/`target_branch` assertions in `taskIntegration.test.ts` are assertions about
the **sentence**, not about the structured half. So the sentence is the entire interface, on both
planes — which is exactly why a prose-only change is worth three rounds.

**And that is a correction round 1 made to itself.** The first draft of D1 wrote *"the UI reads
`paths` and `target_branch` from it and nothing else"*, which is false in the direction that would
have made the change look riskier than it is. Corrected in `design.md` before commit, and task 2.3
now says re-check rather than inherit.

### The proposed repair, in three pieces

- **D1** — `_check_mergeable` carries `named_by_evidence` and `evidence_id` per entry, from
  `Target.evidence_id`. Rejected the alternative of a route flag on `_MergeSituation` on
  *truthfulness*, not cost: the sentence is a claim about the commit being judged, and a
  project-level flag is one inference away from what it asserts — and one inference is what produced
  F155.
- **D2** — the evidence-route remedy is resolve → **record evidence naming the resolved commit** →
  have it accepted, ending in `ACCEPT_OR_GRANT` reused verbatim (`requirement_gate.py:73-80`), whose
  own docstring says naming what an agent cannot take *"is what stops it retrying"* — precisely
  F155's failure mode. The wording must name **which branch** the fresh footprint has to carry,
  because the supersession is per-branch (`newest[target.branch]`).
- **D3** — where the judged commit is no longer reachable from the branch the refusal names, say so.
  That is the state step 6 of the drive created, one `is_reachable_from` call on a path already
  running `merge-tree` and already refusing. Carries a pre-authorised default to **drop it** if a
  round objects; D1 and D2 are the repair proper.

### The open question that could invalidate D2

Recorded in `design.md` as open question 1, and it is the one round 2 must answer at the source: does
a footprint recorded on the resolved commit reliably carry the **same `branch` value** as the stale
row? `restamp_run_footprints` writes `rev-parse --abbrev-ref HEAD` (`requirement_evidence.py:908`);
`read_footprint` with an explicit `at` writes `_branch_at`, which is `""` when the commit is not
exactly one branch's tip (`:516-531`). If a resolution can land `branch=""` while the stale row names
the task branch, the per-branch reduction keeps **both** and the stated remedy fails — in a change
whose entire subject is remedies that fail. Task 1.3 exists to prove the remedy before it is written
into prose.

### Verification

No product code moved. The diff against `6911702` is `STATE.json` plus the four new openspec
documents — 444 insertions, nothing under `src/`, `hub/hub/` or `hub/ui/`.

| Check | Result |
|---|---|
| `openspec validate a-conflict-refusal-names-what-clears-it --strict` | valid |
| Every file/line citation in the proposal and design, checked programmatically | 15 ranges; **1 miss found and fixed** — `_MergeSituation` is at `:265-291`, not `:228-250` |
| `git status` | clean |

Ruff, black and mypy were not run: no Python moved, and CI lints no markdown. The suite was not run
for the same reason — iteration 6 ran all 239 Hub files (3,783 passed, 0 failed) on the tree this
iteration adds documents to.

### Where the branch stands

`approval-waits-for-the-turn-to-end` remains complete, driven and offered. `F155` now has round 1
and nothing more. Round 2 is the next unit of work, and it must be an **independent re-derivation** —
above all of the supersession claim D2 rests on, and of the two-route table, which is round 1's own
reasoning and therefore exactly what round 2 exists to distrust.

---

## Iteration 8 — 2026-08-31T14:33+01:00 — F155-R2: the second remedy was unfollowable too

**Position on arrival.** Branch `autonomous/2026-08-31-the-turn-must-end-first` at `2523326`, tree
clean, `git log` matching STATE.json exactly — iteration 7 recorded, branch released, `30db7b8`
carrying F155 round 1. Clock read **14:24**, inside the 15:30 window, so `next_action` was startable
as written.

**One unit of work.** `F155-R2` — round 2 on `a-conflict-refusal-names-what-clears-it`. A spec round
only. Nothing implemented, no product code touched; the diff is four markdown files.

### The four load-bearing claims, checked at the source

| # | Claim | Verdict |
|---|---|---|
| 1 | `_merge_detail` is the only producer of conflict prose; `_check_mergeable` the only producer of `unmergeable` entries | **Confirmed.** `refusal.unmergeable.append` occurs once in the product, `requirement_gate.py:342`. Every other construction is a test or fixture literal. |
| 2 | `merge_targets` answers two ways, and `Target.evidence_id` is set on every evidence row and `None` on the branch-tip row | **Confirmed.** `_targets` sets `evidence_id=evidence.id` unconditionally (`task_integration.py:259`); `merge_targets:405-409` leaves all three evidence fields `None` and comments why. Note the branch-tip `Target` does carry a `branch` — `worktrees.task_branch_name(task.id)` — which matters for D3. |
| 3 | Nothing reads a key off `unmergeable` | **FALSE as stated.** True of product code; false of the drives. `scripts/drive/t_row17_integration.py:273-282` reads `commit_sha` and `paths` off the refusal body. |
| 4 | The supersession D2's remedy rests on | **The finding.** See below. |

### The finding: round 1's remedy is a second unfollowable sentence

This change exists because the product tells a refused party to do something that cannot clear the
refusal. Round 1's replacement instruction had the same defect, one layer down.

Round 1 wrote that the new wording *"must say **which branch** the fresh footprint has to name"*.
Three facts from the code say it cannot:

1. **`branch` is not a field anybody supplies.** `record` (`requirement_evidence.py:97-190`) takes
   `kind`, `actor`, `locator`, `summary`, `task_id`, `workspace`. The `branch` on
   `EvidenceFootprint` is written only by `_apply_footprint` (`:362-388`) from a `Footprint` the
   repository was measured for. A reader told to name a branch has nowhere to name it.
2. **On the agent route the right value happens automatically**, so open question 1 is answered
   **yes** — but for a reason round 1 did not have. `_take_footprint`'s named-commit path is gated
   on the actor: `named = locator_commit(locator) if actor.kind == "operator" else None`
   (`:282`). An agent therefore *never* reaches `_branch_at`, and the `""` round 1 feared is
   unreachable for it: its branch is `rev-parse --abbrev-ref HEAD` at record time and the same at
   turn end via `restamp_run_footprints` (`:908`). Both agree with the stale row, `newest[branch]`
   collapses them, the refusal clears.
3. **On the operator route it does not.** An operator whose `locator` is the resolved sha — which is
   exactly what "record evidence naming the resolved commit" invites, and what F71 made
   authoritative — gets `read_footprint(root, at=…)` and so `_branch_at`, which returns `""` unless
   the commit is the tip of exactly one local branch. The resolved commit stops being a tip the
   moment anything is committed on top of it, which the turn-end snapshot does. `""` and
   `"agentweave/task/…"` are distinct keys in `newest: Dict[Optional[str], Target]`, both targets
   survive, and the refusal stands.

So the remedy is rewritten as a **condition on the repository and on where the recording is done
from** — the resolved commit on the branch the refusal names, the evidence recorded from that
branch — which an agent satisfies by construction and an operator must arrange. New design section
**D2a** carries the derivation; the delta now forbids instructing the reader to state a branch, and
a new scenario asserts that.

### Two further properties the sentence rests on (new design D6)

Both read rather than assumed, because D2 is only true if they hold.

- **"Newest" means most recently *recorded*, not newest commit.** `_targets` orders by
  `EvidenceFootprint.observed_at.asc()`; `observed_at` is `default=_now` at row creation
  (`db/models.py:2462`) and `_apply_footprint` never touches it, so a restamp corrects a commit
  without moving the row in the ordering.
- **Any accepted evidence on that branch supersedes, not only evidence for the same requirement.**
  The reduction keys on `target.branch` alone across everything the task reaches through
  `TaskRequirementLink`. The delta now says the remedy must *not* claim the requirement has to
  match, because a reader who believed that would think themselves blocked where they are not.

### The consumer round 1 did not have

`t_row17_integration.py:284-288` asserts the refusal's message contains both `"resolve"` and
`"approve"`, lowercased. The evidence-route sentence may contain neither in that form, so this drive
goes red when the change lands — correctly. New task **3.6** replaces the assertion with one that
reads the new requirement instead of deleting it.

### The other open questions, answered

- **2 — should the branch-tip sentence name its commit?** Yes, and on a stronger ground than round
  1's symmetry: `task_branch_tip` is read at the moment the gate asked, so the tip is precisely the
  time-varying thing a reader who has pushed since cannot reconstruct. Naming it is what makes the
  sentence checkable.
- **3 — any other producer of `unmergeable`?** No. One `append`, at `requirement_gate.py:342`.
- **D3, weighed as instructed and kept**, with something round 1 did not say: it can only ever fire
  on the evidence route, because a branch-tip target's commit is that branch's tip by construction
  and is therefore always reachable. The cost is not paid where it buys nothing.

### Verification

No product code moved. `hub/`, `src/` and `hub/ui/` are untouched; the diff is the four openspec
documents, 163 insertions.

| Check | Result |
|---|---|
| `openspec validate a-conflict-refusal-names-what-clears-it --strict` | valid |
| Every `file:line` citation across all four documents, resolved programmatically | 26 ranges checked; **3 corrected** — `_merge_detail` is at `:166`, `_take_footprint`'s actor gate at `:282` not `:285`, and D4's fixture entry at `taskIntegration.test.ts:48` not `:49` |
| `git status` | clean |

Linters and the suite were not run: no Python or TypeScript moved and CI lints no markdown.
Iteration 6's whole-suite run (3,783 passed, 0 failed) still describes this tree.

### Where the branch stands

`approval-waits-for-the-turn-to-end` remains complete, driven and offered. `F155` now has rounds 1
and 2. Round 3 is next and owns different ground: whether the modified requirement contradicts
anything already shipped in `task-lifecycle-governance` (`:638`, `:720`, and
`approval-refuses-unaccepted-evidence`'s ACCEPT_OR_GRANT rule), whether prose alone is enough, and
whether the scenarios are drivable. One thing round 2 checked in passing and round 3 should not have
to re-derive: `evaluate` excludes the acting run from the liveness check (`requirement_gate.py:468`),
so an agent approving inside its own turn is not refused as `unfinished` — the new scenarios are
drivable in a single turn.

---

## Iteration 9 — 2026-08-31T14:41+01:00 — F155-R3: the repair reproduced the defect twice

**Position on arrival.** Branch `autonomous/2026-08-31-the-turn-must-end-first` at `5d51c3f`, tree
clean, `git log` matching STATE.json exactly — iteration 8's round 2 at `8035b5f`, branch released.
Clock read **14:34**, inside the 15:30 window, so `next_action` was startable as written.

**One unit of work.** `F155-R3` — round 3 on `a-conflict-refusal-names-what-clears-it`. A spec round
only. No product code moved: the diff is four markdown files, 210 insertions.

### (a) Does the modified requirement breach the shipped corpus? — No, but it must not land first

Checked at the three places round 3 was pointed at, plus one it was not.

| Shipped/pending requirement | Verdict |
|---|---|
| `:638 Approval integrates the approved work` — *"SHALL be the commit named by the task's accepted evidence footprints … and SHALL NOT be the agent's branch"* | **No breach.** The branch-tip route merges *the task's* branch, and `a-loop-declares-whether-it-needs-evidence` draws exactly that distinction itself: *"SHALL NOT merge any branch belonging to an agent"*, and *"Where evidence governs a task, this requirement SHALL NOT apply to it."* |
| `:720 An integration that cannot proceed does not block approval` | **No breach.** Its enumeration of permitted excuses is about integration being *unattemptable*; a conflict is a separate shipped requirement and this change alters neither which approvals are refused nor why. |
| `approval-refuses-unaccepted-evidence`'s ACCEPT_OR_GRANT rule | **No breach — and it turned into finding 2.** Reusing `ACCEPT_OR_GRANT` verbatim is what that requirement asks for. But the requirement beside it says something rounds 1 and 2 did not carry over. See below. |

**What is real is an ordering constraint, now design D9 and task 6.4a.** The modified requirement's
whole discriminator is *where the judged commit came from*, and one of its two answers is the task's
own branch tip. **No shipped requirement in `openspec/specs/` describes that route** — it is ADDED by
`a-loop-declares-whether-it-needs-evidence`, which is implemented in code (`merge_targets` has both
routes, `task_integration.py:385-409`) but still sits unarchived. Synced first, this change would
state a rule naming a route the corpus does not establish, beside `:638` which appears to forbid it,
legible only to a reader who knows to go and read an unarchived change.

### (b) Is prose alone enough? — Yes, and two more keys the gate already holds

Round 3's answer to the question round 2 was asked to leave open: the gate needs **no new query and
no new join**. Everything the reader needs is already on `Target`. But two of those fields are being
dropped on the floor, and the change as written keeps dropping them.

**Finding 1 — the remedy tells the reader to put the resolution on `master`.** Round 2's delta says
the refusal *"SHALL say that the resolved commit must be on the branch it names"*. `_merge_detail`
reads exactly one branch key, `target_branch` (`requirement_gate.py:172`), which `_check_mergeable`
sets to `situation.main_branch` (`:346`). `source_branch` is written into the structured half
(`:345`) and **never reaches the prose**. So today the only branch that sentence names is the main
branch, and a reader taking round 2's phrase at its word is being told to do the opposite of the
remedy — the change reproducing its own defect, one layer down, for the second consecutive round.
Now design D8: the requirement requires the source branch be named distinctly, and phrases the
condition against that one rather than an ambiguous "it". Round 2 had put the naming into a
*scenario*; a scenario checks behaviour a requirement states, it is not where the statement lives.

**Finding 2 — the branch may not be the reader's, and the module already knows.** `_targets` reaches
evidence through `TaskRequirementLink` (`task_integration.py:244`), and says so in its own docstring:
*"if that evidence were accepted, it is this task's integration that would merge its commit"*
(`:228-230`). So the judged commit may have been recorded by **another task**, on a branch that under
per-task isolation the reader has no checkout of. `_check_unaccepted` carries `recorded_by_task` and
`recorded_by_another_task` for precisely this (`requirement_gate.py:383-386`) and
`_unaccepted_detail` renders it (`:198-199`); `approval-refuses-unaccepted-evidence` states it as a
requirement, and states it **in terms of integration rather than acceptance** — *"that evidence's
commit is part of what this task's approval merges … a fact with no route back to its cause."*
`_check_mergeable` carries neither key. That cost nothing while the sentence asked for nothing
branch-specific; **this change is what makes it cost something**, because the new remedy asks the
reader to resolve *on* that branch and record *from* it. Unfollowable a third time, in the change
about unfollowable remedies. Now design D7 and tasks 2.2a/2.2b/3.3b — two keys from
`Target.task_id`, and a deliberate refusal to prescribe whom the reader should then approach, since
that judgement is not the refusal's to make.

### Distrusting round 2's own material

D6's two properties re-derived and **both hold** — `newest[target.branch]` keys on branch alone
(`task_integration.py:283-286`) and `observed_at` is untouched by `_apply_footprint`. D2a's facts 1
and 3 hold as written.

**D2a fact 2 does not, quite — finding 3.** Round 2 wrote that an agent's footprint is *"always"*
`abbrev-ref HEAD` *"in the worktree it was given — which is checked out on the task branch"*. Which
directory that is, is `footprint_root`'s answer, and it has three
(`requirement_evidence.py:334-340`): the recorded run directory **only while it still exists**, then
the per-agent checkout, then `workspace.root` — which is on the **main** branch. Its own docstring
names both fallbacks as live, including *"a task checkout that has since been released, whose
directory is gone by design"*. On either, the fresh footprint carries a branch the stale row does
not, `newest` gains a second key instead of overwriting, and the refusal stands — round 2's operator
failure, reached from the agent route it declared safe.

This does not overturn round 2's remedy; it is *why* that remedy is a condition on where the
recording is done from. What it overturns is what may be **claimed**: nothing may tell an agent the
branch takes care of itself, and no test may assert it as an invariant. The live drive cleared the
refusal because the agent was mid-turn on the task it was approving, so its worktree existed — a fact
about that drive, not a guarantee. Now D2a's new subsection and task 1.3c.

### (c) Are the scenarios drivable?

All of them, and the two that needed a precondition named now have one. *Following the stated remedy
clears the refusal* depends on finding 3's precondition, which 1.3c holds separately. *A judged
commit that has left its branch* is reachable exactly as the drive reached it — `reset --hard` then
`rebase` leaves the accepted commit orphaned while it still conflicts with master. *An undeterminable
branch* is `_branch_at`'s `""`. Round 2's note that `evaluate` excludes the acting run
(`requirement_gate.py:468`) was taken as given and not re-derived, as instructed.

### Verification

| Check | Result |
|---|---|
| `openspec validate a-conflict-refusal-names-what-clears-it --strict` | valid |
| Every new `file:line` citation, resolved against the source | 16 checked; **2 corrected** — `_targets`' `TaskRequirementLink` join is at `:244`, not `:236-243`, and its docstring sentence at `:228-230`, not `:227-229` |
| Product code moved | none — `git diff --name-only` matches no path under `src/`, `hub/hub/`, `hub/ui/` or `scripts/` |
| `git status` | clean after commit |

Linters and the suite were not run: no Python or TypeScript moved and CI lints no markdown.
Iteration 6's whole-suite run (3,783 passed, 0 failed) still describes this tree.

### Where the branch stands

`approval-waits-for-the-turn-to-end` remains complete, driven and offered. **`F155` now has all
three rounds and is ready to implement.** Implementation is `F155-IMPL` and belongs to a later
firing; the 15:30 rule forbids starting an implementation group after that hour, and the operator's
instruction is that the remaining time belongs to a drive rather than to more spec work.

Three things the implementer must not lose: the two new keys come from data already on `Target` and
need no query (D7); the source branch must reach the **prose**, not only the structured half (D8);
and nothing written may claim an agent's evidence lands on the task branch automatically (D2a). One
constraint on landing: not into `openspec/specs/` before
`a-loop-declares-whether-it-needs-evidence` is archived (D9, task 6.4a).

## Iteration 10 — 2026-08-31T15:15+01:00 — F155-IMPL: the whole change, implemented and driven

**Position on arrival.** Branch `autonomous/2026-08-31-the-turn-must-end-first` at `5587e10`, tree
clean, `git log` matching STATE.json exactly — iteration 9's round 3 at `85fc082`, branch released.
Clock read **14:44**. Well inside the 15:30 window, so `next_action`'s F155-IMPL was startable as
written, and there was room for the drive as well rather than instead.

**One unit of work, as scoped:** implement `a-conflict-refusal-names-what-clears-it` end to end —
all six task groups — and then drive it. Four commits: `229a2c5` (group 1), `0373867` (groups 2–4),
`6c13a00` (group 5, the drive), `31115e4` (a regression the full UI suite surfaced).

### Group 1 — reproduce it, and read the failure

Nine tests in `hub/tests/test_conflict_refusal_names_what_clears_it.py`, of two deliberately
different kinds, because F155 is a defect in a *sentence* about a *world* and only one of those
moves.

**One failed today**, and its output was read rather than assumed:

```
This task's work does not merge cleanly into main: shared.txt. Resolve the conflict on the
branch, then approve — approving is what merges it.
```

No commit, and the instruction that does not work. **Eight passed today and must keep passing**,
because they assert the world: following the old instruction leaves the refusal byte-for-byte
identical (`integration_targets` still yields the commit the accepted evidence names); recording
fresh evidence *from a checkout of that branch* is what clears it; D6's two properties hold — the
reduction keys on branch alone, and a restamp does not move `observed_at`; and **both
non-guarantees are reachable**, reached the way the product reaches them rather than by patching a
flag.

Task 1.2 was specified as a test that should fail first. It cannot: it asserts a fact about the
world that this change does not move, so it passes before and after. Written that way, and said so
in its docstring, rather than contorted into a red-then-green shape it has no business having.

### Groups 2–4 — two sentences, because there are two routes

`_check_mergeable` gains four keys, every one from data already on the `Target` — no new query and
no new join. `named_by_evidence`/`evidence_id` (D1), `recorded_by_task`/`recorded_by_another_task`
(D7, the same two keys the sibling refusal twenty lines below already carries), and
`commit_left_its_branch` (D3, `False` only — `None` means the branch does not resolve, which is a
reason to say nothing).

`_merge_detail` groups on the provenance and composes per group. The branch-tip sentence is
**unchanged**, with a comment saying it is deliberately unchanged, because on that route the commit
judged is whatever the branch then points at and "resolve it on the branch" is true. The evidence
sentence names the commit; names the source branch distinctly from the main branch and attaches the
remedy to the source one (D8); says resolving there and retrying will not clear it, and why; states
the remedy as a **condition on where the recording is done from** rather than a field to supply,
because there is no branch parameter anywhere on the recording path (D2a); says explicitly that it
does not take care of itself; says the fresh evidence need not be about the same requirement (D6);
attributes the commit where another task recorded it and stops short of prescribing whom to
approach (D7); and ends in `ACCEPT_OR_GRANT` reused verbatim (D2).

Fourteen more tests, including both provenance shapes built through the product. That second one
cost a correction worth keeping: **`evidence_governs` answers `True` for a task with no loop at
all** (`task_integration.py:376-388`), so the branch-tip population has to be built through
`POST /jobs` with a documentless loop, not by creating a bare task. A test that built it the lazy
way would have asserted the branch-tip sentence against the evidence route.

Both consumers updated rather than deleted. `t_row17_integration.py` asserted the message contained
both `"resolve"` and `"approve"` lowercased — an assertion about *one* remedy where there are now
two, and the evidence sentence deliberately says neither in that form. Replaced with the new
requirement: names the commit judged, and states a remedy that clears it *on the route it was
refused on*. `taskIntegration.test.ts`'s fixture now carries the shape the product emits; its two
assertions held unchanged, which is the check that the new sentence dropped nothing.

Re-checked every consumer of `unmergeable` across `.py`, `.ts` and `.tsx` rather than inheriting
either earlier round's list: no product-code consumer reads a key off it; `to_dict` copies the list
wholesale; `readableApiError` and `mcp_server._readable_detail` read only `detail.message`.

### Group 5 — the drive, which is what the rounds cannot substitute for

`scripts/drive/t_f155_conflict_remedy.py`, against a Hub **restarted on 8011 from this branch**
(old PID stopped, `/health` confirmed, started from `hub/` from source), against a **fresh** project
in a fresh temporary repository. No agent turns, so no model bound — this refusal's whole population
is operator-facing.

**23/23.** The one that matters is lane 2, and it is the one no unit test can do: it **parses the
branch to act on out of the refusal's own sentence** and uses nothing it knows about its own setup.
It resolves the conflict there, records evidence from a checkout of that branch, approves, and
reaches `merged` with the resolved commit on the main branch. Lane 3 drove the *old* remedy against
a second task and got the byte-for-byte identical refusal back — the defect, unchanged, which is
why the product must stop giving that instruction. Lane 4 confirmed the branch-tip route keeps the
old sentence.

Two product refusals the harness earned by writing itself the lazy way round, both **good**: a
loop's `work_needs_evidence` and a task's `loop_id` are creation-time only, and each refusal says
what to do instead. Recorded in FINDINGS.md as behaviour, not findings.

### What the drive and the tests filed

* **F155 — FIXED**, driven.
* **F165 (B, new)** — an operator whose `locator` **is** the resolved sha gets `branch=""` from
  `_branch_at` once that commit is no longer exactly one branch's tip, so the fresh row lands
  *beside* the stale one and the refusal stands with no visible reason. F71 made naming a commit
  authoritative, so this is the natural thing for an informed operator to do. This change is
  prose-only; its wording steers around it and deliberately promises nothing.
* **F166 (C, new)** — the same hole on the agent route, via `footprint_root`'s two fallbacks. Round
  2 called the agent route safe as a *construction*; round 3 corrected it to a *precondition*, and
  the test confirms the correction.

### The one thing this iteration found that nobody was looking for

Running the **whole** UI suite rather than the file this change touched: **1 failed, 1468 passed.**
`TaskDetailDrawer` gained F163's landing action in an *earlier* iteration on this branch, and
`useLandTask` calls `useQueryClient` unconditionally — so the one test in `taskDetailDrawer.test.tsx`
that renders outside a `QueryClientProvider` threw `No QueryClient set`. That test is the
click-outside one; giving it a provider would change what it is testing. The file already had the
convention (four hooks stubbed in one `vi.mock` block, with a comment saying why); this adds the
fifth. **CI would have failed on this branch.** Fixed at `31115e4`.

That is the second time on this branch that the difference between "the tests I touched" and "the
suite" has been the difference between green and red. It is the same lesson as the drive's, one
layer down.

### Verification

| Check | Result |
|---|---|
| `openspec validate a-conflict-refusal-names-what-clears-it --strict` | valid |
| `ruff check src/ hub/ tests/` | clean |
| `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` | 534 files unchanged |
| `hub/tests` — gate + integration chunk (6 files) | 119 passed |
| Whole hub suite, in three file chunks (see below) | **3,806 passed, 12 skipped, 1 xpassed, 0 failed** |
| `cd hub/ui && npm run lint` | clean |
| `cd hub/ui && npx vitest run` | 142 files, **1469 passed**, 0 failed |
| `t_f155_conflict_remedy.py` against 8011 from this branch | **23/23** |

### The suite numbers, and a counting error worth not repeating

Whole hub suite, **3,806 passed, 12 skipped, 1 xpassed, 0 failed** — which is iteration 6's 3,783
plus exactly the 23 tests this iteration added.

| Chunk | Files | Result |
|---|---|---|
| 1 (`test_a*`–`test_l*`) | 60 | 929 passed, 1 xpassed |
| 2 | 140 | 2,245 passed, 10 skipped |
| 3 | 40 | 632 passed, 2 skipped |
| `hub/tests/browser` | 11 | 72 skipped (no browser on this machine) |
| `pytest tests/` | — | 440 passed, 3 skipped |

**Two mistakes in how that was measured, both mine, both caught before they became a false claim.**

**The chunk split silently dropped 40 files.** `sed -n '61,200p'` was written against a guess at the
file count; there are 240. Chunks 1 and 2 therefore covered 200 of 240 and reported a total that
looked plausible — 3,173 — and the only thing that exposed it was the arithmetic not reconciling
against iteration 6's 3,783. A range-based split needs its upper bound to be unbounded (`'201,999p'`),
or it reports coverage it did not have. **This is the same failure shape as everything else this
iteration found: a plausible number that nobody checked against the thing it was supposed to equal.**

**Chunks 1 and 2 were run concurrently, and chunk 1 produced one failure that does not reproduce.**
`test_agent_trigger.py::test_spawn_failure_marks_run_failed` failed in the concurrent run, passed
alone, and passed at file scope (44 passed). Re-run serially, chunk 1 is **929 passed, 0 failed**.
That is the F109 pattern the STATE file warns about, and running two pytest processes at once is
what invited it. The in-memory database makes concurrency *safe*, not *free*: a spawn-failure test
is timing-shaped. Chunk 1's serial number is the one reported above; the concurrent run is recorded
here rather than quietly discarded.

### Where the branch stands

`approval-waits-for-the-turn-to-end` and `a-conflict-refusal-names-what-clears-it` are both
complete, driven and offered. **Every task in F155's `tasks.md` is checked except `6.4a`, which is a
standing prohibition rather than a step:** do not sync or archive this change into
`openspec/specs/` before `a-loop-declares-whether-it-needs-evidence` is archived (design D9). The
modified requirement's discriminator names the branch-tip route, which that change ADDS and which no
shipped requirement describes today.

Nothing is half-written. The next firing has a free choice, and the obvious candidates are F156
(`integration-preview` says `will_merge:true` where the gate refuses — explicitly a non-goal of this
change, still filed), F154 (severity A, unfixed, unqueued), or re-queueing F130/F127/F111+F3/F113/F61.
