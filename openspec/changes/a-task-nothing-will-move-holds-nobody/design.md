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
  (`Run.task_id`), or a queued `InboundQueueEntry` for the assignee whose `task_id` or
  `review_task_id` names it, **within the project's hop budget** (Round 2). The entry is delivered
  once the agent is no longer running or held and the token budget allows, and that turn then works
  the task.

  R1 wrote *"when the agent's hop budget … allows"*. That is false. A hop budget is a project
  constant, not something that refills. `_attempt_turn` never selects an entry past it
  (`turn_scheduler.py:361-371`, `entry.hop_depth <= hop_budget`). Such an entry is delivered only if
  the operator releases it (`inbound_queue.release_entry`, `:291-318`, which re-bases it to depth 0).
  So it is *"an operator who might get round to it"*, the case the list below says does not move a
  task. See D4.

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

### D2 — "A loop that has not ended" is `Loop.ending_state IS NULL AND Loop.archived_at IS NULL`, and a paused loop holds

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

**An archived loop holds nobody either, and it needs its own test** (Round 2; R1 said it needed
none). R1's argument was that *"a loop archives only after it has ended"*, citing `models.py`'s D17
comment. That is true of `POST /loops/{id}/archive` (`api/v1/loops.py:176`, which refuses
`ending_state IS NULL`). It is **false** of the other route. `POST /jobs/{id}/archive`
(`api/v1/jobs.py:1124-1200`) is the product's only way to retire a *job*. The operator's call to it
on a job with a loop sets `job.enabled = False` and `loop.archived_at`, and leaves `ending_state`
NULL. Its own docstring says so: the operator's path *"does not require the loop to have ended
first"*. **Measured in R2** through the test client: the archive answered 200, and the loop row read
`ending_state None` with `archived_at` set.

Under R1's rule such a loop is "paused", so its tasks hold their assignees forever. The loop
causing it is also hidden from the default listing (`jobs.py:774`, `loops.py:126`). That is the
worst form of the ratchet, because the operator retired the work and cannot see what still holds
their agents. So `live` also requires `Loop.archived_at IS NULL`. One clause covers both routes:
the job route stamps the loop too (`jobs.py:1199-1200`).

**Can an archived loop come back, as a paused one can?** Only through a defect. The same R2
measurement re-enabled the archived job with `PATCH {"enabled": true}` and got **200**. That is
**F222** (B, open): the UI never lists an archived job with an enable control, and the finding
itself calls it *"the exact governance failure loops exist to make impossible"*. Suppose someone
takes that path anyway. The revived loop's tasks are walked again, and their assignees may have
been given other work in the meantime. That is D2's pile-up, reached only through an open defect,
and it is not a reason to hold agents for every archived loop.

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

  **Round 2: it is neither wanted nor incidental. It is F128, which is the operator's open
  decision, and this change widens where it fires.** F128 (B, open since 2026-08-29): *"a loop runs
  on an agent its job does not name, whenever its own agent is busy"*. Its mechanism is exactly the
  guard above. `_agents_that_are_free` is project-scoped, so in a multi-agent project a loop naming
  one agent is not single-agent as far as the guard can tell. The invariant R1 restated two
  paragraphs up, *"a single-agent loop keeps its 'records nothing' property"*, holds only in a
  project with **no other free agent**. F128 is *"filed, not fixed"*. It poses one decision with two
  shapes, and the operator has not made it: make the free list loop-scoped, or stop presenting
  `job.agent` as who runs the loop. (`agent-flows`' first requirement says a documentless loop
  *"fires the job's own agent, as before"*. F128 is how the shipped code already departs from it.)

  What this change does to F128: until now, a sibling holding any live task shielded the loop from
  substitution. After it, only a sibling holding *reachable* work does. In a LoopEngine-shaped
  project, where every sibling holds bookmarks, F128 could not fire before and can after. For
  example, a plain loop whose agent is mid-turn now hands its next pending task to `dev`.

  **R2's position: proceed, and do not decide F128 here.** Scoping the pool per loop is F128's
  first shape. Choosing it inside this change would take the operator's open decision for them.
  Keeping the strict rule for documentless loops alone would mean two definitions of "free", the
  drift D3 exists to prevent. F128's substitution already reaches every multi-agent project with
  one unencumbered sibling, and this change adds projects to that set without adding a new
  behaviour. It is carried to `decisions_for_user`, it is named in the proposal's operator-visible
  behaviour, and F128's entry gets a dated note at archive (task 5.6).

### D4 — The queued-turn arm is keyed to the (task, assignee) pair, within the hop budget

*Rewritten in Round 2. R1's version read the F154 helper and narrowed its answer. R2 found that the
helper's answer cannot be narrowed that way, and that it counts input nothing will deliver.*

A task outside every live loop holds its assignee when `(task.id, task.assignee)` is in `queued`.
`queued` is the set of `(task, agent)` pairs from the `InboundQueueEntry` rows that are all of:
- in the project;
- in `state == "queued"`;
- `hop_depth <= Project.hop_budget`;
- naming the task by `task_id` or `review_task_id`.

It is read by a new function in `run_task_binding.py`, beside the F154 helper (task 1.1a).

- **Why the assignee's turn and nobody else's** (R1, kept). If input naming the task is queued for
  a *different* agent, that agent will work the task, and the assignee will not be moved by it. The
  question D1 asks is *will this agent be kept busy by this task*, not *is anybody on this task*.
- **Why not narrow `tasks_with_a_turn_pending_or_running`, as R1 did.** The helper answers
  `task_id -> one agent`. It builds the pending half with `pending.setdefault(candidate, agent)`
  over an unordered select (`run_task_binding.py:296-307`), so where two agents have input naming
  one task, the helper keeps whichever row comes back first and drops the other.
  **Measured in R2** by staging the task assigned to `dev`, a job entry for `dev` naming it, and a
  hop-7 peer entry for another agent naming it, in both insertion orders:
  - the other agent named `alpha`: `{'task-probe': 'alpha'}`, in both orders;
  - the other agent named `zeta`: `{'task-probe': 'dev'}`, in both orders.

  The rows come back in agent-name order. So `on_it.get(task.id) == assignee` answers *no* whenever
  any agent whose name sorts before the assignee has input naming the task. An agent reporting on
  its own task to an `architect` produces exactly that. The fact the arm needs is a pair, and the
  map has already thrown half of it away.
- **Why the hop-budget bound.** See D1. An entry past the budget is delivered only by the
  operator's release. Counting it would re-create the ratchet this change removes, one table over.
  LoopEngine is the case. F361 records 20 peer chains suspended at hop 7 against a budget of 6,
  still `queued` 2–13 hours later, and **8 of them sent by the Architect**. These are the
  proposal's Q6 *"eight suspended messages"*. `send_message` carries an optional `task_id`
  (`mcp_server.py:209`), and `create_message` copies it onto the entry (`messages.py:263-267`).
  So if those messages named the tasks their recipients hold, then under R1's arm they would hold
  `dev` and `dev_2` permanently, and **LoopEngine would not unfreeze**. R2 cannot read `:8000` to
  say whether they do. Under this rule the answer does not matter.
- **Why a second function rather than widening the F154 helper.** The two ask different questions:
  - The helper asks *is anybody on this task*. Its one reader is the wedged-review test (`:1454`),
    where any agent counts.
  - The pool asks *will input already queued for this agent move it onto this task*. That is
    pair-keyed and bounded by the budget.

  Widening the helper would change F154's answer as a side effect. Whether F154's answer is right
  about input past the budget, or input for a third agent, is its own question, filed as **F371**.
  The new function's docstring says all this and names the helper.
- **The running half is not read.** A running assignee is excluded wholesale by `running`, so a
  running turn bound to the task adds nothing to the pool's answer. The requirement still states
  it, so the rule reads the same whichever half is true.

**Where the arm earns its place.** It applies only to an assignee that is neither running nor held,
with input naming the task queued within the budget. Four cases:
- the project's token budget is spent, so `_attempt_turn` holds autonomous input
  (`turn_scheduler.py:395`);
- the controlling entry's conversation is unavailable;
- a delivery is being retried after a failed run;
- the moment between the entry being written and `schedule_agent` starting the run.

In each case, freeing the agent for a flow queues the flow's briefing behind input already waiting.
That is the pile-up in miniature, and it is F368's shape.

R1's motivating example was *"the operator's message to `dev` … queued behind a spent hop budget"*.
That cannot happen. An operator's trigger is queued at `hop_depth=0` (`agent_trigger.py:1499`),
and so is every job, checkpoint, question and divergence entry. Only peer messages can be past
the budget (`messages.py:57-70`, `agents.py:2117`).

The tests:
- task 1.6 pins the arm;
- task 1.6b pins the budget bound;
- task 1.7 pins the narrowing to the assignee;
- task 1.7b pins the pair against the masking measured above.

**The same masking is live in shipped code, and this change does not repair it there.** The
held-resume arm of `decide_firing` (`:1506`, `a-spent-allowance-holds-the-queue` D6, shipped
`c8e3bbd`) asks `on_it.get(task.id) == agent`. Take a held assignee with its own briefing queued
while another agent whose name sorts first has input naming the same task. That arm judges the
briefing absent and re-briefs on every firing for the length of the hold: F368's held instance,
back. Filed as **F370**.

It is not folded in here. That arm asks a third question, *is a copy of this briefing already
waiting*, so its right filter is the pair **without** the budget bound: a suspended copy still is a
copy. Its requirement shipped today and this change does not modify it. The repair is one line once
this change's function exists, and F370 says so.

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
- **Queued input that is within budget and still never delivered** (Round 2) holds its assignee.
  Two examples: a controlling entry whose conversation was closed (`_attempt_turn` answers
  *"conversation is unavailable"*, `turn_scheduler.py:343-350`), and a project token budget that
  nothing resets. The hop budget is the one bound this change reads, because it is the one the
  product itself documents as waiting on the operator (`release_entry`) and the one LoopEngine is
  actually hitting (F361). Chasing every reason a queue can stall would restate `_attempt_turn` in
  a second place, which is the drift shape.
- **A live loop that cannot fire for a reason of its own** holds its tasks' assignees. A loop whose
  job agent was archived, or whose runner was unbound, is one example. It is a loop the operator can
  see and repair, like the paused one in D2.
- **The held requirement's closing sentence** (`agent-flows`, *"A flow treats an agent whose queue
  is held as unable to take a turn"*: *"Which tasks an agent holds, and which of them make it
  unavailable, is unchanged"*) is left as it is (Round 2). It scopes *that* requirement, and it is
  still true of it. The new requirement is now where the answer lives. Modifying the held
  requirement to add a cross-reference would archive a whole second requirement to change nothing
  it says.

### D6 — Shape of the code

*Round 2: `live` gains the `archived_at` clause (D2), and the queued arm reads pairs within the
hop budget from a new function in place of the F154 helper (D4).*

```
running  = (agents with a Run in `running`) | agents_held(...)            # unchanged
live     = {Loop.id : Loop.project_id == P,
                      Loop.ending_state IS NULL, Loop.archived_at IS NULL} # one query
queued   = await task_agent_pairs_with_a_turn_queued(session, P)         # run_task_binding, new:
           # {(task_id or review_task_id, agent)} over InboundQueueEntry rows with
           # project == P, state == "queued", hop_depth <= Project.hop_budget, agent NOT NULL
rows     = (Task.id, Task.assignee, Task.loop_id)
           where project == P, assignee NOT NULL, status IN LIVE_STATUSES
holding  = {assignee for id, assignee, loop_id in rows
            if loop_id in live or (id, assignee) in queued}
roster   = ...                                                            # unchanged
return [name for name in roster if name not in running and name not in holding]
```

The signature does not change. It still returns `list[str]` in name order, so the three callers and
the existing ordering test are untouched.

**Cost.** The change adds up to three queries to each call: `live`, the project's `hop_budget`
(`inbound_queue.project_limits`, the reader `_attempt_turn` uses, so the two cannot disagree about
which budget applies), and the queued entries. R1's count of three assumed the F154 helper, whose
running half the pool does not need (D4). `resolve_reviewer` calls the pool once per reviewable
candidate, so a wide firing pays this per review. Every query is bounded by the roster or by open
work, not by history. Hoisting the pool out of `resolve_reviewer` would change its signature at
both of its call sites (`scheduler.py:1662`, `run_divergence.py:440`), so it is left for a change
that needs it.

**`project_limits` raises for a missing project** (`inbound_queue.py:71-75`). Every caller of the
pool is scoped to a project that exists, and `_attempt_turn` makes the same call on the same
grounds, so the pool does not guard it. R3 should confirm that no caller reaches the pool with a
`project_id` naming no row. For example: the board batch, and a loop whose project was deleted.

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

  **Round 2: "has something to say" includes a sentence that is true at the tick and gone at the
  next.** The guard asks *is anyone free*, not *can anyone free take this loop's work*. Suppose the
  job's agent is mid-turn and the only other free agent is the author of a completed task. The
  firing now proceeds, finds that review unstaffable, and calls `_emit_review_unstaffed` before any
  refusal (`scheduler.py:2825-2828`). Before this change, a bookmark on that author refused the
  firing silently, and the job's agent could have taken the review once its turn ended. Two
  things bound this:
  - It is shipped behaviour already, wherever the free author holds nothing at all.
  - A continuing stall counts in place (`_stall_run_to_increment`). A repeated `review_unstaffed`
    is F365's territory, not this change's.

  So it is not a new behaviour, but it reaches more projects. R3 should weigh whether the
  `test-guide.md` human check needs to name it.
- **F128's substitution reaches more projects** (D3, Round 2). A plain loop whose agent is mid-turn
  can now hand its next pending task to a sibling that holds only bookmarks. This is the operator's
  open decision, and it is carried to `decisions_for_user`.
- **LoopEngine unfreezes on the operator's next `:8000` restart.** The first firings after it may
  staff `dev` and `dev_2` for reviews and new work in parallel. That is the loop working, but it
  spends allowance at once, on the day the weekly rate-limit window started to matter. The review
  page for 2026-09-15 should say so.

## Test plan

See `tasks.md` and `test-guide.md`. Every test has a named mutation that must make it fail. The drive
reproduces the LoopEngine shape on a fresh drive Hub: a flow, a finished task by one agent, and the
other agents holding out-of-loop tasks. It shows the review staffed.

## Round 2 — first review, night of 2026-09-14/15

R2 re-derived D1 to D7 from the code, reading the code R1 cited and the code its argument depends
on without citing it: the queue writers (`new_entry`'s nine callers), `_attempt_turn`,
`release_entry`, both archive routes, the firing's persist and discard paths, and F128, F222, F361
and F368 in the ledger. It ran three measurements through throwaway tests, each deleted before the
commit: the archive route, the F154 helper's answer, and the status sets.

**What R2 found wrong, and repaired:**

1. **An archived loop held its agents forever (D2).** R1's premise, *"a loop archives only after it
   has ended"*, holds for `POST /loops/{id}/archive` and not for `POST /jobs/{id}/archive`. The
   operator's call to the job route archives a looping job with `ending_state` still NULL. That was
   measured, and the same measurement re-enabled it through PATCH, which is F222. `live` now also
   requires `archived_at IS NULL`. Task 1.5 gets a fourth case, and the delta a scenario.
2. **The queued arm counted input nothing will deliver (D1, D4).** An entry past the hop budget is
   never selected by `_attempt_turn`. Only the operator's release delivers it. R1's D1 said the
   budget "allows" delivery later, which is false. LoopEngine's Q6 messages are exactly such
   entries (F361: hop 7 against a budget of 6). If they named their recipients' tasks, R1's arm
   would have kept `dev` and `dev_2` held, and **the change would have failed at the one board it
   exists for.** The arm is now bounded by the budget. Task 1.6b, and a scenario.
3. **The queued arm read a map that had already dropped the answer (D4).** The F154 helper keeps
   one agent per task, and the measured row order is by agent name. So an assignee's own queued
   input is hidden by any agent whose name sorts first. The arm now reads `(task, agent)` pairs
   from a new function. Task 1.1a and task 1.7b, and a scenario.
4. **R1's motivating example for the arm could not happen (D4).** An operator's input is queued at
   hop 0 and cannot be over budget. The arm's real cases are restated.
5. **The documentless-loop widening is F128 (D3).** R1 asked whether it was wanted or incidental.
   It is the operator's open decision, and this change widens where it fires. R2 proceeds without
   deciding it and carries it to `decisions_for_user`, with reasons (D3).
6. **"A busy agent is not selected" was narrowed wrongly in the delta.** It named only a task in a
   live loop, so it silently dropped the queued-input half of *holding*. It now defers to the new
   requirement's definition.

**What R2 checked and kept:**
- **D1's status argument.** `LIVE_STATUSES` minus the walk's status set is empty (measured).
- **The waiting run.** A run suspended on `ask_user` is still `running`
  (`test_the_agent_whose_run_is_waiting_is_not_free`), so *"has a live run"* is already the
  `running` half and needs nothing in the new one.
- **D2's pause position**, unchanged and still flagged.
- **D3's guard argument.** R2 added a correction to R1's Risk: a proceeding firing may only surface
  a `review_unstaffed` that is true at the tick and would clear when the job agent's turn ends.
  This is shipped behaviour wherever a free author exists, and it now reaches more projects.
- **D5's F154 residual**, and the reading of `task-lifecycle-governance:406`.
- **D7**, confirmed in the source: the ladder test stages `task-held` with no `loop_id`.
- **The MODIFIED block**, diffed against `openspec/specs/agent-flows/spec.md:231-349`. The only
  differences are the rung-2 clause, the two busy-agent scenarios and the one added scenario.

**Findings filed against shipped code:**
- **F370 (B).** The held-resume arm (`:1506`, shipped `c8e3bbd`) has the same masking as item 3,
  so a held assignee is re-briefed on every firing when another agent whose name sorts first has
  input naming its task. Measured at the helper; the consequence at the arm is by reading.
- **F371 (C).** F154's wedged-review reader (`:1454`) counts any agent's queued input naming the
  task as attendance, including a peer message past the budget. So a review nobody is doing can
  read as attended. By reading.

**Left for R3:**
- **The F108 question, for real.** What do `POST /jobs/{id}/run`, the loops board and
  `review_unstaffed` say in the new cases? In particular, when the guard passes and the walk
  proceeds to `DECISION_IN_FLIGHT` or to an unstaffed-only decision.
- **`project_limits`' raise** for a missing project, at every pool caller (D6).
- **Whether each named mutation can fire**, especially 1.7b's. It depends on the helper's row order,
  which R2 measured on SQLite. A mutation that reverts to `on_it.get(...)` must fail, so the test
  must name the other agent to sort *before* the assignee.
