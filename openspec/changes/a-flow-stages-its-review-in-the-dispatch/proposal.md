# Proposal — a flow stages its review in the dispatch

**Round 1, 2026-09-24** (bundle B1, spec track S13). Finding: **F327 (B)**. Built on the operator's
answer of 2026-09-23: option **(b)** of `spec-queue/DECISIONS.md` `F327-scope` (ROUNDS.md S13 row,
`:381`). Re-verified by reading on HEAD `404c7d5`; F327's own table was measured at `75b11ac` and
R3 of `a-refused-review-leaves-nothing-behind` re-measured it unchanged on the fixed tree.
**Nothing here is implemented yet.**

**Ordered last in bundle B1.** It reads `a-task-is-attended-only-by-a-turn-that-will-reach-it`'s
`task_attendance` (the pool is excluded by a waiting review turn, which is a pair question) and edits
`_answer_failed_review` after `a-review-no-reviewer-can-approve-goes-to-the-operator` has added its
branch there.

## Why

A flow firing stages its review before the dispatch: `enter_selected_task` moves the task
`completed -> under_review` and writes the reviewer as assignee (`hub/hub/scheduler.py:846-903`),
called from `_do_fire_job` (`:3336-3341`) and `_stage_selection` (`:3709`), in the commit that queues
the review entry. When that entry's dispatch is refused — the commit under review pruned (F327's
B1), the review checkout path obstructed (B2) — `turn_scheduler._attempt_turn` rolls back only what
the **dispatch** staged (`turn_scheduler.py:448`, F319's fix), and the firing's staging stays.
So the task is `under_review`, held by a reviewer that never ran. F327 measured the consequences:
the flow reports the task **in flight** until the entry is given up (S1's D3 now surfaces it on the
next firing instead), and every other reviewer the operator sends is refused *"already under review
by 'critic' … Let the review in flight finish"* (`agent_trigger.py:497-507` at the route,
`:886-897` at the dispatch).

`task-lifecycle-governance` already requires the opposite: staffing *"SHALL be performed when the
turn is dispatched, so that a request that is never delivered leaves no task held by a reviewer that
never ran"* (`spec.md:1916-1917`). Its sibling requirement says it does not decide the flow's case
(`:2552-2557`). The operator decided it: (b), the dispatch stages it.

A divergence restaff has the same shape one step later: `_answer_failed_review` writes the new
reviewer into `assignee` (`run_divergence.py:469-474`) and commits (`:827`) before
`schedule_agent` runs (`:872-874`).

## What Changes

- **The firing does not stage a review** (design D1). For a review selection, `_do_fire_job` and
  `_stage_selection` skip `enter_selected_task`. The review entry (`review_task_id`) is queued as
  today, and its dispatch stages the task (`agent_trigger.py:898`, which already does this for every
  review entry). A refused dispatch now leaves the task `completed`, as it was.
- **The pool excludes a task by its waiting review turn** (design D2). Before the documentless branch
  and the ladder, `decide_firing` asks `task_attendance` for a review turn on the task: waiting →
  in flight, naming that agent; refused → surfaced with the refusal, and no second review staffed;
  none → the ladder, as today.
- **An under-review task with a replacement's turn waiting is in flight** (design D3). The
  `under_review` arm names the agent whose review turn is waiting where the named holder is not
  attending.
- **A reviewer with a waiting review turn is not free** (design D4). `_roster_availability` counts
  it as a holding, since the reviewer is no longer the assignee until the dispatch.
- **The restaff stops writing the assignee; the dispatch's holder check lets two holders be
  replaced** (design D5, the "D9 collision"): an author left as holder (F70's recovery, which also
  loses its firing-time write), and the silent reviewer a recorded restaff replaced.
- **The review briefing names the status the reviewer will find** (design D6). It is composed before
  the dispatch now, when the task still reads `completed`.

## Capabilities

### Modified Capabilities

- `agent-flows` — *A dispatched review leaves the reviewable pool*: by the waiting turn, not the
  status; a refused one is surfaced, not re-staffed. *An active task makes its assignee unavailable
  only while something will move it*: a waiting review turn holds its reviewer.
- `task-lifecycle-governance` — *Dispatching a review staffs the task, whichever path dispatched it*:
  the two holders a dispatch replaces. *A refused review dispatch leaves the task as it was before
  the dispatch*: the "not decided" paragraph is decided.

## Impact

- `hub/hub/scheduler.py`: `_do_fire_job`, `_stage_selection`, `decide_firing`,
  `_roster_availability`, `_briefing_verdict_lines`, `enter_selected_task`'s docstring.
- `hub/hub/run_divergence.py`: `_answer_failed_review`'s tail.
- `hub/hub/api/v1/agent_trigger.py`: the holder check at the route (`review_dispatch_refusal`,
  `:497-507`) and at the dispatch (`:886-897`).
- `hub/tests/`: a new file, and a known set of existing assertions that a firing alone leaves a
  review task `under_review` (design D8), each moved on purpose.
- No migration, no route shape, no UI.
