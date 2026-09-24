# Design — a loop that is gone lets go of its document

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

1. Should an `in_progress` task adopted from a gone loop keep its assignee (D1), or return to
   `pending` unassigned? Recommended: keep it. Resetting it is a transition nobody performed, and the
   transition machine would have to be bypassed to do it.

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
