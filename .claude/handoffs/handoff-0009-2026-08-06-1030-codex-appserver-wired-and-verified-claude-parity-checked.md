# Handoff: Codex app-server wired into the live run path, breach-tested live, and Claude parity checked

**Date:** 2026-08-06T10:30 · **Branch:** hub-native-experience · **HEAD:** 98117b9
**Agent:** Claude Sonnet 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0008-2026-08-06-0940-codex-appserver-transport-built.md
**Status:** chunk complete. Three commits, all live-verified against a real Hub + real `codex`/
`claude` CLIs, not just unit tests.

## Goal

Continue from handoff-0008: the Codex `app-server` protocol layer (`hub/hub/codex_appserver.py`)
was built and unit-tested last session, but nothing in the live run path called it yet. This
session's explicit job, per handoff-0008's "Next steps" and the operator's own choice at the
first checkpoint, was task 2.8 (wire `run_turn` into `agent_trigger.py`'s `_execute_run`) — the
piece deliberately deferred to a fresh session as "the highest-risk part of this whole change."
After that landed and tested clean, the operator chose to continue into task 2.14 (the live
breach test) and then task 2.15 (Claude parity check) rather than stopping.

## Current state

**Task 2.8 is fully wired, tested, and committed (`f7a6359`).** A codex Runner's `flags`
containing the sentinel `codex_appserver.APP_SERVER_OPT_IN_FLAG` (`"--app-server"`) selects the
app-server transport for that agent's runs; `exec` remains the default for every codex Runner
that doesn't opt in. `trigger_agent_directly` strips the sentinel out of `runner_row.flags`
before it reaches `build_command`, so it can never leak into a real `codex exec` argv.
`_execute_run` branches to a new `_execute_codex_appserver_run` when the flag is set, which wires
`run_turn`'s `on_event`/`on_usage`/`on_accounting` callbacks to the same
`record_agent_output`/`record_context_usage`/`record_turn_usage` calls the `exec` path makes, a
new `on_thread_started` callback (added to `run_turn` itself, small and tested) to the same
conversation-binding-conflict logic `_flush_line` applies for `exec`, `resume_thread_id` to
`known_session_id`, and `should_interrupt` to the existing `_stop_requested` set via a new
`_active_app_server_runs` tracking set (app-server has no PTY/pipe handle to register in
`_active_ptys`, so the stop endpoint and shutdown teardown needed a parallel path).

**Task 2.14 (the live breach test) is done and live-verified three times (`698942c`)** against a
real Hub on `127.0.0.1:8010` and a real `codex app-server` (CLI 0.146.0): a non-yolo codex agent,
bound to an app-server-opted-in Runner, given one turn asking it to (1) call the AgentWeave
`list_tasks` MCP tool and (2) `apply_patch` a file at an absolute path outside its workspace.
Both halves held across all three runs — the tool call succeeded, the write was refused
(`{"decision":"decline"}`, agent's own report: "patch rejected by user" / "The patch was
rejected; no file was created"), and no file ever appeared at the target path.

**A real bug was found and fixed along the way.** The first two breach-test runs showed the
refused write's `tool_result` event as `is_error: false` in the Hub's own timeline —
`map_item_to_events`'s `fileChange`/`commandExecution` branches checked `item.get("status") ==
"failed"`, but a declined item reports `status: "declined"` (confirmed via `codex app-server
generate-json-schema`'s `PatchApplyStatus`/`CommandExecutionStatus` enums: both are
`["inProgress","completed","failed","declined"]`). A refused sandbox-escape attempt was rendering
as a *successful* tool call in the operator-facing timeline. Fixed (`_FAILED_ITEM_STATUSES =
("failed","declined")`, checked in both branches); re-ran the same live breach test a third time
against the fix and confirmed `is_error: true`.

**Task 2.15 (Claude parity check) is done — investigation only, not implemented (`98117b9`).**
Live probe against Claude Code CLI 2.1.221, same throwaway-MCP-server method as the original
Codex investigation. **Claude has the same class of defect**: under `--permission-mode manual`
(a non-bypass mode, needed to control for this dev machine's own
`~/.claude/settings.json:permissions.defaultMode = "bypassPermissions"`, which otherwise
confounds every result), an MCP tool call and an out-of-workspace `Write` are both refused with
the identical undifferentiated "permission not granted" message — no distinction by tool/server
identity. **Unlike Codex, the fix is cheap and does not need a transport rewrite**:
`--allowedTools "mcp__agentweave__*"` (verified live) lets the Hub's own tools through while the
write stays refused. A second, distinct, and arguably more urgent finding: the Hub's
`_build_claude_command` currently sets no `--permission-mode` at all for a non-yolo run, so
whether a "non-yolo" Claude agent is actually sandboxed today silently depends on the
**operator's own machine's** Claude Code settings, not the Hub's `yolo` flag. Full write-up in
`design.md` Decision 6 and `implications-codex-appserver.md` §6. **Not implemented** —
`runner_commands.py` is untouched; whether/when to add the flags is an explicit follow-on scope
decision, deliberately left open per task 2.15's own "record what was established" framing.

## Files touched

**Task 2.8 wiring (commit `f7a6359`):**
- `hub/hub/codex_appserver.py` — added `APP_SERVER_OPT_IN_FLAG` constant; added
  `on_thread_started` optional callback param to `run_turn`, fired once right after
  `thread/start`/`thread/resume` responds and before `turn/start`.
- `hub/hub/api/v1/agent_trigger.py` — imports `codex_appserver`'s `APP_SERVER_OPT_IN_FLAG`,
  `AppServerError`, `TurnOutcome`, `run_turn as codex_run_turn`; new module-level
  `_active_app_server_runs: set`; `trigger_agent_directly` strips the sentinel from
  `runner_row.flags` before `build_command` and computes `use_codex_app_server`; `_execute_run`
  gained `use_codex_app_server`/`cli`/`prompt`/`yolo`/`mcp_command` params and dispatches to the
  new `_execute_codex_appserver_run` (~180 new lines) when set; `stop_agent_run` now checks
  `_active_app_server_runs` when no PTY is registered; `terminate_all_active_runs` now also
  signals app-server runs via `_stop_requested` on shutdown.
- `hub/tests/test_agent_trigger.py` — added `AsyncMock` import, `_wait_for_active_app_server_run`,
  `_bind_codex_app_server_runner`, `_fake_run_turn` helpers; 6 new tests: opt-in routing
  (`test_codex_app_server_opt_in_flag_selects_run_turn_not_exec`), output/usage recording
  (`test_codex_app_server_records_output_events_and_usage`), resume
  (`test_codex_app_server_resume_passes_known_session_id_as_resume_thread_id`), binding conflict
  (`test_codex_app_server_binding_conflict_fails_run`), spawn failure
  (`test_codex_app_server_spawn_failure_fails_run_and_returns_queue_entries`), stop
  (`test_codex_app_server_stop_signals_should_interrupt`).
- `hub/tests/test_codex_appserver_run_turn.py` — 1 new test
  (`test_on_thread_started_fires_before_turn_start_and_before_any_event`).
- `openspec/changes/2026-08-06-agent-messaging-delivery/tasks.md` — §2.6/2.7/2.8 marked done with
  implementation notes.

**Task 2.14 fix + live verification (commit `698942c`):**
- `hub/hub/codex_appserver.py` — new `_FAILED_ITEM_STATUSES = ("failed", "declined")` constant;
  `map_item_to_events`'s `commandExecution` branch now checks
  `item.get("status") in _FAILED_ITEM_STATUSES or bool(exit_code)` (was `bool(exit_code)` alone —
  a declined command never runs, so `exitCode` is null and this alone silently reported it as
  success); `fileChange` branch now checks `item.get("status") in _FAILED_ITEM_STATUSES` (was
  `== "failed"` alone).
- `hub/tests/test_codex_appserver.py` — 5 new tests:
  `test_command_execution_declined_is_marked_error_despite_null_exit_code`,
  `test_file_change_started_emits_tool_use`,
  `test_file_change_completed_success_is_not_marked_error`,
  `test_file_change_declined_is_marked_error`, `test_file_change_failed_is_marked_error`.
- `openspec/changes/2026-08-06-agent-messaging-delivery/tasks.md` — §2.14 marked done with the
  full live-verification narrative and the bug-fix note.

**Task 2.15 write-up (commit `98117b9`):**
- `openspec/changes/2026-08-06-agent-messaging-delivery/design.md` — new "Decision 6" section:
  the confound (this machine's `bypassPermissions` setting), the controlled result (`manual` mode
  blocks both identically), the `--allowedTools` finding, and an explicit "what is and is not
  established" list.
- `openspec/changes/2026-08-06-agent-messaging-delivery/implications-codex-appserver.md` — §6
  updated: the binary "same treatment vs. divergence accepted" framing replaced with the actual
  third outcome (same defect class, cheaper fix, no transport rewrite).
- `openspec/changes/2026-08-06-agent-messaging-delivery/tasks.md` — §2.15 marked done.

**Not committed, not product code (gitignored under `testbed/.gitignore:3 = *`):**
- `testbed/scratch/probe_appserver_filechange_status.py` — dead end, see below; kept on disk.
- `testbed/scratch/probe_claude_mcp_approval.py` — the live probe behind Decision 6's findings,
  parameterized via `PROBE_PERMISSION_MODE`/`PROBE_ALLOWED_TOOLS` env vars for re-running with
  different flag combinations. Kept on disk, reusable.
- `testbed/scratch/appserver_filechange_status_capture.jsonl`,
  `claude_mcp_approval_capture.jsonl` — raw JSONL captures from the probes above.
- Every prior session's probe scripts (`probe_appserver_turn.py`, etc.) — untouched.

**Pre-existing dirty files, not touched this session** (carried across every handoff since
handoff-0001): `M .claude/handoffs/handoff-0001-...md`, `M Makefile`.

## Key decisions

1. **The app-server opt-in is a sentinel string in `Runner.flags`, not a new DB column** —
   confirmed with the operator via `AskUserQuestion` before implementing (three options
   presented: sentinel flag / new column / env var; sentinel chosen as recommended). Reason:
   matches the handoff-0008 plan, no schema migration, and `flags` already exists specifically to
   carry CLI-adjacent per-runner options. The env-var alternative was rejected because it applies
   Hub-instance-wide, losing the ability to run `exec` and `app-server` side by side for the
   equivalence comparison task 8.x wants.
2. **`_execute_codex_appserver_run` is a fully separate function, not branches sprinkled through
   `_execute_run`.** The PTY-based read loop is untouched byte-for-byte except for an early
   dispatch-and-return at the top. Lower risk for a path 720 existing tests cover, and keeps the
   two transports independently readable.
3. **`on_thread_started` was added to `run_turn` rather than working around its absence.**
   Without it, session-id binding could only happen after `TurnOutcome` returns — i.e., after
   every `on_event` call for the turn already fired with `session_id=None`. This would have
   diverged from `exec`'s guarantee (session_id resolved before that line's own events). Adding
   one optional callback, defaulting to `None`, didn't change any existing tested behavior.
4. **`_active_app_server_runs` is a parallel set, not a repurposed `_active_ptys`.** `run_turn`
   owns its subprocess internally; the Hub never gets a handle to it. Interrupt is polling-based
   (`should_interrupt`), not a direct kill — `stop_agent_run` and `terminate_all_active_runs` both
   branch on which set has the run_id.
5. **The breach-test project was created via `/api/v1/projects/open` on a pre-existing, empty
   directory — and it silently rebound the Hub's own bootstrap "Agentweave" project** (previously
   `working_directory: null`) rather than creating a new `proj-xxxxx` row. This is
   `ProjectLifecycleService.open_existing`'s "single unbound legacy project" migration path
   (`project_lifecycle.py:80-81`), triggered because I called `/create` first with a directory
   that already existed (git-init'd ahead of time) — `/create` requires the target to *not*
   exist, so it 400'd, and I fell back to `/open`, which took the legacy-binding path instead of
   minting a new project. **Not reverted** — no unbind/delete endpoint exists (this repo's
   longstanding open question #7), and the project had never been used for anything, so nothing
   of value was lost. Flagged as a new open question below rather than fixed silently.
6. **The Claude parity probe used `--permission-mode manual` as a CLI-flag override, not a
   swapped `HOME`/`USERPROFILE`.** Swapping the profile was tried first and rejected: it produces
   a clean permissions posture but also drops this machine's stored Claude Code auth (no
   `ANTHROPIC_API_KEY` env var is set; auth lives under `~/.claude/`), so the probe would fail
   before ever reaching a tool call. A CLI flag overrides `settings.json` and needs no separate
   auth, so it isolates the one variable under test.
7. **Task 2.15 was deliberately not implemented** — `runner_commands.py`'s `_build_claude_command`
   is untouched. It changes the argv of every non-yolo Claude run (larger blast radius than a
   Codex-only change), and task 2.15's own wording ("record what was established") scoped it as
   investigation-only. Recorded as a follow-on decision point, not silently actioned.

## Constraints and user directives (verbatim)

- Three `AskUserQuestion` checkpoints this session, each answered explicitly:
  1. Sentinel-in-`runner.flags` (Recommended) chosen for the app-server opt-in mechanism, over a
     new DB column or a Hub-instance-wide env var.
  2. **"Run the live breach test now (Recommended)"** — chosen over "Stop here for now" and "Skip
     to task 2.15 instead", after task 2.8's wiring was tested and committed.
  3. **"Continue into task 2.15 now"** — chosen over "Stop here for now (Recommended)", after
     task 2.14's live verification (including the `is_error` fix) was tested and committed.
  4. **"Write a handoff and stop (Recommended)"** — chosen over "Keep going into section 4", after
     task 2.15's investigation was written up and committed. This handoff is that choice.
- From `CLAUDE.md`, load-bearing throughout: never create `.agentweave/`, `agentweave.yml`, or
  `spec/` at the repo root — all exploratory execution happened in `testbed/scratch/` and via the
  live Hub's own API, never at the repo root; stage paths explicitly, never `git add -A`
  (confirmed via `git status --short` before every stage this session); Icon is the only icon
  system (not touched this session, no UI work).
- From memory (`feedback_always_commit_checkpoints`): commit each completed checkpoint without
  asking. All three commits happened unprompted, each after its own test run (and, for the second
  and third, after a live-Hub verification too — a stronger bar than the usual unit-test
  checkpoint).
- From memory (`feedback_verify_on_resume`): live-verify prior claimed work on resume. Done at
  session start — re-ran the full `hub/tests/` suite before touching anything (708 passed, 9
  skipped, matching handoff-0008's claim exactly) rather than trusting the handoff file alone.
  **Repeating the directive here for the next session.**
- **"Root-cause by experiment, not by reading code"** (a decision principle carried from
  handoff-0007, honored again this session): every claim in Decision 6 was checked against a real
  `claude` CLI subprocess, not inferred from `--help` text or documentation, including the
  discovery and control of the `bypassPermissions` confound itself.

## Dead ends

- **A standalone probe script (`probe_appserver_filechange_status.py`) instructing Codex to "use
  apply_patch" to write outside its workspace did NOT reproduce the declined-fileChange scenario**
  — the model self-censored based on its own knowledge of `workspace-write`'s writable roots and
  replied "I can't create that file because it is outside the writable workspace roots" without
  ever calling `apply_patch` or triggering an approval request at all. The real breach-test turn
  through the actual Hub (broader, less leading prompt: "attempt to write...report whether it
  succeeded or was refused") DID trigger a real `apply_patch` attempt and a real
  `item/fileChange/requestApproval`. Model willingness to attempt an out-of-bounds action is
  sensitive to prompt framing in a way that matters for reproducing a specific live shape —
  worth remembering if a future probe needs to force a specific approval-request type.
- **Debug logging added temporarily to `map_item_to_events`'s `fileChange` branch
  (`logger.warning(...)`) never appeared in the dev Hub's log file (`/tmp/hub-dev-8010.log`)**,
  despite the code path definitely executing (the mapped `tool_result` event it should have
  logged alongside did appear in the Hub's own output). Root cause not established — likely
  uvicorn's own logging config not propagating a bare `logging.getLogger(__name__)` call the way
  `2>&1` redirection would capture, but not confirmed. Abandoned in favor of reading the installed
  CLI's own JSON schema directly (`codex app-server generate-json-schema`), which gave a
  definitive, faster answer (`PatchApplyStatus`/`CommandExecutionStatus` enums) than continuing to
  debug the logging pipe. The debug line was fully removed before committing — verified via
  `grep -n "DEBUG_FILECHANGE_ITEM"` returning nothing.
- **The first Claude parity probe (no `--permission-mode` flag) showed both the MCP call and the
  out-of-cwd write succeeding silently** — this was not "Claude has no defect," it was this
  development machine's own `~/.claude/settings.json:permissions.defaultMode = "bypassPermissions"`
  overriding everything. Caught before drawing any conclusion from it; see Key Decision 6.
- **Swapping `HOME`/`USERPROFILE` env vars to get a clean Claude Code profile, to test the CLI's
  true out-of-the-box default free of both the `bypassPermissions` override and any explicit
  `--permission-mode` flag, was attempted and abandoned** — it isolates permissions config but
  also drops this machine's stored auth (Claude Code has no `ANTHROPIC_API_KEY` env var in this
  environment; credentials live under the real `~/.claude/`), so the probe would fail at the
  first API call. This is why Decision 6 explicitly states the CLI's *true, zero-config* default
  was not directly measured, only inferred.

## Verification

**Ran, with real output, this session:**
- Full `hub/tests/` suite, four times as work landed: 708 (session-start baseline, matches
  handoff-0008's claim) → 715 (after task 2.8) → 720 (after the task 2.14 `is_error` fix) →
  720 (unchanged after task 2.15's docs-only commit). Zero failures at any point.
- `openspec validate 2026-08-06-agent-messaging-delivery --strict` — valid, re-run after every
  edit to `tasks.md`/`design.md`/`implications-codex-appserver.md`.
- `ruff check` on every modified `hub/`/`tests/` file — clean except two pre-existing SIM105
  findings in `codex_appserver.py` (confirmed pre-existing via `git stash`/re-lint/`git stash
  pop` — same two findings, same code, before this session's changes).
- **Live, task 2.14, three full runs** through a real Hub (`127.0.0.1:8010`, restarted twice this
  session to pick up code changes) and a real `codex app-server` (CLI 0.146.0): non-yolo agent
  `breach-codex` (project `Agentweave`), Runner `runner-b017d99d` (`cli: codex`, `flags:
  ["--app-server"]`). Run 1 (`run-0d64266c`): `list_tasks` succeeded, `apply_patch` outside
  workspace declined, no file created, `is_error: false` (the bug). Run 2 (`run-c4b94103`): same
  shape, confirmed reproducible. Run 3 (`run-81a47cb1`), after the fix: same refusal, same
  no-file-created result, now `is_error: true`. Confirmed via `ls` after each run that no
  `OUTSIDE_BREACH_MARKER*.txt` file ever existed on disk.
- **Live, task 2.15**, four `claude` CLI subprocess runs (CLI 2.1.221) via standalone probe
  scripts, not through the Hub: (1) no `--permission-mode` flag — both MCP call and write
  succeeded (confounded by this machine's settings, see Dead Ends); (2) `--permission-mode
  manual` — both refused identically; (3) `--permission-mode manual --allowedTools
  "mcp__probe__probe_ping"` — MCP call succeeded, write still refused; (4) `--allowedTools
  "mcp__probe__probe_ping"` with no `--permission-mode` flag (the exact shape
  `_build_claude_command` would produce today if the Hub added just this one flag) — both
  succeeded again, because this machine's `bypassPermissions` override still applies once no
  competing `--permission-mode` flag is present. This is why Decision 6's "not established" list
  includes whether `--allowedTools` needs `--permission-mode manual` alongside it on a
  clean-default machine — that specific combination was never tested without the confound.
- `codex app-server generate-json-schema` re-run this session to extract `PatchApplyStatus` and
  `CommandExecutionStatus`'s real enum values directly from the installed CLI's own schema,
  confirming the `is_error` fix's correctness from ground truth rather than inference.

**Explicitly NOT run — do not assume:**
- **Task 2.15's fix (`--allowedTools`/`--permission-mode` in `runner_commands.py`) was not
  implemented or tested against the Hub's actual Claude spawn path.** All four Claude probe runs
  this session were standalone `claude` CLI invocations, never through `trigger_agent_directly` or
  `_execute_run`.
- **The Claude CLI's true zero-configuration default (no `bypassPermissions` override, no
  explicit `--permission-mode` flag) was never directly measured** — see Dead Ends. Decision 6
  states this explicitly as inferred, not verified.
- **Sections 4 (instance-scoped credentials), 5 (failure visibility), 6 (collaboration readiness),
  7 (runner name mojibake), and 8 (end-to-end multi-agent live verification) of
  `2026-08-06-agent-messaging-delivery` remain fully untouched** — unstarted since handoff-0007.
- **The UI change (`2026-08-06-hub-composer-and-chrome-refinement`) remains fully untouched.**
- The frontend suite (`npm test`, `npx tsc --noEmit`) was not run — no UI code changed this
  session.
- **Whether an actual Codex agent, driven end-to-end through the Hub's UI (not just its API) over
  the app-server path, looks/behaves identically to an `exec`-path agent from an operator's
  perspective** was not checked — all live verification this session used the REST API directly
  (`curl`), never the Hub UI itself.

## Git state

Branch `hub-native-experience`, HEAD `98117b9`, **no upstream configured — nothing has ever been
pushed on this branch** (carried forward from every prior handoff).

Three commits this session: `f7a6359`, `698942c`, `98117b9`.

Uncommitted, all pre-existing and none from this session (identical set to every handoff since
handoff-0001):
- `M .claude/handoffs/handoff-0001-...md`, `M Makefile`
- `?? data/`, `?? scripts/`, `?? .claude/skills/{handoff,resume,review-iteration}/`,
  `?? .claude/handoffs/*.md` (older, un-numbered handoffs plus `LATEST.md` and `reviews/`),
  `?? openspec/explorations/...`, `?? src/agentweave/templates/skills/{handoff,resume}.md`,
  `?? tests/test_handoff_resume_templates.py`

## Live environment

- **Hub dev server on `127.0.0.1:8010`** — restarted twice this session (uvicorn, from `hub/`
  directory, background, no `--reload`) to pick up code changes; currently running the full HEAD
  `98117b9` code (last restart was for the task 2.14 `is_error` fix verification, and nothing
  code-level changed after that). Log at `/tmp/hub-dev-8010.log`. API key in `hub/.env`'s
  `AW_BOOTSTRAP_API_KEY`; `Authorization: Bearer <key>` (not `X-API-Key`). Disposable, kill any
  time — but if reused, note it predates nothing from this session, unlike handoff-0008's warning.
- **Port 8000 still occupied by the old Dockerised Hub** ("cosmic" theme) — unchanged across every
  handoff, kept deliberately for HUB_URL-mismatch reproduction scenarios.
- **New this session: the `Agentweave` project (formerly unbound, `working_directory: null`) is
  now bound to `testbed/scratch/appserver-breach-test/workspace`** (a fresh git repo I
  initialized), via the legacy-single-unbound-project migration path — see Key Decision 5. It has
  one agent, `breach-codex`, bound to Runner `runner-b017d99d` (`cli: codex`, `flags:
  ["--app-server"]`, non-yolo). Three completed runs (`run-0d64266c`, `run-c4b94103`,
  `run-81a47cb1`) exist against it.
- **`Two Codex Mini`** (`proj-d9b5ed67`) and **`Live Verify`** (`proj-de54b547`) test projects,
  unchanged from handoff-0008. `codex-mini-1` still has `config.yolo = true` — reset before
  treating as default-config.
- `testbed/scratch/probe_*.py`, `throwaway_mcp_server.py`, and this session's new
  `probe_claude_mcp_approval.py` / `probe_appserver_filechange_status.py` — all gitignored, safe
  to delete or reuse. `probe_claude_mcp_approval.py` takes `PROBE_PERMISSION_MODE` and
  `PROBE_ALLOWED_TOOLS` env vars for re-running with different flag combinations.

## Next steps

1. **If continuing the messaging-delivery change**: section 4 (instance-scoped run credentials) is
   next in file order and is independent of everything done this session — give each Hub instance
   a stable identity (`openspec/changes/2026-08-06-agent-messaging-delivery/design.md` Decision 3
   already specifies the shape), carry it in the minted run token
   (`hub/hub/agent_auth.py::mint_run_token`/`hash_run_token`), and reject a credential whose
   instance identity doesn't match in the equivalent check path. Write unit tests mirroring
   `hub/tests/test_agent_capability_auth.py`'s existing patterns (the file that currently covers
   `mint_run_token`/`hash_run_token`).
2. **If picking up the Claude `--allowedTools` follow-on instead**: read `design.md` Decision 6 in
   full first — it states exactly what's verified vs. inferred. The concrete implementation task
   is adding `--permission-mode manual --allowedTools "mcp__agentweave__*"` (tool names should be
   read from wherever the Hub already knows its own MCP tool names, not hardcoded — check
   `hub/hub/mcp_server.py`'s `@mcp.tool()` decorators for the canonical list) to
   `_build_claude_command` in `hub/hub/runner_commands.py` for the non-yolo case only. This is a
   new, unscoped change — likely wants its own openspec proposal rather than folding into
   `2026-08-06-agent-messaging-delivery`, since it changes every non-yolo Claude run's behavior,
   not just messaging.
3. **Task 2.14's file-not-found probe capture files
   (`testbed/scratch/appserver_filechange_status_capture.jsonl`,
   `claude_mcp_approval_capture.jsonl`) are scratch and can be deleted** whenever convenient — kept
   only because handoff-0008 established the pattern of leaving probe evidence on disk in case a
   future session needs to re-check a claim.
4. Sections 5-8 of the messaging-delivery change and the independent UI change
   (`2026-08-06-hub-composer-and-chrome-refinement`) remain exactly as described in handoff-0008 —
   no new information this session.

## Open questions for the user

Carried forward, untouched, across nine handoffs now:
1. What should happen to untracked `data/agentweave.db` — gitignore, or commit?
2. `M .claude/handoffs/handoff-0001-...md` and `M Makefile` — intentional WIP, or commit/revert?
3. The `review-0002` agent-name uniqueness gap — still open, still not investigated.
4. `64dbb4b "Add harness-audit and harness-refresh skills"` was not written by the session that
   saw it appear. Expected, or worth investigating?
5. Should `Live Verify` (`proj-de54b547`) and its two claude agents be kept, or removed once
   deletion exists?
6. Should `hub-native-experience` be pushed? Still has no upstream, still never pushed.
7. Should the Hub gain project/agent deletion? Still not specced anywhere; test projects keep
   accumulating.
8. `item/permissions/requestApproval`'s yolo-grant shape (handoff-0008's Key Decision 6) — still
   never actually observed live.

New this session:
9. **The Hub's bootstrap `Agentweave` project got silently rebound** from unbound to
   `testbed/scratch/appserver-breach-test/workspace` (Key Decision 5) as a side effect of the
   breach-test setup, because no "create a genuinely new, non-legacy project" path exists when the
   target directory must be pre-created (e.g., pre-git-init'd) rather than Hub-managed from
   scratch. Worth it? Leave as-is, or is a `/create`-only-workflow (never pre-create the directory)
   worth documenting so this doesn't happen again by accident?
10. Should the Claude `--allowedTools` fix (Next step 2) become its own openspec change now, or
    wait until there's a concrete need driving it?

## Read on resume

- `openspec/changes/2026-08-06-agent-messaging-delivery/tasks.md` — the implementation ledger;
  §1, §2 (all of it), §3 done; §4-8 fully open, read whichever section is picked up next.
- `openspec/changes/2026-08-06-agent-messaging-delivery/design.md` — Decision 6 in full before
  touching anything Claude-permission-related; Decisions 1-3 for context on sections 4/5 if
  picking those up instead.
- `hub/hub/api/v1/agent_trigger.py` — `_execute_codex_appserver_run` (new this session, ~180
  lines) if extending the app-server path further; `agent_auth`-adjacent code near
  `trigger_agent_directly`'s token minting if starting section 4.
- `hub/hub/runner_commands.py` — `_build_claude_command`, the exact function Next-step-2 would
  modify.
- `hub/tests/test_agent_trigger.py` — this session's 6 new app-server integration tests
  (search `app_server`) as the pattern to extend if section 4/8's tests follow the same style.
