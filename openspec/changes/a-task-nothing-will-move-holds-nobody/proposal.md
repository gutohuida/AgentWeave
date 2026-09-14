# Proposal — a task nothing will move holds nobody

**R1, night of 2026-09-14**, from `openspec/explorations/2026-09-14-who-owns-a-loops-queue.md`. The
operator read that exploration as it was written, in an interactive session that evening, and
redirected the night window onto it (`spec-queue/APPROVALS.md` `## 2026-09-14`, *"The operator sat
down at 23:30"*). The queue there calls this change `who-owns-a-loops-queue`. R1 renamed it,
because this change builds the half of the design that the old name does not describe (see *Scope*).

**R2, the same night**, re-derived it against the code and repaired four defects. An archived loop
held its agents forever. The queued-turn arm counted input past the hop budget, which could have
left LoopEngine frozen. The same arm read a map that hides the assignee's own input. And the
documentless widening is F128. Each is marked *Round 2* where it lands; the account is in
`design.md`'s *Round 2* section.

## Why

LoopEngine, the operator's real flow on `:8000`, stood still for twelve hours. From 07:02 to at
least 19:13 on 2026-09-14 its `*/5` job fired on schedule and recorded `review_unstaffed` **498**
times, each claiming that no agent was free. All four agents were idle. Between them they held ten
tasks, and none of the ten had a live run, a queued inbound entry or an open question on it. The
measurements are the exploration's, read `mode=ro` from `:8000` in the evening session. R1 did not
re-read that database, and this window's limits do not let it.

Eight of the ten holdings were tasks the Architect created while executing the loop and assigned to
`dev` and `dev_2`, with `loop_id` NULL. Three facts from the source make them fatal. R1 re-read each:

1. **A loop walks only its own tasks.** `_loop_candidates` filters `Task.loop_id == loop.id`
   (`hub/hub/scheduler.py:717`). A task with no `loop_id` is invisible to every firing, forever.
2. **Any assigned task in a live status disqualifies its assignee.** `_agents_that_are_free`
   (`scheduler.py:1022`) subtracts every assignee of a task in `LIVE_STATUSES` (`pending`,
   `assigned`, `in_progress`, `revision_needed`, `under_review`; `task_transitions.py:338`),
   project-wide (`:1062-1074`). It does not ask whether anything will ever move the task.
3. **One predicate answers three questions.** Its three callers are the firing guard (`:306`, *is
   anyone else free*), the reviewer ladder's rung 2 (`:1187`, *who reviews this*) and the flow walk
   (`:1368`, *who takes new work*).

Composed, they are a ratchet. An agent executing a loop finds follow-up work. It may not add it to
the loop (`_authorize_loop_task_creation`, `hub/hub/api/v1/tasks.py:601`), so it creates a
free-floating task and names an assignee. Nothing will ever walk that task, and its assignee is now
disqualified from every flow in the project, permanently. The more diligent the roster, the faster
the project seizes.

**One of the exploration's supporting facts is wrong, and R1 corrects it here.** The exploration
says `materialise()` is *"the only writer of dependency edges in the system"* (`spec_tasks.py:293-299`).
That was true until F36. Since then `task_dependency_writer.add_dependency` has two callers:
`spec_tasks.py:375`, and the operator's `POST /tasks/{id}/dependencies` (`tasks.py:1630`). So an
**operator** can order a free-floating task, and an **agent** still cannot, since the MCP
`create_task` has no `depends_on` and no agent tool reaches the route. The exploration's amend
trigger survives the correction, restated below. Nothing in this change depends on it.

## Scope — the whole design, and which half this change builds

The operator's model, from the exploration:

> The loop cannot be edited by a worker, only by the one who owns it. The assignee is the
> *executer*, and the creator is the *owner*. A task that appears during a loop goes to the owner for
> approval first. If it is really needed, the owner puts it in the loop and amends the spec, flagged
> as an amend.

The whole design has five parts:

- **A. Reachability.** A task holds its assignee only while something will move it. *This change.*
- **B. Owner and executer.** The loop's owner is derived from `Loop.created_by_run_id`, reversing
  `2026-08-18-a-loop-writes-its-own-queue` design D8 by name. D8 collapsed "creator" into
  `AIJob.agent`, which is the executer.
- **C. Admission.** A task born inside a loop is detected by `Task.created_by_run_id → Run.task_id →
  Task.loop_id`, and is offered to the loop's owner for admission rather than left free-floating.
- **D. The amend trigger.** *Does the new task need a dependency edge?* If not, the owner admits it
  straight to the loop, with no document change. If it does, it needs an amendment, because an
  **agent** can write an edge only through the document. The F36 correction narrows this to agents.
- **E. A question that does not stop the work.** The admission decision is a `Question` with
  `blocking = False` and `blocked_task_id` set, so the asking turn is not suspended. The model has
  both fields, but `ask_user` always blocks, so an agent has no way to raise one.

**This change builds A only.** It touches `hub/hub/scheduler.py` and its tests. There is no
migration, no `hub/hub/mcp_server.py` edit, no API shape change and no UI. B to E stay specced in
the exploration and this proposal, and a later change named `who-owns-a-loops-queue` builds them.

**Why A first, and alone:**

- **A is the half that unfreezes a board.** B to E prevent *new* orphans. They do nothing for the
  ten holdings LoopEngine has now, or for any other project that has already filed follow-ups
  outside a loop. A frees those without writing to a single row.
- **A is correct whether or not B to E ever ship.** The exploration argues that the two decisions
  are coupled: if admission ships, the strict rule stops hurting. That is only partly true. An
  **operator** can still create an assigned task outside any loop, legitimately, and that task
  would still cost the project its assignee. *"Is anything ever going to move this task?"* is the
  right question with or without admission control upstream.
- **B to E need `mcp_server.py` and UI.** `:8000` spawns `mcp_server.py` fresh from this working
  tree on every agent turn (F354), and a UI bundle reaches the operator's live app on their next
  reload. Neither suits a night window with nobody watching.
- **A is severable.** It changes one predicate, and every consumer of that predicate is in one file.

## What changes

- **`_agents_that_are_free` asks whether the holding is reachable, not only what its status is.**
  An agent holds work where it is the assignee of a task in `LIVE_STATUSES` that either:
  - belongs to a loop that has neither ended nor been archived (`Loop.ending_state IS NULL AND
    Loop.archived_at IS NULL`; the second clause is Round 2's, design D2), or
  - has a turn running or queued for that assignee, naming the task, where a queued turn counts
    only within the project's hop budget. *Round 2:* this reads `(task, agent)` pairs from a new
    `run_task_binding` function, not the F154 helper R1 named. That helper keeps one agent per
    task, so it can hide the assignee's own input, and it counts input that only the operator's
    release will deliver (design D4).

  Every other assigned live task is a bookmark. It stays on the board with its status and assignee
  untouched, and it no longer costs anybody anything.
- **All three callers change together**, because they read one function. The guard and the walk must
  not come to different answers (design D3).
- **The docstrings that state the old rule are corrected.** Three places state it: the pool's
  docstring, which claims the pool and the roster cannot disagree; the ladder's rung-2 line; and
  the comment at `:1363`. The roster keeps counting a bookmark as an active task, on purpose: it
  answers *what does this agent hold*, not *may a flow staff it*.
- **The rung-3 sentence is not reworded.** Every agent this change leaves out of the pool still
  holds active work, so the sentence stays true. Rewording it belongs to
  `an-unstaffed-review-names-its-holders`, which is stopped (see *Relation to F352*).

## The six questions the exploration left to R1

1. **Does the owner concept reverse D8, or sit beside it?** *Deferred to `who-owns-a-loops-queue`,
   with a recommendation.* Derive the owner at read time from `created_by_run_id`. The
   exploration's case for a stored column was that it *"survives a run being pruned"*, and nothing
   prunes a `Run`. The only deletes of a run-shaped row in `hub/hub` are of `JobRun`, a firing's
   record (`_discard_unused_run`, `scheduler.py:973-985`, and `_prune_job_history`'s bulk delete at
   `:2539`). So the derived form has no durability cost and cannot drift. It still reverses D8, and
   that change must say so by name.
2. **An operator-created loop has no creating run.** *Deferred, with an answer.* The owner is then
   the operator. That is the default, not an edge case, and it matches `Loop.control`'s own NULL
   convention (`models.py:1456-1463`).
3. **What admits a task: a new row, or a task status?** *Deferred, with a recommendation:* a
   separate admission row, mirroring `SpecEditProposal`. A `proposed` status would reach
   `STATUS_BANDS`, every derived set and the transition table. Nothing in A needs either.
4. **Are the ten existing holdings cleared, and by whom?** *Answered: yes, by this change, with no
   write.* The eight out-of-loop holdings stop disqualifying `dev` and `dev_2` the moment this code
   runs. The two in-loop holdings keep holding, and they should:
   - `tester`'s `pending` task is in the loop, so the loop will brief it.
   - The Architect's `under_review` task is in the loop, and nothing is doing it. That is F154's
     *"a review nobody is doing"*, surfaced by name. It is the operator's to resolve through
     `under_review`'s three exits (design D5, *Residual*).

   **On `:8000` this takes effect only when the operator restarts it.** It runs this checkout
   without `--reload`. The same restart applies migration `0103`, which is already on the review
   page's alarm box. This change adds no migration.
5. **Does admission apply to an unassigned task?** *Answered for staffing, deferred for the rest.* An
   unassigned free-floating task costs nobody an agent today, and A makes an *assigned* one cost
   nobody either. So the cheap mitigation the exploration priced, refusing to assign an out-of-loop
   task, is **not needed for staffing** once A ships. It would also refuse the operator a
   legitimate gesture. Whether admission still wants such tasks for traceability and queue
   membership is `who-owns-a-loops-queue`'s question. The work in them is never done, which is a
   real cost, but not this one.
6. **Are the Architect's eight suspended messages the other half?** *Deferred.* Answering it means
   reading the entries' content on `:8000`. This window's limits allow that only in a read-only
   review that the day's `DIRECTION.md` asks for, and nothing in A depends on the answer. It stays
   with F361.

   *Round 2: R1's "nothing in A depends on the answer" was true only of the fix R2 made, not of
   R1's own design.* Those eight messages are F361's peer chains, suspended at hop 7 against a
   budget of 6. If they name tasks their recipients hold, R1's queued-turn arm would count them as
   turns queued and keep `dev` and `dev_2` held, and LoopEngine would not unfreeze. Under Round 2's
   rule, input past the hop budget holds nobody, so the answer genuinely no longer matters to A.

## Relation to F352, and to the stopped change

This change answers F352's definition half. `an-unstaffed-review-names-its-holders` stopped on the
**OPERATOR QUESTION** *"what free means"*, and offered options (a) to (e). This change is none of
them. Call it **(f) reachability**:

- Closest to (a), but it scopes holding to *any loop that has not ended*, not *this* flow. A task in
  another live loop is a real queue, so (a)'s pile-up objection applies to it, and (f) keeps it.
- Closest to (c) for tasks outside loops. Inside a loop it keeps D4's strict rule, which (c) drops.
- Unlike (d), it does not split review from new work. It removes phantom holdings from both.

> **OPERATOR QUESTION (noted, not blocking).** Building this change answers F352-free as (f). The
> operator set that direction in session on 2026-09-14, so the change proceeds, per the redirect's
> instruction. Carried to `decisions_for_user` for the record.
>
> Two consequences need the operator's eye:
> - `an-unstaffed-review-names-its-holders`' rung-3 half was written against (e). Under (f) it would
>   name only reachable holdings. It must be re-derived before it is built, which `F352-split`
>   already anticipates.
> - Design D2 takes a position the operator may want otherwise: **a paused loop's tasks still hold
>   their agents.**

**F352 stays open** after this change, for its visibility half: the unstaffed sentence still names
nobody. At archive, its Status line records the definition half as fixed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-flows`:
  - adds *"An active task makes its assignee unavailable only while something will move it"*;
  - modifies *"A flow resolves a reviewer by declaration, then by availability"*, so its rung-2
    clause and its busy-agent scenario use that definition. It also gains one scenario.

`agent-loops` defers the meaning of "free" to `agent-flows` (*"A firing is refused while its loop's
agent is already running"*: *"This requirement does not state which agent a firing staffs when
another agent in the project is free"*), so it needs no delta.

## Impact

- **Python:** `hub/hub/scheduler.py`, meaning `_agents_that_are_free`, one docstring line in
  `resolve_reviewer`, and the comment at `:1363`. *Round 2:* also one new function in
  `hub/hub/run_task_binding.py` (task 1.1a). Tests go in a new
  `hub/tests/test_a_task_nothing_will_move_holds_nobody.py`, plus one existing test re-staged
  (tasks 2.1–2.2).
- **Not touched:** `hub/hub/mcp_server.py`, `hub/hub/api/v1/tasks.py`, the transition map,
  `LIVE_STATUSES`, the roster, the rung-3 sentence, and any row. *Round 2:* also not touched are
  `tasks_with_a_turn_pending_or_running`, its reader at `:1454`, and the held-resume arm at `:1506`.
  Each has a defect R2 filed (F371, F370) and this change does not repair.
- **No migration. No API shape change. No UI.**
- **Behaviour an operator will see:**
  - A flow that was stuck on `review_unstaffed` behind out-of-loop holdings starts staffing.
  - A flow whose job agent is mid-turn now proceeds, rather than being refused, when another agent
    holds only bookmarks. This affects the board's stall line and `POST /jobs/{id}/run`'s 409
    (design D3).
  - *(Round 2)* **A plain loop does too, which is F128.** A documentless loop whose agent is
    mid-turn can hand its next pending task to a sibling that holds only bookmarks. F128's
    substitution already reaches any multi-agent project with an unencumbered sibling. This change
    adds the projects where every sibling holds bookmarks. F128's decision is the operator's and
    stays open (design D3).
  - *(Round 2)* Agents held only by tasks in a loop archived through the job route, or only by peer
    messages past the hop budget, become available.
- **Findings:** retires none whole. F352's definition half is fixed, and it stays open for the
  visibility half. *Round 2* filed F370 and F371 against shipped code, and neither is fixed here.
