# Tasks — Many named loops

## 1. Migration `0075`

- [ ] 1.1 New file `hub/hub/migrations/versions/0075_add_loops_and_traceability.py`,
      `down_revision = "0074"`. Three additive changes, none touching an existing constraint, so
      none needs a `batch_alter_table` recreate (unlike `0074`):
      (a) `CREATE TABLE loops` — `id` PK, `project_id` FK to `projects.id`, `job_id` FK to
      `ai_jobs.id` with `ondelete="CASCADE"`, `UNIQUE`, `purpose` TEXT NOT NULL default `''`,
      `stop_at` DATETIME nullable, `stop_when_queue_empties` BOOLEAN NOT NULL default `0`,
      `stop_reason` TEXT nullable, `stopped_at` DATETIME nullable, `created_at` DATETIME NOT NULL,
      `created_by_run_id`/`updated_by_run_id` VARCHAR(64) nullable, index on `project_id`.
      (b) `ALTER TABLE tasks ADD COLUMN loop_id VARCHAR(64)` nullable, no FK (design D2), plus
      `CREATE INDEX ix_tasks_loop_id`.
      (c) `ALTER TABLE job_runs ADD COLUMN conversation_id VARCHAR(64)` nullable, no FK (design D3).
      Guard every step for a missing table the way `0071`/`0073` do — an upgrade starting from an
      early revision reaches `0075` with only the tables those revisions created.
- [ ] 1.2 `downgrade()`: drop `ix_tasks_loop_id` and `tasks.loop_id`, drop `job_runs.conversation_id`,
      drop `loops` — same missing-table guard on each step.
- [ ] 1.3 Run `alembic upgrade head` then `alembic downgrade -1` then `alembic upgrade head` against a
      scratch SQLite file to confirm both directions actually execute, not merely parse — the same
      check `0071`'s and `0073`'s own history record catching real bugs this way.

## 2. Model (`hub/hub/db/models.py`)

- [ ] 2.1 Add `Loop` per design D1, placed near `AIJob`/`JobRun`. Add `runs: Mapped[List["Loop"]]`-
      style back-reference only if a call site needs `AIJob.loop` — check before adding; do not add
      an unused relationship attribute.
- [ ] 2.2 `Task.loop_id` per design D2, beside the existing `spec_document_id`/`spec_task_key` block,
      with the same "deliberately not a ForeignKey" comment reasoning stated once rather than
      silently duplicated without explanation.
- [ ] 2.3 `JobRun.conversation_id` per design D3, beside `session_id`, with a comment distinguishing
      the two: `session_id` is the *resume input*, `conversation_id` is *what this firing actually
      used* — the confusion this proposal's own `Why` names as the reason `JobRun` could not answer
      "what did this firing do" before.

## 3. Scheduler (`hub/hub/scheduler.py`)

- [ ] 3.1 `_do_fire_job`: pass `conversation_id=conversation.id` to the existing `JobRun(...)`
      construction (design D3) — the one-line change.
- [ ] 3.2 New `_loop_stop_reason(session, job)` per design D4, checked in `_do_fire_job` alongside
      the existing `_job_agent_skip_reason` call, before the queue entry is created.
- [ ] 3.3 When `_loop_stop_reason` returns non-`None`: write the `JobRun` as `status="skipped"` with
      that reason (reusing the existing skip-write path `_job_agent_skip_reason` already uses —
      confirm by reading whether that path is a shared helper or duplicated per skip-reason before
      writing a second copy); additionally stamp `loop.stop_reason`/`loop.stopped_at`, set
      `job.enabled = False`, call `self.scheduler.remove_job(job_id)` (via `get_scheduler()`, mirroring
      how `_do_fire_job` already reaches the scheduler singleton from inside itself if it does, or via
      the caller if it does not — read `_fire_job_by_id`/`_fire_job_internal`'s existing call chain
      before assuming which layer has scheduler access), and broadcast a new `loop_stopped` SSE event
      (`{"job_id", "loop_id", "reason"}`) alongside the existing `job_run_skipped` broadcast/persisted
      event.
- [ ] 3.4 Confirm `run_count`/`last_run`/`next_run` bookkeeping still happens even when a fire is
      skipped for a loop's own stop reason — read the existing `_job_agent_skip_reason` skip path to
      see whether it already updates these before returning, and follow the same choice for
      consistency rather than deciding independently.

## 4. API (`hub/hub/api/v1/jobs.py`, `hub/hub/schemas/jobs.py`, `hub/hub/api/v1/tasks.py`)

- [ ] 4.1 `JobCreate` gains `purpose: Optional[str]`, `stop_at: Optional[datetime]`,
      `stop_when_queue_empties: bool = False` (design D6). `JobUpdate` gains the same three plus
      `stop_reason: Optional[str]`.
- [ ] 4.2 `create_job`: after the existing `AIJob` is committed, create a `Loop` row iff at least one
      of the three fields was supplied non-default (`purpose is not None or stop_at is not None or
      stop_when_queue_empties is True`) — the "at least one field" rule from design D6, stated once
      here and reused by 4.3 rather than two independent implementations of the same rule.
- [ ] 4.3 `update_job`: if any of the four loop fields is supplied and the job has no `Loop` row,
      raise `400` (design D6's explicit-rejection rule) *before* creating one implicitly — except
      when the update is the one that opts the job in for the first time (mirror 4.2's rule: creating
      a `Loop` row on first `PATCH` that supplies a loop field is allowed, matching "opting in at
      creation or afterward" from the spec delta's own first requirement); apply supplied fields to
      the existing or newly-created row.
- [ ] 4.4 `LoopSummary` schema (design D5) and `JobResponse.loop: Optional[LoopSummary] = None`.
      `list_jobs`/`get_job`: when a job has a `Loop` row, compute `queue` (group `Task` by `status`
      where `loop_id` matches), `current_task` (design D5's derivation), `open_questions` (design
      D3's join-via-`JobRun.conversation_id` query) and populate `LoopSummary`; leave `loop: None`
      otherwise. Watch `list_jobs`' existing `N+1` shape — it is already one query per job for
      history in `get_job` but not in `list_jobs`; do not silently turn `list_jobs` into one query
      per job per loop-derived field without at least noting the cost in this task's own log entry.
- [ ] 4.5 `hub/hub/api/v1/tasks.py`: `list_tasks` gains `loop_id: Optional[str] = Query(None)`,
      applied as a third `elif` arm per design D2. Check `hub/hub/api/v1/agent_actions.py`'s
      `list_shared_tasks` — the D7 regression from `-the-board-scoped-by-document` was exactly a
      direct-function-call site not forwarding a new parameter and binding it to FastAPI's raw
      `Query(...)` sentinel; forward `loop_id=None` explicitly there, do not assume it is unaffected
      because that assumption was already wrong once tonight.

## 5. UI (`hub/ui/src`)

- [ ] 5.1 `hub/ui/src/api/jobs.ts`: extend the `Job` type with the optional `loop` field; extend
      `JobCreate`/`JobUpdate` request shapes with the three/four loop fields.
- [ ] 5.2 `hub/ui/src/api/tasks.ts`: `useTasks()` options gain `loopId?: string`, applied the same
      way `specDocumentId`/`excludeArchivedCompleted` already are; add `useLoopTasks(loopId)` mirroring
      `useDocumentTasks`, or confirm `useTasks({ loopId })` alone already covers `JobCard`'s need
      before adding a second hook that does the same thing under a different name.
- [ ] 5.3 `hub/ui/src/components/jobs/JobForm.tsx`: collapsed-by-default "Make this a loop" section —
      purpose (textarea), stop time (datetime input), "stop when queue is empty" (checkbox).
- [ ] 5.4 `hub/ui/src/components/jobs/JobCard.tsx`: render a loop block when `job.loop` is present —
      purpose, stop condition/reason if stopped, queue counts by status, current item (title +
      status, linking into the task board scoped to `?loop_id=`), open-questions count. No change to
      a plain job's card.
- [ ] 5.5 `cd hub/ui && npm run build && python ../../scripts/refresh_ui_bundle.py`, twice — once
      before commit, once after, per the standing rule this session has now hit on N2 and N2b both
      (the fingerprint folds in `git status --porcelain`).

## 6. Tests — agent-verifiable

- [ ] 6.1 `hub/tests/test_migrations.py`, `hub/tests/test_project_persistence.py`: bump the head
      assertion from `"0074"` to `"0075"` (three occurrences in the first file per this session's own
      earlier grep, one in the second — recount before editing, do not assume the count held across
      `0074`'s own landing).
- [ ] 6.2 `hub/tests/test_jobs.py` (or wherever job CRUD is already tested — confirm the file before
      assuming its name): creating a job with no loop field yields `loop: null`; creating one with
      `purpose` alone yields a `Loop` row and `loop.purpose` in the response; `PATCH` supplying a
      loop field on a plain job is `400`; `PATCH` supplying a loop field on a job with an existing
      loop updates it.
- [ ] 6.3 Same file or a new one: `_loop_stop_reason` — a loop with `stop_at` in the past causes the
      next fire to be skipped, `job.enabled` becomes `False`, `loop.stop_reason`/`stopped_at` are set,
      and a subsequent manual `run_job` call also refuses (still disabled) rather than firing anyway.
      A loop with `stop_when_queue_empties=True` and zero non-terminal `Task`s naming it stops the
      same way; one with a single `pending` task does not stop.
- [ ] 6.4 `hub/tests/test_tasks.py`: `GET /tasks?loop_id=X` returns exactly the tasks naming that
      loop regardless of status, mirroring 3.1's own `spec_document_id` test shape from the prior
      change. Confirm `GET /api/v1/agent-actions/tasks` (the D7 regression's actual live surface)
      still returns `200` after 4.5's change, not just the direct-router test.
- [ ] 6.5 UI: `hub/ui/src/__tests__/` — a test for `JobCard`'s loop block rendering (present when
      `job.loop` is set, absent otherwise, queue counts and current item shown correctly) and for
      `useTasks({ loopId })`/whatever hook 5.2 lands on requesting the right query string.
- [ ] 6.6 `pytest hub/tests/ -n 8` and `pytest tests/ -n 4` — record counts against this session's
      `20e963e` baseline (2093/11, 362/3) in the log.
- [ ] 6.7 `cd hub/ui && npm test && npm run lint && npx tsc --noEmit` — record counts against the
      `943/943` baseline.
- [ ] 6.8 `ruff check hub/ src/`, `black --check` on every touched file.
- [ ] 6.9 `npx openspec validate --changes --strict` and `--specs --strict` — both clean.

## 7. Driven against the running Hub

Restart the trial Hub onto the implementing commit first. Per this session's own finding on N2b:
check the owning process's `CreationDate` against the commit being tested, not only `/health`'s
status field — a stale process from an earlier iteration can keep answering `/health: ok` while
running old code.

- [ ] 7.1 Create a job with a `stop_when_queue_empties` loop and no tasks naming it yet; fire it
      manually (`POST /jobs/{id}/run`) and confirm the fire is skipped, `loop.stop_reason` names the
      empty queue, and the job's `enabled` flips to `false` in a subsequent `GET`.
- [ ] 7.2 Create a second loop, add a `Task` naming it via `spec_document_id`-free direct creation
      (or via whatever the actual task-creation path in this session's environment supports —
      directly-minted run credential, matching N2/N2b's own verification technique), fire the job,
      confirm the fire proceeds (queue not empty) and `JobRun.conversation_id` is populated —
      recorded by checking `GET /jobs/{id}` history entries carry a conversation id, or by a direct
      DB read if the history schema does not surface it (check `JobRunResponse` before assuming).
- [ ] 7.3 `GET /tasks?loop_id=<loop>` returns the seeded task; `GET /jobs/{id}` shows `loop.queue`,
      `loop.current_task` reflecting it.
- [ ] 7.4 Teardown: delete every row this verification created, confirm `git status` clean afterward
      (this repo is the trial project's own working directory, per this session's standing practice).

## 8. Human-only verification

- [ ] 8.1 **Does a plain job's card look unchanged?** Open the Jobs page with a mix of loop and
      non-loop jobs; confirm a job created before this change (or created without loop fields) shows
      no loop block, no visual regression in its existing layout.
- [ ] 8.2 **Does the loop block read as "this job, plus a purpose and a stop condition," not as a
      second, competing concept on the card?** It should feel like an extension of the job it is
      attached to, not a different kind of thing bolted on beside it.

## 9. User test guide

**Setup.** Hub running on `:8010`. A project with the agent-job allowance enabled (or operator-driven
creation, which needs none).

1. **Create a loop.** In the Jobs page, create a new job, expand "Make this a loop," give it a
   purpose and check "stop when queue is empty," save.
   - *Expect:* the job's card shows the purpose and an empty queue (0 tasks).
2. **Give it work.** Create a task (via the board or an agent) naming this loop.
   - *Expect:* the job card's queue count updates to reflect one pending task, shown as the current
     item.
3. **Finish the work.** Move that task to a terminal status (approve or reject it).
   - *Expect:* the queue count drops to zero open tasks; the current item clears.
4. **The loop stops itself.** Either wait for the job's next cron fire or trigger it manually ("Run"
   on the card).
   - *Expect:* the fire does not start a new conversation; the card now shows the loop as stopped,
     with a reason naming the empty queue, and the "Active" badge is gone.
5. **A plain job is unaffected.** Create a second job without expanding the loop section.
   - *Expect:* its card never shows a loop block, at any point in this walkthrough.

**Where it would go wrong:** if step 4 fires anyway, the stop-condition check (task 3.2/3.3) is not
wired into the fire path, or is checking the wrong field; if step 2's queue count never updates, task
4.5's `loop_id` scope or 4.4's queue-summary query is not reading `Task.loop_id` correctly; if step 5
shows a loop block on a plain job, task 4.2's "at least one field" gate is creating a `Loop` row
unconditionally.
