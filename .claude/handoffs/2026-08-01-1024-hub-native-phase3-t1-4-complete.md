# Handoff: Phase 3 tasks 3.1–3.4 complete; 3.5 (trigger rewrite) about to start

**Date:** 2026-08-01T10:24:27+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `13fe2f8`
**Agent:** Claude Code / Sonnet 5 (1M context)
**Previous handoff:** `.claude/handoffs/2026-07-31-2314-hub-native-phase2-streaming-complete.md`
**Status:** chunk complete — four Phase 3 tasks committed and verified; continuing in this same
session into 3.5 immediately after this handoff is written (not a stopping point — user chose
"write a handoff first, then continue" specifically because 3.5 rewrites a live execution path).

## Goal

Rebuild the AgentWeave Hub into a local-first application that owns agent execution directly,
using T3 Code as a studied reference rather than forking it. Phases 1 (material feel) and 2
(SSE-driven live updates) are done (see the previous handoff). This session's chunk is Phase 3 —
"Native runtime, packaging, and crash recovery" — the phase that starts real process-spawning
work. Full reasoning lives in `openspec/changes/2026-07-30-hub-native-experience/` (`proposal.md`,
`design.md`, `tasks.md`).

## Current state

**Four commits landed this session**, all on `hub-native-experience`, nothing pushed (no
upstream configured):

1. `3f94204` — task 3.1: `agentweave hub start` now runs **natively by default** (no Docker).
   The native start path (`_hub_native_start` in `cli.py`) already existed pre-branch
   (commit `a69f04e`, unrelated earlier feature) but was gated behind an opt-in `--native` flag
   with Docker as the default — backwards from Decision 1. Flipped: bare `agentweave hub start`
   is now native; `--docker` (renamed from `--native`, sense inverted) opts into the container
   path; `--local` (Docker dev flow from `./hub/`) now implies `--docker`. Bundled in the same
   commit: 3.13 (the separate `agentweave-hub` console-script entry point, `hub/hub/main.py:run()`,
   hardcoded `host="0.0.0.0"` — now reads a new `AW_HOST` setting, default `127.0.0.1`; Docker's
   own `Dockerfile` CMD is unaffected, it hardcodes `0.0.0.0` independently and correctly) and
   3.14 (Docker gate only consulted on the explicit `--docker` path now). Docs/skill-templates
   updated throughout (README, docs/index.md, docs/getting-started/{quickstart,installation}.md,
   docs/reference/{cli-commands,env-variables}.md, aw-setup.md, aw-setup-hub.md,
   docs/getting-started/configuration.md, config.py's generated-yml comment, pyproject.toml's
   mypy comment). Live-verified: killed a stale dev Hub, ran bare `agentweave hub start`,
   confirmed native + 127.0.0.1 bind + correct PID-tracked status/stop; `--docker` still gates on
   Docker daemon availability.

2. `19b8e03` — task 3.2: per-agent launchability probe. The CLI already had this
   (`agentweave.diagnostics.check_agent_readiness`/`launch_blockers`, used only by the host
   watchdog before spawning) but the Hub had nothing equivalent. Added `hub/hub/launchability.py`
   (`probe_agent`) — deliberately reimplemented rather than imported, since the Hub has zero
   dependency on the `agentweave-ai` package. Covers CLI presence (`shutil.which`, respecting a
   pinned `cli:` override), `claude_proxy`/`copilot` authorization, pilot/manual blocking, each
   with a stated `reason` when not runnable. Exposed as `GET /api/v1/agents/launchability`
   (`hub/hub/api/v1/agents.py`), merging session-synced config with self-registered `Agent.config`
   the same way the existing agent-list endpoint does. Read-only, no spawning. Live-verified
   against the real running Hub with real `claude`/`kimi`/`manual` agents (present/runnable
   correctly detected), then the test sync was reverted so the dev Hub's actual state wasn't left
   polluted.

3. `3f2b3fb` — task 3.3: introduced the `Run` record. Added `Run` to `hub/hub/db/models.py`
   (`runs` table): `id`, `agent`, `session_id` (typed field, per Decision 2 — session identity
   must never be text embedded in a message body again), `started_at`/`ended_at`, `status`
   (`RUN_STATUSES = running/completed/failed/interrupted/stopped`), `exit_code` + `error` (exit
   outcome), `pid` + `last_heartbeat_at` (what Decision 8's crash reconciliation needs on Hub
   restart). `AgentOutput.run_id` already existed pointing at nothing — `Run` is what it was
   always meant to reference (left as a loose reference, no FK, since nothing populates real
   run_ids yet). Migration `hub/hub/migrations/versions/0012_add_runs_table.py`. Bumped two
   hardcoded `"0011"` version-assertion strings in `test_migrations.py` to `"0012"`. **Schema
   only** — nothing creates/updates/queries a `Run` row yet; `agent_trigger.py` is completely
   untouched, still on the old message-tag protocol. That's exactly what 3.5 (next) does.

4. `13fe2f8` — task 3.4: PTY process spawn prototype. Added `hub/hub/pty_runner.py`
   (`resolve_executable`, `PtySession`) — a thin adapter over `pywinpty` (Windows, wraps ConPTY)
   / `ptyprocess` (POSIX, wraps `pty.fork()`); the two libraries expose near-identical APIs by
   the Windows library's own design. New Hub dependencies in `hub/pyproject.toml`, platform-gated:
   `pywinpty>=2.0; sys_platform == 'win32'`, `ptyprocess>=0.7; sys_platform != 'win32'` — user
   explicitly chose this over hand-rolled ConPTY ctypes when asked. `.cmd` shims (the concern
   named in the task, `cli.py:2341`) handled by mirroring the watchdog's own existing fix:
   `shutil.which()` first (PATHEXT-aware), then spawn the resolved absolute path — no
   `shell=True` anywhere. **Live-verified by hand on this actual Windows dev machine** (both
   packages were installed fresh via `py -m pip install pywinpty ptyprocess` — not previously
   present): real process spawn + output capture (including ConPTY's terminal-handshake escape
   sequences prefixing real output, e.g. `\x1b[1t\x1b[c\x1b[?1004h\x1b[?9001h` — expected ConPTY
   behavior, not a bug, but worth knowing before 3.6 renders this output); a synthetic
   `fakecli.cmd` spawned by bare name with correct output/argument/exit-code (3); missing-binary
   `FileNotFoundError` before any spawn attempt; `terminate(force=True)` stopping a 30s-sleeping
   process. **CI will only ever exercise the POSIX/`ptyprocess` path** —
   `.github/workflows/ci.yml`'s `hub-test` job runs `ubuntu-latest` only, not the 3-OS matrix the
   CLI's `test` job uses. This module is a spawn primitive only — not wired into
   `agent_trigger.py` or `Run` yet.

**`tasks.md` is updated after every task** with detailed inline findings (read it directly rather
than trusting this summary for exact wording — each entry is long and specific).

**Test counts, most recent full runs:** CLI `tests/` — 996 passed. Hub `hub/tests/` — 269 passed,
4 skipped (all pre-existing skips, unrelated). Both green as of `13fe2f8`.

**Two Hub instances have been running in the background this session, both restarted/killed
multiple times during live verification:**
- The "real" persistent one at `~/.agentweave/hub/data/agentweave.db` (via `agentweave hub start`,
  now native by default) — used for 3.1/3.2/3.3's live verification.
- The dev one the actual Vite frontend (port 5174, from the previous session, still presumably
  running) is pointed at: `hub/data/agentweave-dev.db`, started manually via
  `cd hub && DATABASE_URL="sqlite+aiosqlite:///./data/agentweave-dev.db" py -m uvicorn hub.main:app
  --host 127.0.0.1 --port 8000` (backgrounded via `nohup ... &; disown` in the Bash tool). This is
  the one currently running as of this handoff — check `curl -s http://127.0.0.1:8000/health`
  before assuming its state; it has a real `claude` agent registered (session-synced), confirmed
  present/runnable via `/api/v1/agents/launchability`.
- **Do not assume either is still running** when resuming — background bash processes in this
  environment do not reliably survive a context/session boundary. Re-check before using.

## Files touched

**Commit 1 (`3f94204`, tasks 3.1/3.13/3.14):** `src/agentweave/cli.py` (`cmd_hub_start`,
`hub_start` argparse block, `cmd_hub_status`'s stopped-hint print), `hub/hub/config.py`
(new `aw_host` setting), `hub/hub/main.py` (`run()` uses it), `tests/test_hub_commands.py`
(rewritten for `--docker`/native-default semantics), `README.md`,
`docs/getting-started/{configuration,installation,quickstart}.md`, `docs/index.md`,
`docs/reference/{cli-commands,env-variables}.md`, `src/agentweave/config.py`,
`src/agentweave/templates/skills/{aw-setup,aw-setup-hub}.md`, `pyproject.toml`. All finished.

**Commit 2 (`19b8e03`, task 3.2):** `hub/hub/launchability.py` (new), `hub/hub/api/v1/agents.py`
(new `GET /agents/launchability` route + import), `hub/tests/test_launchability.py` (new, 12
tests). All finished.

**Commit 3 (`3f2b3fb`, task 3.3):** `hub/hub/db/models.py` (`Run` class + `RUN_STATUSES`, inserted
before `AgentOutput`), `hub/hub/migrations/versions/0012_add_runs_table.py` (new),
`hub/tests/test_migrations.py` (two hardcoded version strings bumped 0011→0012, two new tests:
`test_migration_0012_creates_runs_table_on_existing_deployment`,
`test_run_model_round_trips_through_the_orm`). All finished. Nothing else references `Run` yet.

**Commit 4 (`13fe2f8`, task 3.4):** `hub/hub/pty_runner.py` (new — `resolve_executable`,
`PtySession`), `hub/tests/test_pty_runner.py` (new, 10 tests), `hub/pyproject.toml` (two new
platform-gated dependencies). All finished. `pywinpty`/`ptyprocess` are now `pip install`ed in
this machine's active Python environment (the global Python 3.11 install at
`C:\Users\huida\AppData\Local\Programs\Python\Python311`, where `agentweave`/`agentweave-hub` are
editable-installed against this repo) — a fresh clone/environment would need
`pip install -e ".[dev]"` in `hub/` to pick these up, which is already how the CI/dev workflow
installs Hub deps, so no extra step should be needed going forward.

**Not touched this session, pre-existing untracked, not to be modified:** the six
`.claude/handoffs/*.md` files from earlier sessions listed in `git status`.

## Key decisions

1. **Bundled 3.1+3.13+3.14 into one commit** rather than three — they're all edits to the exact
   same `cmd_hub_start`/native-start code path; splitting would have meant touching the same
   function three times for no isolation benefit.
2. **`--docker` replaces `--native`, sense inverted, rather than keeping `--native` as a
   deprecated no-op.** This is a pre-merge experimental branch (`"No, merge nothing. Just
   continue."` still in force), small user base, so a clean rename was judged better than a
   backwards-compat shim for a flag that hasn't shipped to real users yet.
3. **Hub's launchability probe is a deliberate reimplementation, not an import of the CLI's
   `diagnostics.py`.** The Hub has zero dependency on `agentweave-ai` by design (must be probeable
   standalone); importing would create a new coupling the architecture doesn't otherwise have.
   *Rejected:* adding `agentweave-ai` as a Hub dependency to reuse the exact logic — more DRY, but
   breaks the Hub's standalone-installability property for a fairly small amount of shared logic
   (one runner→CLI table, PATH/env checks).
4. **Launchability's "authorized" check only reflects what the Hub process's own environment can
   see** (`os.environ`), not a project's `.env` file — the Hub does not yet track a project's
   working directory at all (`Project` has no `working_dir` column; that's Phase 10). Explicitly
   scoped out rather than half-solved; matters more once 3.5 actually spawns processes in a real
   project directory.
5. **`Run.session_id` and other loose references stay unconstrained (no FK) for now.** Adding a
   hard FK from `AgentOutput.run_id` to `Run.id` was considered and rejected — nothing populates
   real run_ids yet, so a constraint would just be inert until 3.5/3.6 wire it up; adding it now
   would be premature schema commitment ahead of the code that uses it.
6. **PTY over plain pipes, per user's explicit choice when asked**: `pywinpty` + `ptyprocess`
   (mature, maintained, near-identical APIs) over hand-rolled ConPTY ctypes. The existing watchdog
   already spawns agents successfully via plain `subprocess.Popen(stdout=PIPE)` — PTY is chosen
   specifically because T3 (the studied reference) owns the PTY, preserving TTY-dependent CLI
   behavior (colour, prompts, `isatty()` checks) that a plain pipe suppresses. This is a real
   behavioral difference from the watchdog's current approach, not a drop-in replacement — worth
   remembering when 3.5 replaces the watchdog's spawn call with this one, since a runner's output
   format could differ under PTY vs pipe (colour codes present that weren't there before, etc.).
7. **`.cmd` shim resolution reuses the watchdog's existing `shutil.which()`-first pattern** rather
   than inventing a new approach or using `shell=True`. Proven correct end-to-end against a
   synthetic shim. `cli.py:2341`'s `shell=True` comment (in `cmd_mcp_setup`, a different, older
   code path) was *not* touched or reconciled — flagged as a known loose end, not fixed, since
   it's out of task 3.4's scope.

## Constraints and user directives (verbatim)

- `"No, merge nothing. Just continue."` — still true, nothing merged/pushed.
- This session, when asked to choose the PTY approach: **"pywinpty + ptyprocess (Recommended)"**
  — user picked the recommended option explicitly over hand-rolled ctypes ConPTY.
- This session, when asked how to handle the Phase-1/2 merge question carried from the last two
  handoffs: **"Keep building, merge later"** — don't merge to master yet, keep accumulating
  phases on `hub-native-experience`. This resolves the open question the last two handoffs both
  raised; **do not ask again** unless something changes.
- This session, when asked whether to continue into 3.4 (a materially bigger/riskier task):
  **"Start Phase 3 (Recommended)"** then **"Continue straight into 3.4"** — user is comfortable
  with the agent proceeding through same-sized chunks without re-confirming each one, but treats
  *qualitatively* bigger jumps (new phase, or a task that rewrites a live execution path) as
  worth a check-in first.
- This session, when asked how to proceed into 3.5 (rewrites the live trigger endpoint, deletes
  behavior the watchdog depends on): **"Write a handoff first, then continue"** — checkpoint to
  disk, but stay in this same session and keep working afterward. This is that checkpoint.
- Carried forward from earlier handoffs, still in force: "After every threshold of implementation
  you must run the skill /handoff." "Before starting a new implementation revise the entire
  session for the spec" (i.e. re-read `tasks.md`/`design.md` before each phase — done at the start
  of this session for Phase 3). "I'm open to trying things other than the CLI... don't hesitate
  [to remake something]." "let's make sure it works with claude and codex first locally" —
  Copilot second. Employer blocks third-party MCP **in GitHub Copilot only**. "the spec screen
  should be as good and nice as the agents one." "We don't need that white square around the
  message queued user message" — queued state is opacity + chip, never a dashed border (Phase 1
  concern, not touched this session, still applies if revisited). Project `CLAUDE.md` rules still
  apply (never commit `.agentweave/tasks/`, `messages/`, `agents/`, `session.json`,
  `transport.json`; stage explicitly, never `git add -A` — every commit this session staged files
  by exact path).

## Dead ends

- **Assuming `agentweave hub start`'s detached-mode failure meant something was broken.** It
  failed its 60s health-check timeout three times in a row at one point during this session, even
  though `--no-detach` (foreground) proved the server actually starts and serves real traffic
  correctly within seconds every time. Root-caused only partially: foreground mode runs
  `uvicorn.run()` in-process (no subprocess spawn); detached mode spawns
  `subprocess.Popen([sys.executable, "-m", "uvicorn", ...])` with `stdout=stderr=DEVNULL`, so any
  slowness in that child process is invisible to the CLI wrapper's health-check poll. This
  predates this session's changes (it happened once during 3.1's very first live-verification
  test, before any code had been touched) and was **not fixed** — logged as an out-of-scope
  finding in task 3.3's `tasks.md` entry. If it recurs and blocks verification again, the working
  workaround is: `cd hub && DATABASE_URL="sqlite+aiosqlite:///<path>" py -m uvicorn hub.main:app
  --host 127.0.0.1 --port 8000` backgrounded manually, bypassing the CLI wrapper's health check
  entirely.
- **A related but distinct, already-harmless, already-swallowed warning**: `_run_alembic_upgrade`
  in `hub/hub/db/engine.py` builds an absolute path to `alembic.ini`, but alembic's own
  `script_location` inside that ini is resolved relative to the process's CWD, not the ini file's
  location — so when the Hub is started from outside `hub/` (e.g. from the repo root, which is
  where `agentweave hub start` is normally run from), this redundant migration-on-boot step
  fails with `Path doesn't exist: hub\migrations` and logs a caught WARNING. Harmless because
  `_hub_native_start` (`cli.py`) already runs migrations correctly via a real absolute path
  *before* spawning the child process — this is only the child's own *second, redundant* attempt
  inside `hub.main`'s FastAPI lifespan. Not fixed, out of scope, logged in `tasks.md`.
- **Manually reproducing the CLI's exact subprocess invocation from the repo root
  (`py -m uvicorn hub.main:app` with CWD = repo root, not `hub/`) raised
  `ImportError: cannot import name '__version__' from 'hub' (unknown location)`** — caused by the
  ambient `AgentWeave/hub/` directory (no `__init__.py`) shadowing/merging with the properly
  installed `hub` package as a Python namespace package when CWD is implicitly on `sys.path` via
  `-m`. This does **not** appear to affect the actual `_hub_native_start` subprocess in practice
  (multiple `agentweave hub start` calls succeeded from this exact CWD earlier in the session),
  so it was not chased further — noted here only so a future investigator doesn't waste time
  re-discovering it as if it were the *actual* cause of the detached-mode timeout above (it
  probably isn't, but wasn't fully ruled out either).

## Verification

**Ran and passed, every commit:**
- CLI: `py -m pytest tests/ -q` → 996 passed (after commit 1; not re-run after 2-4 since those
  didn't touch `src/agentweave/`).
- Hub: `py -m pytest hub/tests/ -q` → 245 (baseline) → 257 (+2, task 3.1's tests were CLI-side) →
  257 (+12, task 3.2) → 259 (+2, task 3.3) → 269 (+10, task 3.4). All green at every commit.
- `py -m ruff check` and `py -m black --check` (with one `py -m black` reformat applied and
  re-verified each time it fired) clean on every changed file, every commit.
- Live verification specific to each task is detailed inline above and in `tasks.md`.

**NOT tested this session:**
- No `mypy src/` run (only touched `hub/`, which isn't in mypy's scope per `pyproject.toml`).
- The Windows PTY path (`pty_runner.py`) has **zero CI coverage** — verified by hand only, as
  documented above. If this module is modified later without Windows access, there is no
  automated safety net for the Windows branch.
- Multi-project / multi-key scenarios for the launchability endpoint — only tested against the
  single bootstrap project.
- No load/concurrency testing of `PtySession` (e.g. multiple simultaneous spawns, resource
  exhaustion) — task 3.4 is a prototype of the primitive, not a hardening pass.
- The Vite frontend (port 5174, if still running) was not reloaded/re-checked against any of this
  session's backend changes — none of the four tasks changed anything the frontend currently
  calls in a way that would be visible (new endpoints are additive, `hub start` flag rename is
  CLI-only).

## Git state

- Branch `hub-native-experience`, **HEAD `13fe2f8`**, working tree clean except the six
  pre-existing untracked `.claude/handoffs/*.md` files (unrelated, from earlier sessions) plus
  this new handoff file being written.
- Four commits made this session, all on top of `4c0b754` (the branch's previous tip, itself the
  handoff-tracking commit from the last session).
- No upstream configured (`no upstream`) — nothing pushed, not requested.

## Next steps

1. **Re-read `design.md` Decision 2 and Decision 8 in full** (already read once this session, but
   re-read before writing code — per the working protocol) — Decision 2 specifies session identity
   as a typed field on the run record (now `Run.session_id`, done in 3.3) and that
   `execution_confidence`/`[Session: …]`/`[NewSession]` are deleted; Decision 8 specifies the
   crash-reconciliation contract 3.5's spawn path must respect (though full reconciliation is
   3.8 — 3.5 just needs to not violate it).
2. **Start task 3.5**: rewrite `hub/hub/api/v1/agent_trigger.py`'s `trigger_agent()` to:
   - Create a `Run` row (status `running`, `pid` set after spawn) instead of a synthetic
     `Message`.
   - Use `hub/hub/pty_runner.py`'s `PtySession.spawn()` to actually launch the agent CLI, using
     the same runner→cli resolution `hub/hub/launchability.py`'s `RUNNER_CLI` table already
     encodes (consider whether to import/reuse that table directly rather than re-deriving it).
   - Delete `execution_confidence`, the `AgentHeartbeat`-based confidence heuristic, the
     `[Session: …]`/`[NewSession]` body-tag construction, and the `is_pilot`/`is_manual` special
     casing that currently just changes the message text (pilot/manual agents presumably should
     now just... not be triggerable this way at all, or be rejected with a clear error — this is
     a real design question to resolve while implementing, not decided yet).
   - Return a real run identifier in the response instead of `message_id`.
   - **Open question, not yet resolved**: what happens to output capture / streaming while this
     task is in progress? Task 3.6 ("emit run lifecycle and output events on the SSE channel") is
     the next task after 3.5 and is presumably meant to consume whatever 3.5 produces — but 3.5's
     own task description doesn't explicitly say whether it needs to persist output into
     `AgentOutput` rows itself or just get the process running and let 3.6 handle output. Decide
     this deliberately when starting 3.5, don't guess mid-implementation.
   - `hub/tests/test_agents.py` already has tests for `agent_trigger` (work_dir validation tests)
     that must keep passing; `hub/tests/test_migrations.py` and `test_pty_runner.py` are unrelated
     and shouldn't need changes.
3. Given 3.5 will delete watchdog-dependent behavior, **check whether any CLI-side tests
   (`tests/test_watchdog*.py`) assert on the message-tag protocol from the Hub side** — if so
   they may need updating too, though the watchdog's own message-scanning trigger branch removal
   is explicitly task **3.10**, not 3.5, so some coexistence period is expected.

## Open questions for the user

- None newly raised this session beyond what's embedded in "Next steps" above (the
  output-capture-timing question for 3.5, and the pilot/manual-agent behavior question for 3.5).
  Both are implementation decisions to make while building 3.5, not blocked on the user — flagged
  here so they're made deliberately rather than by accident.
- Carried forward, unresolved, not urgent: should anything be pushed to a remote at this point?
  No remote/upstream is configured for this branch. Not blocking.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — §3 has detailed inline findings
  for 3.1–3.4 (this handoff summarizes them but the file has the full detail, including exact
  file paths and verification transcripts); 3.5 onward is still the original unstarted task text.
- `openspec/changes/2026-07-30-hub-native-experience/design.md` — Decisions 2 and 8 especially,
  before starting 3.5.
- `hub/hub/api/v1/agent_trigger.py` — the file 3.5 rewrites; read it fresh, it has not changed
  this session.
- `hub/hub/pty_runner.py` and `hub/hub/db/models.py`'s `Run` class — the two primitives 3.5 wires
  together.
- `hub/hub/launchability.py` — has the `RUNNER_CLI` table; check before re-deriving runner→CLI
  mapping logic a third time (CLI's `constants.py` has the first copy).
