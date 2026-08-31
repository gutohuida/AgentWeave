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
