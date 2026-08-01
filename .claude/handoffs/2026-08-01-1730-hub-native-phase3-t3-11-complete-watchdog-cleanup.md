# Handoff: Phase 3 task 3.11 complete; live watchdog double-trigger bug found and fixed

**Date:** 2026-08-01T17:30:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `1ef8986`
**Agent:** Claude Code / Sonnet 5 (1M context)
**Previous handoff:** `.claude/handoffs/2026-08-01-1645-hub-native-phase3-t3-10-complete.md`
**Status:** chunk complete — session end. This is a long handoff for a long session (tasks
3.6–3.11 all landed in one continuous session); read the whole thing before resuming, not
just the tail.

## Goal

Rebuild the AgentWeave Hub into a local-first application that owns agent execution directly
(the `hub-native-experience` OpenSpec change). Phase 3 ("Native runtime, packaging, and crash
recovery") is in progress; 3.1–3.10 were done entering this session's final stretch (all
within this same continuous session — see the chain of prior handoffs starting from
`2026-08-01-1345`). This chunk did task 3.11: "Remove `agentweave switch` and `agentweave
agent set-session` from the Hub-managed path; resolve provider environment and session
continuity inside the Hub." Full reasoning lives in
`openspec/changes/2026-07-30-hub-native-experience/` (`proposal.md`, `design.md`, `tasks.md`).

**Between 3.10 finishing and 3.11 starting, the user live-tested 3.10's work and reported two
real bugs** (see below) — both were diagnosed and fixed as an out-of-band interruption before
3.11's own work began. The user also asked to remove pilot mode entirely; that request is
**not done, deliberately deferred** — see Open Questions.

## Current state

### Task 3.11 — complete, tested, committed at `1ef8986`

**Hub side (the substantive fix):** new `resolve_agent_env(runner, config)` in
`hub/hub/launchability.py`, mirroring `agentweave.watchdog._prepare_agent_env`/
`_prepare_runner_env`'s exact semantics — `ANTHROPIC_API_KEY_VAR` indirection, generic
self-referencing env-var placeholders, and native-Claude proxy-URL-leak stripping.
Deliberately reimplemented rather than imported from the CLI package (matches
`launchability.py`'s own pre-existing stated principle: the Hub must stay probeable/runnable
with zero dependency on `agentweave-ai` being installed, e.g. a Docker-only deployment).

Wired into `trigger_agent_directly()`: computes `env = resolve_agent_env(runner, config)`,
threads it through a new `env` parameter on `_execute_run()`, into
`PtySession.spawn(cmd, cwd=work_dir, env=env)`. **Before this task, `_execute_run` never
passed any env override to spawn at all** — a Hub-triggered `claude_proxy` agent (Minimax,
GLM) only ever authenticated if the operator had *already* exported the right key into the
Hub process's own shell before starting it. That's the exact `eval $(agentweave switch
<agent>)` ceremony this task exists to remove — it just used to be silently required anyway,
aimed at the Hub's own shell instead of a normal one.

**Session continuity was already solved**, no gap found: tasks 3.5–3.7's existing session
picker (`GET /agent/sessions/{agent}`, `AgentOutputPanel.tsx`'s conversation dropdown) already
lets the operator choose which session to resume for a Hub-managed agent. Nothing changed
here.

**CLI side:** `cmd_switch` and `cmd_agent_set_session` (`src/agentweave/cli.py`) now check
`get_transport().get_transport_type() == "http"` first; if so, print a short note steering the
operator to the Hub UI and `return 0` (not a hard failure — running the command isn't wrong,
just superseded). Local/git-transport behavior for both is unchanged, verified by tests.
`cmd_run` — related but not named in the task text — was deliberately left untouched.

**Found and fixed in the same task, not separately requested:** `agent_trigger.py`'s 501
response for an unsupported runner (Kimi/OpenCode/Copilot) claimed "This agent can still be
triggered via the watchdog's own message-based path" — a claim task 3.10 made false by
removing that exact path. Traced the full history: this fallback only ever covered
job-triggered runs (a manual `POST /agent/trigger` for these runners has 501'd since task 3.5,
since that endpoint never created a message for any runner); 3.10 additionally routed job
firing through the same 501-raising function, so as of 3.10 these three runners have **no
Hub-triggered execution path at all over HTTP transport**. Local/git transport is unaffected
(the watchdog's own `_check_jobs`/`_fire_job` "timer duties" still spawn them directly, no Hub
involved). Corrected the module docstring and the 501 detail text to state this accurately.

**Also discovered and documented, not a bug:** `launchability.py`'s `probe_agent()` already
factored pilot mode into its `runnable` field *before this session started* — meaning the
3.10 handoff's claim "the manual-trigger endpoint has never enforced pilot mode" was
incomplete (`trigger_agent_directly()` doesn't say "pilot" literally, but it calls
`probe_agent()`, which does check it). 3.10's `_job_agent_skip_reason` addition still isn't
redundant — it changes a pilot-skipped job's `JobRun.status` to `"skipped"` (not `"failed"`)
and skips wasted work, and its self-registered-poll-agent half is the *only* guard for that
case. Noted in `tasks.md` rather than amending the already-committed 3.10 handoff.

### Live bugs found and fixed before 3.11's own work started

**Bug 1 — double-triggered runs and a Hub message still auto-executing the agent.** The user
reported (verbatim): *"It triggered the agent twice... Also it sent a message via hub. The
message from user is sitting there, and it's triggering the watchdog... why?"*

Root cause: **5 separate `agentweave-watch` processes were running simultaneously**
(PIDs 1892, 21904, 14144, 28572, 25556 — confirmed via
`Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select ProcessId,CommandLine`),
all started between 2026-07-30 19:18 and 2026-08-01 13:19 — every one predates this session's
3.10 fix. Each watchdog has its own independent `known_messages` set, and since each was
running *old* code, each still had the message-auto-trigger logic 3.10 removed — so one Hub
message got picked up and re-triggered independently by every stale process still polling.
This is not a bug in 3.10's code; it's a stale-long-running-process problem, structurally
identical to the stale-static-UI-bundle bug found earlier this session (a running process/
artifact needs an explicit restart/rebuild to pick up source changes — nothing here
hot-reloads).

**Fix applied, with the user's explicit confirmation first:** killed all 5 stale processes
(`taskkill //F //PID <pid>` for each). Attempted to start one fresh watchdog from this repo's
root (`agentweave-watch --auto-ping --retry-after 600`) — **this failed on purpose**: the
command errored immediately with *"--auto-ping without --agent requires an active session.
Run: agentweave init"*, because **this repo root has no `.agentweave/session.json`** — the
actual project the watchdogs were managing is a *different* directory on this machine (some
combination of a `House Manager` project and/or a `claude-smoke-test` temp dir were found via
filesystem search, but neither was confirmed as definitively the live one). **The user was
told to restart their own watchdog from their actual project directory** with the exact
command above; this session did **not** determine or verify that they have done so yet. The
5 stale processes are confirmed dead; a correctly-scoped, freshly-started watchdog is **not
confirmed to exist** as of this handoff.

**Bug 2 (same root cause, separate symptom the user asked about):** *"why do we still need the
watchdog? What does the watchdog even do?"* Answered directly in conversation (not written to
any file until now): after this session's Phase 3 work, the watchdog's only remaining
HTTP-transport duties are context-usage monitoring/posting, compact-decision handling, spec
file syncing, Codex new-session-file handling, and passive message/task notifications (no
longer any triggering). Its local/git-transport job-firing duty is genuinely still load-bearing
there, but is dead weight specifically for this HTTP-transport project. Not acted on — purely
informational, flagged as a bigger architectural question than this session should decide
unilaterally.

## Files touched (task 3.11 only — bug fixes above were process kills, no file changes)

- `hub/hub/launchability.py` — new `resolve_agent_env()` function, placed before
  `get_agent_config()`. Finished.
- `hub/hub/api/v1/agent_trigger.py` — `resolve_agent_env` added to the `launchability` import;
  `trigger_agent_directly()` computes `env` and passes it to `_execute_run`; `_execute_run`
  gained an `env: Optional[Dict[str, str]] = None` parameter, threaded into
  `PtySession.spawn(..., env=env)`; module docstring and the `SUPPORTED_RUNNERS` 501 message
  corrected (see "Found and fixed" above). Reformatted by `black` once. Finished.
- `src/agentweave/cli.py` — `cmd_switch` and `cmd_agent_set_session` each gained an
  `if get_transport().get_transport_type() == "http":` early-return with a steering message.
  `cmd_run` deliberately untouched. Finished.
- `hub/tests/test_launchability.py` — new `TestResolveAgentEnv` class, 6 tests. Finished.
- `hub/tests/test_agent_trigger.py` — new
  `test_trigger_resolves_claude_proxy_env_at_spawn_time`, asserting the real spawn call's
  `env=` kwarg end-to-end. Finished.
- `tests/test_cli.py` — `cmd_agent_set_session`, `cmd_switch` added to the import list; new
  `TestSwitchAndSetSessionRemovedFromHubManagedPath` class, 4 tests (steers to Hub UI under
  http transport; unchanged behavior with no `transport.json`, for both commands). Finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 3.11 checked off with a long
  findings entry (worth reading directly). 3.12 onward still original unstarted text.

**Not touched, pre-existing untracked, not to be modified:** the six `.claude/handoffs/*.md`
files from earlier sessions (listed in every `git status` this session and every prior one).

**Not a file change, but a real system-state change this session made:** 5 stale
`agentweave-watch` processes on this machine were killed. No new watchdog process from this
session is currently running anywhere that this session can confirm.

## Key decisions

1. **`resolve_agent_env` reimplemented in the Hub, not imported from `agentweave.watchdog`.**
   `launchability.py`'s own pre-existing docstring already states this principle for
   `probe_agent`; extended the same reasoning to the new function for consistency and to keep
   the Hub's zero-CLI-dependency property intact for Docker-only deployments.
2. **`cmd_run` left untouched** despite being closely related (it's the CLI command that
   actually launches a `claude_proxy` agent locally using the same env-resolution concept).
   The task's own wording names exactly two commands; `cmd_run` retains real standalone value
   for local/git-transport users with no Hub running at all.
3. **The two live bugs were investigated and fixed *before* starting 3.11's planned work**,
   not deferred — the user reported an actively-broken production-adjacent issue mid-session,
   same judgment call as the stale-UI-bundle fix earlier. *Rejected:* telling the user to wait
   until 3.11 was "done" — the double-trigger was actively confusing their testing right then.
4. **Did not attempt to guess and start a fresh watchdog in the wrong directory.** After the
   first restart attempt correctly failed (no session in this repo root), chose to ask the
   user for the correct directory rather than keep searching the filesystem and potentially
   starting a watchdog against the wrong project (which would create bad/confusing
   `.agentweave/` scaffolding in an unintended location). *Rejected:* continuing to grep the
   filesystem for `.agentweave/session.json` locations and guessing — already tried this twice
   (once via `find`, once via a specific `House Manager` guess) with inconsistent results
   between `find` and `Get-ChildItem`, suggesting the search itself was unreliable.
5. **Pilot mode removal was heard but explicitly deferred, not silently dropped.** The user
   said "I think pilot mode agents are a thing of the past. We can remove that," then
   immediately redirected with "next task" before this session asked any follow-up. Scoping
   pilot-mode removal (touches `Agent.pilot` DB column + migration considerations, the
   `/pilot` API endpoint, `session.get_agent_pilot`/`set_agent_pilot`, this session's own new
   `_job_agent_skip_reason` pilot check from 3.10, `probe_agent`'s pilot check, and whatever UI
   toggle exists) is real, multi-file work that deserves its own explicit go-ahead, not a
   silent bundle-in. Recorded as an explicit open question below so it isn't lost.

## Constraints and user directives (verbatim)

- User, mid-session: **"I think pilot mode agents are a thing of the past. We can remove
  that."** — a real, still-open request, not yet scoped or acted on. See Open Questions.
- User, in response to being asked whether to kill the 5 stale watchdog processes and whether
  they might belong to a different project: **"Kill all of them. Why do we still need the
  watchdog? What does the watchdog even do?"** — confirmed the kill (done); the question was
  answered conversationally (see "Bug 2" above) but not written anywhere durable until this
  handoff.
- User, after the watchdog investigation and this session's proposed pilot-mode-removal
  scoping question: **"next task"** — a clear, explicit instruction to proceed with the
  OpenSpec sequence (3.11) rather than start pilot-mode removal. This is the reason 3.11 was
  worked on and pilot-mode removal was not; do not interpret the earlier pilot-mode comment as
  silently authorizing that work without a fresh go-ahead.
- Carried forward, still in force: **"Yeah and always commit the changes."** — 3.11's 7 files
  committed immediately on completion (`1ef8986`), staged explicitly by path, no fresh ask.
  (The watchdog-process kills were not a code change and were not committed — nothing to
  commit there.)
- Carried forward, still in force (from every prior handoff in this chain): "After every
  threshold of implementation you must run the skill `/handoff`" (this file is that). "Before
  starting a new implementation revise the entire session for the spec" — this task's
  investigation traced through `proposal.md`, `agent_trigger.py`, `launchability.py`,
  `scheduler.py`, and `watchdog.py`'s env-resolution helpers before writing any code, per this
  directive. "let's make sure it works with claude and codex first locally" — Copilot second
  (Copilot's HTTP-transport trigger path is now fully absent per this task's own finding —
  worth remembering this constraint may need revisiting once Copilot support is prioritized).
  Project `CLAUDE.md` rules still apply (never commit `.agentweave/tasks/`, `messages/`,
  `agents/`, `session.json`, `transport.json`; stage explicitly, never `git add -A`).
- Carried forward from 3.8's handoff, applied again for the watchdog kill: **ask before taking
  an action that affects a process/instance the user might be relying on.** Applied here —
  asked before killing the 5 watchdogs, got explicit confirmation, then proceeded.

## Dead ends

- **Locating the "real" project directory the stale watchdogs were managing** — tried `find`
  (returned a `House Manager` directory that a subsequent `ls`/`Get-ChildItem` then reported as
  not existing — inconsistent results, possibly a stale/cached `find` index or a
  since-deleted directory), tried the `claude-smoke-test` temp dir referenced in an earlier
  browser session snapshot (didn't have a `.agentweave/` at all). Abandoned in favor of asking
  the user directly (see Key Decision 4) rather than continuing to search blindly.
- **Restarting a watchdog from the AgentWeave repo root itself** — fails cleanly and
  informatively ("`--auto-ping` without `--agent` requires an active session. Run: `agentweave
  init`"), confirming this repo is not itself a `.agentweave`-managed project the watchdog was
  ever meant to run against. Useful negative information, not a bug.

## Verification

**Ran and passed:**
- `py -m pytest tests/ -q` from `hub/` → 342 passed, 4 skipped (was 335 after 3.10; +7 new
  tests). Same pre-existing CWD-dependent `test_migrations.py` caveat every prior handoff in
  this chain has noted.
- `py -m pytest tests/ -q` from the **repo root** (CLI-side suite) → 995 passed, 4 skipped
  (was 991 after 3.10; +4 new tests).
- `py -m ruff check hub/ tests/` (from `hub/`) → clean.
- `py -m ruff check src/agentweave/cli.py tests/test_cli.py` (from repo root) → clean.
- `py -m black --check hub/ tests/` (from `hub/`) → clean (one file reformatted —
  `agent_trigger.py` — already applied and re-verified).
- `py -m black --check src/agentweave/cli.py tests/test_cli.py` (from repo root) → clean, no
  reformatting needed.
- No frontend changes this task — `tsc`/`vitest`/static-bundle-rebuild were not applicable and
  were not run.
- **`test_agent_trigger.py::test_trigger_resolves_claude_proxy_env_at_spawn_time`** is the
  closest thing to a live-equivalent check this task got: mocks `PtySession.spawn`, sets a
  real `MINIMAX_API_KEY` env var via `monkeypatch.setenv`, triggers a `claude_proxy` agent
  through the real HTTP endpoint, and asserts the mock's actual call arguments contain the
  resolved `ANTHROPIC_API_KEY`/`ANTHROPIC_BASE_URL` — proving the full
  `trigger_agent_directly` → `_execute_run` → `PtySession.spawn(env=...)` wiring is correct,
  without needing a real claude_proxy provider account.

**NOT tested this session:**
- **No live verification against the actual running dev Hub for 3.11** — that instance
  (PID 22636, still up, confirmed via `netstat` at the end of this chunk) has been running
  since before task 3.9 and would need a restart to pick up 3.9/3.10/3.11's combined code
  changes. Deliberately not restarted this time (see Key Decision 3's precedent from 3.9/3.10,
  applied again) — not asked this session, so **if the user wants to see 3.9/3.10/3.11's
  effects live in the real Hub UI, it needs a restart first**, and per the standing
  precedent, ask before doing that restart since it's the same instance the user tested 3.10
  against directly.
- **Whether the user has actually restarted their watchdog** from the correct project
  directory — not confirmed. The double-trigger bug is fixed at the *code* level (3.10, already
  shipped) but will keep recurring in practice until a correctly-scoped, freshly-started
  watchdog process is actually running.
- A real `claude_proxy` (Minimax/GLM) agent triggered end-to-end through a live Hub with a
  real API key — the integration test above proves the wiring, not an actual successful proxy
  API call.
- Nothing from 3.12 (ship `alembic.ini` in package-data) onward was started or touched.
- Pilot mode removal — not started at all, deliberately deferred (see Open Questions).

## Git state

- Branch `hub-native-experience`, **HEAD `1ef8986`** — task 3.11's 7 files committed this
  chunk ("Complete Phase 3 task 3.11: resolve provider env/session in the Hub, not the CLI"),
  on top of `fa8bc1c` (the 3.10 handoff-tracking commit).
- Working tree clean except the six pre-existing untracked `.claude/handoffs/*.md` files from
  earlier sessions (unrelated) plus this new handoff file and `LATEST.md`'s pointer update —
  committed in a separate follow-up commit after this file is finalized, matching the chain's
  established two-commit-per-checkpoint pattern.
- No upstream configured — nothing pushed, not requested, unchanged from every prior handoff.
- **Live process state (not git, but load-bearing context):** the dev Hub uvicorn process
  (PID 22636) is still running, stale relative to 3.9/3.10/3.11. Zero `agentweave-watch`
  processes are confirmed running anywhere on this machine as of this handoff — the 5 stale
  ones were killed, and whether the user started a fresh one from their real project directory
  is unknown.

## Next steps

1. **Ask the user, at the start of the next session, whether they restarted their watchdog**
   from the correct project directory, and whether they want the dev Hub restarted to pick up
   3.9/3.10/3.11's combined changes (asking first, per established precedent).
2. **Resolve the pilot-mode-removal open question** (below) before doing any further Phase 3
   task work that touches pilot mode, `Agent.pilot`, or `_job_agent_skip_reason` — don't let
   3.10's pilot-skip code become stale/contradictory with a half-finished removal.
3. **Read `tasks.md`'s 3.12 entry**: "Ship `alembic.ini` in `package-data` — a pip install
   currently logs *'alembic.ini not found … skipping migrations'* and runs unmigrated." This
   is a packaging/build-config task (likely `pyproject.toml`'s `package-data`/`MANIFEST.in`
   entries for the Hub's distributable package), a different shape of work than 3.6–3.11 —
   not yet investigated at all this session.
4. Per the standing directive, **commit 3.12's changes on completion without waiting for a
   fresh ask** — staged explicitly by path, same as every task in this chain so far.
5. **This session's context is very long** (six substantial tasks: 3.6, 3.7, 3.8, 3.9, 3.10,
   3.11, plus two live bug investigations). Strongly consider starting the next session fresh
   via `/resume` rather than continuing in this same window, even more so than usual — this
   handoff is deliberately thorough to make that safe.

## Open questions for the user

- **New, unresolved, the user's own request: remove pilot mode entirely.** Verbatim: "I think
  pilot mode agents are a thing of the past. We can remove that." Not scoped or started. A
  real, multi-file removal if pursued — touches (at least): `hub/hub/db/models.py`'s
  `Agent.pilot` column (would a migration need to *drop* it, or is leaving an unused nullable
  column acceptable?), `hub/hub/api/v1/agents.py`'s `POST /{name}/pilot` endpoint and
  `register-session`'s pilot-setting behavior, `hub/hub/launchability.py`'s `probe_agent()`
  pilot check, `hub/hub/scheduler.py`'s `_job_agent_skip_reason()` (this session's own 3.10
  addition), `session.get_agent_pilot`/`set_agent_pilot` CLI-side, and whatever Hub UI element
  currently toggles it (not located this session). **Needs an explicit go-ahead and scope
  confirmation before starting** — the user redirected to "next task" immediately after
  raising it, so treat it as heard-but-not-yet-authorized, not silently dropped.
- Carried forward, unresolved, not urgent: should anything be pushed to a remote at this
  point? No remote/upstream is configured for this branch.
- Carried forward from 3.5–3.10, still not resolved: the "ability to question the user"
  comment from an earlier T3-parity discussion — confirm whether the user meant AgentWeave's
  existing `ask_user`/Questions-panel mechanism (unaffected by anything in Phase 3 so far) or
  something else.
- Carried forward from 3.8/3.9/3.10, still open: task 3.20 ("Stop the Hub silently serving a
  stale UI"). Not touched this chunk since 3.11 had no frontend changes, so the bundle didn't
  go stale again this time — but it will the next time any frontend-touching task lands.
- **New, arguably urgent: does the user have a working watchdog running right now?** Not
  confirmed. If not, scheduled/local-transport job behavior and context-usage syncing are
  currently not happening at all for their actual project.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 3.11's entry is long; read
  it directly. 3.12 onward is still the original unstarted task text.
- `hub/hub/launchability.py` — this chunk's `resolve_agent_env()`, alongside the pre-existing
  `probe_agent()` (which already checked pilot mode before this session — relevant to the
  pilot-removal open question).
- `hub/hub/api/v1/agent_trigger.py` — `trigger_agent_directly()`/`_execute_run()`'s env
  threading; also the corrected module docstring/501 message re: unsupported runners.
- `src/agentweave/cli.py` — `cmd_switch`/`cmd_agent_set_session`'s new http-transport
  early-returns; `cmd_run` nearby, deliberately untouched, worth a fresh look if pilot-mode
  removal or a future task decides to extend the same treatment to it.
- `hub/hub/db/models.py` — `Agent.pilot` (line ~51) — the column at the center of the
  pilot-mode-removal open question, if that work gets a go-ahead next.
