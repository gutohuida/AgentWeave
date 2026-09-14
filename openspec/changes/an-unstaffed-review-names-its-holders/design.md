# Design — an unstaffed review names its holders

R1, 2026-09-14. Line numbers are at `2d5674c`.

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
`under_review` rows the F70 recovery and the divergence restaff carry to the ladder.
- **`completed`:** *review it yourself — Land it, on the task, approves it*. This is F163's action,
  in the drawer for exactly this status.
- **`under_review`:** *decide it yourself — approve it, reject it, or send it back with
  revision_needed*. `land` refuses `under_review` with a 409 (`tasks.py:1519-1530`), so naming
  Land it there would name an action that refuses.
- **Both:** a task one of them holds that is no longer wanted can be rejected, which frees that
  agent. This is the operator's `rejected` edge from every live status (`task_transitions.py:101-146`),
  which is what freed `tester` on LoopEngine at 22:33.

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

- **Rung 3 builds within 500 characters.** Clauses are added in name order while they fit. The
  rest collapse into `"and N more agents are excluded, busy or unbound"`. The remedy is always
  kept, so its length is reserved first. The result is deterministic and is the same string on
  every surface.
- **Every `error_summary` write is fitted to the column**, through one helper used by the write at
  `scheduler.py:2762` and by `_stall_run_to_increment`'s comparison at `:923`. The two must compare
  the same fitted string, or a stall row would never match its successor and D6 of
  `loop-notices-and-reacts` would record one row per tick. This change makes long reasons likely,
  so this change fits them. **Unmeasured, R2 to check:** whether an existing reason can already
  pass 500. `_wedged_review_reason` (`scheduler.py:1744-1748`) embeds a title of up to 256
  characters in about 230 characters of prose, and the other `error_summary` writes (`:2580`,
  `:2609`, `:2923`, `:3062`) carry reasons of their own.

### D3 — the exclusion carries its reasons

`resolve_reviewer(exclude=..., excluded_because=...)` is replaced by `exclude: Mapping[str, str]`,
mapping each agent to the clause that says why it is excluded.

- `decide_firing` (`scheduler.py:1550-1584`) builds `{author: "is the one that completed this
  task"}`, or `{a: "has worked on this task" for a in agents_that_may_have_authored(...)}`. Byte for
  byte, these are the clauses it passes today.
- `run_divergence` (`:430-446`) builds the silent reviewers as `"reviewed this task and recorded no
  verdict"`, then lays the author clause over any agent that is also the author.
- Rung 1b (`scheduler.py:1124-1133`) reads `exclude[resolution.agent]` where it read
  `excluded_because`.

*Why:* `run_divergence` puts the silent reviewer into the same set as the author, under one
clause, *"is the one that completed this task"*. Today that clause is generic prose. Under D2 it
would become `"rv is the one that completed this task"`, a false statement about a named agent.
`agent-flows` already forbids that for the operator-completed case (*"The second resolution's
surfaced reason does not claim an agent completed the work"*).

*Rejected:*
- **An extra `also_excluded` mapping beside the set.** It gives three parameters for one idea.
- **Accepting either a set or a mapping.** It gives two shapes for one parameter.

The mapping is one statement of who is excluded and why. The 14 test call sites that pass a set
(`test_reviewer_ladder.py`, `test_a_flow_names_what_it_cannot_staff.py`) are updated. A set
reaching `exclude[name]` raises `TypeError`, so a missed call site fails loudly.

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
| an agent | `update_task` over MCP or HTTP | committed |
| a flow or a dispatch | `enter_selected_task` writes the reviewer, then transitions as `operator()` (`scheduler.py:816-828`) | **staged by this call**, then discarded by the rollback (F334) |

**The sentence must be true in all three**, and the guard cannot tell a staged value from a
committed one. SQLAlchemy's attribute history is cleared by any autoflush between the assignment
and the guard. So the sentence describes the move, not the row. It follows this shape: *"Cannot move
task T to 'under_review' with 'dev' holding it: 'dev' is the agent recorded as completing it, and a
task under review is held by its reviewer, so the move would make its author its reviewer."* That is
true whether `dev` was already there or was being written in. It does not say *"is assigned to"*.

**Then the remedy, chosen by `actor.is_operator`.** The flow's staging arrives as `operator()`
(F47), and its sentence lands in the queue entry's `waiting_reason` and `abandoned_reason`, which
the operator reads. So the operator wording serves both.
- **Operator:** *Land it, on the task, reviews it yourself: it releases the hold and approves it. To
  have another agent review it, send that agent's name as the assignee in the same request.* The
  second half is the one-request form `task-lifecycle-governance` already guarantees (*"Naming a
  reviewer in the same request succeeds"*).
- **Agent:** *No agent can change who holds a task, so this is not yours to fix. Leave it
  `completed`: a reviewer who is not its author is staffed by a flow or by the operator, or the
  operator lands it.*

The trailing *"Left as is, the task is claimable by nobody and 'dev' counts as busy…"* is dropped.
It describes the state the refused move *would* have produced. Read after a refusal, it describes a
state that does not exist, and the agents on LoopEngine quoted it as though it did.

`actor` becomes read, **for wording only**. The docstring's paragraph *"`actor` is deliberately
unread"* is amended to say so. The rule still binds every actor.

**`review_dispatch_refusal`** (`agent_trigger.py:497-514`) is reached only by the operator's
`POST /agent/trigger` with `review_task_id`, an API-only route (F336).
- The author branch drops *"or clear the assignee to review it yourself"*. Clearing the assignee is
  unrelated to that refusal, which is about the *reviewer* being the completer. It gains *"or review
  it yourself: Land it, on the task, approves it"*.
- The evidence-author branch gains the same clause, for consistency.

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
- **Noted, not in scope, unverified by driving.** `PATCH /agent-actions/tasks/{id}`
  (`agent_actions.py:276-289`) takes the operator's `TaskUpdate`, `assignee` included, and
  `update_task_for_actor` writes it for any actor (`tasks.py:1266-1275`). MCP `update_task` carries
  no assignee (`mcp_server.py:307`). So an agent over HTTP can apparently reassign any task, which
  `agent-capability-plane` forbids as a surface difference. D5's agent sentence therefore says *no
  agent can* as a statement of the offered tool surface, and R2 must decide whether that sentence
  is still true. This is filed as F366 for its own loop.

## Risks

- **The sentence is long.** It is still one line on the board, and D6 gives the whole of it on
  hover. It leads with names, and the event feed renders it whole.
- **Holdings churn records.** A flow whose agents keep picking up and finishing live work changes
  the reason often. Each change is recorded, which is the rule. That is bounded by one per task per
  firing, the pre-F154 rate, and only while the task is actually unstaffable.
- **Test churn from D3.** There are 14 call sites. They are mechanical, and a missed one fails
  loudly.
