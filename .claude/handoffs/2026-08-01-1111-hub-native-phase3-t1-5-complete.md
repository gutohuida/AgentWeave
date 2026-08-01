# Handoff: Phase 3 tasks 3.1–3.5 complete; 3.6 (SSE run-lifecycle events) next

**Date:** 2026-08-01T11:11:32+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `eb4925e`
**Agent:** Claude Code / Sonnet 5 (1M context)
**Previous handoff:** `.claude/handoffs/2026-08-01-1024-hub-native-phase3-t1-4-complete.md`
**Status:** chunk complete — session end. User explicitly chose "Stop here for this session"
when asked how to proceed after 3.5 landed, rather than continuing into 3.6.

## Goal

Rebuild the AgentWeave Hub into a local-first application that owns agent execution directly,
using T3 Code as a studied reference rather than forking it. Phases 1 (material feel) and 2
(SSE-driven live updates) are done. This session continued Phase 3 ("Native runtime,
packaging, and crash recovery") from where the previous handoff left off (3.1–3.4 done) through
3.5, the single largest and riskiest task in the phase. Full reasoning lives in
`openspec/changes/2026-07-30-hub-native-experience/` (`proposal.md`, `design.md`, `tasks.md`).

## Current state

**One commit landed this session** (continuing the same session as the previous handoff, which
covered 3.1–3.4): `eb4925e` — task 3.5, "Full Claude+Codex direct-spawn integration in the
Hub." This was scoped, mid-task, by explicit user direction (see Constraints below) to **full
flag/output/session-resume parity for Claude Code and Codex specifically** — not the originally
more modest "minimal prototype" scope first proposed — after the user said "I want a full
integration of claude and codex... all the possible flags etc... no problems being a full
re-implement of the watchdog." Kimi/OpenCode/Copilot were explicitly deferred ("ignore the
others for now") and get a stated `501 Not Implemented` rather than silent mishandling; they
remain fully functional via the watchdog's existing (unmodified) message-tag trigger path.

**`POST /api/v1/agent/trigger` is now a real spawn**, not a message-queue simulation:
- Pre-flight via `probe_agent()` (3.2) — 409 with a stated reason for pilot/manual/missing-
  CLI/unauthorized agents; manual gets its own precise 409 (not the generic 501) since it's a
  permanent structural state, not an unimplemented runner.
- 501 for any runner other than claude/claude_proxy/native/codex, checked *before* the
  launchability probe so the response is deterministic regardless of what happens to be
  installed on the Hub host.
- A DB-based concurrency guard: a second trigger for an agent with an existing `status="running"`
  `Run` row is rejected with 409 (accepted as a small known race window rather than building
  proper locking — this is human-driven UI triggering, not a hot path).
- Spawns via `hub/hub/pty_runner.py`'s `PtySession` in a tracked `asyncio.create_task` background
  job, builds the command via the new `runner_commands.py`, parses output via the new
  `runner_parsing.py`, and records everything (AgentOutput rows, SSE broadcasts, context-usage
  snapshots) via the new `output_recording.py` — the exact same path a self-reporting agent
  (the watchdog, over HTTP transport) already uses, not a parallel one.
- Returns `{run_id, agent, status: "running", session_id}` immediately; the run's actual outcome
  is observable via the `Run` record and `AgentOutput`/SSE, not the HTTP response.

**Two real bugs were found and fixed, both only by live end-to-end testing against the actual
running Hub — not by the mocked unit test suite**, which is exactly the pattern the Phase-2
handoff already flagged as a recurring lesson in this codebase:
1. `launchability.py`'s config-merging never read `Agent.pilot` (a DB column
   `register-session`/`POST /agents/{name}/pilot` write to directly, never into `Agent.config`
   or session.json) — meaning a self-registered pilot agent was never actually recognized as a
   pilot by either 3.2's launchability endpoint or this session's new trigger endpoint. Fixed by
   extracting a shared `get_agent_config()` into `launchability.py`, used by both.
2. `pty_runner.py` had no ANSI-escape stripping. ConPTY prefixes real output with terminal-
   handshake control sequences (OSC title-set `\x1b]0;claude\x1b\\`, CSI mode toggles like
   `\x1b[?9001h`) and injects more later (e.g. a cursor-restore `\x1b[?25h` after the child
   exits) — live-verified via `curl` against the real running Hub. An unstripped leading
   sequence broke JSON parsing of the entire first line (silently degrading to a raw-text
   fallback event and losing session_id extraction from that line); an unstripped trailing
   sequence produced a spurious garbage output row after completion. Fixed with
   `pty_runner.strip_ansi_escapes()`, applied to every line, not just a leading run on the first.

**Test counts, current HEAD (`eb4925e`):** CLI `tests/` — 996 passed. Hub `hub/tests/` — 313
passed, 4 skipped (pre-existing, unrelated). Both green.

**Two Hub instances discussed across this session's work** (see previous handoff for full
detail) — as of this handoff:
- The dev instance the Vite frontend (port 5174) is pointed at
  (`hub/data/agentweave-dev.db`, started manually via
  `cd hub && DATABASE_URL="sqlite+aiosqlite:///./data/agentweave-dev.db" py -m uvicorn
  hub.main:app --host 127.0.0.1 --port 8000`, backgrounded) — **confirmed running and healthy**
  (`curl http://127.0.0.1:8000/health` → 200) as of the end of this session, restarted three
  times during this session's live verification, currently running the `eb4925e` code. It now
  has both `claude` and `codex` agents registered via session sync (added during this session's
  live verification; previously only had `claude`).
- Port 5173 is also listening (a separate, older dev server) — per the previous handoff, this
  is stale/unrelated; ignore it.
- **Do not assume the Hub is still running when resuming** — background bash processes in this
  environment do not reliably survive a session boundary. Re-check
  (`curl http://127.0.0.1:8000/health`) before using; if down, the reliable restart command is
  the `DATABASE_URL=... py -m uvicorn ...` one above (the CLI's own `agentweave hub start`
  detached mode has an intermittent, pre-existing, unfixed health-check timeout — see Dead ends
  in the previous handoff).

## Files touched

**Commit `eb4925e` (task 3.5), all finished:**
- `hub/hub/runner_commands.py` (new) — `build_command()`, full flag construction for
  claude/claude_proxy/native + codex, mirroring `agentweave.watchdog._agent_ping_cmd`'s
  branches for those runners. `UnsupportedRunnerError` for anything else.
- `hub/hub/runner_parsing.py` (new) — `parse_claude_line()`, `parse_codex_line()`, full JSONL
  event + usage-sample parsing mirroring `_parse_claude_stream_line`/`_parse_codex_stream_line`.
- `hub/hub/runner_events.py` (new) — `RunEvent`/`ContextUsageSample` construction + secret
  redaction, mirroring `stream_events.py`'s constructors.
- `hub/hub/output_recording.py` (new) — `record_agent_output()`, `record_context_usage()`,
  factored out of `agents.py`'s existing `POST .../output` / `POST .../context-usage` handlers.
- `hub/hub/api/v1/agent_trigger.py` — full rewrite of `trigger_agent()` (see Current state);
  `get_agent_sessions()` at the bottom of the file is untouched.
- `hub/hub/api/v1/agents.py` — `post_agent_output`/`post_context_usage` now call the shared
  `output_recording.py` helpers (behavior preserved, verified by existing tests staying green);
  `get_agents_launchability` (3.2) now calls the shared `launchability.get_agent_config()`.
- `hub/hub/launchability.py` — new `get_agent_config()` (merges session.json + `Agent.config` +
  `Agent.pilot`, the last of which neither this nor 3.2's endpoint read before — see bug #1
  above).
- `hub/hub/pty_runner.py` — new `strip_ansi_escapes()` + `_ANSI_ESCAPE_RE` (see bug #2 above).
- `hub/tests/test_runner_parsing.py` (new, 34 tests) — `build_command`/`parse_*_line` unit
  tests; JSONL fixtures are trimmed real output captured from this session's live headless
  spawns, not hand-guessed shapes.
- `hub/tests/test_agent_trigger.py` (new, 6 tests) — endpoint integration tests with
  `PtySession.spawn` mocked (manual-runner rejection, resume validation, successful trigger +
  background execution, concurrent-trigger rejection using a real `threading.Event` to
  deterministically block the mock — a naive immediate-return mock let the background task race
  ahead and finish before the second request, which was caught and fixed mid-task), spawn-
  failure handling.
- `hub/tests/test_pty_runner.py` — new `TestStripAnsiEscapes` class (5 tests), retroactive
  coverage for bug #2.
- `hub/tests/test_pilot_mode.py` — two tests asserting the old `execution_confidence`/message-
  queueing pilot behavior rewritten to assert the new 409/501 direct-outcome behavior.
- `hub/tests/test_runtime_diagnostics.py` — two tests asserting old
  `execution_confidence`/`watchdog_status` fields folded into one new test asserting the direct
  409-with-reason behavior; the file's other two (unrelated) tests untouched.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 3.5 checked off with a very
  long, detailed findings entry (worth reading directly, not just via this summary).

**Not touched this session, pre-existing untracked, not to be modified:** the six
`.claude/handoffs/*.md` files from earlier sessions, listed in every `git status` this session.

## Key decisions

1. **3.5's scope was renegotiated mid-task, explicitly, by the user** — see Constraints below
   for the exact quotes. This is the single most important thing for a resuming session to
   internalize: what got built is *bigger* than task 3.5's own one-line description in
   `tasks.md` implies, and *narrower* than "the whole watchdog" in a different dimension (only
   two runners). Don't re-derive scope from `tasks.md`'s text alone — read this handoff's
   Current State section or the tasks.md entry's own detailed writeup first.
2. **T3-parity, not CLI-parity, was the bar for context-usage tracking.** Asked whether to port
   the CLI's rollout-file-cross-referencing collectors, the user said to check what T3 itself
   does. T3's own context meter is stdout-native only (per `design.md`'s existing Context-window
   meter research). That resolved the question: stdout-native usage extraction (already inline
   in the ported `_claude_usage_sample`/`_codex_usage_sample` logic) was in scope; the CLI's
   *additional* rollout-file collectors (a AgentWeave-specific enhancement beyond T3) were not,
   and were not built. If a future task wants those, it's new scope, not something silently
   dropped from 3.5.
3. **Claude's context-window limit is read from the CLI's own self-report
   (`result.modelUsage.<model>.contextWindow`), not ported from the CLI's `CLAUDE_CONTEXT_LIMITS`
   table.** That table is demonstrably stale (no entry for Sonnet 5, silently defaults to a wrong
   200K — live-verified Sonnet 5 actually reports 1,000,000 via its own `result` event). This is
   a deliberate improvement discovered mid-task via live testing, not a faithfulness gap.
   *Rejected:* porting the stale table as-is for "fidelity" — fidelity to a known bug is not a
   virtue.
4. **The permission-bypass gap for yolo-enabled claude agents was fixed, not reproduced.** The
   watchdog's `_agent_ping_cmd` never passes `--dangerously-skip-permissions` for claude even
   when yolo is on (confirmed by reading the whole function), despite a CLI hint string
   (`cli.py:4407`) claiming it "will be used." Harmless for the watchdog (a human is usually
   nearby to click through a permission prompt); fatal for a headless Hub spawn (it would hang
   forever with nobody to answer). Fixed here since this is new code with zero regression risk
   to existing watchdog users — noted explicitly in `runner_commands.py`'s docstring and in
   `tasks.md` so it doesn't read as an unexplained deviation.
5. **Concurrency guard is a DB query (`Run.status == "running"`), not a file lock** like the
   watchdog's `acquire_lock`. Accepted as a known small race window (two near-simultaneous
   triggers could both pass the check before either commits) rather than building equivalent
   locking — judged low-risk for current usage (human-driven UI triggering) and explicitly not
   what 3.5 was asked to solve. Revisit if it ever actually bites.
6. **Manual-runner agents get their own precise 409 (`probe_agent`'s stated reason), checked
   *before* the general "unsupported runner" 501.** Semantically, "manual" is a permanent,
   deliberate no-CLI declaration, not an unimplemented runner — giving it the 501 message would
   misleadingly suggest support is just missing today. *Rejected:* letting it fall through to the
   generic 501 (simpler code, wrong message).
7. **Output recording was factored into a shared module (`output_recording.py`) used by both the
   existing self-report HTTP endpoints and the new direct-spawn path**, rather than writing
   `AgentOutput` rows directly in `agent_trigger.py`. This was not asked for explicitly but is a
   safe, mechanical, behavior-preserving refactor (verified by the existing endpoint tests
   staying green) that prevents the two paths from drifting apart over time.

## Constraints and user directives (verbatim)

- `"No, merge nothing. Just continue."` — still true, nothing merged/pushed. Not re-asked this
  session (already resolved in the previous handoff: **"Keep building, merge later."**).
- **The exact scope-setting exchange for 3.5** (read this before touching `runner_commands.py`
  or `runner_parsing.py` again): asked whether to build a "minimal prototype" (new-session only,
  common runners) or "full parity" with the watchdog, the user said: *"I want a full integration
  of claude and codex. Just like we have in t3 code. All the possible flags etc. Every config
  that we can make. You can read documentation and spawn headless operations to test. Ignore the
  others for now. We'll implement them later. No problems being a full re-implement of the
  watchdog."* Then, asked specifically whether that included porting the context-usage/token-
  tracking subsystem: *"What does T3 do? I have it locally, if it gets the full tracking then we
  get that as well. I know that they also have the ability to question the user etc."* — the
  "ability to question the user" comment refers to T3's approval-gate pattern, which maps to
  AgentWeave's *already-existing* `ask_user`/`get_answer` MCP tools and Questions panel
  (unrelated to and unaffected by this task) — flagged in case the user meant something more by
  it that wasn't addressed.
- **When asked how to proceed after 3.4 (before starting 3.5): "Write a handoff first, then
  continue."** Honored — that handoff is `.claude/handoffs/2026-08-01-1024-hub-native-phase3-t1-4-complete.md`.
- **When asked how to proceed after 3.5 (this handoff's trigger): "Stop here for this session."**
  Distinct from the previous checkpoint — this time the user chose to end the session rather
  than continue, which is why this is a stopping-point handoff, not a mid-session checkpoint.
- Carried forward, still in force: "After every threshold of implementation you must run the
  skill /handoff." "Before starting a new implementation revise the entire session for the
  spec." "I'm open to trying things other than the CLI... don't hesitate [to remake something]."
  "let's make sure it works with claude and codex first locally" — Copilot second (this session's
  3.5 work is a direct instance of this priority). Employer blocks third-party MCP **in GitHub
  Copilot only**. Project `CLAUDE.md` rules still apply (never commit `.agentweave/tasks/`,
  `messages/`, `agents/`, `session.json`, `transport.json`; stage explicitly, never `git add -A`
  — every commit this session staged files by exact path).

## Dead ends

- **A naive `MagicMock` returning `""` immediately from `.read()` to simulate "a run still in
  progress"** doesn't work for testing the concurrency guard — since the test client and the
  background `asyncio.create_task` share one event loop with no real process involved, the
  background task can race ahead and fully complete (including the final `Run.status =
  "completed"` update) before the test's second HTTP request even executes, making the "still
  running" assertion flaky/false. Fixed with a real `threading.Event().wait()` inside the mock's
  `read()`, run via the real thread pool executor `PtySession`'s callers already use — this
  genuinely blocks until the test explicitly releases it, after making its assertion.
- **Assuming the watchdog's claude command construction included a permission-bypass flag for
  yolo mode, because a CLI hint string says so** (`cli.py:4407`: `"--dangerously-skip-permissions"
  if agent == "claude"`, printed with "(will be used)"). Grepping for actual usage of
  `get_agent_yolo`/`agent_cfg.get("yolo")` across the whole of `watchdog.py` showed it's applied
  for kimi, codex, copilot, and codex_mcp — never for claude/claude_proxy/native. The hint string
  is aspirational, not connected to real behavior. Caught by reading the actual command-
  construction function in full rather than trusting the hint text; see Key Decision #4.
- **Manually reproducing `agentweave hub start`'s exact subprocess command from the repo root
  (`py -m uvicorn hub.main:app` with CWD = repo root, not `hub/`)** raised `ImportError: cannot
  import name '__version__' from 'hub' (unknown location)` — an ambient-namespace-package
  shadowing issue from the outer `AgentWeave/hub/` directory (no `__init__.py`) merging with the
  properly-installed package under Python's implicit `-m`-adds-cwd-to-sys.path behavior. Noted in
  the previous handoff as not fully explained and not the actual cause of a separate, real,
  still-not-understood detached-mode health-check flake — still true, not investigated further
  this session, not blocking anything.

## Verification

**Ran and passed:**
- `py -m pytest tests/ -q` (CLI) → 996 passed, 4 skipped.
- `py -m pytest hub/tests/ -q` (Hub) → 313 passed, 4 skipped.
- `py -m ruff check hub/` and `py -m black --check hub/` (with `black` reformats applied and
  re-verified whenever they fired) — clean.
- **Live, hands-on, against real installed CLIs** (Claude Code 2.1.220, codex-cli 0.146.0) —
  not simulated: new-session and `--resume`/`resume <id>` invocations for both runners, run
  directly via bash *and* via a real `PtySession.spawn()` call; confirmed actual conversational
  continuity across resume (asked each CLI to recall a fact stated in a prior turn — both
  correctly did); confirmed `--dangerously-skip-permissions` alone suffices for claude (no
  companion flag needed); confirmed codex's PTY-attached stdin does not trigger its
  pipe-triggered "reading from stdin" prompt-append behavior.
- **Live, end-to-end, through the actual running Hub** (not just direct PtySession calls): used
  `curl` against `POST /api/v1/agent/trigger` on the real dev Hub instance for both a claude and
  a codex agent, watched output arrive via `GET /agents/{name}/output`, confirmed `Run` rows
  reached `status="completed"`, `exit_code=0`, and the correct `session_id` (verified directly
  via `sqlite3` queries against the real `agentweave-dev.db`), confirmed a real `context_warning`
  event was recorded for the codex run with real token counts. **This is what caught the
  `strip_ansi_escapes` bug** — the first live-endpoint run showed raw JSON leaking through as a
  garbage output row; the mocked test suite's synthetic fixtures don't carry real ConPTY escape
  sequences, so this could not have been caught any other way. Re-ran after the fix and confirmed
  clean output for both runners.

**NOT tested this session:**
- No `mypy src/` run (only `hub/` was touched, out of mypy's configured scope).
- No test of the concurrency guard's actual race window under real (not test-simulated)
  concurrent load.
- No test of what happens if the Hub process itself is killed mid-run (crash reconciliation is
  explicitly task 3.8, not yet built — a `Run` row would currently be left `status="running"`
  forever with a stale `pid` after a Hub crash, with nothing to notice or fix it).
- The frontend was not touched, checked, or reloaded — 3.6 is where any UI rendering of runs
  happens; today a triggered run is only observable via `GET /agents/{name}/output` (which
  already renders in the existing agent output view, so it should "just work" for text/status
  content, but this was not explicitly re-verified in the browser this session) and raw SSE
  `agent_output`/`context_warning` events (no dedicated run-lifecycle UI yet).
- Kimi/OpenCode/Copilot triggering was not tested at all this session (out of scope) — they
  still go through the watchdog's unmodified path, which was not touched or re-verified either.

## Git state

- Branch `hub-native-experience`, **HEAD `eb4925e`**, working tree clean except the six
  pre-existing untracked `.claude/handoffs/*.md` files (unrelated, from earlier sessions) plus
  this new handoff file being written.
- One commit made this session (continuing from the previous handoff's checkpoint commit
  `1901b40`), on top of `13fe2f8` (3.4, the previous session's last work).
- No upstream configured (`no upstream`) — nothing pushed, not requested.

## Next steps

1. **Re-read `design.md` and `tasks.md`'s task 3.6 entry in full** before starting (per the
   working protocol) — `tasks.md`: *"Emit run lifecycle and output events on the SSE channel;
   render them in the agent view."* Two halves: backend event types, and frontend rendering.
   Given 3.5 already reuses the *existing* `agent_output`/`context_warning` SSE events for
   output (not new), 3.6's backend half is specifically about adding **new, typed lifecycle
   events** — something like `run_started`/`run_completed`/`run_failed` — distinct from the
   plain-text "Run completed/failed" status line `agent_trigger.py`'s `_execute_run()` currently
   appends to the output stream as a stopgap (see `agent_trigger.py`'s final `sse_manager.broadcast`
   call, kind="status"). Decide whether that stopgap gets replaced by a proper typed event or
   kept alongside one — not decided yet.
2. **Frontend half of 3.6** needs `hub/ui/src/hooks/useSSE.ts`'s `SSE_EVENT_TYPES` allowlist
   extended for whatever new event type(s) get added (the Phase-2 lesson: an event broadcast by
   the backend but missing from this allowlist is silently dropped client-side — this exact bug
   class was found and fixed twice in Phase 2, don't reintroduce it a third time), plus actual
   rendering work in the agent view (`hub/ui/src/components/agents/AgentOutputPanel.tsx` and/or
   `AgentActivityTab.tsx` are the likely targets — not yet investigated this session).
3. Before starting 3.6, **verify in a real browser** that a Hub-triggered run's *existing*
   `agent_output` events (already flowing correctly per this session's live verification) are
   actually rendering in the current UI as expected — this session verified the backend/API side
   exhaustively but never opened the frontend to look. If output isn't rendering correctly today
   even before 3.6's new lifecycle events are added, that's worth knowing before building more on
   top of it.
4. Optional, not blocking, carried from the 3.3 handoff entry: the intermittent detached-mode
   `agentweave hub start` health-check timeout and the CWD-relative alembic.ini warning — both
   pre-existing, both out of scope for whatever's next, still unfixed.

## Open questions for the user

- None newly raised this session. Carried forward, unresolved, not urgent: should anything be
  pushed to a remote at this point? No remote/upstream is configured for this branch.
- Worth surfacing next session, not urgent: the "ability to question the user" comment from the
  T3-parity exchange (see Constraints) — confirm whether the user meant AgentWeave's existing
  `ask_user`/Questions-panel mechanism (unaffected by 3.5) or something else that hasn't been
  addressed.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 3.5's entry is very long and
  detailed; read it directly rather than relying solely on this handoff's summary. 3.6 onward is
  still the original unstarted task text.
- `openspec/changes/2026-07-30-hub-native-experience/design.md` — re-read before 3.6, especially
  anything about the SSE event contract / typed activity stream (design.md's "Typed activity
  stream" section, taken from T3's `orchestration.ts` contracts).
- `hub/hub/api/v1/agent_trigger.py` — the file 3.6 extends; read fresh, especially
  `_execute_run()`'s final status-broadcast block, which is the stopgap 3.6 needs to decide
  whether to replace.
- `hub/ui/src/hooks/useSSE.ts` — the `SSE_EVENT_TYPES` allowlist 3.6 will need to extend, and the
  exact bug class (broadcast-but-not-allowlisted) that bit Phase 2 twice.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — likely where run output already renders
  today (not yet confirmed this session) and where 3.6's lifecycle-event rendering would live.
