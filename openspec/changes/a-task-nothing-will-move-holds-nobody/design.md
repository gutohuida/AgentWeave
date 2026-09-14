# Design — a task nothing will move holds nobody

## Context

`_agents_that_are_free` (`hub/hub/scheduler.py:1022-1090`) is the pool every flow draws from. An
agent is free when it passes three tests:

1. **Not running.** It has no `Run` in `running`, and since `a-spent-allowance-holds-the-queue` D6
   (`c8e3bbd`, archived `4b362f3`) it is not held by a usage refusal (`:1053-1061`).
2. **Holding nothing.** It is not the assignee of any task in `LIVE_STATUSES`, anywhere in the
   project (`:1062-1074`).
3. **On the roster and startable.** It is not archived and has a runner bound (`:1075-1089`).

This change moves only the second test. The first is today's work and is not touched. The third is
`agent-flows` *"A firing determines both the task and the agent"* and is not touched either.

The second test was designed as `loop-becomes-a-flow` D4, which rejected *not running* alone because
*"an agent can hold three assigned tasks and be idle between turns, which is the pile-up the
operator named"*. That argument is right about a queue something will serve. It is wrong about a
queue nothing will serve, and the code cannot tell the two apart. `_loop_candidates`
(`:692-729`) walks only `Task.loop_id == loop.id`. So a task with no `loop_id`, or whose loop has
ended, is never reached by any firing, and its assignee is withdrawn from every flow in the project
until someone other than a flow moves it.

The three callers:

| caller | line | question | what widening the pool does there |
|---|---|---|---|
| `_loop_flow_busy_reason` | `:306` | the job's agent is busy: is anyone else free? | a firing that was refused outright proceeds to the walk |
| `resolve_reviewer` rung 2 | `:1187` | who reviews this, when nobody is declared? | a bookmark-holder can be the reviewer |
| `decide_firing` | `:1368` | who takes fresh work past the default agent? | a bookmark-holder can take it |

The guard has three callers of its own: the firing (`:2629`), the board's stall line
(`api/v1/jobs.py:355`), and `POST /jobs/{id}/run`'s 409 (`api/v1/jobs.py:1350`). All of them read
through the pool, so they move together with it.

`resolve_reviewer` has two callers of its own: `decide_firing` (`:1662`) and the divergence restaff
(`run_divergence.py:440`). The restaff re-resolves a review whose reviewer gave no verdict, and it
excludes that reviewer and the author. So a bookmark-holder can now also be the *replacement*
reviewer. That is the same question rung 2 answers, and it gets the same answer.

## Goals / Non-goals

**Goals.**
- An assigned task that nothing will ever move stops costing its assignee.
- A task something will move keeps holding its assignee, exactly as D4 intended.
- All three callers, and the guard's three readers, keep giving one answer.

**Non-goals.**
- Any of B to E in the proposal: owner, admission, amend trigger, non-blocking question.
- Rewording the rung-3 sentence (`an-unstaffed-review-names-its-holders`).
- Changing any task row, `LIVE_STATUSES`, or what the roster reports.
- F154's review nobody is doing, inside a live loop (D5, *Residual*).

## Decisions

### D1 — The test is reachability, not a status set

**An assigned task in a live status holds its assignee only while something will move it.** Two
things in the Hub move a task on their own:

- **A loop that has not ended.** Its firing walks every task carrying its `loop_id` in a live
  status. `_loop_candidates`' status set is `CLAIMABLE_LOOP_TASK_STATUSES +
  REVIEWABLE_LOOP_TASK_STATUSES + WITH_REVIEWER_LOOP_TASK_STATUSES`, and `LIVE_STATUSES` is exactly
  the agent-actionable and with-reviewer bands (`task_transitions.py:338`). So every live task in
  the loop is a candidate the walk sees. It may be gated, but it is seen.
- **A turn running or queued for the assignee, naming the task.** A running turn bound to it
  (`Run.task_id`), or a queued `InboundQueueEntry` whose `task_id` or `review_task_id` names it.
  The entry is delivered when the agent's hop budget, token budget or hold allows, and the turn
  then works the task.

**What does not move a task:**

- **The assignee field.** It is a record of who holds the task, and F154 already said so in
  `run_task_binding.py:270-293`.
- **Its status.** `pending` is a reservation, and `in_progress` with no turn is a record.
- **A plain scheduled job whose agent is the assignee.** Its entry names no task: the firing sets
  `task_id` and `review_task_id` only from a loop selection (`scheduler.py:2990-3001`), and a plain
  job has none.
- **An operator who might get round to it.** That is real, but it is the operator's gesture, and a
  gesture nobody has made yet cannot be a reason to withdraw an agent from every flow.

**Alternatives, in F352-free's own terms.** The stopped change lists (a) to (e).

- **(a), this loop only.** It frees an agent holding work in a *different* live loop. That loop
  will brief it on every tick, so the agent accumulates two queues. That is the pile-up D4 named,
  arriving across loops. (f) counts every loop that has not ended.
- **(b), `pending` does not hold.** It keys on status, which is the variable the exploration showed
  does not matter. An `in_progress` bookmark still ratchets.
- **(c), a turn running or queued.** It frees an agent between turns *inside* its own loop, which is
  exactly the case D4 rejected. (f) uses (c)'s test only outside loops.
- **(d), review asks a different question.** It is still status-keyed for new work, so a bookmark
  still costs the project its assignee for every new task. (f) and (d) are not exclusive, and (d)
  can still be layered on later.
- **(e), leave the rule.** LoopEngine.

### D2 — "A loop that has not ended" is `Loop.ending_state IS NULL`, and a paused loop holds

`Loop.ending_state` is *"the definitive stopped signal"* (`_authorize_loop_task_creation`'s
docstring, `tasks.py:621-627`). `loop_ending.end_loop` writes it on every ending path, together
with `job.enabled = False`. An ended loop cannot be revived: `toggle_job` refuses to re-enable one
(`jobs.py:857-868`), and D12 of `a-loop-writes-its-own-queue` *"explicitly rejects reviving the
stopped loop"*. So `ending_state IS NOT NULL` means *no firing will walk this loop again*, which is
exactly the fact D1 needs.

**A paused loop** (`AIJob.enabled = False`, `ending_state` NULL) **still holds.** The operator can
re-enable it at any time, and its firing will then brief the assignee on the task. Freeing that
agent for another flow meanwhile would give it a second queue that collides with the first on
resume. The cost is that a paused loop's agents stay unavailable to other flows while the pause
lasts. It is an operator gesture with a visible cause, and the operator can reverse it. **This is
the position in the proposal's OPERATOR QUESTION that the operator may want otherwise.** The
opposite choice is one clause in the query (`AIJob.enabled`), and task 1.4's test pins whichever is
chosen.

**`archived_at` needs no test of its own.** A loop archives only after it has ended (`models.py`'s
D17 comment, *"B2.3 refuses archiving a running loop"*), so every archived loop already fails
`ending_state IS NULL`.

**A `loop_id` naming no loop row holds nobody.** It is not supposed to exist, since `Task.loop_id`
is not a foreign key, but an outer join would read its missing `ending_state` as NULL, *not
ended*, and hold the agent forever. So the implementation reads the set of live loop ids and tests
membership, rather than outer-joining and testing the column (task 1.5 pins this). Loops are
scoped by `project_id` in the same read.

### D3 — One predicate, all three callers, and the guard moves with the walk

The pool stays one function, and all three callers read it. Each needs the change:

- **Rung 2** is LoopEngine's case. The review nobody could staff is staffed.
- **Fresh work.** A bookmark should not cost the project an agent for new work either. **This is
  not a new state for an agent.** `decide_firing`'s default arm already staffs the *job's own*
  agent while it holds active work (`:1525-1542`, tested against `running`, *"deliberately not
  against `free`"*). So *an agent with `in_progress` work elsewhere is given a loop task* is shipped
  behaviour for one agent per flow today. This extends it to agents whose holdings nothing will
  move.
  - A task's checkout is keyed by task (`run_task_binding.py:315-319`, design D8 of the worktrees
    change), so the new task gets its own worktree.
  - The loop's queued entry names its task (`scheduler.py:2997-3001`), so the turn binds to it,
    whatever the agent's conversation was bound to before.
  - The checkpoint briefing will list the agent's bookmarks among its live tasks
    (`checkpoints.py:_tasks_for`). That is information, not a conflict.
- **The guard** (`_loop_flow_busy_reason`) must agree with the walk. It refuses the whole firing
  when the job's agent is busy **and** `_agents_that_are_free` is empty (`:303-308`). If the guard
  kept the strict rule while the walk used (f), it would refuse firings the walk could staff: two
  answers to one question, the drift this module's comments record three times.

  **The consequence an operator sees.** A flow or loop whose job agent is mid-turn, in a project
  where another agent holds only bookmarks, used to be refused silently: no `JobRun`, and a 409
  from Run. It now proceeds to the walk and staffs that agent. This affects three readers:
  - **The firing** (`:2629`). It writes a `JobRun`, which is correct, because it did something.
  - **The board** (`jobs.py:355`). It asks the guard only when the decision is `stalled`, and the
    guard now answers `None` in more cases. So the walk's own stall reason shows instead, which is
    the truth.
  - **`POST /jobs/{id}/run`** (`jobs.py:1350`). It returns 409 only when the guard refuses. It now
    returns the firing's success where the walk staffs somebody.

  **A single-agent loop keeps its "records nothing" property.** Its one agent is the running one,
  so `running` excludes it whatever it holds, and the pool is empty unless the project has another
  free agent. That was already true before this change
  (`test_a_single_agent_loop_whose_agent_is_busy_still_records_nothing`).

  **A documentless loop can recruit from the pool today** (`:1543-1550` has no
  `spec_document_id` test). So this change also widens who a plain loop may recruit. No new kind of
  behaviour, and R2 should confirm that is wanted rather than incidental.

### D4 — The queued-turn arm is keyed to the assignee

A task outside every live loop holds its assignee when `on_it.get(task.id) == task.assignee`, where
`on_it` is `run_task_binding.tasks_with_a_turn_pending_or_running(session, project_id)`. It does not
hold merely because `task.id in on_it`.

- **Why the assignee's turn and nobody else's.** If input naming the task is queued for a
  *different* agent, that agent will work the task, and the assignee will not be moved by it. The
  question D1 asks is *will this agent be kept busy by this task*, not *is anybody on this task*.
- **Why reuse the F154 helper.** Its docstring warns that `tasks_held_by_a_running_turn` already has
  two callers asking two questions, and that a third query answering the same fact is the drift
  shape. This is the helper's third caller, but it asks the helper's own question (*is anybody on
  this task, counting a turn not yet started*) and narrows the answer to the assignee. It does not
  ask a new question of the same rows.
- **Where a running turn wins.** The helper returns `{**pending, **held}`, so a running turn wins
  over a queued entry for a different agent. That matters only for a task two agents are both on,
  and such a task's assignee is either the running agent (already excluded by `running`) or neither.

**Why the arm exists at all, when a running assignee is excluded by `running` anyway.** The arm
earns its place only for a *queued* turn:
- The operator's message to `dev` about a free-floating task sits queued behind a spent hop budget.
- The task's assignee is held by a usage refusal, but `agents_held` already excludes held agents
  through `running`.

In the first case, freeing `dev` for a flow queues the flow's briefing behind the operator's. That
is the pile-up in miniature, and the arm prevents it. Task 1.6 pins the arm, and task 1.7 pins the
assignee narrowing.

### D5 — Residuals, named and not closed

- **F154's review nobody is doing, inside a live loop.** The Architect's `under_review` task on
  LoopEngine is in the loop, and the walk records it as in flight and unstaffed. Nothing moves it
  except the reviewer's turn, which is not happening, or the operator's three exits. Strictly, D1's
  question answers *nothing will move it*. But the walk does reach it every tick, surfacing it by
  name as F154 requires, so it is not invisible in the way a bookmark is. Freeing its reviewer is
  option (d)'s territory, an operator question about reviews specifically, and it stays out.
  **Consequence on LoopEngine:** the Architect stays held after this change. `dev` and `dev_2`
  become free.
- **A task in a live loop that its dependency gate refuses indefinitely** still holds. The gate
  names what it waits on, and the operator reversing a rejection revives it (`agent-loops`,
  *"Reversing a rejection revives the loop"*). It is reachable in principle.
- **The roster and the pool now differ on purpose.** `_agents_that_are_free`'s docstring
  (`:1031-1033`) claims the pool reads *"the same `LIVE_STATUSES` the roster's own 'active task'
  derivation reads, so a third opinion about whether an agent is busy cannot appear here"*. After
  this change that sentence is false and must be rewritten (task 1.8). The roster
  (`api/v1/agents.py:438-446`) answers *what does this agent hold*, which is still every live task.
  The pool answers *may a flow give this agent work*. They were never the same question.
  `task-lifecycle-governance`'s prose at `:406`, *"its assignee counts as holding active work"*, is
  about a task inside a flow, which still holds, so it stays true.

### D6 — Shape of the code

```
running  = (agents with a Run in `running`) | agents_held(...)            # unchanged
live     = {Loop.id : Loop.project_id == P, Loop.ending_state IS NULL}    # one query
on_it    = await tasks_with_a_turn_pending_or_running(session, P)        # F154's helper
rows     = (Task.id, Task.assignee, Task.loop_id)
           where project == P, assignee NOT NULL, status IN LIVE_STATUSES
holding  = {assignee for id, assignee, loop_id in rows
            if loop_id in live or on_it.get(id) == assignee}
roster   = ...                                                            # unchanged
return [name for name in roster if name not in running and name not in holding]
```

The signature does not change. It still returns `list[str]` in name order, so the three callers and
the existing ordering test are untouched.

**Cost.** The change adds one query (`live`) and the helper's two queries (`tasks_held_by_a_running_turn`
and the queued entries) to each call. `resolve_reviewer` calls the pool once per reviewable
candidate, so a wide firing pays this per review. Every query is bounded by the roster or by open
work, not by history. Hoisting the pool out of `resolve_reviewer` would change its signature at
both of its call sites (`scheduler.py:1662`, `run_divergence.py:440`), so it is left for a change
that needs it.

**Why not a separate helper returning `agent -> [task ids]`**, which the stopped change's rung-3
rewrite will want in order to name holdings. That change must be re-derived against (f) first. A
helper shaped for its sentence now would be designed against a requirement that does not exist. The
set comprehension above is one expression and easy to lift out when it does.

### D7 — Tests that encode the old rule

`test_reviewer_ladder.py::test_an_agent_holding_an_active_task_is_not_selected` stages the holding
task with **no `loop_id`**. Under D1 that is a bookmark. `aa-loaded` sorts first and would now be
selected, so the test fails against the new code, **correctly**: it asserts exactly the behaviour
this change removes.

Its point, D4's pile-up, is still true inside a loop. So it is re-staged, not deleted:
- The holding task gets a live loop (task 2.1).
- A sibling stages the same task outside any loop and asserts the opposite (task 2.2).

Any other test that fails because it staged a holding with no `loop_id` is handled the same way.
The implementation lists each in the log, with why re-staging preserves its point (task 2.3).
Weakening an assertion to make it pass is not an option.

## Risks

- **An operator's deliberate out-of-loop assignment no longer reserves the agent.** An operator who
  assigned `dev` a free-floating task *meaning* "keep dev for this" now finds that a flow may staff
  `dev` meanwhile. The reservation was never expressible (there is no reserve gesture), and it
  worked only as a side effect of the ratchet. The operator's own message to `dev` about the task,
  once queued, does hold `dev` (D4).
- **More firings proceed where they used to be refused silently** (D3). Each writes a `JobRun`, and
  `_prune_job_history` keeps 100. It is bounded, since a firing proceeds only when it can staff
  somebody or has something to say.
- **LoopEngine unfreezes on the operator's next `:8000` restart.** The first firings after it may
  staff `dev` and `dev_2` for reviews and new work in parallel. That is the loop working, but it
  spends allowance at once, on the day the weekly rate-limit window started to matter. The review
  page for 2026-09-15 should say so.

## Test plan

See `tasks.md` and `test-guide.md`. Every test has a named mutation that must make it fail. The drive
reproduces the LoopEngine shape on a fresh drive Hub: a flow, a finished task by one agent, and the
other agents holding out-of-loop tasks. It shows the review staffed.
