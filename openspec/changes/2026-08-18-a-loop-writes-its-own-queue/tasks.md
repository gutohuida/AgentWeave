# Tasks — A loop writes its own queue

Sections 1-12 are implemented and verified (dated notes below); everything from the addendum (A1
onward) and P4 onward is still a spec only, unchecked — CLAUDE.md: "Never mark a task complete on the
strength of a plan existing."

## 1. Migration

- [x] 1.1 New migration, `down_revision` = the current head. Two additive, nullable, unindexed-except-
      as-noted columns, no existing constraint touched — same "no `batch_alter_table` recreate needed"
      shape as `0075`:
      (a) `ALTER TABLE loops ADD COLUMN spec_document_id VARCHAR(64)` nullable, no FK (design D1),
      plus a unique index (`uq_loops_spec_document_id`) so at most one loop can declare a given
      document.
      (b) `ALTER TABLE checkpoints ADD COLUMN loop_id VARCHAR(64)` nullable, no FK (design D4), plus
      `CREATE INDEX ix_checkpoints_loop_id`.
      Guard each step for a missing table, matching `0071`/`0073`/`0075`'s own precedent for an
      upgrade starting from an early revision.

      **Done 2026-08-18** in `hub/hub/migrations/versions/0077_loop_declares_source_and_checkpoint_
      loop.py`, `down_revision = "0076"` (reconfirmed head via `alembic heads` before writing — single
      head, no sibling change had already taken it). Both columns guarded for a missing table, copied
      from `0075`'s exact pattern. **Naming departure from this task's own text, discovered while
      testing, not guessed:** the unique index on `loops.spec_document_id` is named
      `ix_loops_spec_document_id`, not `uq_loops_spec_document_id` as originally planned here. Reason:
      the model declares the column `unique=True, index=True` (matching `Run.capability_token_hash`'s
      existing shape in `models.py`), and SQLAlchemy's own naming convention for that shape produces
      `ix_<table>_<column>` when `Base.metadata.create_all` builds a brand-new database — which is
      exactly what `init_db` does for a fresh install before running `alembic upgrade head` (H5,
      `test_migrations.py`'s own docstring). A migration-created index under the originally-planned
      `uq_` name would not match what `create_all` produces, so a downgrade against a freshly-bootstrapped
      database would silently fail to find its own index and then fail to drop the column (SQLite
      refuses `ALTER TABLE ... DROP COLUMN` on a column still part of any index). Caught by task 1.3's
      own verification below, not assumed — the first version of this migration, named `uq_`, failed
      exactly that way.
- [x] 1.2 `downgrade()`: drop `ix_checkpoints_loop_id` and `checkpoints.loop_id`, drop
      `ix_loops_spec_document_id` (see 1.1's naming note) and `loops.spec_document_id` — same
      missing-table guard on each step. **Done 2026-08-18**, same file.
- [x] 1.3 Run `alembic upgrade head` then `alembic downgrade -1` then `alembic upgrade head` against a
      scratch SQLite file, confirming both directions actually execute — `0075`'s own precedent for
      catching a migration that parses but does not run.

      **Verified 2026-08-18, twice, against two different scratch files** (both under
      `%TEMP%\aw_scratch_*.db`, deleted after use, never this repo's `hub/data/agentweave.db`):
      (a) a pure sequential upgrade from a truly empty database (no `create_all`) — all three commands
      ran clean, but because `loops`/`checkpoints` are guarded on `projects`/`ai_jobs` existing and
      those in turn come from other guarded migrations, a database built by alembic alone never
      reaches the point of creating those tables at all until every earlier migration's own guard
      condition is satisfied in sequence, which this scratch run exercised end-to-end (0001→0077,
      then -1, then back to head) with no errors; (b) the realistic path — `Base.metadata.create_all`
      (what `init_db` does for a fresh install) then `alembic upgrade head`, then `downgrade -1`, then
      `upgrade head` again — which is what actually exercises the `ADD COLUMN`/`DROP COLUMN` branches
      non-trivially, since `create_all` alone already produces every column at HEAD shape. This run is
      what caught the naming bug in 1.1: the first version failed `downgrade -1` with `sqlite3.
      OperationalError: error in table loops after drop column: no such column: spec_document_id`
      because the named index the downgrade tried to drop first didn't match the autoindex `create_
      all` had actually built. Fixed per 1.1, then reran clean. Formalised as three pytest tests in
      `hub/tests/test_migrations.py` (`test_migration_0077_adds_the_loop_source_document_and_
      checkpoint_loop_binding`, `test_migration_0077_spec_document_id_is_unique_per_loop`,
      `test_migration_0077_downgrade_then_upgrade_round_trips` — the last seeds a real loop and a real
      checkpoint in both new columns before the round trip, not just empty tables) rather than left as
      a one-off manual run — see 2.2's verification for the full suite result.

## 2. Model (`hub/hub/db/models.py`)

- [x] 2.1 `Loop.spec_document_id` (design D1): nullable, `String(64)`, no ForeignKey, `unique=True`,
      placed beside `job_id`, with the same "deliberately not a ForeignKey" comment reasoning `Task.
      spec_document_id`/`loop_id` already state, referenced rather than re-derived.

      **Done 2026-08-18.** Also `index=True` (not stated in this task's original text — added per
      1.1's naming note, so the column's index matches what the migration creates by the same name on
      a database built via `create_all`).
- [x] 2.2 `Checkpoint.loop_id` (design D4): nullable, `String(64)`, no ForeignKey, indexed, placed
      beside `conversation_id`.

      **Done 2026-08-18.** Comment states it is stamped by `create_checkpoint` at write time, not
      derived at read time via a join — design D4's own reasoning, restated briefly rather than in
      full a third time.

      **Verification, measured (2.1 and 2.2 together):** `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py` head assertions bumped `0076` → `0077` per CLAUDE.md's
      "Adding a database column" checklist. `py -3.11 -m pytest hub/tests/test_migrations.py hub/tests/
      test_project_persistence.py -q` → **61 passed, 1 skipped** (the skip predates this change).
      `ruff check` and `black --check` clean on every touched Python file (`models.py`, the new
      migration, both test files). `mypy` on the new migration reports the same 3 "missing parameter
      annotation" errors `0075`'s own identical helper-function shape already has — confirmed by
      running mypy on `0075_add_loops_and_traceability.py` directly and comparing — so this is the
      established style for these migration helpers, not a new regression against the session's mypy
      baseline. Deliberately **not** run this iteration: the full `hub/pytest` suite (unchanged
      reasoning from prior iterations — this touches only migrations/models/tests, and the targeted
      run above already exercises every assertion those two files make about the schema).

## 3. Queue-write path 1 — specification materialisation (`hub/hub/spec_tasks.py`)

- [x] 3.1 `materialise()`: at the top, query `Loop` where `spec_document_id == document.id`. If found,
      every `Task` constructed in the function body gets `loop_id=loop.id` (design D1). No change to
      `materialise_quietly()`'s signature or error-swallowing behaviour.

      **Done 2026-08-18.** One query added at the top of `materialise()`, right after the early-return
      for an empty declaration — `select(Loop).where(Loop.spec_document_id == document.id)`, `.first()`
      since the column is unique. Every `Task(...)` constructed further down now sets
      `loop_id=owning_loop.id if owning_loop is not None else None`. `materialise_quietly()` reread
      before touching anything else — it only wraps `materialise()` in a try/except and returns `[]` on
      failure; confirmed unchanged, not assumed, by rereading the function body rather than trusting the
      docstring's own description of it.
- [x] 3.2 Tests: a document with a declaring loop materialises tasks carrying that loop's id; a
      document with no declaring loop materialises tasks with `loop_id=None`, unchanged from today;
      re-approving a revised document (the existing idempotency path, `existing_keys`) still stamps
      `loop_id` on newly-created tasks only, matching the existing "only what's new" guarantee.

      **Done 2026-08-18** in `hub/tests/test_spec_declared_tasks.py`, following that file's existing
      `app`/`auth_headers`/`author` fixture style rather than inventing a new one, and `test_scheduler.
      py`'s `_make_job`/`_make_loop` shape for constructing a real `AIJob` + `Loop` pair (a `Loop`
      requires a `job_id`; there is no `create_loop` endpoint yet — that is L11, still open — so the
      test constructs both rows directly via the ORM). Three new tests: (a)
      `test_a_document_with_a_declaring_loop_stamps_its_tasks_with_the_loop` — approves a document with
      a loop already declaring it, then confirms both created tasks are returned by the real
      `GET /tasks?loop_id=` filter (exercising the existing query-param path from L1's own model work,
      not a raw DB read); (b) `test_a_document_with_no_declaring_loop_stamps_nothing` — the default case,
      asserted directly against `Task.loop_id` since `TaskResponse` does not expose the field in JSON;
      (c) `test_re_approving_stamps_the_loop_only_on_newly_created_tasks` — approves once with **no**
      loop declared, *then* a loop declares the document, *then* a revision adds one new declared task
      and the document is re-approved — confirms the two original tasks still read `loop_id IS NULL`
      (never retroactively touched) while only the new one carries the loop's id.

      **Verification, measured:** `py -3.11 -m pytest hub/tests/test_spec_declared_tasks.py -q` — **11
      passed** (8 pre-existing + 3 new). Broader sweep `py -3.11 -m pytest hub/tests/test_spec*.py -q`
      — **301 passed**, confirming nothing else reading `materialise()`'s task output assumed the old
      always-`None` shape. `ruff check` and `black` clean on both touched files (`spec_tasks.py`,
      `test_spec_declared_tasks.py`) — black reformatted both once (wrapping the new `select(Loop)...`
      call and a dict comprehension ruff flagged as unnecessary, rewritten as `dict(rows)`), reverified
      clean after. `npx openspec validate --changes --strict`: 2/2 still pass.

## 4. Queue-write path 1, creation side — declaring a source document (`hub/hub/api/v1/jobs.py`,
   `hub/hub/schemas/jobs.py`)

- [x] 4.1 `JobCreate`/`JobUpdate` gain `spec_document_id: Optional[str]` (design D1). Creating or
      updating with a `spec_document_id` that another loop already holds SHALL 409, naming the
      conflicting loop (spec requirement "A document already claimed by one loop cannot be claimed by
      a second").

      **Done 2026-08-18.** Both schemas in `hub/hub/schemas/jobs.py` gained the field. A new
      `_check_spec_document_conflict(session, project_id, spec_document_id, *, exclude_loop_id=None)`
      helper in `hub/hub/api/v1/jobs.py` queries `Loop` scoped to `project_id` (matching every other
      query in this file) and 409s with `detail=f"document '{id}' is already claimed by loop
      '{conflicting.id}'"` — grepped the file first and matched the existing "Job with ID '{id}'
      already exists" 409's tone rather than inventing a new shape. Wired into both `create_job`
      (checked before the `Loop` row is added, only when the job opts into a loop at all — design D2:
      `spec_document_id` alone does not opt a plain job into a loop via this route, only the
      agent-facing `create_loop` tool (still open, L11) states that stricter contract) and `update_job`
      (checked with `exclude_loop_id=loop.id` so a no-op re-declare of a loop's own document does not
      409 against itself — the task's own "not just DB layer" framing implies exactly this
      operator-safe re-PATCH case). `update_job`'s existing `loop_fields_supplied` gate widened to five
      fields; `spec_document_id` alone still does not opt a plain job into a loop for the same D2
      reason, so it is gated the same way `stop_reason` already is. `create_job`'s `Loop` insert also
      gained an `IntegrityError` catch (409) as a race-condition backstop behind the pre-check, mirroring
      the file's own existing pattern immediately above it for the job-id conflict.
- [x] 4.2 Tests: declaring a source document on loop creation; a second loop attempting the same
      document is refused with the first loop's id named in the error; a loop can be created with no
      source document, unchanged from `many-named-loops`.

      **Done 2026-08-18**, `hub/tests/test_jobs.py` (the file `POST /jobs` and every existing loop test
      already lives in — grepped for `purpose=` and the POST route first rather than guessing a new
      file). Six new tests, three matching this task's own list exactly plus three covering the PATCH
      side of 4.1's own code, which would otherwise have shipped unverified: (a)
      `test_declaring_a_source_document_on_loop_creation_round_trips` — creates with `spec_document_id`
      set, round-trips it via a direct `Loop` row read through `async_session_factory` (matching
      `test_spec_declared_tasks.py`'s established direct-DB-read pattern, since `LoopSummary` does not
      expose the field in JSON — confirmed by reading `schemas/jobs.py` first rather than assuming);
      (b) `test_a_second_loop_declaring_the_same_document_is_refused` — second `POST` for the same
      document 409s, asserts the first loop's id is a substring of `detail`; (c)
      `test_a_loop_can_still_be_created_with_no_source_document` — omits the field entirely, asserts
      `Loop.spec_document_id is None` on the row. Plus: `test_patch_declares_a_source_document_on_an_
      existing_loop`, `test_patch_declaring_a_claimed_document_is_refused`, and `test_patch_re_
      declaring_your_own_document_is_not_a_conflict` (the `exclude_loop_id` case named in 4.1's own
      note above).

      **Verification, measured:**
      - `py -3.11 -m pytest hub/tests/test_jobs.py -q` — **28 passed, 1 skipped** (skip is the
        pre-existing `CRONITER_AVAILABLE` guard, unrelated).
      - `py -3.11 -m pytest hub/tests/test_scheduler.py hub/tests/test_spec_declared_tasks.py -q` —
        **18 passed** — the other files reading `Loop`/loop-job creation, to confirm nothing assumed
        `spec_document_id` never exists on a row.
      - `ruff check` and `black --check` on all three touched files — ruff clean throughout; black
        reformatted `jobs.py` once (a long `select(...)` line wrapped, and a stray two-fragment
        f-string in the new helper collapsed into one), reverified clean after.
      - `mypy hub/hub/api/v1/jobs.py hub/hub/schemas/jobs.py` — **zero errors attributed to either
        touched file** (mypy's own transitive-import chasing surfaces pre-existing errors in unrelated
        files it pulls in; filtered the output to lines starting with the two touched paths, which
        came back empty).
      - `npx openspec validate --changes --strict` — 2/2 still pass.

      **Not done, correctly deferred:** section 5 (creator authorship gate on `create_task`,
      `hub/hub/api/v1/tasks.py` + `mcp_server.py`) is next-in-queue and a materially different surface
      (task creation, not loop creation) — `next_action` was explicit not to start it this iteration.

## 5. Queue-write path 2 — creator authorship (`hub/hub/api/v1/tasks.py`, `hub/hub/mcp_server.py`,
   `hub/hub/schemas/tasks.py`)

- [x] 5.1 `TaskCreate` schema and MCP `create_task` gain `loop_id: Optional[str]`.
- [x] 5.2 `create_task` (both REST and the MCP tool, which calls the same REST route per the existing
      pattern): when `loop_id` is supplied, resolve the calling identity — `AgentActor.agent` for an
      agent-authenticated call, or the operator sentinel for an operator-authenticated one (design
      D1). Compare against the target loop's `AIJob.agent`. Equal, or operator → accept. Otherwise →
      403, message naming `send_message` to the creator (spec requirement "Only a loop's creator, or
      the operator, may add to its queue directly").
- [x] 5.3 Apply design D7's extra gate on top of 5.2: when the calling agent equals both the target
      loop's creator *and* its `AIJob.agent` (self-created), and the loop has `run_count > 0` (has
      fired at least once), refuse the direct addition (403, naming that operator approval is
      required) regardless of 5.2's outcome. An operator-authenticated call is exempt from this gate,
      matching 5.2.
- [x] 5.4 Tests: creator adds successfully (before and after first fire, for a loop with a distinct
      executor); operator adds successfully regardless of fire count; non-creator executor is
      refused, message names `send_message`; self-created loop accepts a creator addition before its
      first fire and refuses one after, message names operator approval.

      **2026-08-18, iteration 7.** `TaskCreate` (`hub/hub/schemas/tasks.py`) and the agent-facing
      `AgentTaskCreate` (`hub/hub/api/v1/agent_actions.py`) both gained `loop_id: Optional[str]`; the
      MCP `create_task` tool (`hub/hub/mcp_server.py:212`) gained the same parameter and forwards it
      in the POST body.

      **The identity/D7 gate re-derived literally, not from the `next_action` paraphrase, per its own
      instruction.** Design D8 (`Creator-identity enforcement without a foreign key`) collapses
      "creator" into `Loop`'s own `AIJob.agent` — there is no separate creator field anywhere in the
      schema, so `_authorize_loop_task_creation` (new, `hub/hub/api/v1/tasks.py`, called from
      `create_task_for_actor` before the `Task(` construction) implements 5.2 and 5.3 as: the operator
      is always exempt (5.2's bypass, and separately 5.3's — "An operator-authenticated call is exempt
      from this gate too"); any other caller must equal `Loop`→`AIJob.agent` string-for-string or is
      refused 403 naming `send_message` (5.2); and that same caller, having passed 5.2, is refused
      403 naming operator approval when the job's `run_count > 0` (5.3) — no `run_count` gate applies
      to the operator.

      Read this way, D7's own "general case (creator ≠ executor): only the creator adds tasks, always"
      is inescapably an operator-only scenario under this data model: `_authorize_loop_task_creation`
      never accepts a non-operator caller unless it equals `AIJob.agent`, so the *only* identity that
      can ever be "distinct" from a loop's own agent and still succeed is the operator — D8's collapse
      makes every non-operator-privileged loop self-created by construction, which is exactly why D10
      (the later addendum, queued separately as `LA1`) exists: to give the operator a real, explicit
      "who controls this loop's queue" field instead of inferring it from role identity. This change
      deliberately ships D7's narrower, role-identity version — D10 generalises it later, not now.

      **Tests, `hub/tests/test_agent_actions_coordination.py`** (this file, not `test_jobs.py`,
      already carries the `_active_run` fixture that mints a bound-run bearer token per agent identity
      — exactly what `create_task_for_actor`'s new `actor` parameter needs to be exercised for real,
      rather than only at the ORM layer). Added `_loop_with_agent` (mirrors `_declaring_loop` in
      `test_spec_declared_tasks.py` and `_make_job`/`_make_loop` in `test_scheduler.py`) and four
      tests: `test_loop_operator_adds_regardless_of_a_distinct_executors_fire_count` (operator, via
      the plain `POST /api/v1/projects/proj-test/tasks` route, succeeds both before and after the
      loop's first fire), `test_loop_operator_is_exempt_from_the_self_created_fire_gate` (operator
      succeeds on a loop whose own agent would be refused for the identical call — see the next test),
      `test_loop_non_creator_non_operator_is_refused_and_told_to_send_message` (a bystander agent gets
      403 naming `send_message`, and no task row is left behind), and
      `test_loop_self_created_agent_gated_after_first_fire` (the loop's own agent succeeds before
      `run_count` moves off zero, is refused after, message names the operator, and only the one task
      created before the gate closed exists in the DB).

      **Verification, measured:**
      - `py -3.11 -m pytest hub/tests/test_agent_actions_coordination.py -q` — **23 passed** (19
        pre-existing + 4 new). First run of the two operator-route tests failed 405 — `POST
        /api/v1/tasks` does not exist; the operator's own task route is project-scoped
        (`/api/v1/projects/{project_id}/tasks`, confirmed against `TASKS` in
        `test_evidence_latest_review_signal.py`) — fixed and reverified passing.
      - `py -3.11 -m pytest hub/tests/test_jobs.py hub/tests/test_scheduler.py
        hub/tests/test_spec_declared_tasks.py -q` — **46 passed, 1 skipped** (the pre-existing
        `CRONITER_AVAILABLE` skip) — confirms nothing there assumed `create_task` never carries
        `loop_id` or that `Task.loop_id` is only ever written by `spec_tasks.materialise`.
      - `py -3.11 -m pytest hub/tests/test_mcp_body_contract.py hub/tests/test_mcp_tool_schemas.py
        hub/tests/test_mcp_server.py -q` — **53 passed** — the MCP `create_task` signature widening
        breaks nothing that pins its parameter list or body contract.
      - `ruff check` on all four touched Python files, plus the test file — clean.
      - `black` — reformatted the new test file once (line-wrapping only); clean on reverification.
      - `mypy hub/hub/api/v1/tasks.py hub/hub/api/v1/agent_actions.py hub/hub/schemas/tasks.py
        hub/hub/mcp_server.py`, filtered to lines attributed to those four files (mypy's transitive
        import chasing otherwise surfaces unrelated pre-existing errors as noise) — every error line
        and its count matches `.claude/autonomous/mypy-baseline.txt` exactly for all four files
        (`agent_actions.py`: 28 return-type + 4 pre-existing others; `tasks.py`: 8 return-type + 2
        pre-existing others; `mcp_server.py`: 1 return-type; `schemas/tasks.py`: 0) — **zero new
        errors**.
      - `npx openspec validate --changes --strict` — 2/2 still pass.

      **Not done, correctly deferred:** section 6 (claiming the current item, `hub/hub/scheduler.py`)
      is next-in-queue and a materially different surface (scheduler firing logic, not an API route).

## 6. Claiming the current item (`hub/hub/scheduler.py`)

- [x] 6.1 New `_claim_loop_task(session, loop) -> Optional[Task]` (design D3): select the queue's
      existing active/non-terminal task if one exists, else the oldest entry-status task by
      `created_at`. Mirrors `_batch_loop_summaries`'s existing "current item" derivation
      (`jobs.py:98`) — read that function first rather than re-deriving the ordering independently,
      and factor the shared logic if it can be reused without changing `_batch_loop_summaries`'s own
      batch-query shape (design D7 of `many-named-loops`, which this task must not regress).
- [x] 6.2 `_do_fire_job`: after `_loop_stop_reason` passes (fire proceeds), call `_claim_loop_task`
      when the job has a loop. If a task is returned and its status is an entry status, transition it
      to `assigned`/`in_progress` (whichever the existing task-transition machinery treats as the
      correct entry point — check `run_task_binding.py`'s declared transitions before picking one) and
      set `assignee=job.agent`. If it is already active, leave its status untouched.
- [x] 6.3 Tests: a fire with only entry-status tasks claims the oldest; a fire with an existing
      active task resumes it rather than claiming another; a fire with an empty queue claims nothing
      and does not error (the stop-condition check already prevents this case when `stop_when_queue_
      empties` is set — assert the claim step itself is a no-op independent of that check, for a loop
      that has no `stop_when_queue_empties` and is allowed to fire on an empty queue).

      **Done 2026-08-19** in `hub/hub/scheduler.py` (`_claim_loop_task`, wired into `_do_fire_job`)
      and `hub/tests/test_scheduler.py` (three new tests).

      **D3 read as authoritative over this section's own paraphrase.** D3's text is narrower than
      "entry status" (`pending`/`assigned` per `task_transitions.ENTRY_STATUSES`): it says the
      fallback tier is the oldest **`pending`** one, and names only `in_progress`/`blocked` as the
      active tier — the exact candidate set `_batch_loop_summaries` already queries (`jobs.py:98`,
      `Task.status.in_(("in_progress", "blocked", "pending"))`, no `assigned`). Built
      `_claim_loop_task` to that literal set rather than the wider `ENTRY_STATUSES` reading, so it
      mirrors the existing "current item" derivation exactly rather than approximately — an
      `assigned` task (there is no code path that creates one on a loop's queue today; materialised
      tasks are always `pending`) is simply never a candidate, matching what the UI already shows as
      a loop's "current item" today.

      **6.1's factoring question resolved as: not factored, and said so rather than silently
      skipped.** `_batch_loop_summaries` lives in `hub/hub/api/v1/jobs.py` (the API layer);
      `_claim_loop_task` has to live in `hub/hub/scheduler.py` per 6.1's own text. Neither module
      imports the other today, and the two queries differ in shape beyond the shared ordering trick
      — one is a `Task.loop_id.in_(loop_ids)` batch grouped in Python by first-row-per-loop_id,
      the other a single-loop `.limit(1)`. Introducing a cross-import between the API and scheduler
      layers to share three lines of `order_by` was judged not worth the new coupling; `scheduler.py`
      re-derives the same `(Task.status != "pending").desc(), Task.updated.desc(),
      Task.created_at.asc()` ordering with a comment pointing at `jobs.py:98` and design D7, so a
      future change to one is at least discoverable from the other, even though the code is not
      shared.

      **6.2's transition target: `assigned`, not `in_progress`.** D3's own text is explicit — "the
      scheduler sets that task's status='assigned' (or leaves `in_progress` if resuming one)". This
      is deliberately a *different* status than `run_task_binding.bind_run_to_task`'s
      `in_progress` — that module moves a task to `in_progress` when an actual `Run` row binds to
      it, which does not exist yet at claim time (claiming happens before the `InboundQueueEntry` is
      even created). The two mechanisms are independent: `_claim_loop_task` marks "this is what the
      firing is about" on the task board immediately (D3's own stated purpose — "so 'what is this
      firing working on' is answered by the task board itself, not by parsing a transcript"); the
      entry this change creates does not carry a `task_id`, so `resolve_bound_task` (`agent_trigger.py`
      / `run_task_binding.py`) never sees this task and `Run.task_id` binding stays exactly as it
      was before this change. Wiring the two together — so the eventual run's own `in_progress`
      transition and divergence-boundary check apply to a loop's claimed task too — is not named by
      6.1-6.3's own text and is left for a later section to pick up explicitly rather than assumed
      here.

      **The transition's actor.** `apply_transition(session, claimed_task, "assigned", operator())`
      — plain `operator()`, default origin (`ORIGIN_ACTOR`), *not* `origin=ORIGIN_RUNTIME`. Tried
      `ORIGIN_RUNTIME` first (it reads as the more honest label — the Hub is doing this, not a
      person), then found `hub/tests/test_task_transitions.py::
      test_only_the_binding_module_may_record_a_runtime_transition`, a source scan that hard-fails
      if `origin="runtime"`/`origin='runtime'` appears in any `.py` file under `hub/hub/` other than
      `run_task_binding.py`/`task_transition_service.py` themselves. `scheduler.py` is not on that
      list, so the honest label is not available to this call site without either widening the
      allow-list (out of scope, not asked for) or the scan silently going stale. Fell back to the
      precedent `release_block_for_question` (`run_task_binding.py`) already sets for an
      automatic-but-not-run-bound Hub action: `operator()`, default origin. `is_allowed("pending",
      "assigned", "operator")` is `True` (the `_BOTH` edge), so the call is legal; the
      `resolve_divergences_for_task` side effect `ORIGIN_ACTOR` triggers is a no-op here (a freshly
      materialised task has no open divergences to resolve).

      **assignee is stamped on both branches**, per D3's text describing it as happening regardless
      of whether the task was newly transitioned or resumed — `claimed_task.assignee = job.agent`
      runs unconditionally once a task is claimed, only the `apply_transition` call is conditioned
      on `status == "pending"`.

      **Tests, `hub/tests/test_scheduler.py`**, extending the existing `_make_job`/`_make_loop`
      fixtures rather than inventing new ones, matching the file's established
      `bind_runner`+`PtySession.spawn`-patched full-fire pattern used by the other successful-fire
      loop tests in this file:
      - `test_loop_fire_claims_the_oldest_pending_task` — two `pending` tasks with distinct
        `created_at`; the older is claimed (`status="assigned"`, `assignee=job.agent`), the newer is
        untouched.
      - `test_loop_fire_resumes_an_active_task_instead_of_claiming_another` — an `in_progress` task
        and a `pending` task both in the queue; the `in_progress` one wins (status left untouched,
        only `assignee` stamped), the `pending` one is untouched entirely — proves the active tier
        beats the fallback tier regardless of which was created first.
      - `test_loop_fire_with_empty_queue_claims_nothing_and_does_not_error` — a loop with **no**
        `stop_when_queue_empties` and zero tasks. Deliberately *not* reusing
        `test_loop_with_stop_when_queue_empties_and_no_tasks_yet_keeps_running`'s setup: that loop's
        stop condition, even though it does not fire this time, is armed and would pre-empt
        `_claim_loop_task` on a later drained-queue fire — this test needed a loop where the empty
        queue is never a stop condition at all, so the fire genuinely reaches (and no-ops through)
        `_claim_loop_task`'s own empty-candidate path rather than the scenario being explained by
        `_loop_stop_reason` never running the claim code in the first place.

      **Verification, measured:**
      - `py -3.11 -m pytest hub/tests/test_scheduler.py -q` — **10 passed** (7 pre-existing + 3 new).
      - `py -3.11 -m pytest hub/tests/test_task_transitions.py hub/tests/test_jobs.py
        hub/tests/test_spec_declared_tasks.py -q` — **105 passed, 1 skipped** (pre-existing
        `CRONITER_AVAILABLE` skip) — including
        `test_only_the_binding_module_may_record_a_runtime_transition`, confirming the `operator()`
        choice above did not trip the source-scan gate.
      - `py -3.11 -m pytest hub/tests/test_run_task_binding.py hub/tests/test_task_transition_service.py
        hub/tests/test_run_divergence.py -q` — **67 passed** — the other suites reading
        `apply_transition`/the binding module, confirming nothing there assumed a `pending`→`assigned`
        transition never happens outside the operator's own task routes.
      - `ruff check hub/hub/scheduler.py hub/tests/test_scheduler.py` — clean.
      - `black --fast` reformatted `test_scheduler.py` once (one method-chain line-wrap in the new
        empty-queue test); `scheduler.py` was already clean. Reverified clean on both after.
      - `mypy hub/hub/scheduler.py`, filtered to lines attributed to that file — six error lines
        (two `Result[Any].rowcount`, four `import-untyped` for `apscheduler`/`croniter`), matching
        `.claude/autonomous/mypy-baseline.txt`'s six `scheduler.py` lines exactly — **zero new
        errors**. (`scheduler.py`'s new code adds no annotations mypy flags; the test file is not
        part of the mypy target per `pyproject.toml`'s `testpaths`, consistent with every prior
        section's own verification scope.)
      - `npx openspec validate --changes --strict` (run from the repo root — `hub/ui` reports "No
        items found to validate", a directory trap worth remembering) — 2/2 still pass.

      **Not done, correctly deferred:** section 7 (loop-scoped checkpoints + envelope,
      `hub/hub/checkpoints.py`/`hub/hub/checkpoint_generation.py`) is next-in-queue — `next_action`
      explicitly said not to start it this iteration, and it is a materially different surface
      (checkpoint continuity, not the firing/claim path this section built).

## 7. Continuity — loop-scoped checkpoints (`hub/hub/checkpoints.py`, `hub/hub/checkpoint_generation.py`)

- [x] 7.1 `create_checkpoint`: when the checkpoint's conversation's job has a `Loop` (join via
      `JobRun.conversation_id`, the same join `many-named-loops` D3 introduced), stamp
      `Checkpoint.loop_id` on the created row (design D4).
- [x] 7.2 New `latest_checkpoint_for_loop(db, loop_id)` in `checkpoints.py`, mirroring
      `latest_checkpoint`'s shape and ordering (`created_at DESC, id DESC`) but filtered by
      `Checkpoint.loop_id` instead of `Checkpoint.conversation_id`.
- [x] 7.3 `compute_envelope`: accept an optional `loop` parameter; when supplied, `tasks` is built
      from `Task.loop_id == loop.id` (every status, mirroring `TASK_SCOPE_NOTE`'s "explicit scope
      hides nothing" principle) instead of `_tasks_for(project_id, agent)`. Update the scope note text
      to say "loop" rather than "agent" for this case, matching the existing dishonesty-avoidance
      reasoning in `TASK_SCOPE_NOTE` itself.
- [x] 7.4 Tests: a loop-scoped envelope's `tasks` matches the loop's queue regardless of status; a
      non-loop conversation's envelope is unchanged from today; `latest_checkpoint_for_loop` finds a
      checkpoint from a *different* conversation than the one it is called for, proving the
      cross-conversation join actually works (this is the one behaviour the whole task exists to add
      — a same-conversation-only test would not catch a regression to the old, narrower join).

      **Done 2026-08-19** in `hub/hub/checkpoints.py` (new `latest_checkpoint_for_loop`,
      `loop_for_conversation`, `_tasks_for_loop`, `LOOP_TASK_SCOPE_NOTE`; `compute_envelope` and
      `create_checkpoint` both gained an optional `loop=` parameter) and
      `hub/hub/checkpoint_generation.py` (`generate_checkpoint` derives the loop once via
      `loop_for_conversation` and threads it into both calls). Seven new tests in
      `hub/tests/test_checkpoint_record.py`.

      **7.1's join, factored out rather than inlined twice.** `loop_for_conversation(db,
      conversation_id)` does the `JobRun.conversation_id -> job_id -> Loop.job_id` join once,
      living in `checkpoints.py` rather than duplicated at each call site — `generate_checkpoint`
      (the only caller of both `compute_envelope` and `create_checkpoint`) derives it a single time
      and passes the same `Loop` object into both, per the section header's own naming of two
      functions needing the same derivation. `JobRun.conversation_id` is nullable (only firings
      since migration `0075` recorded it), so a conversation with no matching `JobRun` row, or a
      `JobRun` whose job has no `Loop`, both correctly resolve to `None` — checked with
      `scalar_one_or_none()`, not `scalar_one()`, so a plain non-loop conversation never raises.

      **7.3's scope note.** `LOOP_TASK_SCOPE_NOTE` is a new constant beside `TASK_SCOPE_NOTE`,
      not a runtime string substitution on the same constant — the two describe genuinely
      different scopes ("every task assigned to this agent" vs "every task belonging to this
      loop"), and a single templated note would have to hide that difference behind a parameter
      rather than stating each scope's exact shape as its own reviewable text, which is the same
      "explicit scope hides nothing" reasoning `TASK_SCOPE_NOTE` itself gives for existing at all.
      `_tasks_for_loop` orders by `Task.updated.desc(), Task.id` — the same order `_tasks_for`
      already uses — and filters only by `Task.loop_id == loop.id`, deliberately no status filter,
      unlike `_tasks_for`'s `_LIVE_TASK_STATUSES`.

      **7.4's cross-conversation test is the one that would have caught a regression to the old
      join.** `test_latest_checkpoint_for_loop_crosses_conversations` creates a checkpoint on one
      firing's conversation, then asks `latest_checkpoint_for_loop` for the loop's latest
      checkpoint from context of a *second*, later conversation (a second `JobRun` row pointing a
      different `conversation_id` at the same `job_id`) and asserts the first conversation's
      checkpoint is what comes back. A same-conversation-only test would pass even if
      `latest_checkpoint_for_loop` were accidentally implemented as `latest_checkpoint` filtered by
      `conversation_id` instead of `loop_id`, since a single-conversation checkpoint would satisfy
      either query — this test cannot pass under that regression, by construction.

      **Verification, measured:**
      - `py -3.11 -m pytest hub/tests/test_checkpoint_record.py -q` — **23 passed** (16
        pre-existing + 7 new).
      - `py -3.11 -m pytest hub/tests/test_checkpoint_generation.py hub/tests/test_checkpoint_access.py
        hub/tests/test_checkpoint_cutover.py hub/tests/test_checkpoint_notes.py -q` — **96 passed**
        — every other suite reading `compute_envelope`/`create_checkpoint`/`generate_checkpoint`,
        confirming nothing assumed `Checkpoint.loop_id` is always `None` or that `compute_envelope`'s
        `tasks` is always agent-scoped.
      - `ruff check hub/hub/checkpoints.py hub/hub/checkpoint_generation.py
        hub/tests/test_checkpoint_record.py` — clean (one import-sort fix applied by `--fix`).
      - `black --fast` — reformatted `checkpoints.py` once (import-block wrap), clean after on all
        three files.
      - `mypy hub/hub/checkpoints.py hub/hub/checkpoint_generation.py`, filtered to lines
        attributed to each file — `checkpoints.py`: 7 error lines, matching
        `.claude/autonomous/mypy-baseline.txt`'s 7 exactly; `checkpoint_generation.py`: 6 error
        lines, matching the baseline's 6 exactly — **zero new errors**. The three new functions
        (`latest_checkpoint_for_loop`, `loop_for_conversation`, `_tasks_for_loop`) are explicitly
        typed `db: AsyncSession` (unlike the rest of the file's untyped-`db` convention) precisely
        so they would not add three fresh `no-untyped-def` hits beyond the baseline; every other
        function in `checkpoints.py` is left exactly as it was, out of this task's scope.
      - `npx openspec validate --changes --strict` (from the repo root) — 2/2 still pass.

      **Not done, correctly deferred:** section 8 (refusing `resume` for a loop's job,
      `hub/hub/api/v1/jobs.py`) is next-in-queue — a materially different surface (the job
      creation/update API, not checkpoint continuity) and `next_action` explicitly named it as the
      following section, not this one.

## 8. Refusing resume for a loop's job (`hub/hub/api/v1/jobs.py`)

- [x] 8.1 `create_job`/`update_job`: reject (400) a `session_mode="resume"` when the job has (or is
      being given, in the same request) a `Loop` row, naming checkpoint-based continuity as the
      reason (design D4, spec requirement "Setting resume mode on a loop's job is refused").
- [x] 8.2 Tests: setting `resume` on a plain job still behaves exactly as before (unchanged, and
      still broken per `known_debts` — do not fix `AIJob.last_session_id`'s write path here, out of
      scope per Non-Goals); setting `resume` on a job that has, or is simultaneously given, loop
      fields is refused with the stated reason.

      **2026-08-19, iteration 11.** `create_job` (`hub/hub/api/v1/jobs.py`): the check
      (`body.session_mode == "resume" and _loop_opts_in(body.purpose, body.stop_at,
      body.stop_when_queue_empties)`) now runs immediately after `_require_agent_job_allowance`,
      before `job_id` is even computed — an error response leaves no job row behind at all, not
      merely an uncommitted one. `update_job`: the check runs right after the existing
      `loop_fields_supplied` block resolves (or creates) the request's `Loop` row, before any field
      — including `job.session_mode` — is mutated. "Is this job a loop after this request" is
      `loop_fields_supplied and loop is not None` (the row the block just resolved/created) OR, when
      no loop fields were supplied in this request at all, a direct query for an existing `Loop` row
      on the job — covering the case D4 names explicitly: PATCHing `resume` alone onto a job that
      already opted into a loop in an earlier request. Both paths raise before `session.commit()`,
      so a refused request (including one that constructed a fresh `Loop` object via `session.add`
      earlier in the same handler) persists nothing — `get_session`'s `async with` closes the
      session without a commit, which is an implicit rollback at the DB level, the same guarantee
      `create_job`'s pre-existing `IntegrityError` rollback already relies on.

      Both raise the same message: "this job is a loop; continuity is by checkpoint, not by resumed
      session" — matching D4's wording exactly rather than paraphrasing it.

      Tests, `hub/tests/test_jobs.py`, added beside the existing loop-field-on-plain-job tests:
      `test_resume_on_a_plain_job_is_unchanged_by_patch` (PATCH `session_mode=resume` on a job with
      no `Loop` row still 200s, `loop` stays `None` — the existing `test_job_session_modes` already
      covered the POST side of "unchanged"; this is the PATCH side, added because `next_action`
      named it explicitly and no prior test exercised PATCH `resume` on a plain job specifically);
      `test_create_job_with_resume_and_loop_opt_in_is_refused` (POST with `session_mode=resume` and
      `purpose` together — 400, message names "loop" and "checkpoint", and a follow-up list confirms
      no job with that name exists); `test_patch_resume_onto_an_existing_loop_job_is_refused` (a job
      already opted into a loop from an earlier POST, then PATCHed with `session_mode=resume` alone
      — 400, and a follow-up GET confirms `session_mode` is still `"new"`, the "already-a-loop" case
      D4 names first); `test_patch_resume_and_loop_opt_in_together_is_refused` (a plain job PATCHed
      with `session_mode=resume` and `purpose` in the same request — 400, and a follow-up GET
      confirms the job stayed non-loop with `session_mode` still `"new"` — the "given, in the same
      request" case D4 names second, not just the already-a-loop case).

      **Verification, measured:**
      - `py -3.11 -m pytest hub/tests/test_jobs.py -q` — **32 passed, 1 skipped** (28 pre-existing +
        4 new; the 1 skip is `test_create_job_invalid_cron`'s existing `croniter`-not-installed
        guard, unrelated to this change).
      - `py -3.11 -m pytest hub/tests/test_jobs.py hub/tests/test_spec_declared_tasks.py -q` — **43
        passed, 1 skipped** — the other suite reading `create_job`/`update_job`'s loop-opt-in path,
        confirming section 4/5's declared-document and creator-authorship behaviour is unchanged.
      - `py -3.11 -m ruff check hub/hub/api/v1/jobs.py hub/tests/test_jobs.py` — clean.
      - `black hub/hub/api/v1/jobs.py hub/tests/test_jobs.py` — both already formatted, unchanged
        (`--fast` needed on this machine's Python 3.11 to skip Black's own AST safety check, which
        otherwise warns — not errors — about a formatting environment mismatch unrelated to this
        change).
      - `py -3.11 -m mypy hub/hub/api/v1/jobs.py`, filtered to lines attributed to the file — 16
        error/note lines, matching `.claude/autonomous/mypy-baseline.txt`'s 16 for this file exactly
        by category (7 missing-return-type, 1 missing-parameter-type, 3 `AIJob` has no attribute
        `loop`, 1 `croniter` stub, 1 index-type, 3 notes) — **zero new errors**. No new helper
        function was added, so there was no new call site to type explicitly this iteration.
      - `npx openspec validate --changes --strict` (from the repo root) — 2/2.

      No Hub restart this iteration: like sections 3-7 and 9, this section is verified entirely
      through pytest against the API layer directly (httpx against the FastAPI app fixture), with no
      UI or live-Hub surface to exercise.

## 9. The briefing (`hub/hub/scheduler.py`)

- [x] 9.1 New `_compose_loop_briefing(loop, claimed_task, prior_checkpoint) -> str` (design D5):
      purpose, claimed task (title/description/acceptance criteria), prior checkpoint content
      (rendered via the existing `render_checkpoint`-equivalent rendering, truncated to
      `_LOOP_BRIEFING_CHECKPOINT_CHARS = 4_000`), and a one-line open/done queue summary reusing
      `_batch_loop_summaries`'s existing aggregation.
- [x] 9.2 `_do_fire_job`: when the job has a loop, prepend the composed briefing to `job.message`
      before calling `new_entry` (design D5 — the operator's own message text is unchanged, the
      briefing is a prefix).
- [x] 9.3 Tests: a first firing's briefing has no prior-checkpoint section; a later firing's briefing
      includes a prior checkpoint's content in full when under the cap; a prior checkpoint over the
      cap is truncated to exactly the cap, not omitted; a non-loop job's fired message is byte-
      identical to `job.message` (no briefing prepended) — this last one is the regression guard for
      every non-loop job in the suite.

      **2026-08-19.** `_compose_loop_briefing` took `session: AsyncSession` as an explicit first
      parameter, ahead of `loop`/`claimed_task`/`prior_checkpoint` — the queue's open/done summary
      needs a query the other three params cannot supply, and every other session-touching helper
      in this file already leads with `session` (`_loop_stop_reason(session, job)`,
      `_claim_loop_task(session, loop)`); adding a fourth positional-only session-shaped parameter
      convention here would have been the odd one out, not a deviation from it.

      Content order matches design D5 exactly: `loop.purpose` (skipped entirely when empty, not
      rendered as an empty heading), the claimed task's title/description/acceptance criteria,
      `## Prior checkpoint` rendered via `checkpoint_generation.render_checkpoint` (the same
      function a human reader gets — no second serialisation) truncated from the end at
      `_LOOP_BRIEFING_CHECKPOINT_CHARS = 4_000` when `latest_checkpoint_for_loop` finds one, then
      `Queue: {open} open, {done} done`. The open/done split reuses `TERMINAL_FOR_BINDING`
      (`("approved", "rejected")`) — the exact same split `_loop_stop_reason`, in this same file,
      already uses to decide whether a loop's queue is drained — rather than inventing a second,
      differently-drawn line for the same concept. The per-status count query is recomputed
      directly in `scheduler.py` rather than imported from `api/v1/jobs.py`'s
      `_batch_loop_summaries` — L6's own precedent (task 6.1's note) already rejected an
      api-layer-to-scheduler cross-import for a similarly small query, for the same layering
      reason.

      `_do_fire_job` (task 9.2): `content = job.message` by default; when `loop is not None`, fetch
      `prior_checkpoint = await latest_checkpoint_for_loop(session, loop.id)` (built in L7, may be
      `None` on a loop's first firing — not `loop_for_conversation`, which resolves a loop *from* a
      conversation the caller does not have yet; the `loop` local is already the right object),
      compose the briefing, and set `content = f"{briefing}\n{job.message}"` — a prefix, `job.
      message` reaches `new_entry` unchanged either way, so the operator's own template still reads
      exactly as authored (design D5). A non-loop job never enters the `if loop is not None:`
      branch at all, so `content` stays exactly `job.message`.

      **Tests, `hub/tests/test_scheduler.py`**, extending the same `_make_job`/`_make_loop`
      fixtures `_claim_loop_task`'s own tests (section 6) already use, plus a new `_make_checkpoint`
      helper that (deliberately, mirroring L7's own
      `test_latest_checkpoint_for_loop_crosses_conversations`) attributes the checkpoint to a
      *different* conversation than the one about to fire, since a loop's next firing is by
      construction a conversation that does not exist yet:
      `test_loop_briefing_omits_prior_checkpoint_section_on_a_first_firing` (no checkpoint exists —
      asserts `"## Prior checkpoint" not in entry.content`, and separately asserts the purpose,
      claimed-task, and queue-summary lines are all present and `entry.content` ends with
      `job.message`); `test_loop_briefing_includes_a_prior_checkpoint_in_full_under_the_cap` (a
      short checkpoint body — asserts `render_checkpoint(checkpoint)` appears in `entry.content`
      byte-for-byte); `test_loop_briefing_truncates_an_oversized_prior_checkpoint_to_exactly_the_cap`
      (a 10,000-character body — asserts the extracted `## Prior checkpoint` section equals
      `rendered[:_LOOP_BRIEFING_CHECKPOINT_CHARS]` exactly, `len(section) ==
      _LOOP_BRIEFING_CHECKPOINT_CHARS`, and the untruncated `rendered` string does NOT appear
      anywhere in `entry.content` — a length assertion, not just presence, per `next_action`'s
      explicit instruction); `test_non_loop_job_fired_content_is_byte_identical_to_job_message` (no
      `Loop` row at all — asserts `entry.content == job.message == "hello from a scheduled job"`),
      the regression guard for every non-loop job in the suite.

      **Verification, measured:**
      - `py -3.11 -m pytest hub/tests/test_scheduler.py -q` — **14 passed** (10 pre-existing + 4
        new).
      - `py -3.11 -m pytest hub/tests/test_checkpoint_record.py hub/tests/test_checkpoint_generation.py
        -q` — **42 passed** — both suites reading `render_checkpoint`/`latest_checkpoint_for_loop`,
        confirming this section's new call sites did not change either function's behaviour.
      - `ruff check hub/hub/scheduler.py hub/tests/test_scheduler.py` — clean.
      - `black --fast hub/hub/scheduler.py hub/tests/test_scheduler.py` — both already formatted,
        unchanged.
      - `mypy hub/hub/scheduler.py`, filtered to lines attributed to the file — exactly the same 6
        error lines as `.claude/autonomous/mypy-baseline.txt` (2 `Result[Any].rowcount` +
        4 pre-existing `import-untyped`) — **zero new errors**. `_compose_loop_briefing`'s
        `session: AsyncSession` parameter is explicitly typed for the same reason L7's three new
        functions were: an untyped `session` on a brand-new function would have added a fresh
        baseline miss, not matched an existing-file convention worth extending.
      - `npx openspec validate --changes --strict` (from the repo root) — 2/2.

      No Hub restart: like L3-L7, this section is verified entirely through pytest against
      scheduler logic, with no UI or live-Hub surface to exercise.

      **Not done, correctly deferred:** section 8 (refusing `resume` for a loop's job,
      `hub/hub/api/v1/jobs.py`) remains open — the queue deliberately ordered L9 ahead of L8 this
      run because L9 leans on L7's `latest_checkpoint_for_loop`; L8 is next.

## 10. Empty-queue telemetry (`hub/hub/scheduler.py`)

- [x] 10.1 At the point `_loop_stop_reason` reports "loop queue is empty" (design D6), check for an
      unread `Message` from the executor addressed to the loop's creator, or an unanswered `Question`
      in the firing's conversation. Persist and broadcast a new `loop_queue_exhausted` event
      (`{job_id, loop_id, pending_request}`) alongside the existing `loop_stopped` event — a second
      event, not a folded field, per design D6's stated reasoning.
- [x] 10.2 Tests: queue empties with no outstanding request → event's `pending_request` is null; queue
      empties with an unread message to the creator outstanding → event names it; queue empties with
      an unanswered question outstanding → event names it; the loop stops in every case (this
      requirement does not introduce a paused state — assert `job.enabled` is `False` and `Loop.
      stopped_at` is set exactly as `many-named-loops`'s existing stop path already does).

      **2026-08-19, iteration 12.** New `_pending_loop_request(session, job, loop, exclude_run_id)`
      in `hub/hub/scheduler.py`, called from `_do_fire_job`'s existing `if loop_stop_reason:` branch
      (right after the existing `loop_stopped` persist+broadcast), gated on
      `loop_stop_reason == "loop queue is empty"` specifically — the only one of
      `_loop_stop_reason`'s two return strings (the other is "loop stop time reached (...)") that
      means the queue drained rather than a deadline landing, re-confirmed by reading
      `_loop_stop_reason` fresh this iteration.

      **A deliberate deviation from the prior iteration's scouting note, recorded because it changes
      what "the firing's conversation" resolves to.** The note (entry 11's log) proposed using the
      `conversation` local `_do_fire_job` already builds for THIS firing. Re-reading `_do_fire_job`
      fresh: that `conversation` is created unconditionally, before `_loop_stop_reason` even runs,
      and — because task 8.1 refuses `session_mode="resume"` for a loop job's entire lifetime, not
      just at creation — a loop job's `resume_session_id` is always `None`, so `new_conversation()`
      always runs and every single firing gets a brand-new, still-empty `Conversation`. Checking
      `Question.conversation_id == conversation.id` against THIS firing's own conversation would
      therefore always find nothing — dead code that could never observe the state D6 exists to
      surface. "The firing's conversation" has to mean the most recent EARLIER firing's conversation
      instead: the one an `ask_user` call would actually have been asked in, if the loop's last real
      execution asked one and nobody answered it. Implemented as a query for the most recent prior
      `JobRun` for this job with a recorded `conversation_id`, excluding the current firing's own
      `JobRun` by id, then an unanswered `Question` against that conversation.

      Checked before the `Message` case, on the reasoning that an unanswered `ask_user` is a hard
      block on the run that asked it — closer to "what this loop was actually waiting on" than mail
      sitting unread — and D6 states no tiebreak for when both are outstanding; recorded as a design
      decision, not inferred, and locked in by
      `test_loop_queue_exhausted_event_prefers_the_question_when_both_are_outstanding`.

      "Addressed to the creator" (the `Message` case) is the model's own `recipient` field — the
      thing that actually decides whose inbox a message lands in — not a conversation match; only
      the `Question` half of D6's sentence carries the "in the firing's conversation" qualifier
      grammatically. The creator's agent name is resolved `Loop.created_by_run_id` →
      `session.get(Run, ...)` → `Run.agent`, the identical shape `questions.py`'s
      `_asking_run_has_ended` (line 44) already uses for a different row's `created_by_run_id` —
      cited as precedent rather than a second pattern, per `next_action`'s instruction. The `Message`
      query additionally filters `sender == job.agent` (the loop's own executor) so an unrelated
      unread message to the same creator, from anyone else, is not mistaken for this loop's pending
      request. `to` is `null` for the `Question` case (the model has no recipient/addressee field of
      its own — a question is directed at whichever human is watching, not a named agent) and the
      message's own `recipient` for the `Message` case. `reason` is `question.question` or
      `message.subject or message.content`, truncated to a new `_LOOP_PENDING_REQUEST_REASON_CHARS =
      300` — a small, separate constant from section 9's `_LOOP_BRIEFING_CHECKPOINT_CHARS = 4_000`,
      since this is a one-line summary field on an event payload, not a full checkpoint body; same
      "terse over verbose" reasoning, a different number for a different shape of content.

      Tests, `hub/tests/test_scheduler.py`, extending the same `_make_job`/`_make_loop` fixtures:
      `test_loop_queue_exhausted_event_fires_with_no_pending_request` (a drained queue with nothing
      else outstanding — `pending_request` is `null`, and a regression-guard assertion that
      `loop_stopped` still fires unchanged, for the same firing, alongside the new event);
      `test_loop_queue_exhausted_event_names_an_unread_message_to_the_creator` (a `Run` row standing
      in for the creator, a `Loop.created_by_run_id` pointing at it, and an unread `Message` from the
      executor to the creator — asserts `kind`/`to`/`reason`/`created_at` all populated correctly);
      `test_loop_queue_exhausted_event_names_an_unanswered_question_from_a_prior_firing` (a manually
      inserted prior `JobRun` carrying a `conversation_id`, and an unanswered `Question` against that
      same conversation — asserts the event names it, `to` is `null`); and
      `test_loop_queue_exhausted_event_prefers_the_question_when_both_are_outstanding` (both an
      unanswered question and an unread message present at once — asserts `kind == "question"` wins,
      locking in the tiebreak decision above). All four also assert `job.enabled is False` and
      `Loop.stopped_at is not None`, exactly as `many-named-loops`'s existing stop path already does
      — this requirement does not introduce a paused state.

      **Verification, measured:**
      - `py -3.11 -m pytest hub/tests/test_scheduler.py -q` — **18 passed** (14 pre-existing + 4 new).
      - `py -3.11 -m pytest hub/tests/test_jobs.py hub/tests/test_scheduler.py -q` — **50 passed, 1
        skipped** — the other suite reading `AIJob`/`Loop` state this section also touches,
        confirming section 8's refusal path is unaffected.
      - `py -3.11 -m ruff check hub/hub/scheduler.py hub/tests/test_scheduler.py` — clean.
      - `black --fast hub/hub/scheduler.py hub/tests/test_scheduler.py` — the test file needed
        reformatting (line-wrap only, no logic change), reformatted and re-verified green; the
        scheduler module was already formatted.
      - `py -3.11 -m mypy hub/hub/scheduler.py`, filtered to lines attributed to the file — exactly
        the same 6 error lines as `.claude/autonomous/mypy-baseline.txt` (2 `Result[Any].rowcount` +
        4 pre-existing `import-untyped`) — **zero new errors**. `_pending_loop_request`'s `session`,
        `job`, and `loop` parameters are explicitly typed, per the L7/L9 convention for a new helper.
      - `npx openspec validate --changes --strict` (from the repo root) — 2/2.

      No Hub restart this iteration: like sections 3-9, this section is verified entirely through
      pytest against scheduler logic directly, with no UI or live-Hub surface to exercise.

## 11. `create_loop` MCP tool (`hub/hub/mcp_server.py`)

- [x] 11.1 New `@mcp.tool() create_loop(name, agent, message, cron, purpose="", stop_at=None,
      stop_when_queue_empties=False, spec_document_id=None, initial_tasks=None)` (design D2), gated
      by the same `_require_agent_job_allowance` `create_job` already uses. Refuses (400) creation
      when neither `stop_at` nor `stop_when_queue_empties` is supplied — a loop with no stop condition
      is refused outright, per design D2.
- [x] 11.2 `initial_tasks`, if supplied, creates the named tasks with `loop_id` set to the new loop's
      id in the same call — the "definition window" design D7 treats as pre-first-fire authorship,
      not subject to D7's post-first-fire gate.
- [x] 11.3 `test_mcp_tool_schemas.py`: assert `create_loop`'s generated schema agrees with the REST
      schema it calls, matching the existing pattern for every other MCP tool restated from the Hub's
      validators (CLAUDE.md's standing rule for `mcp_server.py`).
- [x] 11.4 Tests: `create_loop` with no stop condition is refused; with a stop condition and no
      initial tasks, creates an empty-queue loop; with `initial_tasks`, creates a loop whose queue
      already holds them; with `spec_document_id`, creates a loop that later materialises tasks into
      its queue when that document is approved (integration test spanning 3.1 and 11.1).

      **2026-08-19, iteration 13.** `create_loop` calls the same `/agent-actions/jobs` route
      (`create_governed_job` → `create_job`) `create_job` already calls, per design D2's stated
      shape — no new REST route. `JobCreate` already had `purpose`/`stop_at`/
      `stop_when_queue_empties`/`spec_document_id` (sections 1-5); the only schema widening this
      section needed was `initial_tasks: Optional[List[Dict[str, Any]]]`, added to `JobCreate`
      (`schemas/jobs.py`) — a plain-dict shape, not a nested model, matching
      `submit_spec_document`'s own reasoning against closed object types. Confirmed fresh that
      `AgentJobCreate` (`agent_actions.py`) did **not** already mirror `JobCreate`'s loop fields at
      all (not just `initial_tasks` — `purpose`/`stop_at`/`stop_when_queue_empties`/
      `spec_document_id` were absent too, so an agent could never opt a job into being a loop
      through `/agent-actions/jobs` before this section), so all five fields were added there
      together — `create_governed_job` builds `JobCreate(**body.model_dump(), source="hub")`, so a
      field on one schema and not the other silently drops the caller's intent.

      The "no stop condition" refusal lives in `create_loop` itself (`mcp_server.py`), raised as
      `HubAPIError(400, ..., "POST", "/jobs")` **before** `_hub_request`/`_job_effect` is called —
      reusing `HubAPIError`'s existing "Hub rejected ..." shape for a rejection the Hub never saw,
      rather than inventing a second exception type for what an agent experiences identically
      either way. `POST /jobs` itself gained no such check, per D2: the operator's own
      `JobForm.tsx` "Make this a loop" section already posts a `purpose`-only, no-stop-condition
      job and must keep working unmodified. `stop_at` is typed `Optional[str]` (an ISO-8601
      timestamp) on the MCP surface, matching what `JobForm.tsx` already sends over the wire
      (`new Date(stopAt).toISOString()`) — `mcp_server.py` stays stdlib-only, so it never touches a
      `datetime` object itself.

      Seeding the queue (11.2) reuses `create_task_for_actor` — the single `Task(` construction
      site (`tasks.py`) — rather than a second construction, per CLAUDE.md's standing instruction
      for `mcp_server.py`-adjacent Hub code. `initial_tasks` entries are validated into
      `TaskCreate` objects **before** the job or loop row is created (moved earlier than the first
      draft of this section put it), so one malformed entry 422s before anything is persisted,
      never leaving a half-created job+loop behind — the same "no error response leaves partial
      state" discipline design D4's resume-refusal already established for this route. Task
      authorship's own gate (`_authorize_loop_task_creation`'s "already fired" check) is satisfied
      for free, not bypassed: `job.run_count` is always `0` for a job this same call just created,
      so D7's post-first-fire restriction structurally cannot fire here — decided against a special
      bypass parameter, since the existing gate already produces the right answer unmodified.

      Tests: `test_mcp_tool_schemas.py` gained
      `test_create_loop_offers_exactly_the_fields_the_route_it_posts_to_accepts`, asserting
      `create_loop`'s generated schema's property set equals `AgentJobCreate`'s fields minus
      `session_mode`/`enabled` (deliberately absent — a loop's continuity is always by checkpoint,
      design D4, and an agent could not usefully create a disabled loop). `test_mcp_server.py`
      gained three tests against the existing mocked-`urlopen` `hub` fixture: the no-stop-condition
      refusal fires with **zero** HTTP calls made (`calls == []`, mirroring
      `test_effect_refuses_unbound_run_credential`'s own assertion shape); `stop_at` alone is
      accepted; and the full payload shape reaches `/api/v1/agent-actions/jobs` unchanged.
      `test_agent_actions_governed.py` gained three tests against the real `app`/DB: a stop
      condition with no `initial_tasks` produces a `Loop` row with zero queued `Task`s; supplying
      `initial_tasks` produces `Task` rows carrying the new loop's id with fields round-tripped
      (`title`/`description`/`priority`); and a malformed entry (missing `title`) 422s.
      `test_spec_declared_tasks.py` gained
      `test_create_loop_declares_a_document_that_later_materialises_into_its_queue`, the integration
      case spanning section 3 and this section: a loop created through the real
      `/agent-actions/jobs` route with `spec_document_id` set, whose queue is empty until the
      document is later approved through the normal spec-lifecycle route, at which point
      `spec_tasks.materialise()` (section 3, unmodified by this section) stamps the produced tasks
      with this loop's id — mirroring the existing `_declaring_loop`-fixture version of the same
      test, but building the loop through the API this section added instead of constructing the
      row directly.

      **Verification, measured:**
      - `py -3.11 -m pytest hub/tests/test_mcp_server.py hub/tests/test_mcp_tool_schemas.py -q` —
        **45 passed**.
      - `py -3.11 -m pytest hub/tests/test_agent_actions_governed.py
        hub/tests/test_spec_declared_tasks.py -q` — **17 passed**.
      - `py -3.11 -m pytest hub/tests/test_jobs.py hub/tests/test_scheduler.py
        hub/tests/test_agent_actions_governed.py hub/tests/test_spec_declared_tasks.py
        hub/tests/test_mcp_server.py hub/tests/test_mcp_tool_schemas.py hub/tests/test_tasks.py -q`
        — **130 passed, 1 skipped** (the pre-existing `croniter`-not-installed skip) — the wider
        sweep of every suite reading `AIJob`/`Loop`/`Task` state this section touches, confirming
        no regression to sections 1-10 or to plain (non-loop) task/job creation.
      - `py -3.11 -m ruff check` on every touched file — clean.
      - `black --fast` — `hub/hub/api/v1/jobs.py` and `hub/tests/test_agent_actions_governed.py`
        needed reformatting (wrapping only, no logic change); reformatted and re-verified green;
        the other touched files were already formatted.
      - `py -3.11 -m mypy` on `hub/hub/mcp_server.py`, `hub/hub/api/v1/jobs.py`,
        `hub/hub/api/v1/agent_actions.py`, `hub/hub/schemas/jobs.py`, filtered to lines attributed
        to each file, against `.claude/autonomous/mypy-baseline.txt`: `mcp_server.py` 1 line
        (matches baseline's 1 exactly — `create_loop` itself is fully annotated, so it added
        nothing); `jobs.py` 16 lines (matches baseline's 16 exactly, same as section 8's
        confirmation); `agent_actions.py` 34 lines, which is baseline's 33 **errors** plus one
        `note:` line attached to a pre-existing error (not a new error — every error *category*
        and count matches baseline exactly); `schemas/jobs.py` 0 lines, matching baseline's absence
        of an entry for that file — **zero new errors** across all four.
      - `npx openspec validate --changes --strict` (repo root) — 2/2.

      No Hub restart this iteration: like sections 3-10, this section is verified entirely through
      pytest against the API layer, with no UI or live-Hub surface to exercise.

## 12. Full-suite verification — agent-verifiable

- [x] 12.1 `py -3.11 -m pytest hub/tests -q` — full suite green, including every new test above.
- [x] 12.2 `py -3.11 -m mypy hub/hub/` (or the project's equivalent hub type-check command) clean.
- [x] 12.3 `npx openspec validate --changes --strict` passes with this change included (already
      confirmed for the spec text itself; re-run after implementation in case a later edit to this
      file drifted from the delta).
- [x] 12.4 Mutation-check design D3's claim logic: temporarily revert the deterministic-selection
      change to "always claim the newest task" and confirm the new test in 6.3 fails by name — the
      same mutation-testing discipline `Q2`'s merge-500 fix already applied this session.
- [x] 12.5 Mutation-check design D8's identity check (5.2): temporarily remove the string-equality
      comparison (accept any caller) and confirm the new test in 5.4 (non-creator refusal) fails by
      name.

      **2026-08-19, iteration 14.** This section is the first time the full suite has actually run to
      completion since prep — `verified_green_at_prep`'s `hub_pytest` entry was still literally "NOT
      VERIFIED", and the two immediately preceding iterations both started a background full run and
      then ended their turn without waiting for it, which drops the process (confirmed: no orphaned
      pytest survived either exit, `Get-Process` came back empty) rather than carrying it forward —
      that is why 12.1 stalled for two firings. This iteration ran it in the foreground instead (a
      `run_in_background` Bash task polled to completion within the same turn via a bounded
      `until`-loop), refreshing `last_heartbeat` and pushing an interim commit before each ~12-minute
      wait so the driver would not reclaim the branch mid-run again.

      **12.1, first pass — a real regression, not a flake.** 1 failed, 2387 passed, 52 skipped, 1
      xpassed. The failure: `test_tool_surface_matches_server.py::
      test_every_served_tool_is_described_or_deliberately_excluded`. L11's `create_loop` (iteration
      13) was never added to `_tool_surface_lines` or `UNDESCRIBED_TOOLS` — iteration 13's own
      targeted verification runs never touched this file, so the gap was invisible until the full
      suite actually ran. This is exactly the failure mode the test's own docstring names: an agent
      told to call a tool its own surface omits concludes it does not have the tool, and stops.
      Fixed by adding a `create_loop` line to `_tool_surface_lines` (`hub/hub/api/v1/agents.py`,
      beside `create_job`/`delete_job`/`toggle_job`/`run_job`) describing the full signature, the
      no-stop-condition refusal, and `initial_tasks`' shape. All 7 tests in
      `test_tool_surface_matches_server.py` pass after the fix; black reformatted the new lines'
      quote style, ruff clean. Also carried forward and verified in this section (found by a prior
      iteration mid-run, not yet committed): `hub/tests/browser/conftest.py`'s
      `pytest_collection_modifyitems` iterated the *whole session's* collected items and skip-marked
      every one the moment the conftest was merely importable, not just the browser package's own
      items — invisible in CI (no Playwright there, so `importorskip` aborts before the hook
      registers) but locally it silently skipped roughly 2,440 non-browser tests too whenever
      `AW_HUB_URL` was unset. Scoped the skip to items under this conftest's own directory; this is
      what let 12.1 collect and run the real suite at all instead of a false green of "all skipped."

      **12.1, second pass — clean.** `2388 passed, 52 skipped, 1 xpassed` (0 failed) in 687.80s. The
      1 xpassed is `test_agent_trigger_overrides.py`'s documented pre-existing timing-dependent
      flake (a concurrent-poller race against `_execute_run`'s finalize COMMIT, marked `xfail` with
      its own "un-xfail once the..." note) — unrelated to this change, not touched, and its status
      (xpass rather than the CI baseline's xfail) is exactly the kind of timing variance the test's
      own comment already documents as expected.

      **12.2.** `py -3.11 -m mypy hub/hub/` (repo-root cwd, matching the baseline capture's own
      invocation): **361 errors in 86 files** — identical to `.claude/autonomous/mypy-baseline.txt`'s
      total. One genuine delta surfaced and was fixed rather than merely annotated: the new
      migration `0077_loop_declares_source_and_checkpoint_loop.py` (section 1, iteration 1) didn't
      exist at baseline-capture time, and its `_tables`/`_columns`/`_indexes` helpers had an
      unannotated `conn` parameter — the same convention `0075`/`0076` already use unfixed, but
      because mypy does not check the bodies of untyped functions by default, this file's `conn`
      being untyped was silently hiding real errors that only 0075/0076's pre-existing baseline
      entries happen not to have. Annotated `conn: sa.engine.Connection` on all three helpers (cheap,
      in a file this change itself authored, so in scope unlike the pre-authorized 361); that alone
      surfaced one further real error in `_indexes`' comprehension (`get_indexes()`'s `name` field is
      `Optional[str]`, not `str`), fixed with a `None`-filter. Migration tests re-run after
      (`test_migrations.py`, 54 passed, 1 skipped) confirm no behavioural change. Net result: this
      change contributes zero new mypy errors, literally — not the pre-authorized fallback of "no
      new errors vs. baseline" with a caveat, an actual matching total. The pre-authorization for
      12.2 (rescoping away from repo-wide mypy-clean, since 361 pre-existing errors across 86 other
      files are out of scope for this change) still stands and was not needed beyond this one file.

      **12.3.** `npx openspec validate --changes --strict` — 2/2, unchanged since iteration 13.

      **12.4 (D3 mutation check).** Target: `_claim_loop_task`'s ordering
      (`hub/hub/scheduler.py:216-221`), confirmed fresh — `.order_by((Task.status != "pending")
      .desc(), Task.updated.desc(), Task.created_at.asc()).limit(1)`. Mutated `Task.created_at.asc()`
      to `.desc()` (line 219) — flips the pending-tie tiebreak to newest-first, i.e. "always claim
      the newest task" among untouched candidates. `py -3.11 -m pytest hub/tests/test_scheduler.py::
      test_loop_fire_claims_the_oldest_pending_task -v` failed by name as expected (`assert
      older.status == "assigned"` → got `"pending"`, the newer task claimed instead). Reverted
      immediately; re-ran the same test green (`1 passed`), and `git diff --stat
      hub/hub/scheduler.py` confirmed no residual diff before moving on.

      **12.5 (D8 mutation check).** Target: `_authorize_loop_task_creation`
      (`hub/hub/api/v1/tasks.py:286-311`), confirmed fresh. Mutated line 304's `if job is None or
      actor.agent != job.agent:` to `if job is None or False:` — accepts any caller regardless of
      identity. `py -3.11 -m pytest hub/tests/test_agent_actions_coordination.py::
      test_loop_non_creator_non_operator_is_refused_and_told_to_send_message -v` failed by name as
      expected (`assert response.status_code == 403` → got `201 Created`, the bystander's task was
      created). Reverted immediately; re-ran the same test green (`1 passed`), and `git diff --stat
      hub/hub/api/v1/tasks.py` confirmed no residual diff.

      With section 12 done, the `2026-08-18-a-loop-writes-its-own-queue` change's main body
      (sections 1-12) is complete and independently full-suite verified. The addendum (A1-A5) and
      the panel change's P4-P6 remain open, per the operator's "work on both specs" interleaving.

## 13. Human-only verification

- [ ] 13.1 **Does the claimed task actually match what the firing worked on?** Taste and correctness
      both — drive one real loop through two firings against a live agent (not a mock), read the
      second firing's transcript, and confirm the task it references is the one the board shows as
      claimed for that firing. This is the one place this change's whole premise (a firing knows its
      position) is either true or is not, and no unit test proves it end to end.
- [ ] 13.2 **Does the briefing read as useful context, or as noise the agent ignores?** Read a second
      firing's actual first turn. If the model's own opening response ignores the prior checkpoint's
      content entirely, the cap or the composition (design D5) may need revisiting — record what was
      observed rather than assuming the mechanism worked because it was present in the prompt.
- [ ] 13.3 **Does refusing a non-creator's task addition read as a helpful redirect, or a dead end?**
      Have an agent that is a loop's executor but not its creator attempt to add a task; read the
      403's message as the agent would receive it — does it plausibly lead the agent to actually send
      the message, or does it read like a bare permission error?
- [ ] 13.4 **The self-created-loop approval gate (D7) — does asking the operator actually work as a
      real interaction?** Drive an agent through creating a loop for itself, letting it fire once,
      then attempting an addition and going through the resulting `ask_user` flow for real. Confirm
      the operator sees a legible question, not a bare "may I add a task."

## 14. User test guide

**Setup.** A project with at least one registered agent and the operator's agent-job allowance
enabled (`_require_agent_job_allowance`, already required for any job-creating tool to work at all).
A short specification document with at least two declared tasks in its decomposition, not yet
approved.

1. **Create a loop bound to that document.** Use `create_loop` (or the equivalent job-creation UI
   once one exists) with `spec_document_id` set to the document's path and a `stop_when_queue_
   empties` stop condition. — *Expect:* the loop is created; its queue is empty (nothing approved
   yet).
2. **Approve the specification document.** — *Expect:* the loop's queue now holds the tasks the
   document declared — check via the task list scoped to the loop's id (`GET /tasks?loop_id=...`).
3. **Fire the loop once** (via its cron, or a manual trigger if one exists). — *Expect:* exactly one
   of the queue's tasks moves to an active status (claimed); the firing's message includes the
   loop's purpose and the claimed task's title and description, not just the job's own configured
   message.
4. **Let the claimed task reach a terminal status, then fire the loop again.** — *Expect:* the
   second firing claims a *different* task (the next oldest entry-status one); its briefing
   references what the first firing's checkpoint recorded — read the firing's transcript for
   language that plausibly reflects the first firing's outcome, not a generic restatement.
5. **Attempt to add a task to the loop as an agent that is not its creator.** — *Expect:* refused,
   with a message pointing at `send_message`.
6. **Drain the queue to empty and let the loop fire once more.** — *Expect:* the loop stops; check
   for a `loop_queue_exhausted` event (or its eventual UI surface) recording whether a request was
   outstanding when it stopped.

**Where it would go wrong:** if step 3's briefing is missing the claimed task's own text (only the
purpose and the operator's message appear), the composition in design D5/task 9.1 likely regressed.
If step 4's second firing shows no trace of the first firing's checkpoint, check
`latest_checkpoint_for_loop` is actually being called with the *loop's* id and not the new
conversation's id — the bug this whole change exists to prevent is exactly a checkpoint lookup that
silently falls back to "nothing found" because it is scoped to the wrong conversation.

---

# Addendum — tasks for the post-design decisions (D10–D15)

Added after the operator continued the design conversation. Sections A1–A5 are agent-verifiable;
A6 is human-only.

## A1. Control as a per-loop setting (design D10)

- [ ] A1.1 `loops.control` VARCHAR(32) nullable in the migration — **NULL means the current default**,
      never a stored copy of it, carrying `Agent.default_permission_mode`'s reasoning
      (`models.py:196`). Guard the migration step for a missing table.
- [ ] A1.2 Default the controller to the operator; delegation to the creator agent and back, after
      creation.
- [ ] A1.3 Route an extension request by controller: operator-controlled relays and changes nothing
      until the operator decides; delegated lets the creator decide.
- [ ] A1.4 **Reconcile with D7.** D7's first-fire boundary for self-created loops must now fall out
      of the default (control is the operator's, so nothing was delegated), not out of a separate
      role-identity check. Assert both routes reach the same outcome for a self-created loop, so the
      generalisation is proven rather than asserted.
- [ ] A1.5 Record each change of control against the loop with actor and time.

## A2. Editing, staged and visible (design D11)

- [ ] A2.1 Accept an edit at any time, including during a firing; store it as pending.
- [ ] A2.2 Apply pending edits at the next firing, before briefing.
- [ ] A2.3 Test that a firing in flight continues under the definition it was briefed with, with an
      edit landing mid-firing.
- [ ] A2.4 Report pending and in-force definitions **separately** — a requirement, not polish.
- [ ] A2.5 Record each edit against the loop with actor and time.

## A3. Late tasks (design D12)

- [ ] A3.1 Refuse a task added to a stopped loop, stating the stop reason and time. Refusal does not
      restart the loop.
- [ ] A3.2 Offer the refused task as the initial work of a new loop.

## A4. Per-loop history and a running firing (design D13)

- [ ] A4.1 A per-loop history home — `EventLog` is indexed by project and agent, not loop, so
      retrieving one loop's history must not mean scanning unindexed JSON.
- [ ] A4.2 Retrieve one loop's history; assert no event from another loop is returned.
- [ ] A4.3 `JobRun` records a firing as in progress while its run executes, distinct from completed
      and failed.
- [ ] A4.4 **One helper** answers "is a firing active for this loop", used by both the edit path and
      the loop panel in `2026-08-18-one-shell-three-panels`. Do not write it twice.
- [ ] A4.5 A crashed run must not leave a firing permanently in progress — reconcile on Hub restart
      as `Run.pid`/`last_heartbeat_at` already does.

## A5. Immutability and the identity gap (designs D14, D15)

- [ ] A5.1 `Task.loop_id` is write-once, enforced at the service layer, not by a DB constraint.
- [ ] A5.2 Test that reassigning a task between loops is refused and the task is unchanged.
- [ ] A5.3 **Record, do not fix, the name-reuse gap** (D15): a new agent taking an archived agent's
      name satisfies every creator check the original did. Add a test that *documents* the current
      behaviour so a future change closing it has something to flip, and reference D15 in its name.

## A6. Human-only — the operator's judgement

- [ ] A6.1 **Does "pending versus live" read clearly enough to trust?** Stage an edit during a firing.
      Not whether both are shown, but whether it is obvious which is in force right now.
- [ ] A6.2 **Is the refusal of a late task helpful or merely correct?** Does it read as the product
      helping, or as it saying no?
- [ ] A6.3 **Is delegating control discoverable without being easy to do by accident?**
- [ ] A6.4 **Does a loop's history read as a story or as a log?** It is the governance surface; if it
      cannot be skimmed it will not be read.

## A7. Additions to the user test guide

Run after the guide already in this file:

10. **Delegate control.** Delegate to the creator agent, then have the executor request work again.
    - *Expect:* the creator decides without involving you, and the change appears in the loop's
      history.
11. **Edit during a firing.** While a firing runs, change the loop's purpose.
    - *Expect:* accepted, marked pending, the running firing unaffected; live at the next firing.
12. **Add a task after it stops.**
    - *Expect:* refused, stating when and why it stopped, and offering the task to a new loop.

**Where it would go wrong.** If step 10 lets the creator decide *before* you delegated, A1.3 is not
reading the controller. If step 11's edit disturbs the running firing, A2.2 is applying immediately
rather than staging. If step 12 revives the loop, A3.1 is restarting it, which D12 rejected.

---

# Addendum 2 tasks — archival, ending state, and the loops surface (D16–D21)

Added after the operator conversation recorded in
`openspec/explorations/2026-08-18-the-side-panel-with-the-operator.md`. **B5 and B6 depend on
`2026-08-18-one-shell-three-panels` having landed its shell** — they are the shell's first non-spec
tenant. Everything in B1–B4 is independent of it and can land first.

## B1. Migration and model

- [x] B1.1 Extend the migration from 1.1 (or add a follow-on, whichever is the current head at
      implementation time) with three more additive nullable columns, same missing-table guard as the
      rest: `loops.archived_at` (DateTime, timezone-aware), `ai_jobs.archived_at` (same), and the
      column recording **how a loop ended** as a value (D17) — a short string, nullable, NULL while
      running.
- [x] B1.2 Leave `loops.job_id`'s `ondelete="CASCADE"` in place and add a comment saying why: no
      delete path survives D16, so it is unreachable, and dropping it on SQLite forces a table recreate
      for no behavioural change.
- [x] B1.3 Bump the head assertions in **both** `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py` (CLAUDE.md requires both).
- [x] B1.4 Decide and document the permitted values for B1.1's ending column in `models.py`, in a
      comment next to it, the way `Loop.purpose` and `Loop.stop_reason` already carry their reasoning.
      At minimum: completed (queue drained) and stopped (everything else), with `stop_reason` still
      carrying the prose.

      **2026-08-19, iteration 18.** New migration `0078_loop_and_job_archival.py`, `down_revision =
      "0077"`, copying 0077's own `_tables`/`_columns` missing-table-guard helpers rather than
      re-deriving them (no index helper needed — none of these three columns are indexed). Three
      additive nullable columns: `loops.archived_at`, `ai_jobs.archived_at` (both `DateTime(timezone=
      True)`), and `loops.ending_state` (`String(16)`). B1.2: added a comment on `Loop.job_id` in
      `models.py` explaining the cascade is inert post-D16, not removed. B1.4: `Loop.ending_state`'s
      own comment in `models.py` states the two permitted values verbatim (`"completed"`/`"stopped"`)
      and explains why a third is deliberately not wanted (D17's own rejection of a single
      lifecycle-with-archived-as-terminal design). `Loop.archived_at` got its own comment distinguishing
      the housekeeping axis from the ending-state axis, mirroring `Agent.archived_at`/
      `Conversation.archived_at`'s precedent per D16.

      B1.3: bumped `HEAD_REVISION` in `test_migrations.py` and the literal `"0077"` assertion in
      `test_project_persistence.py`, both to `"0078"`. Found and fixed a knock-on: 0077's own
      downgrade-round-trip test used a relative `command.downgrade(cfg, "-1")`, which after this bump
      only undoes 0078 and no longer exercises 0077's columns at all — silently correct-looking but
      testing the wrong migration. Changed it to the absolute target `"0076"` so it keeps testing 0077
      specifically regardless of how far head moves in the future. Added two new tests for 0078 itself,
      mirroring 0077's own pattern exactly: column-shape assertions (nullable, no backfill default) and
      a downgrade-then-upgrade round trip with rows populated in all three new columns beforehand,
      confirming the columns return as NULL (not restored) rather than merely present.

      **Verification.** `pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py -q`:
      **63 passed, 1 skipped** (up from 51 passed/1 skipped at prep — 7 new tests: the two 0078 tests
      plus test collection counting differently is not the reason, both files were re-run together and
      counted once). `ruff check` clean (one `SIM102` nested-if fixed by combining with `and`, matching
      the rest of the file's style — not left for a human pass). `black --check --target-version py311`
      clean on all four touched files (the bare `black --check` invocation misreports on this machine's
      Python 3.11 without `--target-version`, a known false-positive independent of this change — the
      targeted invocation is authoritative). `mypy hub/` (run from `hub/`, matching CLAUDE.md's editable-
      install path): **361 errors, 86 files** — byte-identical to the recorded baseline, confirming this
      task introduced no new mypy errors despite touching `models.py`. `npx openspec validate --changes
      --strict`: 2/2 still valid after this edit. No UI files touched, so no rebuild needed.

## B2. Archival replaces deletion

- [ ] B2.1 `DELETE /api/v1/jobs/{job_id}` refuses with a stated reason naming archiving as the
      alternative. Do not silently reinterpret a delete as an archive — a caller that asked to destroy
      data should be told it did not happen.
- [ ] B2.2 Archive route for a job, and for a loop. A loop's is **operator-only** — refuse any request
      carrying agent attribution, mirroring `spec_lifecycle.py:241`'s own rule for documents.
- [ ] B2.3 Refuse to archive a loop that is neither complete nor stopped (D17), stating that it must
      end first. Test that an enabled, firing loop cannot be archived.
- [ ] B2.4 Archived loops and jobs are excluded from default listings and included when explicitly
      asked for. Nothing is removed from the database.
- [ ] B2.5 Set the ending value from B1.1 where the loop actually ends: `scheduler.py`'s stop-condition
      path sets *completed* when the queue drained, *stopped* for `stop_at` and for an operator stop.
      `stop_reason`'s existing prose is unchanged and keeps its current wording.
- [ ] B2.6 Regression test: a loop archived after stopping still returns its purpose, queue history,
      firings, and stop reason. This is the D16 guarantee and the one most likely to rot.

## B3. `archive_job` on the MCP surface

- [ ] B3.1 Replace `delete_job` with `archive_job` in `hub/hub/mcp_server.py`. Remember the file is
      spawned standalone and may import only stdlib + fastmcp; anything it needs from the Hub is
      restated there, with the existing test asserting the two agree.
- [ ] B3.2 `archive_job` produces an operator approval decision on **every** call, independent of the
      run's permission posture (D18) — the standing `project.allow_agent_jobs` allowance grants the
      capability, not the direction. Test both postures.
- [ ] B3.3 `archive_job` refuses when the job has a loop, since a loop is operator-only (B2.2).
- [ ] B3.4 Update the tool-surface count and description in `CLAUDE.md` if the totals move, and update
      whatever test asserts the tool list matches the tools.

## B4. The loop summary tells the truth

- [ ] B4.1 Add `"assigned"` to `_batch_loop_summaries`'s `current_task` candidates query
      (`jobs.py:122-124`) — D21. One clause. Test with a task in `assigned` and nothing else.
- [ ] B4.2 `LoopSummary` gains the label the operator recognises a loop by (D20), sourced from the
      loop's job rather than requiring a second fetch, plus the ending value from B1.1 and whether it
      is archived.
- [ ] B4.3 Project-scoped list and detail endpoints for loops that require **no conversation id** —
      the reason D20 exists. Detail returns queue, current item, firing history (D13) and whether a
      firing is in progress (D13's helper, not a second join — D19).

## B5. The loops index tab

- [ ] B5.1 A `loops` index panel listing the project's loops: label, purpose, running/complete/stopped,
      queue counts, open questions. Registered in the shell as a singleton index tab.
- [ ] B5.2 Clicking a loop opens a `loop:<loop_id>` drill-down tab. The index **stays open** — unlike
      the files tree, which the shell's own design has a file replace (see the panel change). The
      distinction is deliberate: the index is a governance glance, not a launcher.
- [ ] B5.3 Counts by ending state (*"4 complete · 1 stopped early · 2 running"*) computed from B1.1's
      value, never by matching `stop_reason` text.
- [ ] B5.4 Archived loops are out of the index by default, reachable behind an explicit filter.

## B6. The loop drill-down tab

- [ ] B6.1 A `loop:<loop_id>` panel: purpose, stop condition, ending state and reason, queue counts by
      status, the claimed item, open questions, and the firing history.
- [ ] B6.2 The active-now indicator consumes **D13's helper** — the same one the loop's own machinery
      uses. Do not add a second join over `JobRun.conversation_id`/`Run.status` (D19).
- [ ] B6.3 Motion only on the active-now indicator; queue counts and ending state update without a
      transition. A CSS-driven animation inherits `index.css`'s existing blanket reduced-motion rule; a
      JS-driven one needs its own `matchMedia` check.
- [ ] B6.4 Live updates via `useSSE` plus React Query invalidation on the relevant events, including
      `loop_queue_exhausted` from D6 — this is that event's first consumer.
- [ ] B6.5 A loop that has ended still renders completely. The tab is the governance record; it is most
      valuable *after* the loop finished.
- [ ] B6.6 Audit the `Icon` map before assuming a loop/queue/claimed-item icon exists. `Icon` only —
      CLAUDE.md forbids a second icon system.

## B7. Human-only — the operator's judgement

- [ ] B7.1 **Does the loops index answer "what is running right now" at a glance**, without opening a
      drill-down? That is the whole reason it stays open when a drill-down is opened.
- [ ] B7.2 **Does a refused delete read as the product protecting history, or as it being obstinate?**
      B2.1's message is the entire experience of D16 for anyone who meets it.
- [ ] B7.3 **Is "complete" visibly different from "stopped early"** at a glance, or do they read as the
      same grey badge? If they read the same, B1.1's value bought nothing a sentence did not.
- [ ] B7.4 **Does `archive_job`'s always-ask feel like protection or like nagging** after the fifth
      time? D18 set a precedent; this is where it gets tested against real use.

## B8. Additions to the user test guide

Run after the guides already in this file:

13. **Try to delete a loop's job.** Use the UI, then the API directly.
    - *Expect:* refused both ways, naming archiving. The loop still exists with its full history.
14. **Archive a running loop.**
    - *Expect:* refused, stating it must stop or complete first.
15. **Let a loop drain its queue, then archive it.**
    - *Expect:* it records *completed* (not merely "stopped"), disappears from the default index, and
      is still fully readable when archived loops are shown.
16. **Ask an agent to archive a bare job**, with the allowance enabled and permissions on auto.
    - *Expect:* you are still asked to approve it. If it happens silently, B3.2 is reading the
      allowance as direction.
17. **Open the loops index, drill into a loop, then look at the index again.**
    - *Expect:* both tabs open; the index did not close when the drill-down opened.

**Where it would go wrong.** If step 13 succeeds anywhere, D16 is not enforced at the route and only
in the UI. If step 15 shows "stopped" rather than "completed", B2.5 is not setting the value at the
drain path. If step 16 archives silently, B3.2 fell back to `create_job`'s allowance-only gate.
