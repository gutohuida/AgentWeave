# Design — a loop that is gone lets go of its document

## Operator review, 2026-09-24

The adversarial Opus review is in `spec-queue/tracks/reviews/B11-2026-09-24.md`, §5 (REVISE, spec
deltas only). The operator decided that **loop adoption gets its missing deltas and an adoption
event, and is approved**, and that **an adopted `in_progress` task keeps its assignee** (Open
Question 1 below is now closed). The fixes applied here:

- **HIGH, three existing SHALLs contradicted.** The change now carries three MODIFIED deltas against
  `openspec/specs/agent-loops/spec.md`:
  - *A loop's queue is the tasks that name it…* (`:36`): "exactly two mechanisms" becomes three,
    naming claim-time adoption.
  - *A loop MAY declare one specification document…* (`:147`): "no other **live** loop" and "the
    **live** declaring loop". The refusal text had been stale since `2239f38`.
  - *A loop and a job are archivable, never deletable* (`:483`): the archived loop's queue history
    survives adoption as a `loop_tasks_adopted` event (D6).
- **MEDIUM, archived assignee:** D7 and tasks 1.10-1.11.
- **LOW:** D1 now says that a loop that has ended but is not archived still blocks a successor. The
  races the review checked hold: the partial unique index, and the rollback at `jobs.py:765-770`.
  The review found no collision with B10.

**Overlap with B1's `a-task-is-attended-only-by-a-turn-that-will-reach-it`:** its `agent-loops`
delta MODIFIES only *A task reported as in flight is one an agent is actually working*. That is not
one of the five requirements this change touches, so the two deltas do not collide. It changes the
`queued` half of the staffing gate. D7 adds an archived-assignee branch in the walk's `task.assignee`
arm (`scheduler.py:1839-1843`). That arm is a different line from the one it changes, but an
implementer landing the second of the two should re-read the first.

**Built on the recommended answers to B11's F53 and F157 questions** (ROUNDS.md D13, *"a loop's
archive releases adopted tasks?"* and *"`spec_document_id` on non-loop jobs"*): **a successor loop
adopts a gone loop's unfinished tasks (F53, option b′ below), and a create refuses a document on a
job that is not a loop (F157).** The two ship together because they share one requirement file and
one function's neighbourhood, but they are independent: if the operator answers one otherwise, drop
its D-section, its tasks and its requirement edit.

## Context — measured on `ce086b6`

| Fact | Where |
|---|---|
| The conflict check ignores archived loops (F53's fixed half) | `hub/hub/api/v1/jobs.py:166-170` |
| Adoption takes only `loop_id IS NULL` tasks of the document | `jobs.py:239-270`, the filter at `:266` |
| Adoption runs at creation and at a PATCH claim | `jobs.py:762`, `:1027` |
| Archiving a job ends and archives its loop; clears no task | `jobs.py:1275-1285` |
| Archiving a loop directly (operator only, ended loops only) clears no task | `hub/hub/api/v1/loops.py:152-185` |
| Every loop-queue query reads `Task.loop_id == loop.id` | `hub/hub/scheduler.py:329, 402, 787, 2258, 2766` |
| A holding in a dead loop is "unreachable" for staffing | `scheduler.py:1165-1180` (`reachable=loop_id in live or …`) |
| Terminal task statuses | `hub/hub/task_transition_service.py:736` `TERMINAL_STATUSES = {"approved", "rejected"}` |
| Materialise picks the owning loop by document only, first row | `hub/hub/spec_tasks.py:176-180`, used at `:284` |
| `create_job` reads `spec_document_id` only when the job opts in | `jobs.py:699-704`, `:746-763` |
| PATCH refuses a loop field on a non-loop job | `jobs.py:989-1011` |
| The `work_needs_evidence` refusal on create, the precedent | `jobs.py:614-631` |
| The MCP loop tools always opt in (`purpose` defaults to `""`, not `None`) | `hub/hub/mcp_server.py:676-686`, `:761-770` |

## D1 — A successor adopts a gone loop's unfinished tasks

```python
gone = select(Loop.id).where(Loop.project_id == project_id, Loop.archived_at.is_not(None))
update(Task).where(
    Task.project_id == project_id,
    Task.spec_document_id == loop.spec_document_id,
    or_(
        Task.loop_id.is_(None),
        and_(Task.loop_id.in_(gone), Task.status.not_in(TERMINAL_STATUSES)),
    ),
).values(loop_id=loop.id)
```

- **Unfinished only.** An `approved` or `rejected` task is done; its old loop is the true record of
  who ran it, and the successor has nothing to do with it. Every other status is work the successor
  must be able to see: `pending` and `assigned` it will staff, `completed` and `under_review` a
  flow will review, `in_progress` it will treat as work in flight.
- **Unassigned or not.** An `in_progress` task held by the gone loop's agent moves to the successor
  still assigned. That is the successor's normal in-flight state, and it ends the staffing gate's
  "unreachable holding" for that agent (`scheduler.py:1165-1180`), which is the ratchet LoopEngine
  froze on.
- **A live loop's tasks are never taken**, as today: the partial unique index and
  `_check_spec_document_conflict` already allow only one live loop per document, and the `gone`
  subquery names archived loops only.
- **Live means not archived.** A loop that has ended (`ending_state` set) but has not been archived
  still holds its document. `_check_spec_document_conflict` filters on `archived_at IS NULL` only
  (`jobs.py:166-170`), and so does the partial index. A successor is refused until the operator
  archives the ended loop. That is deliberate: archiving is the operator's statement that the loop is
  finished with its document, and adoption must not take tasks from a loop the operator can still
  read as current.

## D6 — The move is recorded against both loops

Adoption changes `loop_id` on existing tasks, so after it `GET /tasks?loop_id=<archived loop>` no
longer lists them. The spec's promise that an archived loop's queue history is *"still retrievable"*
would then be false. `_adopt_document_tasks` therefore selects the ids it is about to move from an
archived loop (grouped by their old `loop_id`, since several archived loops may have held tasks of
the document). For each old loop it writes two `EventLog` rows with
`persist_event(..., event_type="loop_tasks_adopted", data={"from_loop", "to_loop", "task_ids"},
commit=False)` (`hub/hub/utils.py:32`):
one with `loop_id=<from_loop>` and one with `loop_id=<to_loop>`. Two rows are needed because
`EventLog.loop_id` is a single column (`hub/hub/db/models.py`, `class EventLog`, indexed by
`ix_event_logs_loop_ts`), and `GET /loops/{id}` reads its events by `EventLog.loop_id == loop.id`
(`hub/hub/api/v1/loops.py:78-83`).

The rows go into the caller's transaction, before the commit at `jobs.py:764` (create) or the
PATCH's own commit (`:1027`). An `IntegrityError` rollback (`jobs.py:765-770`) then discards the move
and its events together. Tasks that were unowned (`loop_id IS NULL`) are adopted as today and write
no event, because no loop's history loses anything. The detail view's event list is capped at ten
(`loops.py:81`), so the durable record is the `event_logs` rows, not that view.

## D7 — An adopted task whose assignee is archived is a stall, not a briefing

Keeping the assignee (the operator's decision) means an adopted `in_progress` task can name an
agent that has been archived since. On HEAD the walk's `if task.assignee:` arm
(`scheduler.py:1839-1843`) takes `agent = task.assignee` without checking its lifecycle. The firing
then selects the task for that agent, and the turn is refused at the trigger (`agent_trigger.py:696-707`:
*"… is archived and cannot be triggered. Unarchive it first."*). Nothing on the loop says why its
queue does not move. That is read, not measured; task 1.10 measures it.

The fix is in that arm. When the assignee is archived, append
`(task.id, f"{task.id} is held by {agent}, who is archived; unarchive {agent} or reassign the task")`
to `unstaffed` and `continue`. The F64 rule promotes `unstaffed[0][1]` to `stall_reason`
(`scheduler.py:1803`). Neither the task nor its assignee is changed: resetting either is a transition
nobody performed. The archived names come from one query per walk,
`select(Agent.name).where(Agent.project_id == project_id, Agent.lifecycle == "archived")`. That is
the complement of the roster filter at `scheduler.py:1185`, which drops archived agents and so
cannot answer this question.

## D2 — Why not release at archive (option b)

F53's own write-up offered (b): clear `loop_id` at archive for tasks never started. Against it:

1. **It needs a backfill.** Loops archived before this ships keep their tasks, so (b) needs a
   migration to un-strand them. D1 recovers them the first time anyone claims the document.
2. **It destroys the record for no one.** Clearing `loop_id` on archive, when nobody is taking the
   tasks, removes the only link between them and the loop that held them.
3. **Two archive doors** (`jobs.py` and `loops.py`) would both need it. D1 has one door, the claim.

What (b) does better: tasks of a document nobody reclaims show as unowned rather than owned by a
dead loop. They are equally unworked either way, and the task board lists them regardless of loop.

## D3 — Materialise stamps a live loop, or none

```python
owning_loop = (await session.execute(
    select(Loop).where(
        Loop.project_id == document.project_id,
        Loop.spec_document_id == document.id,
        Loop.archived_at.is_(None),
    )
)).scalars().first()
```

At most one row can match (the partial unique index `ux_loops_spec_document_live`, migration
`0090`), so `.first()` is no longer a coin flip. With no live loop the tasks get `loop_id = NULL`, and
the next loop to claim the document adopts them under today's rule.

## D4 — A create refuses a document on a job that is not a loop

Beside the `work_needs_evidence` refusal (`jobs.py:621-631`), before the job row:

```python
if body.spec_document_id is not None and not _loop_opts_in(
    body.purpose, body.stop_at, body.stop_when_queue_empties
):
    raise HTTPException(400, "spec_document_id describes a loop; give this job a purpose or a "
                             "stop condition to make it one")
```

**Why refuse rather than let the document opt the job in:** the requirement's opt-in rule is *"at
least one of purpose, a stop time, or a queue-emptiness stop condition"*, and PATCH already refuses
the document alone. Letting it opt in on create would split the two doors the other way. **Who is
affected:** no product surface. The MCP tools always opt in (Context), and the UI has no job-create
form that sends a document (`grep -rn spec_document_id hub/ui/src/api` finds only task queries). A
raw API caller that sent one was getting a job that silently did not do what it asked.

## D5 — What each route returns when the new code raises

- `_adopt_document_tasks` runs inside the create/PATCH transaction before its commit
  (`jobs.py:762-764`, `:1027`). A raise there propagates as today (500): the loop is not
  committed, but on create the job row already was, at `:734`. That is F54's shape and predates this
  change. R2 should check whether the widened `UPDATE` adds any new way to raise; it adds a subquery,
  not a new write.
- D4 raises before any write.

## Open questions

None. The former question 1 (does an adopted `in_progress` task keep its assignee?) was decided by
the operator on 2026-09-24: keep it. D7 covers the case where that assignee is archived.

## Round log

- R1 2026-09-24: written.
- R2 2026-09-24: re-read adoption (`jobs.py:239-270`, calls `:762`, `:1027`), the create order
  (job committed at `:734` before `_check_spec_document_conflict`, so D4 must sit before `:734`, as
  written), materialise (`spec_tasks.py:176-180`, no `archived_at`/project filter), the partial index
  (`ux_loops_spec_document_live`, migration `0090`) and the staffing gate (`scheduler.py:1162-1180`).
  Use the canonical `task_transitions.TERMINAL_STATUSES` (same set as `task_transition_service.py:736`).
  **Interactions checked:** B10's `a-loop-is-stopped-archived-and-delegated-from-its-own-tab` adds
  events and a tab over the same two archive doors and changes no ownership, so D1 (adopt on claim)
  and D3 (materialise stamps only a live loop) compose with it; B2's firing changes touch neither
  materialise nor `loop_id`. B1's `a-task-is-attended-only-by-a-turn-that-will-reach-it` changes the
  `queued` half of the staffing gate's `reachable` test; D1 changes the `loop_id in live` half:
  independent, no text collision. No claim disagreed.
- Operator review 2026-09-24 (`spec-queue/tracks/reviews/B11-2026-09-24.md` §5), applied on
  `09127ba`: three MODIFIED deltas, D6 (`loop_tasks_adopted`), D7 (archived assignee), the
  ended-but-not-archived note in D1, and Open Question 1 closed. Citations re-checked on `09127ba`:
  `jobs.py:166-170`, `:239-270` (filter `:266`), `:762`, `:765-770`, `:1027`, `:1275-1285`;
  `loops.py:78-83`, `:152`; `scheduler.py:1803`, `:1839-1843`, `:1185`; `agent_trigger.py:696-707`;
  `utils.py:32` (`persist_event(..., loop_id=, commit=)`).
