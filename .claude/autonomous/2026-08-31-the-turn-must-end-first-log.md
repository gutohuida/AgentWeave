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
