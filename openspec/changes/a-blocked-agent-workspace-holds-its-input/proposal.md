## Why

Two refusals stop an agent from running. One holds the operator's message until they perform the
repair. The other destroys it on the third schedule. They are eleven lines apart in the same
function and the difference is a keyword argument.

**F188**, `scripts/drive/FINDINGS.md`. `hub/hub/api/v1/agent_trigger.py:879-883` raises the worktree
refusal:

```python
except (worktrees.GitCommandError, worktrees.IsolationUnavailableError) as exc:
    raise TriggerAgentError(
        status.HTTP_409_CONFLICT,
        f"Could not prepare isolated worktree for {agent}: {exc}",
    ) from exc
```

No `agent_wide=True`. The three sibling refusals at `:573` (no runner bound), `:594` (the bound
runner row is gone) and `:624` (the runner's CLI is not launchable) all pass it, and
`turn_scheduler.py:204` reads that flag to decide whether a delivery attempt is counted against the
queued input. Driven twice on two fresh projects, a plain directory left at
`.agentweave/worktrees/<agent>` produced:

```
entry-f1c4b3e23097 withdrawn 3 'blocked r5a' | delivery failed 3 times (Could not prepare isolated
                                                worktree ...); the Hub stopped retrying
entry-758804ddd0f2 queued    2 'blocked2'
```

against the flagged refusal's behaviour on the same four schedules:

```
r5norun: [["queued", 0], ["queued", 0], ["queued", 0], ["queued", 0]]
         waiting_reason: "No runner is bound to this agent. Bind one in the Hub UI before it can run."
```

Both conditions are ones only the operator can clear. Both stop the agent starting. One of them eats
the message, and the control the conversation view offers for exactly this situation — the Continue
button — is itself a schedule, so the operator's attempts to find out why nothing is happening are
what consume the allowance. That is **F114 reproduced verbatim at a site the F114 fix did not
reach.**

### What this change is allowed to claim, and what it is not

The reproduction above is from the 2026-08-28 sweep. The night window of 2026-09-03 re-confirmed the
mechanism at HEAD **by reading the code, not by driving it** — the raise site is still unflagged, the
three siblings still pass the flag, and `turn_scheduler.py:204` still gates on it. So the *code path*
is measured at HEAD and the *behaviour* is inference from it. Task 1 of this change reproduces it
again before anything is changed, and a round that cannot reproduce it should stop rather than build.

### The asymmetry is the finding, and one half of it is right

`TriggerAgentError`'s own docstring says why this site is unflagged:

> `:756` (the isolated worktree could not be prepared) is environment-level *and* entry-specific,
> because the workspace it failed to prepare is the **task's** rather than the agent's.

That sentence is correct about the case it describes and **the site does not distinguish the two
cases.** `worktrees.resolve_turn_workspace` dispatches on `takes_task_workspace`:

- task-bound writing turn in a repository → `ensure_task_worktree` → `.agentweave/tasks/<task-id>`.
  A failure here blocks *this* entry. Other queued input for the agent — a plain message, a review,
  work on a different task — runs in a different directory and is genuinely starving behind it.
  **Counting the attempt is right, and this change does not alter it.**
- everything else → `resolve_agent_workspace` → `ensure_worktree(repo_root, agent)` →
  `.agentweave/worktrees/<agent>`. A failure here blocks every turn of that agent that is not about
  a task, which is the whole ordinary population of an agent's queue.

One `except` clause catches both, so the agent-level case inherits the rule written for the
task-level one. The repair is not to flag the site — it is to make the site say **which of the two
workspaces it could not prepare**, and let the rule that already exists apply to each.

### The literal wording of the shipped requirement, which a blanket flag would breach

`agent-conversation-workspace`, *A delivery attempt is counted only where a delivery was attempted*:

> Input refused for a reason that prevents the agent from running **at all** SHALL NOT have a
> delivery attempt counted against it […] This SHALL NOT extend to a refusal that prevents only this
> input from being delivered. **Where other queued input could have run**, the input at the head of
> the queue is in the way, and the system SHALL go on counting its attempts.

An unpreparable agent workspace does not always prevent the agent from running at all. A task-bound
entry in another conversation takes `.agentweave/tasks/<task-id>` and would run — and
`turn_scheduler.schedule_agent` builds its turn from the oldest eligible entry across the agent's
*whole* queue, so an unbound entry at the head really does hold that task entry back. Passing
`agent_wide=True` unconditionally at this site would therefore hold input the requirement says must
keep counting: a fix that breaches a requirement shipped on 2026-08-28 in order to repair a finding
from the same sweep.

So the deciding question is the one the requirement asks, and the scheduler is the only party that
can answer it, because it is the only one holding the rest of the queue. The raise site states the
scope of what it could not prepare; the scheduler asks whether anything outside that scope was
waiting.

**Naming a task is not the same as taking a task's checkout.** `agent_trigger` never hands
`resolve_turn_workspace` an entry's `task_id` — it hands it `turn_workspace.task_id`, and
`task_workspace.resolve_turn_workspace_inputs` returns `None` there for a **grandfathered** task
(`Task.workspace_scheme == 'agent'`, stamped once by migration `0095`), for a task id
`validate_task_id` refuses, and — one layer up, in `resolve_bound_task` — for a task that has been
deleted or already decided (F79). All four run in `.agentweave/worktrees/<agent>`, the directory that
is blocked. So the scheduler's question is *does this entry's task take its own checkout*, asked of
the task row, and not *does this entry name a task*. Getting that wrong would leave F188 alive on
every project old enough to have grandfathered tasks; design D3 is written against the task row for
that reason.

### And the refusal still does not say what would clear it

`ensure_worktree`'s message names the path and the branch precisely —

> refusing existing path C:\…\.agentweave\worktrees\r5runnerr5b: it is not the registered git
> worktree for refs/heads/agentweave/r5runnerr5b

— and never says what to do about it. Removing that directory and pruning is the entire repair, and
under this change the operator's input is held until they perform it, which makes stating it part of
the same defect rather than a separate nicety. `_merge_prerequisites` already sets the precedent: the
`worktrees` module writes the operator-facing sentence, because it is the only code that knows which
of the branches it took.

## What Changes

- The single `except` around `resolve_turn_workspace` becomes two refusals that differ by which
  workspace failed. The agent-workspace refusal carries a new classification; the task-checkout
  refusal keeps today's behaviour exactly and names the task instead of the agent.
- `turn_scheduler` treats an agent-workspace refusal as agent-wide **unless** other queued input for
  that agent would have run in a different workspace, in which case it counts the attempt as it does
  today. Nothing else about the counter changes.
- `worktrees.ensure_worktree`'s refusals gain the repair sentence, per failure branch.
- `agent-conversation-workspace` gains the agent-workspace case as a scenario of the existing
  requirement, and `workspace-isolation` gains a requirement that a refusal to provision states what
  would clear it and which workspace it is about.

## Impact

- Affected specs: `agent-conversation-workspace` (MODIFIED), `workspace-isolation` (ADDED, MODIFIED)
- Affected code: `hub/hub/api/v1/agent_trigger.py`, `hub/hub/turn_scheduler.py`,
  `hub/hub/worktrees.py`, `hub/hub/task_workspace.py` (a read-only predicate, extracted — design D3a)
- No migration. No API shape change: `TriggerAgentError` is internal, the HTTP status and the
  operator-visible sentence are the only things a caller sees, and both stay a 409 with a longer
  sentence.
- Behaviour change visible to an operator: a message queued for an agent whose own worktree is
  blocked is **held** rather than dropped after three schedules, and `GET /queue/{agent}/status`
  keeps reporting the refusal's own sentence for as long as it is held
  (`api/v1/inbound_queue.py:183`).
