## Why

Seven defects were found on 2026-08-21 by **driving** the trial Hub rather than reading it, and they
share one shape: when a loop's firing cannot do its work, the Hub tells the operator something untrue
and then gives them no way to clear it.

The measurements, all from `aw-loop10` on 8010 and recorded in
`openspec/explorations/2026-08-21-what-a-flow-fires-into.md` §2a:

- A firing whose agent could not launch reported `"firing_active": true` — **continuously**, with a
  `JobRun` stuck at `in_progress`, `session_id` null, and no row in `runs`. The one signal the
  operator has said the opposite of the truth.
- The explanation offered was `Runner CLI 'probe-norunner' was not found in PATH.` — the agent's own
  name presented as a missing binary, for an agent whose actual problem was `runner_id IS NULL`.
- Archiving that agent was **refused** because it held undelivered queue entries — entries it could
  only have accumulated *because* it cannot launch.
- Retiring the loop took three undiscoverable steps, because a loop outlives its job's archival.
- Five firings produced five conversations; **three of those firings were refused** and left named,
  empty threads.

None of this is hypothetical and none of it is a flow problem — it is all reachable by a loop today.
Two of the seven have fixes already landed (`blocked` leaving the claim, commit `dc37b1a`; the
unbound-runner reason, this change's task 1). The remaining five have no home, which is why this
change exists: they are currently prose in an exploration, and this repository learned on the *same
day* what that costs — `task-dependencies` 1.6–1.8 were real, unchecked and invisible to anyone
walking tasks in order, and needed a gate task invented to rescue them.

## What Changes

- **A firing that queues but never starts stops being reported as running.** `schedule_agent` returns
  a `ScheduleResult` carrying the reason; `scheduler.py:1015` discards it. The `JobRun` therefore
  stays `in_progress`, and `_batch_loop_summaries` (`api/v1/jobs.py:228-234`) builds its
  `firing_active` flag from exactly that.
- **A stranded firing is recoverable without restarting the Hub.** `reconcile_stale_job_runs`
  (`run_reconciliation.py:102`) already flips these rows and its docstring already names this exact
  case — but nothing calls it on a timer, so "reconciled at startup" means "wrong until someone
  restarts", which for an unattended loop is indefinite.
- **An agent with no way to launch says so.** ✅ *Landed.* `get_agent_config` now reads the bound
  `Runner` and reports `RUNNER_UNBOUND` when nothing anywhere supplies a runner, ending a fallback
  that named a CLI after the agent. This also removes byte-identical blocks duplicated in
  `api/v1/agents.py` and `api/v1/inbound_queue.py`.
- **A broken agent can be archived.** The guard refusing to strand queued messages stays; what
  changes is that the operator is told how to clear them, and that undeliverable entries for an
  unlaunchable agent are not an obstacle the operator has to discover an endpoint to remove.
- **Archiving a job retires its loop.** Today the loop survives, then refuses archival as *"still
  running"* though nothing can fire it.
- **A refused firing does not leave an empty conversation.** `scheduler.py:818` creates and names the
  conversation before the stop check (~868) and the stall check (~956-985) can refuse.
- **A second question about an already-blocked task can release it.** `park_task_for_question`
  (`run_task_binding.py:394`) returns early because `blocked` is not a target of itself in
  `TRANSITIONS`, so `question.blocked_task_id` is never set and answering that question releases
  nothing.

**Non-Goals — stated, not left to omission:**

- **Changing what any status means, or which transitions are legal.** `blocked` stays reachable only
  from `in_progress`; `blocked -> completed` stays absent.
- **The already-running guard on the firing path.** That is `loop-notices-and-reacts` group 1 and
  stays there. This change must not pre-empt it, and its fixes must survive that restructuring.
- **Anything about flows.** Every defect here is a loop defect today. `loop-becomes-a-flow` makes
  several *more likely* to be met, which is evidence for fixing them, not a dependency.
- **Making the operator-in-the-loop path smarter.** No new question routing, no new detection.
- **A periodic scheduler for arbitrary reconciliation.** Only the stale-`JobRun` case is in scope.
- **Deleting conversations.** Nothing in this change removes one; the question is whether a refusal
  creates one.

## Capabilities

### New Capabilities

- `loop-firing-accountability`: What a firing must record about its own outcome — that a firing which
  starts no agent is never reported as running, that its reason is preserved rather than discarded,
  and that a refused firing leaves no artefact implying work happened.

### Modified Capabilities

- `agent-loops`: A refused firing leaves no conversation; archiving a job retires its loop.
- `agent-configuration`: An agent with no runner bound is reported as unbound rather than as a
  missing CLI, and can be archived once its undeliverable queue entries are cleared.
- `run-task-binding`: A second question about an already-blocked task records the task it is waiting
  on, so answering it releases the block.

## Impact

**Code**

- `hub/hub/scheduler.py` — stop discarding `schedule_agent`'s result; move conversation creation past
  the refusal points.
- `hub/hub/run_reconciliation.py` — a trigger other than Hub start for `reconcile_stale_job_runs`.
- `hub/hub/launchability.py` — ✅ landed (`RUNNER_UNBOUND`, bound-`Runner` merge).
- `hub/hub/api/v1/agents.py`, `hub/hub/api/v1/inbound_queue.py` — remove the duplicated runner-merge
  blocks now that the root supplies it; the archive refusal's guidance.
- `hub/hub/api/v1/jobs.py` — archiving a job retires its loop.
- `hub/hub/run_task_binding.py` — stamp `blocked_task_id` for a second question.

**Database**

- None. No new columns, no migration.

**Coordination**

- Overlaps `loop-notices-and-reacts` in `_do_fire_job` only. That change is unstarted (0/44); this one
  must leave its group 1 and group 4 territory intact.
