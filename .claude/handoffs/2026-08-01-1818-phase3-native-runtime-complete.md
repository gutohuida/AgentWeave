# Handoff: Phase 3 native runtime complete

**Date:** 2026-08-01T18:18:35+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `b86b3a3`
**Agent:** T3 Code / Codex (gpt-5.6-sol)
**Previous handoff:** `.claude/handoffs/2026-08-01-1746-phase3-task-3-17-readme-complete.md`
**Status:** chunk complete

## Goal

Complete Phase 3 of `openspec/changes/2026-07-30-hub-native-experience/`: make the native Hub own
Claude/Codex execution, output streaming, process lifecycle, crash recovery, packaging, and the
one-command local start. The user explicitly asked to finish Phase 3 and keep checkpointing with
`/handoff`.

## Current state

Phase 3 is fully complete: tasks 3.1–3.19 are checked. Task 3.18 was the final substantive item and
is committed at `b86b3a3`. It passed all live acceptance cases on an isolated Windows Hub and found
two real ConPTY defects that were fixed before acceptance: 80-column wrapping corrupted JSONL, and
pywinpty's reader could hang forever after fast process exit. Task 3.19 is this checkpoint.

The next phase is Phase 4, “Identity, runner capability, and surface split.” Its first task is 4.1:
inject a per-run agent identity at spawn and bind identity to the tool-protocol connection. No
Phase 4 investigation or implementation has started.

## Files touched

- `hub/hub/api/v1/agent_trigger.py` — finished and committed in `b86b3a3`; direct agent spawns now
  request `STRUCTURED_OUTPUT_DIMENSIONS` so JSONL is not visually wrapped by ConPTY.
- `hub/hub/pty_runner.py` — finished and committed in `b86b3a3`; added the structured-output PTY
  dimensions and a Windows reader-socket timeout that preserves buffered output while preventing
  pywinpty's post-exit hang.
- `hub/tests/test_agent_trigger.py` — finished and committed in `b86b3a3`; asserts direct triggers
  use the structured-output PTY size.
- `hub/tests/test_pty_runner.py` — finished and committed in `b86b3a3`; adds Windows regressions for
  delayed output and an intact 2,000-character JSON record.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — task 3.18 evidence committed in
  `b86b3a3`; task 3.19 checked by this checkpoint commit.
- `.claude/handoffs/2026-08-01-1818-phase3-native-runtime-complete.md` — this checkpoint; new.
- `.claude/handoffs/LATEST.md` — updated to point to this checkpoint.

Six unrelated pre-existing untracked `.claude/handoffs/*.md` files remain untouched and are listed
under Git state.

## Key decisions

1. Direct structured-output PTYs use `(24, 32767)`, not the default `(24, 80)`. Windows ConPTY
   materializes visual wraps as newline bytes; Claude's multi-kilobyte JSON records were therefore
   split into invalid fragments at width 80. A very wide PTY keeps the JSONL protocol intact.
2. Retained pywinpty's blocking native reader and set a 100 ms timeout on its local socket.
   pywinpty's blocking native reader captures fast-process output reliably but sometimes never
   closes its socket after the child exits; the timeout lets AgentWeave poll `isalive()` and return
   EOF. Rejected `PYWINPTY_BLOCK=0`: live testing showed it can close before flushing final CLI
   output, producing completed runs with empty output tables.
3. Accepted Claude's live rate-limit response as valid launch/stream evidence, not successful model
   completion. The actual installed Claude CLI launched through the Hub, established a typed session,
   streamed two output events, and ended `failed` with exit 1 and the stated account-limit message.
   Codex supplied the successful completion case with the exact `PHASE3_CODEX_OK` marker.
4. Used an isolated Hub (port 18188), throwaway SQLite DB/project/key, and no harness watchdog.
   Unrelated user watchdog processes already running elsewhere were not stopped; they had no access
   to or role in the isolated direct-trigger path.
5. Used controlled console shutdown rather than force-killing an arbitrary process. This exercises
   FastAPI lifespan teardown, `terminate_all_active_runs()`, and then startup reconciliation against
   the same database without disturbing the user's Hub on port 8000.

## Constraints and user directives (verbatim)

- User this chunk: **“Finish Phase 3. I'm going to eat. Keep using handoff to create checkpoints.”**
- Carried from the standing session chain: **“Yeah and always commit the changes.”**
- Carried from the standing session chain: **“After every threshold of implementation you must
  run the skill `/handoff`”**
- Carried from the standing session chain: **“Before starting a new implementation revise the
  entire session for the spec”**
- Carried from the standing session chain: **“let's make sure it works with claude and codex first
  locally”**
- Repository rule: never commit runtime `.agentweave/` state; stage explicitly rather than using
  `git add -A`.

## Dead ends

- First live harness waited 180 seconds for `PHASE3_CLAUDE_OK`. Claude was actually out of credits
  until 19:10 and had emitted a rate-limit result immediately; width-80 ConPTY had split that JSON
  into dozens of fragments, making it appear stuck while the Hub persisted each fragment.
- Simply widening the PTY fixed JSON wrapping but exposed a separate hang: pywinpty's blocking
  native reader could remain blocked after the child exited, leaving the Run `running` forever.
- Setting `PYWINPTY_BLOCK=0` avoided the hang but was rejected: its private `0011Ignore` sentinel
  could be coalesced with data, and more importantly fast CLI output was dropped before socket
  closure. Completed Codex runs then had empty output tables.
- A post-exit nonblocking drain window did not fix that fundamental output-loss race. The final
  socket-timeout design keeps the reliable blocking native reader instead.
- Early diagnostic scripts used fresh databases and short outer timeouts; Alembic startup plus real
  CLI execution exhausted those bounds, and one exception path initially left the isolated Hub on
  port 18183 alive. That exact listener was identified, stopped, and its child confirmed dead. Later
  harnesses used guaranteed `finally` cleanup. Final checks found no listeners on ports 18183–18188
  and no phase3 diagnostic children.

## Verification

Ran and passed:

- `py -m pytest tests/test_agent_trigger.py tests/test_run_reconciliation.py tests/test_pty_runner.py
  -q` before live work: 38 passed (pre-new-tests baseline).
- Final focused suite: `py -m pytest tests/test_pty_runner.py tests/test_agent_trigger.py -q` —
  36 passed.
- Real direct `PtySession` Claude check after the final socket-timeout fix: exit 1 (expected external
  rate limit), 4,640 bytes captured in four intact lines, `rate_limit_event` present, maximum parsed
  line length 2,529.
- Final isolated end-to-end Hub harness on port 18188:
  - Claude run `run-c439913d`: direct spawn, session
    `ca6b3401-75d2-46e7-b00b-cc56faaf2efc`, exit 1/account limit, SSE sequence included
    `run_started`, two `agent_output`, `run_failed`, and terminal status output.
  - Codex run `run-a21a310a`: direct spawn, session
    `019fbe52-d587-7683-947f-bef9b8471ce5`, output `PHASE3_CODEX_OK`, exit 0, SSE included
    `run_started`, `agent_output`, `run_completed`, and terminal status output.
  - Missing pinned Codex executable: HTTP 409 with exact missing path and “not an executable file.”
  - Active Codex run `run-9e5f3857`, PID 24908: controlled Hub shutdown returned exit code 3;
    OS check found the child absent; restart reconciled the row to `interrupted` with `ended_at`.
- Complete Hub suite: `py -m pytest tests/ -q` — 331 passed, 4 skipped, 4 Alembic deprecation
  warnings.
- `py -m ruff check hub/ tests/` — clean.
- `py -m black --check hub/ tests/` — clean; Black emitted its existing Python 3.11/cfg target
  warning but would leave all 91 files unchanged.
- `git diff --check` and `git diff --cached --check` — clean before the task 3.18 commit.
- Task implementation commit: `b86b3a3 Complete Phase 3 task 3.18: verify and harden direct
  execution` (5 files, 104 insertions, 9 deletions).

Ran but not passing as a repository gate:

- `py -m mypy hub/` reports 107 pre-existing errors across 19 files, including missing third-party
  stubs, many pre-existing untyped route functions, and parent `pyproject.toml` targeting Python 3.8
  (unsupported by the installed mypy). No new error points to the socket-timeout code; mypy was not
  clean before this task and was not broadened into an unrelated 19-file remediation.

Not tested:

- Claude successful model completion was unavailable because the account was rate-limited. Direct
  launch, typed session parsing, output streaming, explicit failure, and lifecycle completion were
  verified; Codex covered successful model completion.
- The new wide structured-output PTY was live-tested on Windows/ConPTY. POSIX accepts the same
  winsize shape and existing PTY tests pass, but no separate Linux live-agent run was performed.
- Docker deployment was not involved; task 3.18 specifically verifies native execution ownership.

## Git state

- Branch: `hub-native-experience`.
- Substantive Phase 3 HEAD before this checkpoint commit: `b86b3a3`.
- No upstream configured; nothing pushed.
- Tracked implementation tree was clean after `b86b3a3`; this handoff, its `LATEST.md` pointer, and
  the task 3.19 checkbox are the only intended checkpoint changes.
- Pre-existing untracked files, intentionally untouched:
  - `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md`
  - `.claude/handoffs/2026-07-29-2110-spec-navigation-t1-t9-implemented.md`
  - `.claude/handoffs/2026-07-30-0004-agentweave-strategy-discussion-resolved.md`
  - `.claude/handoffs/2026-07-30-1912-spec-navigation-closed-r1-audit-next.md`
  - `.claude/handoffs/2026-07-31-2049-hub-native-phase1-feel-foundation.md`
  - `.claude/handoffs/2026-07-31-2112-hub-native-phase1-complete.md`

## Next steps

1. Before implementation, read Phase 4 and the relevant identity/tool-surface specs under
   `openspec/changes/2026-07-30-hub-native-experience/specs/`, then trace current identity flow in
   `hub/hub/api/v1/agent_trigger.py`, `hub/hub/mcp_server.py`, `src/agentweave/mcp/server.py`, and
   CLI `--from-agent` handling. Produce a concrete map of caller-controlled versus Hub-bound
   identity for task 4.1.
2. Implement task 4.1 for Claude and Codex first: generate/inject per-run identity at spawn and bind
   it on the tool-protocol connection. Add tests proving an agent process cannot claim a different
   identity.
3. Run focused/full tests and static checks, update the task ledger, commit explicitly by path, and
   use `/handoff` at the next implementation threshold per the user's standing directive.

## Open questions for the user

None blocking. The branch has no upstream; pushing remains unrequested.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — Phase 4 task order and completed
  Phase 3 evidence.
- `openspec/changes/2026-07-30-hub-native-experience/specs/agent-tool-surface/spec.md` — identity and
  tool-path requirements for Phase 4.
- `hub/hub/api/v1/agent_trigger.py` — spawn boundary where per-run identity must be injected.
- `hub/hub/mcp_server.py` — Hub tool-protocol identity/effect attribution.
- `src/agentweave/mcp/server.py` — CLI/local MCP caller-supplied identity path.
- `hub/hub/pty_runner.py` — completed Phase 3 ConPTY fixes; do not revert wide dimensions or socket
  timeout without re-reading this handoff's decisions and dead ends.
