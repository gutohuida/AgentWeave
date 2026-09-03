## Context

`trigger_agent_directly` provisions a turn's workspace at `agent_trigger.py:871` and converts every
failure into one refusal at `:879-883`. `worktrees.resolve_turn_workspace` behind that call is a
dispatch, not a single operation:

```python
def resolve_turn_workspace(repo_root, agent, config, *, task_id=None, base=None, prerequisites=()):
    if not takes_task_workspace(repo_root, config, task_id):
        return resolve_agent_workspace(repo_root, agent, config)   # .agentweave/worktrees/<agent>
    ...
    return ensure_task_worktree(repo_root, task_id, base, prerequisites)  # .agentweave/tasks/<id>
```

`takes_task_workspace` is `task_id is not None and is_writing_agent(config) and is_git_repo(repo_root)`.
The two arms fail for different reasons and block different populations, and the refusal collapses
them into one sentence and one classification.

Downstream, `turn_scheduler.py:204` asks three questions of the refusal it caught — is it transient,
is it about the request, does it stop the agent running at all — and counts a delivery attempt
against the queued input unless one of them says not to. At the third attempt the input is withdrawn
and the operator is told the Hub gave up.

## Goals / Non-Goals

**Goals**

- Input queued for an agent whose *own* workspace cannot be prepared is held for the repair, exactly
  as input for an agent with no runner bound already is.
- Input at the head of a queue where something else really could have run keeps counting, exactly as
  it does today. The shipped requirement's second paragraph is not weakened.
- The refusal says which workspace it could not prepare, and what would clear it.

**Non-Goals**

- No new operator event. The three flagged sibling refusals emit none either: they are reported
  through `GET /queue/{agent}/status`, whose `waiting_reason` already falls back to the last
  refusal's own sentence across the agent's whole queue (`api/v1/inbound_queue.py:183`), and this
  refusal reaches that fallback unchanged. Adding a `queue_agent_paused` here would give the
  worktree case a louder surface than the case it is being made consistent with.
- No change to the direct-trigger response. See D5.
- No change to when a workspace is provisioned, to what `ensure_worktree` accepts, or to the
  one-turn-per-task refusal above it.
- Not a fix for F189 (the Workspace section's invented session path), which is adjacent in the ledger
  and unrelated in the code.

## Decisions

### D1 — The scope is decided by asking `takes_task_workspace`, not by restating it

The refusal has to know which arm of `resolve_turn_workspace` failed. Three ways to learn it:

1. inspect the exception — `IsolationUnavailableError` is raised by both arms and carries no scope;
   `GitCommandError` carries git's argv, which would mean parsing a path out of it. Rejected: a
   classification derived from a message is a classification that breaks when the message improves;
2. have `worktrees` raise two exception types. Rejected under D6 below — it puts the same fork in two
   modules and gives the Hub layer a reason to grow a second copy of the dispatch rule;
3. ask `worktrees.takes_task_workspace(repo_root, config, turn_workspace.task_id)` at the raise site,
   which is the same call `resolve_turn_workspace` makes and the same call the one-turn-per-task
   refusal eleven lines above already makes.

(3), for the reason `takes_task_workspace`'s own docstring gives about the refusal above it: *"the
refusal asks this function, `resolve_turn_workspace` obeys it, and a change to either moves both."*
The predicate is pure, already imported, and already evaluated in this scope for the D8 collision
check — so this is a second read of a value the function has, not a new dependency.

### D2 — A new classification, not a fourth meaning for `agent_wide`

`TriggerAgentError` gains `agent_workspace_unavailable: bool = False`: *the refusal is that the
agent's own workspace could not be prepared.*

- Not a reuse of `agent_wide`. That flag's docstring is explicit that it means "giving up on the
  input at the head of the queue would let **nothing** else run", and it is stated as certain at the
  raise site: *"Only refusals that are certainly agent-wide are marked."* An agent-workspace failure
  is not certainly that (D3), so writing it into `agent_wide` would make the existing flag's
  documented invariant false and every reader of it slightly wrong.
- Named for parallelism with `workspace_unavailable`, which already means *the **project's**
  workspace could not be resolved*. The two are the same question one scope apart, and a reader who
  knows one can guess the other.
- **It does not imply `transient`.** `workspace_unavailable` does, and that is right for it: a
  project directory can come back on its own (a disconnected drive, a directory being restored). A
  blocked agent worktree does not — somebody has to remove the directory. Holding it as `transient`
  would be a second way to reach the same held-forever behaviour with the wrong reason on record,
  and `GET /queue/{agent}/status` would then report a wait that nothing is waiting for. It also
  reaches further than the counter: `schedule_agent` returns `terminal_failure=not transient`, which
  `scheduler.py:2919` and `:3058` read when deciding whether a job or a flow step failed, so
  `transient` here would quietly reclassify those outcomes too.

### D3 — The scheduler answers the starvation question, because it is the only party holding the queue

The requirement's test is *"where other queued input could have run"*. `trigger_agent_directly` sees
one turn; `schedule_agent` already has `entries` (every queued entry for the agent, across
conversations) and `selected` (the batch it just tried). So:

> An `agent_workspace_unavailable` refusal does not count a delivery attempt **unless** some queued
> entry for that agent outside the refused batch would have run in a different workspace.

Computing "would have run in a different workspace". **R1 reduced this to one column, and that
reduction is wrong:**

- Reaching the agent-workspace arm at all means `is_writing_agent(config)` and `is_git_repo(repo_root)`
  both held — otherwise `resolve_agent_workspace` returns `repo_root` and provisions nothing, so no
  refusal exists. That part is true, and both are properties of the agent and the project rather than
  of an entry, so they hold identically for every other entry in this agent's queue.
- **It does not follow that `takes_task_workspace` reduces to `entry.task_id is not None`.**
  `agent_trigger` never hands `resolve_turn_workspace` an entry's `task_id`; it hands it
  `turn_workspace.task_id`, and `task_workspace.resolve_turn_workspace_inputs` returns that as `None`
  for a **grandfathered** task (`Task.workspace_scheme == 'agent'`, stamped once by migration `0095`
  and never written again) and for a task id `worktrees.validate_task_id` refuses. Upstream of it,
  `run_task_binding.resolve_bound_task` drops the binding entirely for a task that has been deleted,
  and for one `decided_task_refusal` reports as approved or abandoned (F79). Each of those four is a
  turn *about a task* that executes in `.agentweave/worktrees/<agent>` — the directory that is
  blocked.
- So an entry naming a grandfathered task, queued behind the refused head, would **not** have run.
  Under R1's reduction it counts as "could have run elsewhere", the attempt is counted, and the head
  is destroyed at the limit having released nothing. That is F188 surviving its own fix, on precisely
  the projects that predate per-task isolation — which is every project that had work on it when
  `work-is-isolated-per-task` shipped, and none of the fresh ones a test or a drive tends to create.

The test, stated against what actually decides the workspace:

> An entry outside `selected` would have run in a different workspace when it is **eligible** — within
> the hop budget, in an open conversation — **and** either names a review (`review_task_id`, which
> takes the review checkout under `.agentweave/reviews/<reviewer>`; that is resolved before this
> branch is reached and does not consult any scheme), or is about a task that **takes its own
> checkout**: a task row that exists in this project, is not in `TERMINAL_FOR_BINDING`, carries
> `workspace_scheme == 'task'`, and whose id `validate_task_id` accepts. *About a task* covers both
> the entry's own `task_id` and the `Conversation.task_id` its thread inherits
> (`binding_for_conversation`), because a plain follow-up in a thread about a task binds to that task.

Two queries answer the whole thing: one over the task ids the remaining entries name, one over their
distinct conversation ids.

**Every approximation in that test must err toward holding.** The two errors are not symmetric: a
false *no* holds input the requirement says to keep counting, and the operator's queue waits; a false
*yes* counts an attempt and destroys the operator's message at the third schedule. R1's version had
no eligibility filter at all, so an entry over the hop budget or in a closed conversation — neither
of which can run — counted as evidence that something could have. Both are free to exclude:
`hop_budget` is already in scope at the refusal, and the conversation query the inherited-binding half
needs already reads the rows that carry `lifecycle`.

**Entries inside `selected` are still excluded**, and the exclusion is right — but not for the reason
R1 gave. R1 said a task-named entry surviving inside `selected` on this arm is one whose task was
deleted or decided. It is one whose task was deleted, decided, grandfathered, or carrying an id the
product could not have minted: four routes to the same place, and the two R1 missed are the two that
persist. All four fail here identically on the next schedule, so counting them as "could have run
elsewhere" would be counting an entry that cannot run either.

The whole test runs only on the refusal path, and only for this one classification.

### D3a — The predicate lives in `task_workspace`, not in a fourth copy of the rule

The corrected test asks *does this task take its own checkout?* — which is exactly the question
`resolve_turn_workspace_inputs` already answers, and answers by falling through to `UNBOUND` in three
places. Restating those three conditions inside `turn_scheduler` is how the scheduler's idea of the
workspace and the resolver's drift apart, which is the failure D1 rejects one module over.

So `task_workspace` gains a read-only `takes_own_checkout(task) -> bool`, and
`resolve_turn_workspace_inputs` is refactored to call it — keeping its `logger.warning` on the
invalid-id branch, which is the one thing the predicate cannot carry. `task_workspace` reads and never
writes `workspace_scheme` (its own module docstring, and `test_task_workspace_scheme.py` enforces it),
and this adds a read.

The F79 half stays where it lives: `run_task_binding.decided_task_refusal`, asked by the scheduler's
helper about the task rows it loaded. A deleted task is the absence of a row.

### D4 — Rejected: pass `agent_wide=True` at the site and stop

This is the one-line change the finding's own sentence suggests, and it is wrong. It holds the head
entry in the case where a task-bound entry sits behind it in another conversation, and the shipped
requirement *A delivery attempt is counted only where a delivery was attempted* says in as many
words that such input must keep counting so that it "cannot hold the queue indefinitely". Shipping
it would repair a finding from the 2026-08-28 sweep by breaching a requirement from the same sweep —
the exact failure mode round 3 caught on that date.

It is also *unnecessarily* wrong: the case it would break is a case D3 answers with data both parties
already hold.

### D5 — Rejected: make the agent-workspace refusal `request_level`

`request_level=True` would let `POST /agent/trigger` answer 409 instead of 200-queued. It is the
wrong axis: that flag means *waiting could never help*, and here waiting is exactly what helps —
the operator removes the directory and the input is delivered. Worse, the route acts on it by
calling `withdraw_refused_entry`, so marking this site `request_level` would destroy the operator's
message on the **first** attempt rather than the third. The direct trigger keeps returning
`queued` with the refusal's sentence in `waiting_reason`, which is what F96 promises.

### D6 — The repair sentence belongs to `worktrees`, per failure branch

`ensure_worktree` has two refusal branches — a symlink, and a directory that is not the registered
worktree for the expected ref — and they are one `raise` today. The repair for both is *remove the
directory, then `git worktree prune`*, but only the module knows which branch it took and what the
expected ref was, and `_merge_prerequisites` already establishes that this module writes the
operator-facing sentence rather than handing the caller a code to translate. The Hub layer's own
sentence keeps its prefix and interpolates the module's, exactly as it does now.

The refusal that names an agent's workspace says so; the refusal that names a task's checkout names
the **task**, not the agent. Today both say `Could not prepare isolated worktree for {agent}`, which
is misleading in the task case for the same reason `api/v1/agents.py` was wrong to hardcode
`branch_name(agent)` for task-bound turns.

### D7 — What an operator sees afterwards

Held input reports the refusal's sentence through `GET /queue/{agent}/status`, because `reason` falls
back to `entry.waiting_reason` over the agent's whole queue and `schedule_agent` writes that field on
every selected entry before it classifies anything. So the held case is stated, indefinitely, with
the repair in it — which is what makes holding acceptable rather than a silent wedge.

## Risks / Trade-offs

- **A held queue behind a repair the operator does not notice.** Mitigated by D7 and bounded by D3:
  anything that could have run still gets the head dropped on schedule. The residual is an agent all
  of whose queued input is unbound, which is precisely the population the requirement says to hold.
- **Two extra reads on a refusal path.** One query over the task ids the remaining entries name, one
  over their distinct conversation ids. Only on this classification, and only when entries outside
  the refused batch exist.
- **The grandfathered population is invisible to anything that starts clean.** `workspace_scheme` is
  `'task'` by default and is written only by migration `0095`, so a fresh project, a new fixture and
  a live drive all produce task-scheme tasks — the shape that makes the scope test *right*. The case
  that makes it wrong has to be constructed on purpose, which is why it is a named task rather than
  a line inside an existing one, and why it cannot be left to the drive to catch.
- **The behaviour is inferred, not driven, at HEAD.** Task 1 reproduces it before anything changes,
  and says to stop if it does not reproduce.

## Migration Plan

None. No schema, no persisted field, no API shape.

## Open Questions

None for the operator. The one judgement this change makes that is worth their disagreement is D3's
scope test — whether "something else could have run" is worth computing at all, against simply
holding everything (D4). It is written up rather than asked because the shipped requirement already
answers it.
