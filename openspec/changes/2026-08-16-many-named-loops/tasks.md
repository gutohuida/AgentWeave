# Tasks — Many named loops

## 1. Migration `0075`

- [x] 1.1 New file `hub/hub/migrations/versions/0075_add_loops_and_traceability.py`,
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
- [x] 1.2 `downgrade()`: drop `ix_tasks_loop_id` and `tasks.loop_id`, drop `job_runs.conversation_id`,
      drop `loops` — same missing-table guard on each step.
- [x] 1.3 Run `alembic upgrade head` then `alembic downgrade -1` then `alembic upgrade head` against a
      scratch SQLite file to confirm both directions actually execute, not merely parse — the same
      check `0071`'s and `0073`'s own history record catching real bugs this way. Verified live this
      iteration: all three steps ran clean against a scratch file at `%TEMP%\aw_0075_test.db`
      (upgrade to 0075, downgrade to 0074, upgrade back to 0075), file deleted after.

## 2. Model (`hub/hub/db/models.py`)

- [x] 2.1 Add `Loop` per design D1, placed near `AIJob`/`JobRun`. Add `runs: Mapped[List["Loop"]]`-
      style back-reference only if a call site needs `AIJob.loop` — check before adding; do not add
      an unused relationship attribute. No call site in this slice needs it (the scheduler queries
      `Loop` directly by `job_id`, matching design D4's own code) — no back-reference added.
- [x] 2.2 `Task.loop_id` per design D2, beside the existing `spec_document_id`/`spec_task_key` block,
      with the same "deliberately not a ForeignKey" comment reasoning stated once rather than
      silently duplicated without explanation.
- [x] 2.3 `JobRun.conversation_id` per design D3, beside `session_id`, with a comment distinguishing
      the two: `session_id` is the *resume input*, `conversation_id` is *what this firing actually
      used* — the confusion this proposal's own `Why` names as the reason `JobRun` could not answer
      "what did this firing do" before.

## 3. Scheduler (`hub/hub/scheduler.py`)

- [x] 3.1 `_do_fire_job`: pass `conversation_id=conversation.id` to the existing `JobRun(...)`
      construction (design D3) — the one-line change.
- [x] 3.2 New `_loop_stop_reason(session, job)` per design D4, checked in `_do_fire_job` alongside
      the existing `_job_agent_skip_reason` call, before the queue entry is created.
- [x] 3.3 When `_loop_stop_reason` returns non-`None`: write the `JobRun` as `status="skipped"` with
      that reason (reusing the existing skip-write path `_job_agent_skip_reason` already uses —
      confirmed by reading: it is inline code at each call site, not a shared helper, so the loop path
      is a second inline copy with the loop-specific additions, matching the existing pattern rather
      than inventing a new one); additionally stamps `loop.stop_reason`/`loop.stopped_at`, sets
      `job.enabled = False`, calls `self.remove_job(job.id)` (confirmed `_do_fire_job` is itself a
      `JobScheduler` method with its own `remove_job` wrapper already defined on the class — `self.
      remove_job`, not `get_scheduler()`, which is only used by the module-level `_scheduled_job_runner`
      outside the class), and broadcasts a new `loop_stopped` SSE event (`{"job_id", "loop_id",
      "reason"}`) alongside the existing `job_run_skipped` persisted event (confirmed: `job_run_skipped`
      is persisted only, never broadcast via SSE, in the existing agent-skip path either — matched that
      precedent rather than the design prose's looser "persisted and broadcast" phrasing).
- [x] 3.4 Confirm `run_count`/`last_run`/`next_run` bookkeeping still happens even when a fire is
      skipped for a loop's own stop reason — confirmed: `job.last_run`/`job.run_count`/`job.next_run`
      are all updated unconditionally at lines 296-298 (fire time, unaffected by which skip path is
      taken later), before either the agent-skip or the new loop-stop check.

## 4. API (`hub/hub/api/v1/jobs.py`, `hub/hub/schemas/jobs.py`, `hub/hub/api/v1/tasks.py`)

- [x] 4.1 `JobCreate` gains `purpose: Optional[str]`, `stop_at: Optional[datetime]`,
      `stop_when_queue_empties: bool = False` (design D6). `JobUpdate` gains the same three plus
      `stop_reason: Optional[str]`.
- [x] 4.2 `create_job`: after the existing `AIJob` is committed, create a `Loop` row iff at least one
      of the three fields was supplied non-default (`purpose is not None or stop_at is not None or
      stop_when_queue_empties is True`) — the "at least one field" rule from design D6, stated once
      here and reused by 4.3 rather than two independent implementations of the same rule.
- [x] 4.3 `update_job`: if any of the four loop fields is supplied and the job has no `Loop` row,
      raise `400` (design D6's explicit-rejection rule) *before* creating one implicitly — except
      when the update is the one that opts the job in for the first time (mirror 4.2's rule: creating
      a `Loop` row on first `PATCH` that supplies a loop field is allowed, matching "opting in at
      creation or afterward" from the spec delta's own first requirement); apply supplied fields to
      the existing or newly-created row.
- [x] 4.4 `LoopSummary` schema (design D5) and `JobResponse.loop: Optional[LoopSummary] = None`.
      `list_jobs`/`get_job`: implement per design D7 (added in round 2's cold review) — four batch
      queries over the full job/loop page, never one query per job per loop-derived field. `get_job`
      calls the same batch functions with a one-element id list rather than a separate single-job
      code path. `list_jobs` today runs exactly one query (confirmed in round 2: it does not even
      fetch history the way `get_job` does), so this is the floor to hold, not merely a shape to
      "watch."
- [x] 4.5 `hub/hub/api/v1/tasks.py`: `list_tasks` gains `loop_id: Optional[str] = Query(None)`,
      applied as a third `elif` arm per design D2. Check `hub/hub/api/v1/agent_actions.py`'s
      `list_shared_tasks` — the D7 regression from `-the-board-scoped-by-document` was exactly a
      direct-function-call site not forwarding a new parameter and binding it to FastAPI's raw
      `Query(...)` sentinel; forward `loop_id=None` explicitly there, do not assume it is unaffected
      because that assumption was already wrong once tonight.

## 5. UI (`hub/ui/src`)

- [x] 5.1 `hub/ui/src/api/jobs.ts`: extend the `Job` type with the optional `loop` field; extend
      `JobCreate`/`JobUpdate` request shapes with the three/four loop fields, all optional and
      **omitted from the request body**, not sent as `""`/`false`, when the loop section (5.3) is
      collapsed. Design D6's opt-in rule is `purpose is not None` server-side — a controlled form
      that always serialises its (empty) textarea state as `purpose: ""` would opt every job into
      being a loop the moment the request shape includes the field at all, regardless of whether the
      operator ever touched the collapsed section. Confirmed in round 2's cold review: this is a real
      client-side boundary, not merely a server-side one, since the server cannot distinguish "sent
      empty on purpose" from "sent empty because the form always sends it." Implemented via
      `JobForm.tsx`'s spread-only-when-`loopEnabled` shape (5.3). ALSO FIXED THIS SLICE: `LoopSummary`
      (both `hub/hub/schemas/jobs.py` and `hub/ui/src/api/jobs.ts`) was missing its own `id` — the
      design never gave the frontend a way to build `?loop_id=<loop id>` at all, since `Task.loop_id`
      scopes by the `Loop` row's own id, not the job's. Added `id: str`/`id: string` and populated it
      at both `LoopSummary(...)` call sites in `hub/hub/api/v1/jobs.py` (`_batch_loop_summaries` and
      `create_job`'s zero-history construction).
- [x] 5.2 `hub/ui/src/api/tasks.ts`: `useTasks()` options gain `loopId?: string`, applied the same
      way `specDocumentId`/`excludeArchivedCompleted` already are; add `useLoopTasks(loopId)` mirroring
      `useDocumentTasks`, or confirm `useTasks({ loopId })` alone already covers `JobCard`'s need
      before adding a second hook that does the same thing under a different name. Confirmed:
      `useTasks({ loopId })` alone covers it — no second hook. `loopId` takes priority over
      `excludeArchivedCompleted` in the querystring builder, matching the server's `elif` chain
      (design D2): passing both is not meaningful, so the client never sends both.
- [x] 5.3 `hub/ui/src/components/jobs/JobForm.tsx`: collapsed-by-default "Make this a loop" section —
      purpose (textarea), stop time (datetime input), "stop when queue is empty" (checkbox). Loop
      fields spread into the `onSubmit` payload only when the section was expanded (`loopEnabled`),
      never as empty-string/false defaults.
- [x] 5.4 `hub/ui/src/components/jobs/JobCard.tsx`: render a loop block when `job.loop` is present —
      purpose, stop condition/reason if stopped, queue counts by status, current item (title +
      status, linking into the task board scoped to `?loop_id=`), open-questions count. No change to
      a plain job's card. New `LoopBlock` sub-component owns its own `useTasks({ loopId })` call so a
      plain job never triggers it; the current-item line is the click target that calls `onOpenTasks`
      with every task id the loop's fetch returned — the same `setActiveTaskIds` mechanism
      `SpecDocumentTasksLink` already proved (design D5). `onOpenTasks` threaded
      `App.tsx` → `JobsPage.tsx` → `JobCard.tsx`, identical shape to the existing spec-coverage wiring
      already in `App.tsx`.
- [x] 5.5 `cd hub/ui && npm run build && python ../../scripts/refresh_ui_bundle.py`, twice — once
      before commit, once after, per the standing rule this session has now hit on N2 and N2b both
      (the fingerprint folds in `git status --porcelain`).

## 6. Tests — agent-verifiable

- [x] 6.1 `hub/tests/test_migrations.py`, `hub/tests/test_project_persistence.py`: bump the head
      assertion from `"0074"` to `"0075"` (three occurrences in the first file per this session's own
      earlier grep, one in the second — recount before editing, do not assume the count held across
      `0074`'s own landing). Recounted: 11 occurrences in `test_migrations.py` (0074 landed with its
      own extra assertions), 1 in `test_project_persistence.py`. Also fixed the stale
      `f"expected alembic_version=0074..."` message text in two of those assertions, missed by a
      naive `"0074"` string replace since the message itself has no surrounding quotes.
- [x] 6.2 `hub/tests/test_jobs.py` (or wherever job CRUD is already tested — confirm the file before
      assuming its name): creating a job with no loop field yields `loop: null`; creating one with
      `purpose` alone yields a `Loop` row and `loop.purpose` in the response; `PATCH` supplying a
      loop field on a plain job is `400`; `PATCH` supplying a loop field on a job with an existing
      loop updates it.
- [x] 6.3 Same file or a new one: `_loop_stop_reason` — a loop with `stop_at` in the past causes the
      next fire to be skipped, `job.enabled` becomes `False`, `loop.stop_reason`/`stopped_at` are set,
      and a subsequent manual `run_job` call also refuses (still disabled) rather than firing anyway.
      A loop with `stop_when_queue_empties=True` whose queue has held a task and now has zero
      non-terminal ones stops the same way; one with a single `pending` task does not stop; one
      whose queue has never held a task does not stop either (design D4a).
- [x] 6.4 `hub/tests/test_tasks.py`: `GET /tasks?loop_id=X` returns exactly the tasks naming that
      loop regardless of status, mirroring 3.1's own `spec_document_id` test shape from the prior
      change. Confirm `GET /api/v1/agent-actions/tasks` (the D7 regression's actual live surface)
      still returns `200` after 4.5's change, not just the direct-router test.
- [x] 6.5 UI: `hub/ui/src/__tests__/` — a test for `JobCard`'s loop block rendering (present when
      `job.loop` is set, absent otherwise, queue counts and current item shown correctly) and for
      `useTasks({ loopId })`/whatever hook 5.2 lands on requesting the right query string.
      `jobCard.test.tsx` (new, 4 cases: no block for a plain job even expanded, full block with
      purpose/queue/current-item/open-questions, stopped state, click-through to `onOpenTasks` with
      every loop task id) plus one case added to the existing `tasksApi.test.tsx` for
      `useTasks({ loopId })`'s querystring, including that it wins over `excludeArchivedCompleted`
      when both are passed.
- [x] 6.6 `pytest hub/tests/ -n 8` and `pytest tests/ -n 4` — record counts against this session's
      `20e963e` baseline (2093/11, 362/3) in the log. Recorded this iteration: hub 2102/11 (unchanged —
      this slice touched only `jobs.py`'s schema/API adding `LoopSummary.id`, no new Python test; one
      `test_agent_trigger.py::test_spawn_failure_marks_run_failed` failure under `-n 8` reproduced the
      exact same known xdist flake `verified_green_at_20e963e` already named — confirmed by rerunning
      it standalone, passed), CLI 362/3 (unchanged, untouched by this slice).
- [x] 6.7 `cd hub/ui && npm test && npm run lint && npx tsc --noEmit` — record counts against the
      `943/943` baseline. `npm test`: 948/948 (943 baseline + 5 new: 4 `jobCard.test.tsx` + 1
      `tasksApi.test.tsx`). `npm run lint`: clean. `npx tsc --noEmit`: clean.
- [x] 6.8 `ruff check hub/ src/`, `black --check` on every touched file. Clean.
- [x] 6.9 `npx openspec validate --changes --strict` and `--specs --strict` — both clean (20/20, 30/30).

## 7. Driven against the running Hub

Restart the trial Hub onto the implementing commit first. Per this session's own finding on N2b:
check the owning process's `CreationDate` against the commit being tested, not only `/health`'s
status field — a stale process from an earlier iteration can keep answering `/health: ok` while
running old code.

- [ ] 7.1 Create a job with a `stop_when_queue_empties` loop, add a task naming it, take that task to
      a terminal status, then fire manually (`POST /jobs/{id}/run`) and confirm the fire is skipped,
      `loop.stop_reason` names the empty queue, and the job's `enabled` flips to `false` in a
      subsequent `GET`. Then repeat with a loop whose queue has *never* held a task and confirm the
      fire proceeds instead (design D4a).

      **Superseded and needs re-running.** The original 7.1 verified the no-tasks-yet case *stopping*
      the loop, and did so live against the trial Hub (restarted onto that commit first — confirmed
      by the owning PID's actual `CreationDate`, not just `/health`): manual fire returned `409` with
      `"loop queue is empty"`, and the subsequent `GET` showed `enabled: false`. That result was
      real, and it is now the wrong behaviour — the operator ruled on 2026-08-17 that the condition
      means drained rather than never-filled. `hub/tests/test_scheduler.py` covers both cases; the
      live re-run has not been done.
- [x] 7.2 Create a second loop, add a `Task` naming it via direct creation (`TaskCreate` has no
      client-settable `loop_id` — confirmed by reading the schema — so this used a direct SQLite
      insert, the same technique N2/N2b used for a run credential), fire the job, confirm the fire
      proceeds (queue not empty) and `JobRun.conversation_id` is populated. `JobRunResponse` and
      `get_job`'s hand-built history dict both omit `conversation_id` (checked before assuming, per
      the task's own instruction) — read directly from `job_runs` instead: populated on the row the
      fire created. The manual fire did not report the empty-queue skip (confirming `_loop_stop_reason`
      passed once the queue held one task); `trigger_agent_directly` then raised its own "no runner
      bound" `TriggerAgentError` for the placeholder agent name, caught by `schedule_agent` — no real
      process was spawned, and `conversation_id` was already committed before that call, so the
      no-runner outcome downstream does not affect what this task verifies.
- [x] 7.3 `GET /tasks?loop_id=<loop>` returns the seeded task; `GET /jobs/{id}` shows `loop.queue`,
      `loop.current_task` reflecting it. Verified: `queue.pending >= 1` and `current_task.id` matched
      the seeded task's id.
- [x] 7.4 Teardown: delete every row this verification created, confirm `git status` clean afterward
      (this repo is the trial project's own working directory, per this session's standing practice).
      Script (`testbed/scratch/n3_live_verify.py`, gitignored) deletes its own tasks/loops/jobs/runs
      in a `finally` block; `git status --porcelain` confirmed clean after the run — 16/16 checks
      passed.

## 8. Human-only verification

**Cannot be completed unattended — findable, not verified.** A live screenshot this iteration
(`?project=proj-5e960453&tab=jobs`, expanded card) shows a job named `screenshot-loop-demo` with a
green "Active" loop badge, its purpose text, "Queue: 1 pending: 1", and a blue clickable current-item
line — consistent with both items below, but an agent cannot judge "does this look unchanged" or
"does this read as an extension, not a second concept" the way an operator's own eye can. Left
unticked for the operator to confirm against a live Hub.

- [ ] 8.1 **Does a plain job's card look unchanged?** Open the Jobs page with a mix of loop and
      non-loop jobs; confirm a job created before this change (or created without loop fields) shows
      no loop block, no visual regression in its existing layout.
- [ ] 8.2 **Does the loop block read as "this job, plus a purpose and a stop condition," not as a
      second, competing concept on the card?** It should feel like an extension of the job it is
      attached to, not a different kind of thing bolted on beside it.

## 9. User test guide

**Checked this iteration against the actually-implemented UI** — a live screenshot of an expanded
`JobCard` with a purpose, one pending task and a clickable current item matched steps 1-2 exactly
(purpose text, "Queue: 1 pending: 1", the current item as a blue link). One correction made to step 4
below: a direct DB check after a manual fire that hit the empty-queue stop showed the scheduler still
creates a `Conversation` row before either skip check runs (`_do_fire_job` builds/reuses the
conversation at lines ~317-334, then checks `_job_agent_skip_reason` and `_loop_stop_reason`
afterward, committing whichever branch it takes together with the already-`session.add`-ed
conversation) — pre-existing scheduler behaviour, not introduced by this change, and true of the
older agent-skip path too. The row carries no message and triggers no turn, so "the agent is not
triggered" is accurate and is what the guide now says; "does not start a new conversation" was not.

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
   - *Expect:* the agent is not triggered and no turn is queued for it; the card now shows the loop as
     stopped, with a reason naming the empty queue, and the loop block's own "Active" badge becomes
     "Stopped" (the job's separate header badge changes from "Active" to "Paused" at the same time,
     since the fire also disabled the job).
5. **A plain job is unaffected.** Create a second job without expanding the loop section.
   - *Expect:* its card never shows a loop block, at any point in this walkthrough.

**Where it would go wrong:** if step 4 fires anyway, the stop-condition check (task 3.2/3.3) is not
wired into the fire path, or is checking the wrong field; if step 2's queue count never updates, task
4.5's `loop_id` scope or 4.4's queue-summary query is not reading `Task.loop_id` correctly; if step 5
shows a loop block on a plain job, task 4.2's "at least one field" gate is creating a `Loop` row
unconditionally.
