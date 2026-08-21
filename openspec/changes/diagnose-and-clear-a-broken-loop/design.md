## Context

Seven defects, all measured on 8010 on 2026-08-21, all reachable by a loop today. Full observations
in `openspec/explorations/2026-08-21-what-a-flow-fires-into.md` §2a and
`2026-08-21-which-band-blocked-belongs-to.md`.

Two constraints shape every decision here.

**This change is small and must stay small.** Each defect has a narrow, local cause. The temptation
is to fix the *class* — to build a general "firing outcome" abstraction, or a periodic reconciliation
framework. That would collide head-on with `loop-notices-and-reacts`, which owns the firing decision
and is unstarted at 0/44.

**`loop-notices-and-reacts` will restructure `_do_fire_job`.** Two of these fixes live in that
function. They must be written so that change rewrites *around* them rather than reverting them — see
D5.

## Goals / Non-Goals

**Goals:**

- A firing that starts no agent is never reported as running, and says why.
- An operator can clear a broken loop and a broken agent without restarting the Hub and without
  knowing an endpoint exists.
- Every fix survives `loop-notices-and-reacts` restructuring the firing path.

**Non-Goals:** as stated in the proposal — no status or transition changes, no already-running guard,
nothing flow-specific, no general reconciliation scheduler, no conversation deletion.

## Decisions

### D1 — Record the waiting reason where the firing already records everything else

`schedule_agent` returns `ScheduleResult(waiting_reason=...)` and `scheduler.py:1015` throws it away.
The reason is already computed, already a sentence written for an operator, and already used by
`api/v1/checkpoints.py:233-234` and `checkpoint_cutover.py:136-140`. So this is not new information —
it is information already produced and dropped one line from where it belongs.

**A firing whose selection did not start is not `in_progress`.** It becomes a terminal `JobRun` state
carrying the reason, exactly as the stall path already does with `skipped`.

*Rejected:* **inferring it later from the absence of a `Run`.** That is what
`reconcile_stale_job_runs` does, and D2 keeps it — but it is a backstop, not the primary path. A fact
known at the moment it happens should not be rediscovered by a sweep.

*Rejected:* **leaving `in_progress` and fixing only `firing_active`'s derivation.** The `JobRun` row
would still claim a firing is in progress; every other reader would inherit the lie.

### D2 — The reaper keeps its job and gains a trigger, and that is all

`reconcile_stale_job_runs` is correct and its docstring already names this exact case
(`job-0b490274`, agent `claude-1`, `runner_id` NULL). Measured: before a restart the row read
`in_progress` and `firing_active: true`; after, `failed` and `false`. The function works. Only its
**trigger** is wrong — Hub start, which for an unattended loop is never.

D1 removes the main producer of these rows, so this is a genuine backstop for crashes rather than the
routine path. It should run on a **schedule the Hub already owns** rather than a new mechanism.

*Rejected:* **a general periodic-reconciliation framework.** Scope creep, and it would need a
policy for every reconciler rather than the one case measured.
*Rejected:* **dropping the reaper once D1 lands.** A crashed process still produces exactly this row,
which is what the function was written for; D1 covers the refused case, not the died case.

### D3 — The archive refusal keeps its guard and gains a remedy

*"`probe-norunner` has messages waiting to be delivered. Archiving it would strand them, because
nothing delivers to an archived agent."* — correct, well worded, and unhelpful, because the entries
exist *because* the agent is broken and the operator is not told how to clear them.

**The guard stays.** What changes is that the refusal names the remedy. The operator should not have
to discover `DELETE /queue/entries/{id}` and find an entry id first.

*Rejected:* **archiving anyway and discarding the entries.** Silently dropping queued work is worse
than a refusal, and the guard's reasoning is sound.
*Rejected:* **auto-draining entries for an unlaunchable agent.** "Unlaunchable" is a probe result that
can change — binding a runner fixes it — so entries queued meanwhile are legitimately deliverable. A
sweep that deleted them would destroy recoverable work.

### D4 — Archiving a job retires its loop, because the loop cannot outlive its own trigger

A `Loop` has exactly one `AIJob` (`Loop.job_id` is unique). An archived job never fires. So a loop
whose job is archived is not "still running" in any sense the operator would recognise — but
`archive_loop` (`api/v1/loops.py:171-175`) refuses on `ending_state is None`, which an archived job's
loop never reaches on its own.

Measured cost: `stop_at` in the past → fire once to evaluate the stop condition → archive. Three
steps, none discoverable.

**`archive_job` retires the loop in the same operation.** The D17 reasoning that `archive_loop`
protects — never hide unattended work that is still firing — is *satisfied*, not bypassed: archiving
the job is what stops it firing.

*Rejected:* **letting `archive_loop` accept a loop whose job is archived.** Same outcome, two calls,
and the operator still has to know the second one exists.

### D5 — The conversation is created after the refusal points, and this is the fix most at risk

`scheduler.py:818` calls `new_conversation` and `name_conversation` before the stop check (~868) and
the stall check (~956-985) can return `False`. Measured: five firings, five conversations, three of
them refused.

This violates no requirement as written — `agent-loops` names three things a refused firing must not
do (claim, queue input, change status) and this is not among them. It undercuts **§626**, which
exists because *"a loop left running fills the list with threads the operator never began"*. On a
5-minute cron a stalled loop makes twelve an hour.

**Moving creation later is the whole fix**, and it is the one `loop-notices-and-reacts` is most
likely to disturb, because that change restructures precisely these branches. The mitigation is a
test asserting the *property* — a refused firing creates no conversation — rather than the ordering,
so a restructure that reintroduces the bug fails rather than silently passing.

*Rejected:* **creating it and deleting it on refusal.** Two writes and a window where it exists;
nothing else in this codebase deletes a conversation.
*Rejected:* **marking refused conversations and hiding them.** Keeps the row, adds a concept, and
leaves §626 collapsing threads that stand for nothing.

### D6 — A second question about a blocked task records what it is waiting on

`park_task_for_question` (`run_task_binding.py:394`) opens with
`if STATUS_BLOCKED not in allowed_targets(task.status, actor.kind): return None`, and `blocked` is
not a target of itself in `TRANSITIONS`. So for an already-blocked task it returns early and
`question.blocked_task_id` is never set — and `release_block_for_question` requires that field. The
operator answers the newest question and nothing is released.

**Stamp `blocked_task_id` even when no transition is needed.** The task is already parked for a
question; a second question about the same task should be able to release it too.

**This does not make `blocked -> blocked` legal.** The transition map is untouched (a Non-Goal); what
changes is that recording *which task a question is about* stops being a side effect of a successful
transition. Those are two different facts and only one of them needs an edge.

*Rejected:* **refusing the second question.** An agent may legitimately need to ask again.
*Rejected:* **releasing on any question for the task.** Then an unrelated question about a blocked
task would release it, which is the opposite error.

## Risks / Trade-offs

**[D1 and D5 both live in `_do_fire_job`, which `loop-notices-and-reacts` restructures]** → Assert
properties, not line ordering, and say so in the tasks. A restructure that reintroduces either bug
must fail a test rather than pass silently. Coordinate: this change should land *before*
`loop-notices-and-reacts` starts, or its group 1 must adopt these tests.

**[D4 changes what archiving a job does]** → Existing callers expect job archival to touch only the
job. The loop suite is the check, and a loop with no job is not a state the model allows, so nothing
legitimate depends on the loop surviving.

**[D2's trigger could fire during a live firing]** → The function already skips any `JobRun` whose
`Run` is `running` (`run_reconciliation.py:131-132`), so the guard exists; the risk is a race between
a firing reaching `in_progress` and its `Run` being created. Whatever interval is chosen must be long
enough that this window is not a routine occurrence.

**[Fixing six small things at once obscures which fix broke what]** → One commit per defect, each
with its own reproduction, in the order of the task groups.

## Migration Plan

No data migration and no new columns. Existing stranded `JobRun` rows are cleared by the reaper the
first time it runs under D2's trigger, which is the same treatment they get today at Hub start.

## Open Questions

- **What triggers the reaper under D2** — the APScheduler instance the Hub already runs, a
  lifespan-owned task, or piggybacking on an existing periodic path. Wants a look at what already
  exists before choosing.
- **How does the archive refusal name its remedy** (D3) — prose naming the endpoint, a structured
  field the UI turns into a button, or an operator-facing "discard queued input" action. The last is
  the most useful and the largest.
- **Does the `JobRun` state in D1 reuse `skipped` or need its own?** `skipped` currently means
  "refused before the claim"; a selection that claimed and then failed to start is a different story
  and may deserve a different word.
