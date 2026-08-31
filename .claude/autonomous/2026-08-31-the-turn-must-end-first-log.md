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
