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
