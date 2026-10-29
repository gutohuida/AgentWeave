# A checks send-back leaves stale accepted evidence as what gets checked, so the task can never complete

**Status: fixed** 2026-10-29 as F1081 by `a-checks-send-back-returns-the-task-s-accepted-evidence` (commit 8f05f16, on master): a checks or landing send-back holds the task's accepted evidence, so the next completion is checked on the fix. The race in its own test is still open as F1084. Archived as done.

Recorded 2026-10-29 by Architect at the operator's request.

## What happened

The flow "Vault sources can be edited, replaced and archived" (spdoc-ed2248eba283) sat for about
9 hours on task-28241f64fb0a (archive and restore), with Developer retrying it over and over.

1. 2026-10-28 23:11. QA approved the task and accepted its evidence for FR-6, 10, 11, 12 and 16
   at commit f7cf6d3.
2. 23:31. The landing batch (lbat-34ab1776047f) sent it back: f7cf6d3 failed the
   routes-without-a-client test (22 routes against a limit of 19). Developer fixed it by adding
   client hooks in hub/ui/src/api/vault.ts (8ce3b6f).
3. 23:58. Completion was refused because the project's checks (chk-b6f585386df2) failed. The
   check had run on **f7cf6d3, the old accepted commit**, not on the fix. The send-back held only
   FR-10, so FR-6, 11, 12 and 16 stayed accepted at f7cf6d3.
4. From then until 08:30 every completion attempt was refused the same way. The mender reset the
   task at 04:51, which only restarted the loop. Developer kept adding empty commits to force a
   re-run and recorded about 280 duplicate evidence rows that were never decided.
5. 08:31 on 2026-10-29. Architect reviewed 6303720 (full Hub suite: 9359 passed) and accepted
   evidence there by hand. That unblocked it.

## Why it cannot get out on its own

- When evidence decides what merges, the check targets come from accepted evidence only:
  `merge_targets` in hub/hub/task_integration.py (the `evidence_governs` branch,
  `_targets(..., ACCEPTED)` reduced by ancestry).
- `request_run` in hub/hub/project_checks.py falls back to the reviewed commit
  (`review_target`) only when there are **no** accepted targets (the F773 path).
- So the check keeps re-testing the commit known to fail. Newer evidence could replace it, but
  only a reviewer can accept it, and a reviewer is only given the task once it completes, which
  the check refuses. Retrying, re-running the check and resetting the task all point back at
  f7cf6d3.

## Direction for the fix (not decided)

- A checks or landing send-back should hold **every** accepted evidence row for the task, not
  just the piece it names. The next completion is then checked at the review commit, through the
  existing F773 path.
- Or: when the task's branch has moved past its accepted evidence, the completion check should
  target the branch's reviewed commit rather than the accepted one.
- Also worth handling: an agent stuck in this state should not record evidence again on each
  retry (about 280 duplicate awaiting rows), and the mender should recognise "completion refused
  on a stale target" as something a reset cannot fix.

## Acceptance drive to write first

Take a task with accepted evidence at commit A, where A fails a project check. Send it back.
Commit a fix B on its branch and record evidence at B. Complete. Expected: the check runs on B
and the task reaches under_review. Today: the check runs on A and completion is refused forever.
