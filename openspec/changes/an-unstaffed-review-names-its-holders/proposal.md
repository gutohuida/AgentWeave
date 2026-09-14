# Proposal — an unstaffed review names its holders

## Why

On the operator's own Hub (LoopEngine, `:8000`, read mode=ro on 2026-09-13 and 2026-09-14), a flow
stood still for most of a night with two finished tasks nobody reviewed. Every firing recorded the
same `review_unstaffed` sentence (`hub/hub/scheduler.py:1161-1168`):

> *could not staff this step: no agent is free to take it. Every agent on the roster is either
> running a turn, already holding active work, or is the one that completed this task and so may
> not review it.*

It names no agent and no task. No turn was running. Every agent was held by a task in a live status,
almost all of it outside the flow (F352's table). The reviewing agent was asked to diagnose it and
blamed the wrong thing. It then told the operator to reassign, which the app does not offer (F353).
The operator unblocked it by hand at 22:33 UTC with two `land` calls and one rejection.

Four defects share that surface, and this change repairs all four. R2 found a fifth on the column
the sentence is written to, F367, which is under *What changes*.

1. **F352, the visibility half.** The rung-3 sentence names nobody. F352 itself says what any
   repair must do, *"whatever else changes, the unstaffed sentence has to name the holdings — agent
   → task — because it is the whole of what the operator is shown"*. The sentence is also the
   loop board's stall line, rendered one line and truncated (`LoopsIndexTab.tsx:237-244`), so
   what it says first is most of what anyone reads.
2. **F365 (new, measured), the sentence is recorded 357 times, not once.** `agent-loops`
   *"A surfaced step is recorded once, not once per tick"* requires one record per task while the
   reason is unchanged. `_review_unstaffed_already_stands` (`scheduler.py:1913-1941`) reads the
   **loop's** newest `review_unstaffed` and then compares its `task_id`. When two or more tasks
   are unstaffed, their events alternate, the newest is always the other task's, and every firing
   records again. Measured on LoopEngine (`%TEMP%\f352\q1.py`, mode=ro), **347 of 357** events
   repeat their own task's previous reason word for word. Between 22:35 and 22:55 UTC only one
   task was unstaffed, and it recorded once, as designed. So the rule works only while one task is
   stuck. The existing test (`test_an_unchanged_wedge_is_recorded_once_not_once_per_tick`) stages
   exactly one.
3. **F353, the remedy names controls that do not exist.** Three refusals tell the reader to *"clear
   the assignee"* and to *"assign"* or *"dispatch a different reviewer"*:
   - `_guard_reviewer_is_not_the_author`, both branches (`task_transition_service.py:447-464`);
   - `review_dispatch_refusal` (`agent_trigger.py:498-504`).

   The drawer renders Assignee read-only (`TaskDetailDrawer.tsx:380-395`). The agents' MCP
   `update_task` has no assignee field (`mcp_server.py:307`). No UI control dispatches a review
   (F336). The action that does work, **Land it** (`tasks.py:1473`, F163), sits in the same drawer
   and none of the three names it. On LoopEngine the agents met the guard's refusal eight times: the
   Architect six, `tester` twice. In every form the observations quote, the holder named is `dev`,
   so each refused agent was a would-be reviewer, not the author. None of them could act on the
   remedy it was given (`spec-queue/observations/2026-09-14-LoopEngine.md`, Architect item 4 and
   `tester` item 3).
4. **F334, the dispatch-time refusal states an assignment nobody can see.** The flow and the
   dispatch stage the reviewer into `assignee` before the transition (`scheduler.py:816`), and the
   rollback after a refusal discards it. So *"it is assigned to 'authr8f'"* describes a state that
   was never committed. The task is `("completed", None)` before and after. F334 is folded in
   because it edits the same sentence (DIRECTION.md 2026-09-14, *"When two fixes would edit the
   same lines, they become one change"*).

## What changes

- **Rung 3 names every roster agent and why it cannot take the review**, in name order:
  - excluded, with the exclusion the caller applied (the author; every agent that worked on an
    operator-completed task; a reviewer that gave no verdict);
  - holding, with each held task's id and status, three per agent and then a count;
  - running a turn, for an agent that holds nothing;
  - no runner bound, for a live roster agent the pool leaves out.

  The per-agent list comes first. After it comes a remedy that exists for the task's status: for a
  `completed` task, **Land it** as the operator's own review; for `under_review`, the three exits.
  The last clause is rejecting a held task that is no longer wanted, which frees its agent. The
  facts come from the **same queries** `_agents_that_are_free` reads, restructured so the pool and
  the sentence are one computation.

  The remedy never promises an approval. `land` runs the approval gate first, and at this rung the
  gate refuses while evidence awaits judgment (R2). One status-aware helper writes the remedy, for
  this sentence and for the dispatch refusal below.
- **The sentence fits in 500 characters, and every `error_summary` write is fitted to its
  column.** `GET /jobs/{id}/history` validates `error_summary` at `max_length=500`
  (`schemas/jobs.py:88`). A longer reason would be stored without complaint by SQLite, and would
  then turn that route into a 500. R2 confirmed that with the real schema at 501 characters.
  - Agents that do not fit collapse into a count, and the remedy is always kept.
  - The fit is applied **at the model**, so none of the eight writes can miss it.
  - **F367 (new, R2, computed):** `_wedged_review_reason` already passes 500 today, with a long
    title and a long agent name.
- **`resolve_reviewer` takes the exclusion with its reasons.** The divergence restaff
  (`run_divergence.py:430-446`) excludes the silent reviewer and the author together under one
  `excluded_because`, *"is the one that completed this task"*. That is harmless while the sentence
  names nobody. Once the sentence names each agent, it would say a reviewer that gave no verdict
  completed the work, which `agent-flows` already forbids for the author case. The silent
  reviewer's clause overrides *"has worked on this task"*, because the wider author set always
  contains it (R2).
- **A surfaced step is recorded once per task.** `_review_unstaffed_already_stands` compares against
  the newest `review_unstaffed` **for this task** in this loop, not the loop's newest.
- **The author guard's two sentences and the dispatch refusal name remedies that exist**:
  - to the operator, **Land it**, or the one API request that names a reviewer and sends the task
    to review;
  - to an agent, that none of its tools changes who holds a task, and who can move the work on.
    R1 wrote *"no agent can"*, and F366's HTTP route makes that false (R2).
  - the dispatch refusal's remedy follows the task's status, because that refusal can meet an
    `under_review` task, which `land` refuses (R2).

  They are worded so they are true whether the assignee was committed before the request or staged
  by it (F334). The rule the guard enforces does not change.
- **The board's stall line shows the whole reason on hover** (`title` on the truncated `<p>`). This
  is UI, so the day's bundle rule applies. If it cannot be driven in a browser today, the group is
  left unbuilt and its row says so.

## OPERATOR QUESTION — what "free" means (F352's other half, NOT in this change)

`agent-flows` *"A flow resolves a reviewer by declaration, then by availability"* states the rule
the code enforces, *"any agent that is not running a turn and holds no task in an active status"*,
project-wide. The rule's design (`loop-becomes-a-flow` D4) rejected *not running* alone because of
*"the pile-up the operator named"*. Changing what counts as holding changes a shipped requirement
and a position the operator took, so it is **the operator's to decide**. This change does not decide
it. On LoopEngine the pool was empty because:

| agent | held (2026-09-13 22:30 UTC) | freed by (a) | (b) | (c) | (d) |
|---|---|---|---|---|---|
| Architect | 1 `under_review` in the flow (a review awaiting the operator, no turn) | no | no | yes | no |
| dev | 2 `in_progress` with no turn, 1 `pending`, all `loop_id` NULL | yes | no | yes | yes |
| dev_2 | 5 `pending`, `loop_id` NULL | yes | yes | yes | yes |
| tester | 1 `in_progress` with no turn (superseded) | yes | no | yes | yes |

- **(a) Scope holding to the flow.** Only tasks carrying this loop's `loop_id` hold an agent. It
  frees every agent whose backlog is outside the flow, but agents file their follow-ups with no
  `loop_id`. It re-opens the pile-up for any non-flow work, because a flow would give work to an
  agent holding three ad-hoc tasks.
- **(b) `pending` with an assignee does not hold.** A reservation, not work. It is narrow, and on
  LoopEngine it frees only `dev_2`, which would have been enough that night.
- **(c) A live task holds only while a turn is running or queued on it** (F154's predicate,
  `tasks_with_a_turn_pending_or_running`). It frees an agent between turns, which is exactly the
  case D4 rejected *not running* alone for.
- **(d) A review asks a different question from new work** (the 2026-08-26 exploration's option 2).
  - For a **review**, an agent is free when it is not running a turn and is not already the
    reviewer on an `under_review` task.
  - For **new work**, the full rule stays.
  - The argument: a review is one bounded turn against somebody else's commit, not accumulated
    ownership, and D4's pile-up objection is about being given work.
  - Open under (d): whether a review turn is refused or confused for an agent whose own task is
    `in_progress` (worktree, session binding). That needs its own R1.
- **(e) Leave the rule.** The flow surfaces truthfully, and after this change the sentence names
  exactly which holdings to resolve. A roster of four then sustains review only while holdings stay
  low.

**Recommended: (d).** It is the only option that separates the two questions D4 conflated. Of the
options that do not re-open the pile-up for new work, it frees the most on LoopEngine. Whatever is
chosen is a separate change, taken through its own spec loop. This change is built for the sentence
that option will need.

**Why this change is built without the answer**, stated so REV can reject the reading. DIRECTION.md
2026-09-14 says that if R1 finds a choice that is the operator's, *"the change stops after REV,
unbuilt"*. This change was scoped so that it contains no such choice. It keeps the rule exactly as
the corpus states it, and nothing in it depends on the answer. The sentence lists why each agent is
not free under whatever rule is in force, and F352 says that listing is required *"whatever else
changes"*. **F352 stays open** after this change. If REV reads DIRECTION as covering the finding
rather than the change, REV stops it, and it waits for the operator like any other.

## Capabilities

### Modified Capabilities

- `agent-flows` — adds *"A review nobody is free to take names who holds what"*.
- `agent-loops` — *"A surfaced step is recorded once, not once per tick"* gains a scenario for two
  steps surfaced by one loop. It also adds *"A firing's recorded reason never makes the loop's
  history unreadable"* (R2, F367).
- `task-lifecycle-governance` — *"A task entering review must not still name its author as its
  holder"*: the refusal's remedy is one the refused actor can take, and it is true whether the
  assignee was staged by the request. The operator's author-refused dispatch names a remedy for
  the task's status (R2).

## Impact

- **Python:**
  - `hub/hub/scheduler.py`: `_agents_that_are_free` restructured over a per-agent availability
    read; `resolve_reviewer` rung 3; `own_review_remedy`; `_wedged_review_reason`'s title fit;
    `_stall_run_to_increment`'s comparison; `_review_unstaffed_already_stands`.
  - `hub/hub/db/models.py`: `JOB_RUN_ERROR_SUMMARY_CHARS`, `fit_error_summary`, and
    `@validates("error_summary")` on `JobRun`. `hub/hub/schemas/jobs.py` reads the constant.
  - `hub/hub/run_divergence.py`: the exclusion carries reasons.
  - `hub/hub/task_transition_service.py`: the guard's two sentences.
  - `hub/hub/api/v1/agent_trigger.py`: the dispatch refusal's sentence.
- **UI:** `hub/ui/src/components/spec/LoopsIndexTab.tsx`, one `title` attribute. The bundle is
  committed only under the day's rule: it must be driven in a browser, and nothing it calls may be
  newer than the `:8000` process. It calls nothing new.
- **Not touched:** `hub/hub/mcp_server.py` (F354; nothing here needs it), the definition of free,
  the transition map, and every guard's decision.
- **No migration.** No API shape change: `reason` is already a string on the event and on
  `stall_reason`.
- **Findings:** retires F353, F334, F365 and F367. **Leaves F352 open** with a dated note, because
  its definition half is the operator's question above. **Leaves F366 open**: this change stops
  relying on the route's hole, and closing it is that finding's own loop.
