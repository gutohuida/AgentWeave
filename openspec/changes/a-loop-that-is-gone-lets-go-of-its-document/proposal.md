# Proposal — a loop that is gone lets go of its document

**Round 1, 2026-09-24** (bundle B11, `spec-queue/tracks/B11.md`). Findings: **F53 (B)**, the
tasks half, and **F157 (C)**. Both are about how a job comes to hold, or silently fails to hold, a
specification document, and both edit `hub/hub/api/v1/jobs.py`'s claim path and `agent-loops`. Re-
verified on `ce086b6`. R1 also found a third defect of the same kind, in `spec_tasks.materialise`
(below, and design D3). **Nothing here is implemented yet.**

## Why

**F53: an archived loop keeps its tasks forever.** `2239f38` (2026-08-26) fixed the document half:
`_check_spec_document_conflict` ignores archived loops (`jobs.py:166-170`), and a partial unique index
allows a new loop on the same document. The tasks half is open. `_adopt_document_tasks`
(`jobs.py:239-270`) adopts only tasks with `loop_id IS NULL` (`:266`). Archiving (`jobs.py:1275-1285`
through the job, `loops.py:173-181` directly) clears nothing. So a replacement loop on the same
document starts with an empty queue, and the old loop's unfinished tasks are invisible to every
loop-queue query, which reads `Task.loop_id == loop.id` (`scheduler.py:329, 402, 787, 2258, 2766`).
The finding reproduced it in three API calls. `jobs.py:155-163` names the open half and leaves it
*"for the operator"*.

**A third defect, found by R1: new tasks can be stamped with a dead loop.**
`spec_tasks.materialise` resolves the owning loop by document alone:
`select(Loop).where(Loop.spec_document_id == document.id)` then `.first()` (`spec_tasks.py:176-180`).
There is no `archived_at` filter, no project filter, and no ordering. Since `2239f38` allowed a
second loop on a document, a later approval that materialises more tasks can pick the archived loop,
and those tasks are stranded from birth. Read, not measured; task 1.4 measures it.

**F157: a document named on a job that is not a loop is silently dropped.** `create_job` reads
`spec_document_id` only inside `if _loop_opts_in(...)` (`jobs.py:746-763`), so
`POST /jobs {…, spec_document_id}` with no purpose or stop condition answers **201** with no loop and
no document. `PATCH` refuses the same field on a non-loop job (`jobs.py:989-1011`). `create_job`'s
own comment names the asymmetry (`:614-619`), and so does `hub/tests/test_jobs_crud.py:602`. The
refusal for `work_needs_evidence` on the same route (`:621-631`) is the precedent.

## What Changes

- **A loop claiming a document adopts the tasks a gone loop left** (design D1). `_adopt_document_tasks`
  also takes tasks of that document whose loop is archived and whose status is not terminal
  (`approved`, `rejected`, `task_transition_service.py:736`). Terminal tasks keep their old loop as
  history. Tasks a **live** loop owns are still never taken.
- **Archiving changes nothing** (design D2). The release happens when a successor claims, so
  archive stays a pure retire, and tasks already stranded in real databases are recovered by
  creating a new loop, with no backfill.
- **Materialise stamps only a live loop** (design D3): `Loop.archived_at IS NULL` and the document's
  project, in the owning-loop query.
- **`POST /jobs` refuses a document on a job that is not a loop** (design D4), with the sentence the
  `PATCH` door and `work_needs_evidence` already use, before the job row is written.

- **The move is recorded** (design D6): a `loop_tasks_adopted` event `{from_loop, to_loop,
  task_ids}` is persisted against both loops in the claim's transaction, so the archived loop's
  queue history survives.
- **An adopted task whose assignee is archived is reported, not briefed** (design D7): the
  successor's stall reason names the task and the archived agent.

No migration, no UI. One API behaviour change: a create that silently dropped a field is now a 400.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-loops`: *A recurring job may be named as a loop…* (the refusal covers creation as well as
  update) and *A flow adopts the tasks already materialised from the document it claims* (an
  archived loop's unfinished tasks are adoptable; tasks are only ever stamped with a live loop).
  Added after the operator review of 2026-09-24: *A loop's queue is the tasks that name it…*
  (claim-time adoption is the third writer of `loop_id`), *A loop MAY declare one specification
  document…* (one **live** loop per document; the live declaring loop is stamped), and *A loop and a
  job are archivable, never deletable* (history survives adoption as a `loop_tasks_adopted` event).

## Impact

- `hub/hub/api/v1/jobs.py` (`_adopt_document_tasks`, `create_job`'s pre-write checks, the comments
  at `:155-163` and `:614-619`), `hub/hub/spec_tasks.py:176-180`.
- `hub/tests/`: a new `test_a_gone_loop_lets_go.py`, and `test_jobs_crud.py:600-604`'s docstring.
- **Interaction with the operator's loop-ownership model** (`openspec/explorations/2026-09-14-who-owns-a-loops-queue.md`): unaffected. That
  model is about tasks born inside a live loop; this is about tasks a dead loop holds.
