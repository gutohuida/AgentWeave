# Handoff: Local multi-project workspace phase 3.5/3.6 — design complete, implementation not started

**Date:** 2026-08-04T00:08:57+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `b973e69`
**Agent:** Claude Code (Sonnet 5)
**Previous handoff:** `.claude/handoffs/2026-08-04-0100-local-multi-project-phase3a.md`
**Status:** in progress — full implementation plan is decided and detailed below (file-by-file,
line-by-line where possible), but almost no code has actually been written yet. Do not assume
anything beyond "## Files touched" is done.

## Goal

Implement the remainder of phase 3 ("Runtime and filesystem isolation") of the approved local
multi-project workspace change: tasks 3.5 (write unavailable-directory tests, test-first) and 3.6
(implement unavailable/repair scheduling behavior). Tasks 3.1-3.4 (project-rooted runtime paths)
are already complete and committed (`eb54db7`, `b973e69`) — this chunk is the "Unavailable project
directories preserve state and pause execution" requirement from
`openspec/changes/2026-08-03-local-multi-project-workspace/specs/local-project-workspace/spec.md`
(lines 117-136), which the phase 3.1-3.4 handoff explicitly deferred.

## Current state

**Verified working (re-ran, unchanged from prior handoff):** Full Hub suite — 555 passed, 7
skipped — confirmed at the start of this session before any new work.

**Research complete, fully informs the plan below** (see "Key decisions" and "Next steps" — do
not re-research, just implement):

- Traced every place new agent-turn input gets queued (`hub/hub/inbound_queue.py`'s `new_entry`)
  and confirmed **no code path currently refuses an HTTP request when the project workspace is
  unavailable** — every "new input" endpoint queues first, unconditionally, then calls
  `schedule_agent`, which internally swallows a `TriggerAgentError` into a `waiting_reason` string
  with no distinction from any other transient wait condition (already-running, hop-budget, etc.)
  and **no event is persisted for it**.
- Confirmed the event-log system: `hub/hub/utils.py:14-34`'s `persist_event(session, project_id,
  event_type, data=None, agent=None, severity="info")`, read back via `GET /events/history`
  (`hub/hub/api/v1/events.py:19-43`, oldest-first) and broadcast live via
  `sse_manager.broadcast(project_id, event_type, payload)`. Precedent for a "went wrong but isn't
  fatal" event: `job_run_skipped` (`hub/hub/scheduler.py:314-328`, severity default "info") and
  `job_run_failed` (`hub/hub/scheduler.py:394-409`, severity "error").
- Confirmed there is **no generic periodic retry sweep** — `hub/hub/scheduler.py`'s `JobScheduler`
  is cron-driven per job, not a sweep of all waiting work. Re-scheduling after repair must be
  triggered explicitly by the repair action itself (relocate/open), the same way
  `hub/hub/api/v1/projects.py:240-258`'s `update_project_settings` already re-drains queued agents
  after a settings change — that inline loop is the pattern to extract and reuse.
- Confirmed `Project.directory_state` (`hub/hub/db/models.py:62-64`, check constraint at 82-88
  already allows `unbound/available/missing/unreadable/not_directory/identity_conflict`) is
  **already** fully surfaced in `ProjectSummary.directory_state` and every `hub/hub/api/v1/projects.py`
  project route — the "project remains visible with that state" half of the requirement needs no
  new code.
- Read `hub/hub/turn_scheduler.py` in full (29-87): `schedule_agent(project_id, agent)` already
  never lets a failure drop a queued entry — on any failure (agent running, empty queue, hop
  budget, token budget, or a caught `TriggerAgentError`) it just returns a `ScheduleResult` without
  touching the `InboundQueueEntry` rows. This means requirement (b) "existing queued entries...
  remain durable" is **already true today**, it's just unobserved (no event, no distinction of
  cause).
- Read `hub/hub/scheduler.py:246-409` (`_do_fire_job`/`_fire_job_internal`) in full: a cron job
  fire creates and commits its `InboundQueueEntry` *before* calling `schedule_agent`, and
  `schedule_agent` never raises — so a workspace-unavailable failure during a job fire already
  leaves `JobRun.status == "fired"` (not "failed") and never touches `Job.enabled`. **No code
  change needed in `scheduler.py`** — jobs get pause-not-fail behavior for free once
  `schedule_agent` itself is fixed, and the missing piece (an attributed event) will apply to
  every caller uniformly once added in one place (`turn_scheduler.py`).
- Traced auth on every "new input" route to separate genuine operator input (must be refused) from
  agent-to-agent/autonomous continuation (must NOT be refused, only paused):
  - `hub/hub/api/v1/agent_trigger.py`'s `trigger_agent` (`POST /agent/trigger`) — `get_project`
    dependency (`aw_live_...` operator credential). **Operator input.**
  - `hub/hub/api/v1/messages.py`'s `create_message` (`POST /messages`) — `get_project` dependency.
    **Operator input.**
  - `hub/hub/api/v1/questions.py`'s `answer_question` (`PATCH /questions/{id}`) — `get_project`
    dependency. **Operator input.**
  - `hub/hub/api/v1/agent_actions.py`'s `send_peer_message` (`POST /agent-actions/messages`) —
    `get_agent_actor` dependency (`Bearer aw_run_...` run token, minted per `Run`). Calls the
    *same* `create_message_for_actor` function as the operator route above. **NOT operator
    input** — an already-running agent's own outbound hop; refusing this mid-turn would drop a
    live agent's output, not "refuse new input". Must stay durable/paused, not refused.
  - `hub/hub/api/v1/agents.py`'s `request_agent` (`POST /agents/request`, ~line 660-775) — uses
    `get_project` at the FastAPI layer, but its own docstring states "source identity is derived
    from the bound running Run... neither the MCP tool nor the command endpoint accepts a
    caller-supplied requester identity" — functionally this is an **agent** delegating to a new
    teammate mid-turn, not a human. Treated as autonomous/pause, not refused, for the same reason
    as `send_peer_message`.
  - **Conclusion: gate exactly three routes** (`trigger_agent`, `create_message`,
    `answer_question`) with a pre-queue availability check; leave `send_peer_message` and
    `request_agent` alone (they already pause correctly via `schedule_agent` once 3.6 is done).

## Files touched

- `hub/hub/project_workspace.py` — **only change made so far**: added `NoReturn` to the
  `typing` import and `from fastapi import HTTPException, status`. **The actual
  `raise_workspace_http_error` function body has NOT been written yet** — this was the very next
  edit in progress when the session was interrupted. See "Next steps" step 1 for its exact shape
  (it's a straight relocation of `hub/hub/api/v1/projects.py`'s existing private
  `_raise_workspace_http_error`, lines 139-153, unchanged in behavior, made public and shared).

Nothing else has been edited. No test file exists yet for phase 3.5.

## Key decisions

- **Scope "refuse new operator input" to exactly three routes** — `trigger_agent`,
  `create_message`, `answer_question` — identified by auth dependency *and* product intent (see
  "Current state" above for the full trace). Rejected alternative: gating the shared
  `create_message_for_actor`/`request_agent` functions themselves, which would have refused a
  live agent's own in-flight message/delegation, not "new operator input" — caught via grep
  showing `agent_actions.py`'s `send_peer_message` calls the identical `create_message_for_actor`
  function under run-token auth.
- **`trigger_agent_directly`'s existing workspace-resolution check (`agent_trigger.py:227-232`,
  from task 3.2) already refuses new *process starts*** — task 3.6 does not need new refusal logic
  there, only needs to tag the raised `TriggerAgentError` with a `workspace_unavailable: bool`
  flag (plus `directory_state: Optional[str]`) so `turn_scheduler.py` can distinguish this cause
  from every other `TriggerAgentError` cause (no runner bound, already running, unsupported
  runner, etc.) without string-matching `exc.detail`. Rejected alternative: reusing
  `ProjectWorkspaceError.code` string values inside `turn_scheduler.py` — rejected because it
  would make `turn_scheduler.py` depend on `project_workspace`'s code taxonomy for something
  `agent_trigger.py` already knows definitively at the point it raises.
- **One generic event, persisted in exactly one place** (`turn_scheduler.schedule_agent`'s
  `except TriggerAgentError` branch), not a job-specific event in `scheduler.py` or a
  trigger-specific one in `agent_trigger.py`. Every one of the 7+ callers of `schedule_agent`
  (operator trigger, operator message, operator question-answer, agent-to-agent message, agent
  delegation, cron job fire, settings/relocate re-drain) gets the same attributed
  `queue_agent_paused` event for free. Rejected alternative: adding the event at each call site —
  rejected as needless duplication when `schedule_agent` is the one place that already
  uniformly catches the exception.
- **Re-drain-on-repair reuses and extends the existing pattern, not a new mechanism.**
  `projects.py:240-258` already re-drains queued agents after a settings PATCH. Plan: extract that
  loop into `turn_scheduler.redrain_queued_agents(project_id) -> None`, then call it from three
  places: the existing settings-PATCH site (refactor, no behavior change), the new
  `relocate_project` route (after a successful relocate), and the new `open_project` route (after
  a successful open — this is the literal "unavailable project's marked directory is opened at a
  new path" repair scenario named in the spec, distinct from the explicit `/relocate` action).
- **No `scheduler.py` change at all.** Confirmed by full read that cron job firing already
  degrades correctly (queue entry durable, `JobRun.status` stays "fired", `Job.enabled` untouched)
  once `schedule_agent` stops being silent about the cause — see "Current state" above.

## Constraints and user directives (verbatim)

- "This repo has no AgentWeave session, and must not acquire one."
- "Do the work directly."
- "Write to `openspec/changes/<date>-<name>/`."
- "Nothing under `.agentweave/`, `agentweave.yml`, or `spec/` should exist at the repository root."
- "Also: stage paths explicitly. `git add -A` sweeps in untracked `.claude/handoffs/` scratch."
- User commands in this workstream: `$resume`, `approve`, `continue`.
- Do not invoke shipped `aw-*` product skills against this framework repository.
- Re-read the proposal, design, all three delta specs, and tasks before every phase; demonstrate
  failing contracts before implementation (test-first) — task 3.5 is explicitly "write ... tests"
  before task 3.6 "implement". **The next session must write the test file before writing any
  production code**, even though the full design (including exact production edits) is already
  decided below — writing tests first is still the required order, not just a nice-to-have.
- From standing memory: commit each completed task/checkpoint without asking first; verify prior
  session's claimed work still functions on every resume (done at the start of this session —
  full Hub suite re-run, 555/7, matched the prior handoff exactly).
- Commit titles must name the actual current change (`local multi-project workspace`), checked
  against the openspec change directory name, not copy-pasted from a different change's style.

## Dead ends

None hit this session — this was a research-and-design session, not an implementation session,
so no failed attempts to report. One corrected assumption (not a dead end in code, just in
planning): initially assumed the refusal check belonged inside the shared
`create_message_for_actor`/`request_agent` functions; corrected after grep showed those are
shared with agent-authenticated (run-token) callers — see "Key decisions" above.

## Verification

- `py -3.11 -m pytest hub/tests -q` from `hub/` — 555 passed, 7 skipped, ~98s. Confirms prior
  session's work (phase 3.1-3.4) still functions; this is the *only* test run this session, before
  any new code was written.

Not yet done (this whole chunk is still ahead):

- No new test file written.
- No production code written beyond two import lines in `project_workspace.py`.
- Nothing has been run against the new (not-yet-written) behavior.

## Git state

- Branch `hub-native-experience`; HEAD is `b973e69` (unchanged this session — no new commits).
- Worktree dirty state is **unchanged from the phase 3.1-3.4 handoff** except for one in-progress,
  uncommitted edit: `hub/hub/project_workspace.py` gained two import lines (`NoReturn` added to
  the `typing` import; `from fastapi import HTTPException, status` added). Every other dirty/
  untracked file listed in `git status --short` at the top of this session is pre-existing state
  from phases 0-2, untouched this session (see phase 0/1/2 handoffs for that detail).
- No upstream configured.
- Root `.agentweave/`, `agentweave.yml`, `spec/` — not checked this session (no test run touched
  the repo root); confirmed absent as of the last full suite run in the phase 3.1-3.4 handoff.

## Next steps

Write the test file first (per the constraints above), *then* implement — even though every
production edit below is already fully decided, do not reorder this.

1. **Write `hub/tests/test_project_workspace_unavailable.py`** (new file — phase's own convention
   of one dedicated file per real multi-directory scenario, per the 3.1-3.4 handoff's "Key
   decisions"). Use `bind_project_workspace(directory)` (conftest.py) to register a real directory
   for `proj-test`, then make it unavailable by deleting/moving it on disk (not by re-monkeypatching
   — `bind_project_workspace` already restores the *real* `resolve_project_workspace`, so it will
   naturally raise once the bound path is gone). Planned tests (7):
   - `test_trigger_is_refused_when_workspace_unavailable` — bind a dir, `shutil.rmtree` it, `POST
     /agent/trigger` → expect 409 with `{code, message, directory_state}` detail; assert zero
     `InboundQueueEntry` rows exist for that agent (refused *before* queuing, not after).
   - `test_message_is_refused_when_workspace_unavailable` — same shape via `POST /messages`.
   - `test_answering_question_is_refused_when_workspace_unavailable` — insert a `Question` row
     directly via `async_session_factory()` (mirrors `test_agent_actions_coordination.py:11-25`'s
     direct-DB-insert style) before removing the directory, then `PATCH /questions/{id}` → 409;
     assert `question.answered` stays `False`.
   - `test_agent_to_agent_message_is_not_refused_but_stays_queued_when_workspace_unavailable` —
     use the `_active_run(run_id, agent)` pattern from
     `test_agent_actions_coordination.py:11-25` (mint a real `Run` + capability token, `Bearer
     aw_run_...` header) to call `POST /agent-actions/messages` while the directory is unavailable
     → expect 201 (not refused), and the resulting `InboundQueueEntry` stays `state="queued"`.
     This is the regression lock for the "operator vs. autonomous" design decision above — without
     it, someone could "fix" the trigger/message/question gating by moving the check into the
     shared function and silently break agent-to-agent continuation.
   - `test_queued_entry_survives_and_pause_is_attributed_when_workspace_becomes_unavailable` —
     bind dir, bind runner, insert a blocking `Run(status="running")` directly via DB for the
     target agent (so `schedule_agent`'s first check stops it deterministically, no PTY mocking
     needed), `POST /agent/trigger` while *available* → entry queues normally (200, not refused).
     Then `shutil.rmtree` the directory, flip the blocking `Run.status` to `"completed"` via DB,
     and call `hub.turn_scheduler.schedule_agent("proj-test", agent)` directly. Assert: no
     exception; the `InboundQueueEntry` is still `state="queued"`; a `queue_agent_paused` (or
     whatever name is chosen in step 3 below — keep this test's assertion in sync) `EventLog` row
     exists with `severity="warn"`, queried directly via `select(EventLog).where(...)`
     (`hub/hub/api/v1/events.py`'s response shape for reference, but query the DB directly like
     `test_scheduler.py` does — no need to go through the HTTP endpoint).
   - `test_job_fire_pauses_without_failing_when_workspace_unavailable` — mirrors
     `test_scheduler.py:22-101`'s `_make_job` + `scheduler._fire_job_internal(job,
     trigger="scheduled", session=db)` pattern, but with the directory removed first (no PTY
     mocking needed — the failure happens before spawn). Assert: `_fire_job_internal` returns
     (does not raise); `JobRun.status == "fired"` (not `"failed"`); `job.enabled` stays `True`; the
     `InboundQueueEntry` stays `"queued"`; a `queue_agent_paused` event exists.
   - `test_relocate_repairs_and_redrains_queued_work` — end-to-end repair test. Bind dir_a, bind a
     runner, get an entry stuck queued (reuse the blocking-`Run` trick above, or the job trick —
     either works), `shutil.move` (not rmtree — must preserve `.agentweave/project.json`) dir_a to
     a new path, clear the blocking condition, then `POST /projects/proj-test/relocate {"path":
     str(new_path)}` with `PtySession.spawn` patched via the `_fake_pty` helper (copy the pattern
     from `test_project_scoped_runtime.py:73-78`) so the re-drain's `schedule_agent` call can
     actually complete a run. Assert: relocate response is 200 with `directory_state="available"`;
     after draining `agent_trigger._background_runs`, a `Run` row now exists for the agent (proof
     the re-drain actually fired `schedule_agent`, not just that relocate succeeded).
2. Run the new test file in isolation (`py -3.11 -m pytest hub/tests/test_project_workspace_unavailable.py
   -v` from `hub/`) and confirm it **fails** for the right reasons (no refusal exists yet, no
   `queue_agent_paused` event exists yet, no re-drain on relocate exists yet) — this is the
   "demonstrate failing contracts before implementation" checkpoint the working protocol requires.
3. **Implement, in this order:**
   a. `hub/hub/project_workspace.py` — finish the in-progress edit: add
      ```python
      def raise_workspace_http_error(exc: "ProjectWorkspaceError") -> NoReturn:
          if isinstance(exc, ProjectIdentityConflict):
              status_code = status.HTTP_409_CONFLICT
          elif isinstance(exc, ProjectWorkspaceUnavailable):
              status_code = status.HTTP_409_CONFLICT
          else:
              status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
          raise HTTPException(
              status_code=status_code,
              detail={"code": exc.code, "message": str(exc), "directory_state": exc.directory_state},
          ) from exc
      ```
      (straight relocation of `projects.py:139-153`'s private version, now public/shared).
   b. `hub/hub/api/v1/projects.py` — delete the local `_raise_workspace_http_error`
      (lines 139-153), import `raise_workspace_http_error` from `...project_workspace` instead,
      update its 3 call sites (`open_project`, `create_project`, `relocate_project`). Extract the
      inline re-drain loop (lines 240-258) into `turn_scheduler.redrain_queued_agents` (see 3c),
      call it from `update_project_settings` (replacing the inline loop), `relocate_project`
      (new, after success), and `open_project` (new, after success).
   c. `hub/hub/turn_scheduler.py` — add `from .utils import persist_event`, `from .sse import
      sse_manager`. Add `async def redrain_queued_agents(project_id: str) -> None` (the extracted
      loop: select distinct `InboundQueueEntry.agent` where `project_id` matches and
      `state == "queued"`, call `schedule_agent(project_id, agent)` for each — needs its own
      `async_session_factory()` session for the query since callers may be mid-request with a
      different session doing the querying; check how `projects.py`'s existing inline loop gets
      its session before deciding whether `redrain_queued_agents` takes a `session` param or opens
      its own). In `schedule_agent`'s `except TriggerAgentError as exc:` branch (line 85-86): if
      `getattr(exc, "workspace_unavailable", False)`, persist a `queue_agent_paused` event
      (`severity="warn"`, payload `{"agent": agent, "reason": exc.detail, "directory_state":
      exc.directory_state}`) and broadcast it via `sse_manager.broadcast`, *then* still `return
      ScheduleResult(waiting_reason=exc.detail)` unchanged (do not change the returned string —
      existing tests in `test_agent_trigger.py`/`test_inbound_queue.py`/`test_accounting_budget.py`
      assert substrings of other `waiting_reason` values; grepped and confirmed none assert on
      workspace-related text, so this is safe, but don't change the string anyway).
   d. `hub/hub/api/v1/agent_trigger.py` — add `workspace_unavailable: bool = False,
      directory_state: Optional[str] = None` params to `TriggerAgentError.__init__` (line 132),
      store as attrs. At the existing workspace-resolution catch (lines 227-232), pass
      `workspace_unavailable=True, directory_state=exc.directory_state`. In the `trigger_agent`
      route (line 423+), add an early check right after the existing `session_mode` validation and
      before `get_agent_config`: resolve `workspace_root = await
      project_workspace.resolve_project_workspace(session, project_id)`, catching
      `ProjectWorkspaceError` and calling `project_workspace.raise_workspace_http_error(exc)`.
      Reuse this `workspace_root` for the existing `if body.work_dir:` block below (lines 447-452)
      instead of that block re-resolving — removes a now-redundant second resolve call.
   e. `hub/hub/api/v1/messages.py` — in the `create_message` route (not
      `create_message_for_actor`, which stays untouched so `agent_actions.py`'s `send_peer_message`
      is unaffected), add the same resolve-or-refuse check before calling
      `create_message_for_actor`.
   f. `hub/hub/api/v1/questions.py` — in `answer_question`, add the same check before creating the
      queue entry (before line 132's `new_entry(...)` call).
4. Re-run the new test file — all 7 should pass. Then run the full Hub suite
   (`py -3.11 -m pytest hub/tests -q` from `hub/`) to confirm no regression, especially in
   `test_agent_trigger.py`, `test_messages.py`, `test_questions.py`, `test_scheduler.py`,
   `test_project_scoped_runtime.py` (all touch the changed routes/functions).
5. Check off tasks 3.5 and 3.6 in
   `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md`.
6. Move to task 3.7 (verify — black/compileall/openspec validate/git diff --check, per the exact
   command list in the phase 3.1-3.4 handoff's own "Verification" section) and 3.8 (`/handoff`
   covering the full phase 0-3 arc).

## Open questions

None. Design is fully decided (see "Key decisions"); nothing here requires a human call.

## Read on resume

- `hub/hub/turn_scheduler.py` — the file most next-step edits center on; re-read in full before
  editing (last read in full this session, 29-87).
- `hub/hub/api/v1/agent_trigger.py` — `TriggerAgentError` (line 124-135), the workspace-resolution
  catch (227-232), and the `trigger_agent` route (423-520) — all three need edits.
- `hub/hub/api/v1/projects.py` — `_raise_workspace_http_error` (139-153), `update_project_settings`
  (228-259, has the re-drain loop to extract), `relocate_project` (262-278, needs the new re-drain
  call).
- `hub/tests/conftest.py` — `bind_project_workspace` (135-157) is the fixture the new test file
  builds on; re-read its docstring before writing tests that make a bound directory unavailable.
- `hub/tests/test_agent_actions_coordination.py` lines 1-52 — `_active_run` helper pattern needed
  for the agent-to-agent regression test.
- `hub/tests/test_scheduler.py` lines 1-101 — `_make_job` + `_fire_job_internal` pattern needed
  for the job-pause test.
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/local-project-workspace/spec.md`
  lines 117-136 — the exact requirement text this chunk implements; re-read once more right before
  writing the test file's docstring/scenarios.
