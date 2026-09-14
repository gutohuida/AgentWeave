# Design — an unstaffed review names its holders

R1, 2026-09-14. Line numbers are at `2d5674c`. R2, 2026-09-14, re-derived at `e8ea490`: every
decision it changed is marked **R2**, and *Round 2* at the end lists what changed and why.

## Context

Rung 3 of the reviewer ladder is the only thing an operator is shown when a flow cannot staff a
review. The facts behind it are computed on the same call: who is running, and who holds which task
in a live status (`_agents_that_are_free`, `scheduler.py:977-1040`). The ladder discards them
(`scheduler.py:1136-1168`) and returns a sentence written for the general case. The sentence then
travels, unchanged, to three places:

| where | how | what the operator sees |
|---|---|---|
| `FiringDecision.unstaffed` → `stall_reason` (`scheduler.py:1655`) | F64's promotion of `unstaffed[0][1]` | the loop board's amber line, one line, CSS `truncate`, no tooltip (`LoopsIndexTab.tsx:237-244`) |
| `JobRun.error_summary` (`scheduler.py:2762`) | the stall row, incremented while equal (`:923`) | the run history |
| `review_unstaffed` event (`scheduler.py:1944-1995`) | persisted and broadcast, once per fact (`:1978`) | the activity feed, `no agent could review <task>: <reason>` (`eventSummary.ts:79-80`) |

The divergence restaff (`run_divergence.py:440-451`) calls the same ladder and surfaces the same
`choice.reason`.

## Decisions

### D1 — one availability read, two consumers

`_agents_that_are_free` becomes a projection of a new `_roster_availability(session, project_id)`,
which returns one record per **non-archived** agent in name order:

```
AgentAvailability(name, has_runner: bool, running: bool, holdings: tuple[(task_id, status), ...])
```

The record is built from the same three queries the function runs today:
- `Run.status == "running"`;
- `Task.assignee` over `LIVE_STATUSES`, now selecting `Task.id` and `Task.status` too, with holdings
  ordered by task id;
- the roster, now **without** the `runner_id IS NOT NULL` filter, which moves into the projection.

The pool is `[a.name for a in availability if a.has_runner and not a.running and not a.holdings]`.
That is the predicate the function has today, and `agent-flows` states it. **No agent enters or
leaves the pool because of this change**, and the existing ladder, width and busy-guard tests are
the proof that it does not.

*Why one read:* the function's own docstring argues that *"a third opinion about whether an agent
is busy cannot appear here"*. A sentence built from a second query would be exactly that third
opinion, able to name an agent the pool thought free. *Rejected:* building the sentence at the call
site from `decide_firing`'s precomputed `free` and `running`. The divergence restaff has neither
precomputed, so it would need its own copy.

**R2: three callers, and one read per ladder.** The projection has three callers, not two:
`_loop_flow_busy_reason` (`scheduler.py:298`), `decide_firing`'s pool (`:1298`), and rung 2
(`:1137`). All three keep the projection unchanged. Inside `resolve_reviewer`, the read must happen
**once**. Rung 2 walks the projection of the records, and rung 3 describes the same records. Calling
`_agents_that_are_free` for rung 2 and then `_roster_availability` for rung 3 would be two reads, the
third opinion this decision exists to prevent.

**R2: an empty roster says so.** Rung 3 is reachable with no record at all: a project whose agents
are all archived, or that has none. The clauses are then empty, and the sentence says *"the project
has no agent on its roster"* in their place, before the remedy.

### D2 — what rung 3 says, and in what order

For each record, the **first** of these that holds becomes that agent's clause:

1. **excluded** — `"{name} {clause}"`, where the clause is the caller's reason for this agent (D3);
2. **no runner** — `"{name} has no runner bound"`;
3. **holds** — `"{name} holds {id} ({status})"`, listing up to three held tasks and then
   `"and N more"`;
4. **running** — `"{name} is running a turn"`.

Clauses are in name order. The pool is empty by construction at rung 3, so every record matches
one of the four.

The order is chosen for the operator, not for the code. Exclusion is a fact about this task and
outlasts everything else, so it wins. An agent with no runner can never be staffed, so that fact
comes before any holding. Holdings are the standing cause, and F352's whole finding is about them.
Running comes last because it is transient, and an agent mid-turn usually holds the task it is
working on, so it is named by that task instead. That choice also keeps the reason stable across
ticks (D4). A reason naming whoever is mid-turn would change on every turn boundary, and each change
is recorded as news.

**The sentence leads with the names.** It is `could not staff this step: nobody is free. ` followed
immediately by the clauses, then the remedy. It has no general sentence before the names, because
the board shows about 80 characters of it.

**The remedy depends on the task's status.** Rung 3 is reached for `completed` tasks, and for
`under_review` rows the F70 recovery and the divergence restaff carry to the ladder. **One helper,
`own_review_remedy(task)`, writes it**, and D5's dispatch refusal calls the same helper (R2). It is
public, without a leading underscore, because `agent_trigger` imports it from `scheduler`. That is
the rule `enter_selected_task`'s docstring states for the same situation.
- **`completed`:** *Land it, on the task, to review it yourself*. This is F163's action, in the
  drawer for exactly this status (`TaskDetailDrawer.tsx:345`).
- **`under_review`:** *decide it yourself: approve, reject, or send it back with revision_needed*.
  `land` refuses `under_review` with a 409 (`tasks.py:1519-1530`), so naming Land it there would
  name an action that refuses.
- **Both:** *rejecting a held task that is no longer wanted frees its agent*. The operator can take
  `rejected` from every status that holds an agent. `LIVE_STATUSES` is pending, assigned,
  in_progress, revision_needed and under_review (`task_transitions.py:218-228, 338`), and each has
  an operator `rejected` edge (`:100-146`). That is what freed `tester` on LoopEngine at 22:33.

**R2: the `completed` remedy does not promise an approval.** R1 wrote *"Land it, on the task,
approves it"*. That is false in the common case.
- `land_task` evaluates the approval gate before it moves anything (`tasks.py:1543-1545`).
- `_check_unaccepted` (`requirement_gate.py:493-541`) refuses when evidence naming a commit is still
  waiting to be judged and nothing else would merge. It is rigor-independent.
- A task at rung 3 has evidence naming a commit **by construction**: the arm refuses anything else
  first (`scheduler.py:1538-1548`).
- A flow's review is usually what would judge that evidence. So on a repository project with a main
  branch, Land it refuses with *accept or grant* until someone decides the evidence.
- LoopEngine's two landings at 22:33 worked only because every piece of their evidence had already
  been decided. Read mode=ro: `task-611ae46fe0fb` had 1 accepted and 2 rejected, and
  `task-c8d4a3d70c19` had 3 accepted, all decided by `tester` at 21:21 and 21:41 without moving
  either task.

*"To review it yourself"* is true either way. The drawer renders a gate refusal where the button
is (`TaskDetailDrawer.tsx:335-369`), naming what approval still needs.

*Rejected:* a structured `holders` field on the event beside the sentence. The board renders
`stall_reason`, a string, and a second field would give two accounts of one fact. The sentence is
what every surface already carries.

**Length: the sentence is bounded, because one route would fail on it.** `JobRun.error_summary` is
declared `String(500)` (`models.py:1349`), and SQLite does not enforce that. **The response does:**
`JobRunResponse.error_summary` is `Field(max_length=500)` (`schemas/jobs.py:88`), and
`GET /jobs/{job_id}/history` answers `List[JobRunResponse]` (`api/v1/jobs.py:1197`). A stall reason
longer than 500 characters would be stored without complaint, and it would turn the job's history
route into a response-validation 500 for as long as that row is among the rows it returns. With
four agents and three holdings each, D2's sentence reaches that length. So:

- **Rung 3 builds within 500 characters.** If the whole sentence fits, it is used. Otherwise
  clauses are added in name order while prefix, clauses, the tail
  `"; and N more agents are excluded, busy or unbound"` and the remedy still fit. The remedy is
  always kept. The result is deterministic and is the same string on every surface.
- **R2, measured budget** (`%TEMP%\f352r2\len3.py`):

  | piece | characters |
  |---|---|
  | prefix `could not staff this step: nobody is free. ` | 43 |
  | `completed` remedy | 109 |
  | `under_review` remedy | 139 |
  | tail | 50 at most |
  | clause budget with a tail, `completed` / `under_review` | 297 / 267 |
  | widest single clause (a 32-character name, three held `revision_needed` tasks, "and 2 more") | 159 |
  | LoopEngine's four agents, as `completed` / as `under_review` | 459 / 489 |
  | task 2.6's shape | 402 |

  So at least one agent is always named, and LoopEngine's whole roster is named. **R1's wording
  would not have named it.** With an honest remedy in R1's phrasing
  (*"…approves it or says what approval still needs. Rejecting a task an agent holds…"*), the
  LoopEngine sentence measures 514, and `tester` would have collapsed into the count. R1's 483
  fitted only because its remedy promised the approval above.
- **Every `JobRun.error_summary` write is fitted to the column (R2: at the model, not at two call
  sites).** The column is `String(500)` (`models.py:1349`), SQLite does not enforce it, and
  `JobRunResponse` does (`schemas/jobs.py:88`). R2 confirmed the mechanism with the real schema
  class (`%TEMP%\f352r2\route.py`): a `response_model=List[JobRunResponse]` route answers 200 at
  500 characters and **500 at 501**.
  - One constant, `JOB_RUN_ERROR_SUMMARY_CHARS = 500`, beside `JobRun`, is read by the column, by
    the schema's `max_length`, and by `fit_error_summary(text)`. The helper leaves text that fits
    unchanged, and cuts longer text to 499 characters plus `…`.
  - `JobRun` gets `@validates("error_summary")`, which applies the helper. That is the column
    enforcing its own declared length, which SQLite will not. It is the first `@validates` in
    `hub/hub`. It is chosen over wrapping each call site because there are eight writes today
    (`scheduler.py:2580, 2609, 2762, 2923, 2966, 3062`, `api/v1/jobs.py:81` and
    `run_reconciliation.py:222`), and the next one would be written without the wrapper.
  - `_stall_run_to_increment` (`:923`) compares `latest.error_summary` with
    `fit_error_summary(stall_reason)`. The stored value is fitted, so comparing the raw reason would
    never match its successor, and D6 of `loop-notices-and-reacts` would record one row per tick.
- **R2 answered R1's open check: an existing reason already passes 500 today.** Computed, not
  observed:
  - **`_wedged_review_reason`** (`scheduler.py:1744-1748`) reaches `error_summary` through F64's
    promotion (`:1655`) and the stall write (`:2762`). It measures 551 characters with a
    32-character reviewer and a 256-character title, and passes 500 once the title reaches 206
    characters. The title is quoted with `!r`, so escapes grow it: 256 backslashes make the
    sentence 807 characters long.
    The model-level fit would cut its remedy off the end, so **the function shortens the quoted
    title to what fits** (with `…`), and the sentence keeps its remedy.
  - **`schedule_result.waiting_reason`** (`:2923`, `:3062`) is the `detail` of any non-transient
    `TriggerAgentError`. Several embed exception text: git's stderr and two absolute paths
    (`agent_trigger.py:966, 970`), and `str(exc)` (`:607, 806, 853, 867, 1116`). These are unbounded
    by construction. The fit covers them, and cutting them loses only the tail of a git message.
  - `_job_agent_skip_reason` (`:2580`), the stop reasons (`:2609`), both `_safe_error_summary`
    copies (`scheduler.py:2966` and `api/v1/jobs.py:81`, each already `[:500]`) and the
    reconciliation constant are bounded.
  - **Observed:** the `:8000` database's longest `error_summary` is 276 characters over 43 rows,
    and the trial Hub's 3 rows are empty (mode=ro, `%TEMP%\f352r2\len.py`). Nothing has failed yet.
    Filed as **F367 (C)** and retired by this change.

### D3 — the exclusion carries its reasons

`resolve_reviewer(exclude=..., excluded_because=...)` is replaced by `exclude: Mapping[str, str]`,
mapping each agent to the clause that says why it is excluded.

- `decide_firing` (`scheduler.py:1550-1584`) builds `{author: "is the one that completed this
  task"}`, or `{a: "has worked on this task" for a in agents_that_may_have_authored(...)}`. Byte for
  byte, these are the clauses it passes today.
- `run_divergence` (`:430-446`) builds the mapping in three layers, each overwriting the one
  before (**R2**; R1 had the order wrong):
  1. on the operator-completed branch, `agents_that_may_have_authored` → `"has worked on this task"`;
  2. the silent reviewers and `run.agent` → `"reviewed this task and recorded no verdict"`;
  3. on the agent-completed branch, the recorded completer → `"is the one that completed this
     task"`.
- Rung 1b (`scheduler.py:1124-1133`) reads `exclude[resolution.agent]` where it read
  `excluded_because`.

**R2: why the silent reviewer overwrites "has worked".** R1 laid the author clause over the silent
reviewers. On the operator-completed branch, that erases the one fact this decision exists for.
`agents_that_may_have_authored` is the union of the transitions, the **assignee**, the agents of
**runs bound to the task**, and the evidence recorders (`task_transition_service.py:329-332`). The
silent reviewer is the assignee, and its review run is bound to the task, so it is always in that
set. Under R1's order, it would read *"has worked on this task"*, which is not false but loses
the fact. R1's own scenario (*"states that the agent which gave no verdict reviewed the task without
recording one"*) would then fail on exactly the branch F316 was about. A recorded completer still
wins over both: it is the fact the corpus is keyed on (`scheduler.py:1550-1555`).

*Why:* `run_divergence` puts the silent reviewer into the same set as the author, under one
clause, *"is the one that completed this task"*. Today that clause is generic prose. Under D2 it
would become `"rv is the one that completed this task"`, a false statement about a named agent.
`agent-flows` already forbids that for the operator-completed case (*"The second resolution's
surfaced reason does not claim an agent completed the work"*).

*Rejected:*
- **An extra `also_excluded` mapping beside the set.** It gives three parameters for one idea.
- **Accepting either a set or a mapping.** It gives two shapes for one parameter.

The mapping is one statement of who is excluded and why. The 14 test call sites that pass a set
(`test_reviewer_ladder.py`, 12, and `test_a_flow_names_what_it_cannot_staff.py:472, 482`) are
updated, along with the two runtime callers.

**R2: a missed call site fails loudly only where it reaches a named exclusion.** R1 said a missed
call site "fails loudly". A set reaching `exclude[name]` does raise `TypeError`. But
`candidate in exclude` works on both shapes, so a set only fails where a test reaches rung 1b or
rung 3 with an excluded agent. Nothing else catches it either: CI runs `mypy src/` only
(`.github/workflows/ci.yml:77`), never over `hub/`. Task 2.1 therefore lists every call site by line,
and IMPL greps for `exclude=` before ticking it.

### D4 — once per fact means once per task

`_review_unstaffed_already_stands` (`scheduler.py:1913-1941`) adds the task to its query:
`EventLog.data["task_id"].as_string() == task_id`, newest first, `limit(1)`. That makes it the
newest record **for this task** in this loop, which its own docstring already claims to read.

*Measured:* 347 of LoopEngine's 357 `review_unstaffed` events repeat their own task's previous
reason. The one stretch with a single unstaffed task (22:35–22:55 UTC) recorded once. The rule
works for one task and fails for two.

*Why SQLAlchemy's JSON path and not a Python scan:* the scan is unbounded over a loop's history (357
rows here and growing), and the JSON path compiles to SQLite's `JSON_EXTRACT`, which is built into
the SQLite that Python 3.11 ships. No runtime code uses a JSON path yet. The note in migration
`0083` avoids `json_extract` *in a migration*, for data-shape reasons that do not apply to a column
written only by `persist_event`. **IMPL proves this with a test against real SQLite, not a mock.**
If the path cannot be made to work, the fallback is a bounded Python scan, and R2 or IMPL records
the switch.

**R2: it works.** `EventLog.data` is a SQLAlchemy `JSON` column (`models.py:1018`), and
`persist_event` writes the payload dict into it (`utils.py`, `data=data or {}`). R2 ran the query
against the Hub's own models on `sqlite+aiosqlite:///:memory:` under `py -3.11`
(`%TEMP%\f352r2\jp.py`). It used four `review_unstaffed` rows alternating between two tasks, the
way LoopEngine's did. The statement compiles to
`JSON_EXTRACT(event_logs.data, '$."task_id"') = :task_id` and returns the right newest row for each
task, and no row for a task with none. A grep finds no other `.as_string()` in `hub/hub`, so R1's
*"no runtime code uses a JSON path yet"* holds. The fallback is not needed.

*Interaction with D2:* the reason now changes whenever the named holdings change. That is a changed
fact, and `agent-loops` requires it recorded again. D2 keeps the reason from changing on every turn
boundary.

### D5 — the refusals name what the refused actor can do

The guard's **decision** does not change: same edges, same actors bound, same exceptions. Only the
sentences change.

**`_guard_reviewer_is_not_the_author`** (`task_transition_service.py:443-464`, both branches) is
reached by three audiences:

| audience | how | the assignee it judges |
|---|---|---|
| the operator | `PATCH …/tasks/{id}`, including the drawer's status menu | committed, or set by the same request |
| an agent | `update_task` over MCP; `PATCH /agent-actions/tasks/{id}` over HTTP | committed over MCP; **over HTTP also set by the same request** (R2, F366) |
| a flow or a dispatch | `enter_selected_task` writes the reviewer, then transitions as `operator()` (`scheduler.py:816-828`) | **staged by this call**, then discarded by the rollback (F334) |

**The sentence must be true in all three**, and the guard cannot tell a staged value from a
committed one. SQLAlchemy's attribute history is cleared by any autoflush between the assignment
and the guard. So the sentence describes the move, not the row. It follows this shape: *"Cannot move
task T to 'under_review' held by 'dev': 'dev' is the agent recorded as completing it, and a task
under review is held by its reviewer, so the move would make its author its reviewer."* That is true
whether `dev` was already there or was being written in. It does not say *"is assigned to"*. **R2**
changed R1's *"with 'dev' holding it"* to *"held by 'dev'"*: the first reads as a statement about the
row now, which is F334's defect again. The second names the state the move would produce.

**Then the remedy, chosen by `actor.is_operator`.** The flow's staging arrives as `operator()`
(F47), and its sentence lands in the queue entry's `waiting_reason` and `abandoned_reason`, which
the operator reads. So the operator wording serves both. The guard only ever judges a `completed`
task, because `under_review` is entered from `completed` alone (`task_transitions.py:134-137`). So
Land it is always the right remedy **here**.
- **Operator:** *Land it, on the task, to review it yourself. To have another agent review it, one
  API request can name that agent as the assignee and send the task to review.* The second half is
  the one-request form `task-lifecycle-governance` already guarantees (*"Naming a reviewer in the
  same request succeeds"*).
  - **R2** removed *"it releases the hold and approves it"*: the approval gate can refuse (D2).
  - **R2** also says *"API"* outright. The drawer renders Assignee read-only
    (`TaskDetailDrawer.tsx:380-395`), so an unqualified *"in the same request"* reads as a control
    in the app, which is F353's defect.
- **Agent:** *None of your tools changes who holds a task, so this is not yours to fix. Leave it
  `completed`. The operator can land it, or a flow or the operator can staff a reviewer who is not
  its author.*

**R2: the agent sentence no longer says "no agent can".** R1's wording was *"No agent can change
who holds a task"*, and F366 makes that false.
- `PATCH /agent-actions/tasks/{id}` takes the operator's `TaskUpdate` (`agent_actions.py:276-289`),
  and `update_task_for_actor` writes `assignee` for any actor (`tasks.py:1266-1275`).
- An agent over HTTP can therefore send `{assignee: <another agent>, status: under_review}` and
  succeed. Worse, a refusal telling it that it cannot would sit one request away from being
  disproved.
- What **is** true is the offered surface. The MCP `update_task` carries `status` and `notes`
  (`mcp_server.py:307`). The HTTP rendering lists the fields the adapter sends,
  `fields=("status", "notes")` (`agents.py:1003-1008`), and every agent without MCP is shown that
  rendering (`launchability.py:392-400`).

*"None of your tools changes who holds a task"* is a claim about the surface. It makes no claim
about the route, and it does not advertise the route's hole. Whether the route should take
`assignee` at all is F366's own loop. **Neither this sentence nor the operator's names the hole to
an agent.**

The trailing *"Left as is, the task is claimable by nobody and 'dev' counts as busy…"* is dropped.
It describes the state the refused move *would* have produced. Read after a refusal, it describes a
state that does not exist, and the agents on LoopEngine quoted it as though it did.

`actor` becomes read, **for wording only**. The docstring's paragraph *"`actor` is deliberately
unread"* is amended to say so. The rule still binds every actor.

**`review_dispatch_refusal`** (`agent_trigger.py:497-514`) is reached only by the operator's
`POST /agent/trigger` with `review_task_id`, an API-only route (F336).
- The author branch drops *"or clear the assignee to review it yourself"*. Clearing the assignee is
  unrelated to that refusal, which is about the *reviewer* being the completer. It gains
  `own_review_remedy(task)`, the helper D2's rung 3 uses.
- The evidence-author branch gains the same helper, for consistency.

**R2: the dispatch refusal's remedy depends on the status, as rung 3's does.** R1 gave both
branches *"Land it"* unconditionally, and that is wrong for one reachable state.
`review_dispatch_refusal` admits `WITH_REVIEWER_LOOP_TASK_STATUSES` as well as the reviewable ones
(`agent_trigger.py:480`). Its D9 check refuses only a *different* holder (`:487-491`). So the author
branch is reached for an `under_review` task that nobody holds, or that is held by the very reviewer
being dispatched. `land` refuses `under_review` with a 409 (`tasks.py:1519-1530`). One helper for
both surfaces is also what keeps them from drifting into two accounts of the same remedy.

### D6 — the board line shows the whole reason on hover

Add `title={loop.stall_reason}` to the truncated `<p>` (`LoopsIndexTab.tsx:237-244`). It is one
attribute and calls nothing new, so it is compatible with any running `:8000` by construction. It is
committed only if it was driven in Chromium against the served bundle (`day-window.md`, *A day that
builds*). Otherwise it is left for the night, and the Python half stands without it.

*Rejected:* expanding the line, or a drawer for the loop. That redesigns a surface, which is not this
change's business.

## What this change does not do

- **It does not change who is free** (proposal, *OPERATOR QUESTION*). D1 keeps the predicate byte
  for byte.
- **It does not add an assignee control or a review-dispatch control to the app** (F336 names the
  second as a product decision). The sentences stop naming controls that do not exist, and name the
  one that does.
- **It does not edit `hub/hub/mcp_server.py`.** Nothing here needs it, and on a build day it may not
  be edited (F354).
- **It does not close F366.** `PATCH /agent-actions/tasks/{id}` (`agent_actions.py:276-289`)
  takes the operator's `TaskUpdate`, `assignee` included, and `update_task_for_actor` writes it for
  any actor (`tasks.py:1266-1275`). MCP `update_task` carries no assignee (`mcp_server.py:307`). R2
  re-read this and it holds: an agent over HTTP can reassign any task. That is code read, not
  driven. `agent-capability-plane` forbids that surface difference. **R2 decided that R1's sentence
  was not true enough to say**, and D5 now describes the offered surface instead. Closing the
  route is F366's own loop. It is not folded in here: refusing `assignee` to agents is a change to
  what an agent may do, with its own argument, and it would edit none of this change's lines.

## Risks

- **The sentence is long.** It is still one line on the board, and D6 gives the whole of it on
  hover. It leads with names, and the event feed renders it whole.
- **Holdings churn records.** A flow whose agents keep picking up and finishing live work changes
  the reason often. Each change is recorded, which is the rule. That is bounded by one per task per
  firing, the pre-F154 rate, and only while the task is actually unstaffable.
- **Test churn from D3.** There are 14 call sites. They are mechanical. A missed one fails loudly
  only where it reaches a named exclusion (R2), so 2.1 lists them.
- **The first `@validates` in `hub/hub` (R2).** A validator that silently shortens a value is a
  pattern a reader may not expect. The docstring on the constant says what it does and why, and
  test 2.9 exercises it through the real route.

## Round 2 — what the code disagreed with

R2 re-derived each decision against the code at `e8ea490`, and did not re-read R1's argument. It
answered R1's four open checks and found five disagreements. Each is fixed above, in the proposal,
in the deltas and in `tasks.md`.

**R1's four checks, answered.**
1. *Can an existing `error_summary` already pass 500?* **Yes, computed:** `_wedged_review_reason`
   at a 206-character title and a 32-character reviewer. Dispatch refusals carrying git stderr are
   unbounded by construction. None is observed yet (`:8000` max 276). This is F367, and the fit
   moved to the model (D2).
2. *Does D5's "no agent can change who holds a task" survive F366?* **No.** The agent sentence now
   describes the offered surface (D5).
3. *Does D4's JSON path work on real SQLite?* **Yes, run:** it compiles to `JSON_EXTRACT` and
   selects per task (D4).
4. *D3's call sites?* Two runtime callers and 14 test call sites, as R1 counted. The "fails loudly"
   claim was overstated (D3).

**Five disagreements.**
1. **The `completed` remedy promised an approval that `land` refuses** whenever evidence naming a
   commit awaits judgment. At rung 3, such evidence exists by construction (D2).
2. **R1's example would not have named LoopEngine's whole roster** once its remedy was made
   honest: 514 characters. The wording was tightened and the budget measured (D2).
3. **The divergence overlay erased "recorded no verdict"** on the operator-completed branch,
   failing R1's own scenario (D3).
4. **The dispatch refusal named Land it for an `under_review` task**, which `land` refuses with a
   409. It now shares rung 3's status-aware helper (D5).
5. **The guard's sample sentence, *"with 'dev' holding it"*, still read as a claim about the row**
   (D5). Also, *"in the same request"* read as an app control, so it now says API.

**Also found:** `_agents_that_are_free` has three callers, not two, and rung 3 can meet an empty
roster (D1).
