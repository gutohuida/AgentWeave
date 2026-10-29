# Bug: a reviewer named in a task cannot move it into review while its author holds it

**Status: fixed** (checked on master 2026-10-29) by `every-task-can-always-be-moved-on`: FR `a-reviewer-takes-completed-work` (any agent but the author can move completed work to under_review and becomes its holder; `task_transition_service.py:473`), `board-hands-to-a-reviewer`, and `evidence-tools-take-spdoc-ids` for the related 404. Archived as done.

Found 2026-10-24 by Architect, reviewing task-5d4cf0a5006d ("Checks wait less (one shot)"). The
operator asked for this to be filed.

## What happened

- The operator asked Architect to review the task. Architect was named as reviewer in the task's
  description and in the delegation message to DeveloperOpus.
- DeveloperOpus completed the task. It stayed assigned to DeveloperOpus, its author.
- Architect reviewed it: re-ran the tests, drove the Hub's startup, and approved FR-1 to FR-8.
  Recording that verdict as a status change was refused twice:
  - `update_task(status="under_review")` returned 403: "Cannot move task ... to 'under_review' with
    'DeveloperOpus' as its holder: it is the agent recorded as completing this task, so the move
    would claim its own author is reviewing it. None of the task tools you are offered reassigns a
    task; the operator can move it on."
  - `update_task(status="approved")` returned 409: "From 'completed' the available transitions are:
    under_review."
- No agent can fix this. `update_task` has no assignee field, the author has the same tools, and
  the mender's `mend_reset_task` only goes back to `assigned` or `pending`. The operator had to
  step in, and the verdict could only be written into the task's notes.
- Accepting evidence failed for the same reason until the operator granted Architect
  `decide_evidence`. A verdict could not be recorded as one.

## Why it matters

Every task built by one agent and reviewed by another (the normal pattern for direct delegation
outside a flow) needs the operator in the middle, even when the reviewer is named and willing.
Approvals are scarce (operator, 2026-10-08), and this spends one on a hand-off.

## Possible directions (not decided)

- When a task the author holds is completed, move it to its reviewer: a named reviewer if the task
  has one, otherwise whoever the delegating agent named.
- Or let the agent asked to review take `completed → under_review` itself, becoming the holder, as
  a flow's review turn already does.

## Related friction found the same day

`list_evidence(document="spdoc-5b0709d54ab2")` returned 404 ("no specification document at
spdoc-..."), although `read_spec_document` accepts the same `spdoc-` id.
