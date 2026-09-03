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
  and `GET /queue/{agent}/status` would then report a wait that nothing is waiting for.

### D3 — The scheduler answers the starvation question, because it is the only party holding the queue

The requirement's test is *"where other queued input could have run"*. `trigger_agent_directly` sees
one turn; `schedule_agent` already has `entries` (every queued entry for the agent, across
conversations) and `selected` (the batch it just tried). So:

> An `agent_workspace_unavailable` refusal does not count a delivery attempt **unless** some queued
> entry for that agent outside the refused batch would have run in a different workspace.

Computing "would have run in a different workspace", precisely and cheaply:

- Reaching the agent-workspace arm at all means `is_writing_agent(config)` and `is_git_repo(repo_root)`
  both held — otherwise `resolve_agent_workspace` returns `repo_root` and provisions nothing, so no
  refusal exists. Both are properties of the agent and the project, not of an entry, so they hold
  identically for every other entry in this agent's queue. `takes_task_workspace` therefore reduces
  to **`task_id is not None`** for the whole comparison.
- An entry that names a task (`entry.task_id`) takes that task's checkout. An entry that names a
  review (`entry.review_task_id`) takes the review checkout, which is resolved before this branch is
  ever reached and never touches the agent worktree. Either one counts.
- An entry naming neither still takes a task checkout when **its conversation** is already bound to
  one — `resolve_bound_task` falls through to `binding_for_conversation`, which reads
  `Conversation.task_id`. So a plain follow-up in a thread about a task runs in that task's checkout.
  Omitting this half would hold input that could have run: less harmful than destroying it, but still
  a breach of the requirement's second paragraph. One query over the distinct conversation ids of the
  remaining entries answers it.
- **Entries inside `selected` are excluded**, and not merely for tidiness. If any of them named a
  live task, `binding_from_entries` would have bound the turn to it and `resolve_turn_workspace`
  would have taken the task arm — so a task-named entry surviving inside `selected` is one whose task
  was deleted or decided (`resolve_bound_task` drops the binding, F79), which resolves to no task on
  the next schedule too. Counting it as "could have run elsewhere" would be counting an entry that
  will fail here identically.

The whole test runs only on the refusal path, and only for this one classification.

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
- **Two conversation reads on a refusal path.** Only on this classification, only when other entries
  exist, and one query for all of them.
- **The behaviour is inferred, not driven, at HEAD.** Task 1 reproduces it before anything changes,
  and says to stop if it does not reproduce.

## Migration Plan

None. No schema, no persisted field, no API shape.

## Open Questions

None for the operator. The one judgement this change makes that is worth their disagreement is D3's
scope test — whether "something else could have run" is worth computing at all, against simply
holding everything (D4). It is written up rather than asked because the shipped requirement already
answers it.
