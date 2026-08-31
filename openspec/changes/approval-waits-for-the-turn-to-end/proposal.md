## Why

A task's work is not knowable while its turn is live, and the product currently answers the question
anyway.

An agent calls `update_task(completed)` **mid-turn** — the board says done at that moment. Its edits
are committed onto the task branch by `worktrees.snapshot_worktree` at turn **end**
(`hub/hub/api/v1/agent_trigger.py:1993`, `:2043`). Between the two, `task_integration.task_branch_tip`
(`hub/hub/task_integration.py:307`) answers with the commit the branch was cut from.

Driven on 2026-08-31 (`scripts/drive/t_f162_window.py`, lanes 11/11 and 4/4, finding **F162**): an
approval landing in that window resolves the **base commit** as the work, `integrate` records
`ALREADY_INTEGRATED`, and `is_retryable` classifies that as **not retryable** on purpose
(`task_integration.py:112-134`). The task reads `approved` on the board, its work sits unmerged on
its branch, and no screen offers a button. The window measured **10.5 seconds** on an ordinary
three-step turn, and it is the *agent* that sizes it — nothing bounds how long an agent works after
marking its task done. All three transitions in the drive answered `200` with the agent still mid-turn.

The product has met this window before and said so. `requirement_evidence.restamp_run_footprints`
(`hub/hub/requirement_evidence.py:846`) exists because *"an agent records evidence during its turn,
while its work is still uncommitted… The window is structural — there is no moment at which recording
could observe the right sha — so the record is corrected once the commit exists."* The evidence route
survives the window because it has three defences: that restamp, a human acceptance step before
approval is permitted, and coverage vocabulary (`verified, not integrated`) for the gap. The
branch-tip route added by `a-loop-declares-whether-it-needs-evidence` inherited **none** of them —
and coverage structurally cannot describe it, because `requirement_coverage` selects from
`SpecRequirement` (`hub/hub/requirement_coverage.py:219`) and a documentless loop's task serves no
requirement.

Two further findings from the same drives share one cause — a loop being pushed through a review leg
it has no second party for:

- **F161**: a loop that declared its work needs no evidence still stalls with *"there is no commit to
  review"*, emitted at `hub/hub/scheduler.py:1472` from `requirement_evidence.commit_for_task_review`,
  which resolves the review commit from evidence rows and nothing else. The sentence is false for
  exactly the population the declaration was built for: approving that same task merges its branch
  tip seconds later.
- **F163**: landing a loop's work costs the operator three hand transitions, two of which begin as
  refusals — a `403` because the task is still assigned to its author, then a `409` because
  `completed` reaches only `rejected` and `under_review` (`hub/hub/task_transitions.py:137-141`). A
  flow never meets the first: it resolves a reviewer who is not the author. A loop has one agent.

F163's obvious remedy — shorten the route — makes F162 **more** likely, not less: the drive fired all
three hops in **640 milliseconds**, well inside the window. So these are one change, sequenced, not
three.

## What Changes

- **The gate learns one more precondition.** `requirement_gate` refuses the `-> approved` transition
  while the task has a live turn, as a sibling of the existing `unmergeable` and `unaccepted`
  categories on `GateRefusal` (`hub/hub/requirement_gate.py:84-113`). This is the pattern the
  archived change `2026-08-13-approved-means-it-is-in-the-product` established when it put
  mergeability in the gate: *"a branch that conflicts with main is refused before approval, in the
  same typed refusal… not discovered halfway through a merge."*
- **The refusal is rigor-independent**, for the same reason `_check_mergeable` is
  (`requirement_gate.py:288-292`): rigor is a claim about how well work must be proven; this is a
  claim about whether the work exists yet to be put anywhere.
- **Liveness is tested, not read.** The condition is a `Run` row for this task with
  `status == "running"` **and** a live pid. `reconcile_interrupted_runs` runs **only** in
  `lifespan()` startup (`hub/hub/main.py:350`; stated at `hub/hub/pty_runner.py:150` and
  `hub/hub/run_reconciliation.py:143`), so a crashed agent leaves `status == "running"` until the Hub
  is restarted. Reading the column alone would wedge approval indefinitely on one crash.
- **A loop never enters the review leg.** The scheduler stops selecting a loop's `completed` task for
  review, so `commit_for_task_review` is never asked for a commit and F161's sentence is never
  emitted — rather than being made true by teaching that function about branch tips. A loop has one
  agent and no second party; a review it staffs is the author reviewing itself, which
  `_guard_reviewer_is_not_the_author` refuses anyway.
- **Landing a loop's work becomes one operator action**, composed of the transitions that already
  exist — clear the assignee, `-> under_review`, `-> approved` — rather than three hand-made calls.
  The operator *is* the reviewer in that sequence, which is exactly the remedy the existing 403 names
  (*"clear the assignee to review it yourself"*), so the recorded history stays true.
- **BREAKING** for anything approving a task through the API while its agent is still running: that
  call now returns a refusal instead of a `200` that strands the work.

## Non-Goals

Stated explicitly, not by omission:

- **What `approved` means does not change.** It still means the work is in the product, as
  `2026-08-13-approved-means-it-is-in-the-product` decided. Deferring the merge to turn-end — making
  approval a promise rather than an act — was considered and rejected for that reason.
- **`is_retryable` is not touched.** `ALREADY_INTEGRATED`'s classification stays as written; the
  situation that produced a false one can no longer arise.
- **`TRANSITIONS` is not widened.** Adding `completed -> approved` would make review guard-enforced
  rather than structurally unavoidable for every task in the product, to save one hop for loops.
- **No deferred-merge queue, no turn-end merge trigger, no new asynchronous screen state.**
- **F154 and F155 are not in scope.** Both are severity A, both are filed with reproductions in
  `scripts/drive/FINDINGS.md`, and both are about what a flow's machinery *tells* an agent to do
  rather than about when work is knowable.
- **The evidence route's own exposure to this window is in scope only if the rounds confirm it.**
  The hypothesis is that approving mid-turn on the evidence route merges the stale pre-turn commit
  named by an accepted evidence row, with `restamp_run_footprints` correcting the row after the merge
  already happened. If confirmed, the precondition covers both routes with one rule; if not, it is
  scoped to the branch-tip route.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `task-lifecycle-governance`: approval acquires a precondition — a task whose turn is still live is
  refused, because its work is not yet knowable. States what the refusal must name and that it clears
  itself.
- `agent-loops`: a loop does not staff a review of its own agent's work, and landing a loop's
  approved work is one operator action rather than three.
**`agent-flows` is deliberately not modified.** Its review requirements are already written about a
flow — *"A flow resolves a reviewer by declaration, then by availability"* (`agent-flows:134`), whose
scenarios all begin *"WHEN a flow fires"*. Nothing in the corpus says a **loop** staffs a review. The
code applies the flow's review arm to loops anyway, which is what emits F161's sentence, so the
breach is code exceeding its spec rather than a requirement needing amendment. The `agent-loops`
delta states the negative that was never written down.

## Impact

**Code:**

- `hub/hub/requirement_gate.py` — a fifth `GateRefusal` category and the check that fills it.
- `hub/hub/run_reconciliation.py` or a shared helper — a liveness predicate (`status == "running"`
  and `pid_alive`) reachable from the gate without importing the trigger.
- `hub/hub/scheduler.py` — the review arm no longer selects a loop's completed tasks (`:1440-1500`).
- `hub/hub/api/v1/tasks.py` — the operator's one-action landing route, or the composition behind it.
- `hub/ui/src/components/tasks/` — the affordance that issues it, and rendering the new refusal.

**Tests:** `hub/tests/` — a reproduction of F162 before the fix, in the shape the drive proved
(mark completed mid-turn, approve, assert the refusal rather than a stranded `approved`).

**Drives:** `scripts/drive/t_f162_window.py` is the existing harness and should re-run to a different
outcome; `t_drive2_loop_lands.py` covers the loop's landing route.

**No migration.** No column, no schema change, no data to backfill.
