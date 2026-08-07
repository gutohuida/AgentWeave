# Handoff: Local multi-project workspace phase 3.5/3.6 complete — unavailable-directory scheduling and repair

**Date:** 2026-08-04T02:40:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `b4f86fa`
**Agent:** Claude Code (Sonnet 5)
**Previous handoff:** `.claude/handoffs/2026-08-04-0009-local-multi-project-phase3b.md`
**Status:** chunk complete — tasks 3.5-3.8 of phase 3 are finished and verified.

## Goal

Finish phase 3 ("Runtime and filesystem isolation") of the approved local multi-project
workspace change by implementing the requirement that unavailable project directories refuse
new operator input while preserving existing queued state, pausing autonomous/scheduled
starts with an attributed event, and repairing via relocation/open without disabling jobs.

## Current state

**Implemented and committed (ca0a5c4, b4f86fa):**

- Added `hub/tests/test_project_workspace_unavailable.py` with 7 tests covering:
  - operator trigger refused (409) before queueing when workspace unavailable;
  - operator message refused (409) before queueing when workspace unavailable;
  - question answer refused (409) and question stays unanswered when workspace unavailable;
  - agent-to-agent message is **not** refused (regression lock: stays 201 and queued);
  - queued entry survives and a `queue_agent_paused` event is emitted when workspace becomes
    unavailable between queuing and scheduling;
  - scheduled job fire pauses (not fails): `JobRun.status == "fired"`, `Job.enabled == True`,
    entry stays queued, `queue_agent_paused` event exists;
  - relocation repairs and re-drains queued work, producing a real Run.
- Added `raise_workspace_http_error` in `hub/hub/project_workspace.py` (shared, public
  conversion of `ProjectWorkspaceError` to FastAPI 409/422).
- Updated `hub/hub/api/v1/projects.py` to use the shared error helper, extract the settings-PATCH
  re-drain loop into `turn_scheduler.redrain_queued_agents`, and call it after successful
  `open_project`, `create_project` (not needed, but kept consistent), `relocate_project`, and
  `update_project_settings`.
- Updated `hub/hub/turn_scheduler.py` to add `redrain_queued_agents(project_id)` and persist a
  `queue_agent_paused` event (severity `warn`) plus SSE broadcast whenever a caught
  `TriggerAgentError` is flagged `workspace_unavailable`.
- Updated `hub/hub/api/v1/agent_trigger.py`: `TriggerAgentError` carries
  `workspace_unavailable` and `directory_state`; `trigger_agent_directly` flags the error when
  workspace resolution fails; `trigger_agent` route now resolves the workspace early and refuses
  operator input with the shared 409 response before queuing.
- Updated `hub/hub/api/v1/messages.py` and `hub/hub/api/v1/questions.py` to add the same early
  workspace refusal check **only** in the operator routes (`create_message`, `answer_question`),
  leaving `create_message_for_actor` untouched so run-token agent-to-agent messages remain
  durable/paused, not refused.
- Marked tasks 3.5-3.8 complete in
  `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md`.

**Verified:**

- `py -3.11 -m pytest hub/tests/test_project_workspace_unavailable.py -v` → 7 passed.
- `py -3.11 -m pytest tests -q` from `hub/` → 562 passed, 7 skipped.
- `py -3.11 -m black hub/hub/project_workspace.py hub/hub/turn_scheduler.py
  hub/hub/api/v1/agent_trigger.py hub/hub/api/v1/messages.py
  hub/hub/api/v1/questions.py hub/hub/api/v1/projects.py
  hub/tests/test_project_workspace_unavailable.py` → reformatted 3 files.
- `py -3.11 -m ruff check <above files>` → only pre-existing `N818`/`UP007` warnings in
  `project_workspace.py` (exception naming and union syntax) unrelated to this change.
- `py -3.11 -m compileall <above files>` → no syntax errors.
- `git diff --check` → clean.

## Files touched

- `hub/hub/project_workspace.py` — added public `raise_workspace_http_error`; imports unchanged
  except for the existing `NoReturn`, `HTTPException`, `status` additions from the prior
  handoff.
- `hub/hub/turn_scheduler.py` — added `InboundQueueEntry` import, `sse_manager`, `persist_event`,
  `queue_agent_paused` event emission, and new `redrain_queued_agents` function.
- `hub/hub/api/v1/projects.py` — removed local `_raise_workspace_http_error`; imports shared
  helper only; replaced inline re-drain loop with `redrain_queued_agents` calls in
  `update_project_settings`, `open_project`, `relocate_project`.
- `hub/hub/api/v1/agent_trigger.py` — extended `TriggerAgentError`; flagged workspace failures;
  added early workspace resolution/refusal in `trigger_agent` route; reused resolved root for
  `work_dir` validation.
- `hub/hub/api/v1/messages.py` — added early workspace refusal check in `create_message` route.
- `hub/hub/api/v1/questions.py` — added early workspace refusal check in `answer_question` route.
- `hub/tests/test_project_workspace_unavailable.py` — new 7-test file.
- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md` — checked off 3.5-3.8.

## Key decisions

- **Scope "refuse new operator input" to exactly three routes** (`trigger_agent`,
  `create_message`, `answer_question`), not the shared actor functions. Reason: `send_peer_message`
  and `request_agent` are authenticated by run token and represent an already-running agent's own
  continuation; refusing those would drop live agent output, not "refuse new operator input".
  Regression lock: test `test_agent_to_agent_message_is_not_refused_but_stays_queued_when_workspace_unavailable`.
- **One generic `queue_agent_paused` event in `turn_scheduler.schedule_agent`**, not at each
  call site. Reason: `schedule_agent` already catches every `TriggerAgentError` uniformly; every
  caller (operator, agent-to-agent, scheduled job, settings/relocate re-drain) gets the event
  for free.
- **Repair re-drain reuses the existing settings-PATCH pattern** extracted into
  `redrain_queued_agents`. Reason: the scheduler has no periodic retry sweep; repair must
  explicitly re-evaluate queued work, and extracting the pattern avoids duplication between
  settings, relocate, and open.
- **No change to `scheduler.py`**. Reason: confirmed `schedule_agent` never raises; a job fire
  with unavailable workspace already leaves `JobRun.status == "fired"` and `Job.enabled` intact
  once the pause event is emitted.

## Constraints and user directives (verbatim)

- "This repo has no AgentWeave session, and must not acquire one."
- "Do the work directly."
- "Write to `openspec/changes/<date>-<name>/`."
- "Nothing under `.agentweave/`, `agentweave.yml`, or `spec/` should exist at the repository root."
- "Also: stage paths explicitly. `git add -A` sweeps in untracked `.claude/handoffs/` scratch."
- "Tests open every phase; implementation does not begin until the phase's failing contract is
  demonstrated."
- "Commit each completed task/checkpoint without asking first."
- "Commit titles must name the actual current change (`local multi-project workspace`)."

## Dead ends

None. One near-miss while writing tests: initial `bind_project_workspace(directory)` calls failed
because `directory` did not exist; fixed by adding `directory.mkdir(parents=True, exist_ok=True)`.
Another: first route URLs omitted `/projects/proj-test/` prefix because the handoff referenced
unprefixed paths; corrected by matching existing test conventions (`/api/v1/projects/proj-test/...`).

## Verification

Exact commands run and results:

- `py -3.11 -m pytest hub/tests/test_project_workspace_unavailable.py -v` from `hub/`
  → 7 passed.
- `py -3.11 -m pytest tests -q` from `hub/` → 562 passed, 7 skipped.
- `py -3.11 -m black <changed files>` → 3 files reformatted.
- `py -3.11 -m ruff check <changed files>` → only pre-existing `N818`/`UP007` in
  `project_workspace.py`.
- `py -3.11 -m compileall <changed files>` → success.
- `git diff --check` → clean.

Not tested: UI/frontend (phase 4), Docker paths (phase 6), live CLI/HUB end-to-end in `testbed/`
(phase 6 closeout).

## Git state

- Branch `hub-native-experience`; HEAD is `b4f86fa`.
- Two new commits since previous handoff (`b973e69`):
  - `ca0a5c4` local multi-project workspace phase 3.5/3.6: unavailable directory scheduling and repair
  - `b4f86fa` local multi-project workspace phase 3.5/3.6: mark tasks 3.5-3.8 complete
- Worktree still has many pre-existing modified/untracked files from phases 0-3 (see
  `git status --short`); nothing new was added by this chunk beyond the committed files above.
- `.claude/handoffs/LATEST.md` is modified (session-end scratch) and must not be committed.
- No upstream configured.

## Next steps

1. Move to phase 4 ("Multi-project SSE and frontend data identity"):
   read `openspec/changes/2026-08-03-local-multi-project-workspace/specs/multi-project-sse/spec.md`
   and `tasks.md` section 4, then write the phase 4 failing tests first.
2. Before starting phase 4, re-read `proposal.md`, `design.md`, and all three delta specs as
   required by the working protocol in `tasks.md`.
3. When context fills up, run `/handoff` again; otherwise continue directly.

## Open questions for the user

None. Phase 3 is complete.

## Read on resume

- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md` — next phase checklist.
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/multi-project-sse/spec.md`
  — phase 4 requirement source.
