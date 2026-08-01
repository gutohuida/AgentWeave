# Handoff: Phase 3 task 3.9 complete (terminate process tree on Hub shutdown); committed

**Date:** 2026-08-01T15:45:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `2655ee5`
**Agent:** Claude Code / Sonnet 5 (1M context)
**Previous handoff:** `.claude/handoffs/2026-08-01-1500-hub-native-phase3-t3-8-complete.md`
**Status:** chunk complete — session end.

## Goal

Rebuild the AgentWeave Hub into a local-first application that owns agent execution directly
(the `hub-native-experience` OpenSpec change). Phase 3 ("Native runtime, packaging, and crash
recovery") is in progress; 3.1–3.8 were done entering this session (well, this same continuous
session — see the previous handoff for 3.8, and the one before that for 3.7 and an unplanned
stale-UI-bundle bug fix). This session did task 3.9: "Terminate the process group on Hub
shutdown so no agent process is orphaned." Full reasoning lives in
`openspec/changes/2026-07-30-hub-native-experience/` (`proposal.md`, `design.md`, `tasks.md`).

## Current state

**Task 3.9 is complete, tested (including a genuine real-process/real-lifespan test), and
committed at `2655ee5`. Backend-only — no frontend changes this task.**

New `terminate_process_tree(pid: int, force: bool = True) -> None` in `hub/hub/pty_runner.py`.
Checked pywinpty's own source this session (`inspect.getsource(winpty.PtyProcess.terminate)`):
`PtySession.terminate()` (the thing 3.7's stop endpoint already calls) only ever signals the
*direct* child process it wraps — no process-group or job-object awareness at all, on either
backend. That's fine for 3.7's scope (stop *this* run), but wrong for 3.9's: a Hub shutting down
cleanly must not leave anything the agent CLI itself spawned (a Bash-tool subprocess, a `node`
child, etc.) running detached. `terminate_process_tree` fixes that:
- **POSIX:** `os.killpg(os.getpgid(pid), signal.SIGKILL)`. A PTY child from
  `ptyprocess.PtyProcessUnicode.spawn()` is a session leader — `pty.fork()` calls `setsid()`
  internally — so its process group ID equals its own pid, and `killpg` reaches every process in
  that group.
- **Windows:** `taskkill /F /T /PID <pid>` via `subprocess.run`. Windows has no POSIX-style
  process group; `/T` is the standard idiom for "kill this pid and everything the OS's own
  parent-child tree says descends from it." No new dependency.
- Both branches silently no-op if the pid is already gone.

New `terminate_all_active_runs() -> int` in `hub/hub/api/v1/agent_trigger.py`: walks
`_active_ptys` (the in-memory dict 3.7 introduced, populated per in-progress run) and calls
`terminate_process_tree` on each tracked pid. Wired into `main.py`'s `lifespan()` teardown,
before `shutdown_scheduler()`. **Deliberately does not touch any `Run` row's DB status** — a
shutdown-then-restart is picked up by 3.8's `reconcile_interrupted_runs()` on the *next* boot,
which is the single place that owns transitioning persisted run status; this function's own
docstring and 3.9's `tasks.md` entry both call out that duplicating status-writing here would
risk the two disagreeing about *when* a run's status actually changes.

**3.7's stop endpoint was deliberately left unchanged** — still calls `pty.terminate(force=True)`
(single-process), not `terminate_process_tree`. `design.md`'s Decision 8 wording ("On shutdown
the Hub terminates the process *group*") scopes tree-kill to shutdown specifically, distinct
from a deliberate mid-session stop. Not revisited without evidence a stopped run actually leaves
orphaned grandchildren in practice.

## Files touched

- `hub/hub/pty_runner.py` — new `terminate_process_tree()` function, placed right after
  `pid_alive()` (3.8's addition). Finished.
- `hub/hub/api/v1/agent_trigger.py` — `terminate_process_tree` added to the existing
  `pty_runner` import line; new `terminate_all_active_runs()` function, placed right after the
  `stop_agent_run` endpoint. Finished.
- `hub/hub/main.py` — imports `terminate_all_active_runs` from `.api.v1.agent_trigger`;
  `lifespan()`'s teardown half calls it before `shutdown_scheduler()`. Finished.
- `hub/tests/test_pty_runner.py` — `terminate_process_tree` added to the import line; new
  `TestTerminateProcessTree` class, 2 tests (kills a real spawned long-running subprocess via
  the same `sys.executable` pattern the rest of the file uses; an already-dead pid doesn't
  raise). Finished.
- `hub/tests/test_agent_trigger.py` — 2 new tests:
  `test_shutdown_terminates_all_active_runs` (patches `hub.api.v1.agent_trigger
  .terminate_process_tree` to assert it's called with the right pid, using the same
  blocking-read-released-by-the-patched-call pattern as 3.7's stop tests) and
  `test_terminate_all_active_runs_with_nothing_running_returns_zero`. Finished.
- `hub/tests/test_lifespan_shutdown.py` — **new file**, 1 test. The only test in this whole
  suite that exercises the **real** ASGI lifespan via Starlette's `TestClient` (which, unlike
  `conftest.py`'s `httpx.ASGITransport`-based `app` fixture, actually runs `lifespan()` on
  `__enter__`/`__exit__`) against a genuine spawned OS subprocess: populates `_active_ptys`
  directly with a real long-running process, enters and exits a `TestClient` context, confirms
  the process is actually dead afterward via `pid_alive()`. Finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 3.9 checked off with a
  findings entry (worth reading directly). 3.10 onward still original unstarted text.

**Not touched, pre-existing untracked, not to be modified:** the six `.claude/handoffs/*.md`
files from earlier sessions (listed in every `git status` this session and every prior one).

## Key decisions

1. **`test_lifespan_shutdown.py`'s `TestClient`-based real-lifespan test was chosen as this
   task's live-verification method instead of restarting the user's live dev Hub** (the way
   3.7 and 3.8 did). Reasoning: it exercises the exact same `main.py` wiring end-to-end against
   a real OS process, is automated and repeatable rather than a one-off manual check, and
   doesn't require disrupting an instance the user was actively using — for 3.8, a live restart
   was genuinely necessary (reconciliation depends on real persisted DB state across a process
   boundary that's hard to fake), but 3.9's shutdown path has no such dependency; the ASGI
   lifespan itself *is* the thing under test, and `TestClient` triggers the real one.
2. **Windows graceful-shutdown signal delivery was investigated and abandoned as a live-
   verification approach.** Considered sending `SIGINT`/`CTRL_C_EVENT` to the backgrounded
   `nohup ... &` uvicorn process to trigger a real OS-level graceful shutdown, matching how a
   production Hub would actually be stopped. Windows has no POSIX signals, and a `nohup`-
   backgrounded process launched from this Bash tool's Git-Bash environment isn't reliably
   reachable via `GenerateConsoleCtrlEvent` (that requires shared console/process-group state
   this setup doesn't guarantee). *Rejected* in favor of decision 1 above — `TestClient`
   sidesteps the whole signal-delivery problem by driving the lifespan directly through
   Starlette's own test machinery, which is the mechanism real deployments rely on anyway
   (uvicorn calls the same lifespan protocol on a real SIGTERM).
3. **`terminate_process_tree` does not update `Run.status`** — same reasoning as
   `reconcile_interrupted_runs()` not doing so on the crash-reconciliation side (3.8): a single
   function owning "when does a Run row's status change" avoids the two functions racing or
   disagreeing. A clean shutdown leaves affected rows `"running"` in the DB until the *next*
   boot's reconciliation pass notices the process is gone and marks them `"interrupted"` — this
   is intentional, not a gap, and is stated explicitly in both functions' docstrings so a future
   reader doesn't "fix" it by adding a second status-writer.
4. **3.7's `PtySession.terminate(force=True)` call in the stop endpoint was left untouched,
   not upgraded to `terminate_process_tree`.** `design.md`'s own wording scopes tree-kill to
   Hub *shutdown* ("On shutdown the Hub terminates the process group"), not to every
   termination path. Expanding 3.7's already-shipped, already-tested behavior without being
   asked and without evidence of an actual orphaned-grandchild problem there would have been
   scope creep beyond what 3.9's task text or the design doc calls for.

## Constraints and user directives (verbatim)

- User said **"keep going"** at the start of this session's continuation (after the previous
  handoff's summary of 3.8 + the stale-UI fix), in response to being asked whether to
  prioritize task 3.20 (stale UI) ahead of 3.9 or continue in the OpenSpec sequence — confirms
  the sequence-following default, not a detour into 3.20.
- Carried forward, still in force: **"Yeah and always commit the changes."** — 3.9's 7 files
  committed immediately on completion (`2655ee5`), staged explicitly by path, no fresh ask.
- Carried forward, still in force: *"At resume ... verify the previous work done."* — not
  re-triggered this session since this handoff chains directly off the same continuous session
  as 3.8's, not a fresh `/resume`.
- Carried forward, still in force (from every prior handoff in this chain): "After every
  threshold of implementation you must run the skill `/handoff`" (this file is that). "Before
  starting a new implementation revise the entire session for the spec." "let's make sure it
  works with claude and codex first locally" — Copilot second (unaffected by this session).
  Project `CLAUDE.md` rules still apply (never commit `.agentweave/tasks/`, `messages/`,
  `agents/`, `session.json`, `transport.json`; stage explicitly, never `git add -A`).
- **Carried forward from the 3.8 handoff, as a concrete precedent, not re-tested this
  session since it wasn't needed:** when live-verifying against a Hub instance the user might
  be actively using, ask before restarting it. This session avoided the question entirely by
  choosing a verification method (`TestClient`) that doesn't touch the live instance at all —
  worth remembering as an available alternative for future tasks, not just "always ask."

## Dead ends

- **Windows signal delivery to a backgrounded process, for graceful-shutdown testing** — see
  Key Decision 2 above. Not pursued to completion; abandoned once `TestClient` was identified
  as a strictly better (automated, repeatable, non-disruptive) alternative that tests the same
  code path.
- Nothing else notably dead-ended this task — it was comparatively straightforward compared to
  3.6/3.7/3.8, mostly because the `_active_ptys` infrastructure and the
  persist-status-only-in-one-place discipline were both already established by prior tasks in
  this same session.

## Verification

**Ran and passed:**
- `py -m pytest tests/ -q` from `hub/` → 330 passed, 4 skipped (was 325 after 3.8's
  static-UI-fix commit; +5 new tests — 2 in `test_pty_runner.py`, 2 in
  `test_agent_trigger.py`, 1 in the new `test_lifespan_shutdown.py`). Same pre-existing
  CWD-dependent `test_migrations.py` caveat every prior handoff in this chain has noted.
- `py -m ruff check hub/ tests/` → clean, first pass, no fixes needed this time.
- `py -m black --check hub/ tests/` → clean, first pass, no reformatting needed this time.
- No frontend changes this task, so `tsc --noEmit`/`vitest run`/static-bundle-rebuild were not
  applicable and were not run.
- **`test_lifespan_shutdown.py::test_hub_shutdown_kills_a_real_tracked_process`** — this *is*
  the live verification for this task (see Key Decision 1): a real `sys.executable` subprocess
  spawned via `PtySession.spawn`, registered directly into `agent_trigger._active_ptys`, then a
  real `create_app()` instance entered/exited via Starlette's `TestClient` (genuinely runs
  `lifespan()`'s startup and shutdown, unlike every other test in this suite); confirmed via
  `pid_alive()` that the real OS process was alive before and dead after the `TestClient`
  context exited. Ran in isolation (`pytest tests/test_lifespan_shutdown.py -v`) and as part of
  the full suite; passed both times.

**NOT tested this session:**
- POSIX `terminate_process_tree` branch (`os.killpg`) — this dev environment is Windows;
  exercised the Windows `taskkill /T` branch throughout. Matches every prior handoff's note
  that this repo's CI (`ubuntu-latest`) is what actually covers the POSIX path for anything
  platform-branched in `pty_runner.py`; not independently re-verified here.
- A real signal-delivered (`SIGTERM`/`CTRL_C_EVENT`) graceful shutdown of an actually-running,
  separately-launched uvicorn process — see Dead Ends above; deliberately not pursued in favor
  of the `TestClient` approach, which tests the identical `lifespan()` code path without the
  signal-delivery complexity.
- Whether a real Claude/Codex CLI process, if it had itself spawned genuine subprocesses (a
  Bash tool invocation, etc.) at the moment of a Hub shutdown, would have those subprocesses
  actually survive `PtySession.terminate()` alone (the pre-3.9 behavior) versus be correctly
  caught by `terminate_process_tree` (the post-3.9 behavior) — the *mechanism* is proven
  correct against a real OS process tree in the unit test, but no live reproduction was done
  with an actual multi-process CLI invocation specifically to demonstrate the before/after
  difference.
- Kimi/OpenCode/Copilot — still out of scope (watchdog path, unaffected, not re-verified).
- Nothing from 3.10 (route scheduled jobs through the direct execution path) or anything past
  it was started or touched.

## Git state

- Branch `hub-native-experience`, **HEAD `2655ee5`** — task 3.9's 7 files committed this
  session ("Complete Phase 3 task 3.9: terminate the process tree on Hub shutdown"), on top of
  `682edda` (the 3.8 handoff-tracking commit).
- Working tree clean except the six pre-existing untracked `.claude/handoffs/*.md` files from
  earlier sessions (unrelated) plus this new handoff file and `LATEST.md`'s pointer update —
  committed in a separate follow-up commit after this file is finalized, matching the chain's
  established two-commit-per-checkpoint pattern.
- No upstream configured — nothing pushed, not requested, unchanged from every prior handoff.

## Next steps

1. **Read `tasks.md`'s 3.10 entry in full before starting** — it's a materially bigger, more
   architecturally significant task than 3.6–3.9 were. Its text: "Route scheduled jobs through
   the direct execution path; remove the watchdog's message-scanning trigger branch, keeping
   only timer duties." This is not another additive run-lifecycle feature — it's the first task
   in this phase that *removes* an existing code path (the watchdog's message-tag-based
   triggering for scheduled jobs), which every prior task in this session's chain has
   deliberately left untouched ("unaffected — `agentweave` watchdog's message-tag construction
   ... is untouched by this file's rewrite," per `agent_trigger.py`'s own module docstring).
2. Locate the scheduler's current job-triggering code (`hub/hub/scheduler.py`, touched
   read-only this session while checking `init_scheduler`/`shutdown_scheduler` were safe to
   invoke in `test_lifespan_shutdown.py` — not otherwise investigated) and the watchdog's
   message-scanning trigger branch (likely in `src/agentweave/watchdog.py`, per the CLI side of
   this repo, not the Hub side — this task may be the first one in the Phase 3 chain that needs
   changes on *both* sides of the CLI/Hub split, unlike 3.5–3.9 which were Hub-only).
3. Given the "before starting a new implementation revise the entire session for the spec"
   standing directive, this is a good task to actually do that revision seriously for — re-read
   `proposal.md` and `design.md` in full (not just excerpts) before touching code, since 3.10
   crosses a boundary (CLI watchdog vs. Hub direct-spawn) that hasn't been crossed yet in this
   chain.
4. Per the standing directive, **commit 3.10's changes on completion without waiting for a
   fresh ask** — staged explicitly by path, same as every task in this chain so far.

## Open questions for the user

- Carried forward, unresolved, not urgent: should anything be pushed to a remote at this point?
  No remote/upstream is configured for this branch.
- Carried forward from 3.5/3.6/3.7/3.8, still not resolved: the "ability to question the user"
  comment from an earlier T3-parity discussion — confirm whether the user meant AgentWeave's
  existing `ask_user`/Questions-panel mechanism (unaffected by anything in Phase 3 so far) or
  something else.
- Carried forward from 3.8, still open: task 3.20 ("Stop the Hub silently serving a stale UI")
  caused a real user-visible bug this session (fixed manually, twice). The user chose to keep
  going in sequence rather than prioritize 3.20 — worth re-raising once 3.10+ introduces more
  frontend changes, since the staleness risk recurs with every frontend-touching task until
  3.20 is actually fixed.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 3.9's entry is long; read it
  directly. 3.10's entry is short (one line) but represents a bigger architectural task than
  its brevity suggests — read `proposal.md`/`design.md` too, not just this file, before
  starting (see Next Steps 3 above).
- `hub/hub/scheduler.py` — read read-only this session (just enough to confirm
  `init_scheduler`/`shutdown_scheduler` were safe to call from a test); 3.10 will need to
  understand its current job-triggering mechanism in full before changing it.
- `hub/hub/api/v1/agent_trigger.py` — `terminate_all_active_runs()` (this session's addition)
  and `trigger_agent()`/`_execute_run()` (3.5/3.6/3.7's) are the direct-execution path 3.10
  needs to route scheduled jobs *through* — re-read fresh.
- `src/agentweave/watchdog.py` — the CLI-side message-scanning trigger branch 3.10 needs to
  remove "keeping only timer duties." Not read at all this session; entirely fresh territory
  for this task chain.
- `hub/hub/main.py` — `lifespan()` now has the full startup/shutdown sequence
  (`init_db` → `reconcile_interrupted_runs` → `init_scheduler` → yield → `terminate_all_active_runs`
  → `shutdown_scheduler`) that 3.10's scheduler-routing changes will sit alongside.
