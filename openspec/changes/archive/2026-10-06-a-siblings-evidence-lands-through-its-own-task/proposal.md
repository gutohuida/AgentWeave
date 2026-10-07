## Why

**Tier 2** (the merge contract: what approving a task writes into the operator's repository).

F520 (A), driven on the trial Hub `:8010` on 2026-10-06. Task 1 of the F510 slice was approved and
merged. Task 2 served the same FR-1..3 and was still `under_review`, and none of its check runs had
passed. The operator accepted task 2's evidence, and
`task_integration.integrate_what_was_waiting_for_this_evidence` re-ran **task 1's** integration. Task 1's
merge targets (`task_integration._targets`) are every accepted footprint for its requirements, whoever
recorded it, so two commits of task 2 landed on master (`3bae149`, `4f2face`), recorded under task 1.
Task 2's review verdict and the project's checks gate never ran on them. Reproduced through the routes by
`hub/tests/test_sibling_evidence_waits_for_its_task.py` (fails on master).

## What Changes

- Evidence recorded by **another task** counts toward this task's merge targets, and toward its
  "awaiting a decision" refusal, only once that other task is `approved`. Until then it is that task's
  work, landed by its own approval through its own gate.
- Evidence recorded by this task, and evidence recorded with no task, are unchanged.
- The one filter is `_targets`, which both the gate and the merge read, so they cannot disagree.

Kept: `agent-loops`' rule that "evidence recorded against a shared requirement by a different task is
integrated by this task". Once that task is approved this still holds, and before then the work
cannot be stranded, because the recording task's own approval lands it.

## Hazard, migration, rollback

- **Hazard.** This narrows what an approval merges. Evidence recorded by a sibling that is never
  approved (for example `rejected`) no longer lands through an approved task, which is the intent.
  `:8000` gets this on its next restart. It adds no data change and runs no migration.
- **Rollback.** Revert the commit. Nothing is stored differently.

## Acceptance drive

`test_sibling_evidence_waits_for_its_task.py` (real repository, real routes) has two parts:
1. Accepting task 2's evidence leaves main without task 2's commit.
2. Task 2's own approval then merges it.

Both fail on master. It is written in the same order as the trial: two tasks on FR-1, the first
approved and merged, then the second's evidence accepted.
