# Handoff: Phase 3 task 3.10 complete (scheduled jobs route through direct execution)

**Date:** 2026-08-01T16:45:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `2c99bf1`
**Agent:** Claude Code / Sonnet 5 (1M context)
**Previous handoff:** `.claude/handoffs/2026-08-01-1545-hub-native-phase3-t3-9-complete.md`
**Status:** chunk complete — session end.

## Goal

Rebuild the AgentWeave Hub into a local-first application that owns agent execution directly
(the `hub-native-experience` OpenSpec change). Phase 3 ("Native runtime, packaging, and crash
recovery") is in progress; 3.1–3.9 were done entering this session (all in this same
continuous session — see the chain of prior handoffs). This session did task 3.10: "Route
scheduled jobs through the direct execution path; remove the watchdog's message-scanning
trigger branch, keeping only timer duties." Full reasoning lives in
`openspec/changes/2026-07-30-hub-native-experience/` (`proposal.md`, `design.md`, `tasks.md`).

## Current state

**Task 3.10 is complete, tested, and committed at `2c99bf1`. First task in this session's
chain to touch both the Hub (`hub/`) and the CLI (`src/agentweave/`) sides of the repo.**

### What changed and why

Before this task, there were **two different trigger protocols** for getting an agent to
actually run, depending on who initiated it:
- **Manual trigger** (`POST /agent/trigger`): already fixed in task 3.5 — spawns the agent
  directly via `PtySession`, no message, no watchdog involvement.
- **Scheduled job fire** (`hub/hub/scheduler.py`'s APScheduler cron callback, or the manual
  "run now" button): still used the *old* protocol — wrote a synthetic `Message` row
  (`sender="user"`, `[Session: <id>]`/`[NewSession]` as literal text in the body), and relied
  on the CLI-side watchdog polling the Hub over HTTP, scanning for `sender == "user"`
  messages, and calling `_trigger_agent_from_message()` to parse the tags back out and spawn
  the CLI itself. This is the exact indirection `proposal.md`'s finding #3 already fixed for
  manual triggers — jobs just hadn't caught up yet.

This task closed that gap:

1. **Extracted `trigger_agent_directly()`** from `agent_trigger.py`'s `trigger_agent()` route
   handler — same validation, same spawn logic, same `Run` row creation, just factored out of
   the FastAPI-specific route function so it has no request/response coupling. Raises a new
   `TriggerAgentError(status_code, detail)` instead of `HTTPException`. The route itself is now
   a ~10-line wrapper: call the function, catch `TriggerAgentError`, re-raise as
   `HTTPException`. Existing `/trigger` behavior is unchanged (verified — all its existing
   tests still pass unmodified).

2. **`scheduler.py`'s `_do_fire_job()` rewritten** to call `trigger_agent_directly()` instead
   of creating a `Message`. New `_job_agent_skip_reason()` helper ports two guards the removed
   watchdog function used to enforce — pilot mode, self-registered poll-mode agents — by
   querying the Hub's own `Agent` table (`pilot`/`self_registered`/`contact_mode` columns)
   directly, instead of the CLI's `session.json`. **Deliberately not added to
   `trigger_agent_directly()` itself** — that function also backs the manual-trigger endpoint,
   which has never enforced either guard, and adding them there would silently change manual
   trigger behavior too (nothing asked for that).

3. **`JobRun.status` gained a third value: `"skipped"`** (model comment previously said only
   `"fired"`/`"failed"` are used). A job skipped for pilot/poll reasons is not a failure —
   conflating the two would misreport *why* nothing ran. No schema/migration change (`status`
   is already a plain `String` column).

4. **Adjacent bug found and fixed in `jobs.py`'s `POST /{job_id}/run`**: it used to treat *any*
   non-`True` return from `_do_fire_job` as a generic 500 "Failed to fire job" and additionally
   persisted its own duplicate `job_run_failed` event on top of the one `_do_fire_job` already
   persists internally. Once `"skipped"` became a real outcome, this would have surfaced a
   pilot-mode agent's manual "run now" click as a confusing server error instead of the correct
   "this was deliberately skipped" message. Fixed: the endpoint now reads back the just-written
   `JobRun` row's actual `status` (409 for `"skipped"`, 500 only for a genuine `"failed"`) and
   no longer duplicates the persist call.

5. **Watchdog side**: removed the `if sender == "user" and ...:
   self._trigger_agent_from_message(recipient, msg)` block from `_check_once_http()`, and
   deleted `_trigger_agent_from_message()` itself (147 lines) — confirmed via grep it had
   exactly one call site before removal, and no other references anywhere in the repo.
   `_check_jobs()`/`_fire_job()`/`_run_agent_subprocess()` — the local/git-transport "timer
   duties" the task's own wording says to *keep* — are untouched; confirmed by reading
   `_check_once_local` first: `_check_jobs()` is gated on `transport_type in ("local", "git")`
   only and never routed through the removed function.

## Files touched

- `hub/hub/api/v1/agent_trigger.py` — `trigger_agent()`'s body extracted into new
  `trigger_agent_directly()`; new `TriggerAgentError` exception class; route reduced to a thin
  wrapper. Reformatted by `black` once. Finished.
- `hub/hub/scheduler.py` — `Agent` added to the `db.models` import; new
  `_job_agent_skip_reason()` helper; `_do_fire_job()` rewritten to call
  `trigger_agent_directly()`, handle `TriggerAgentError` (→ `"failed"`) and skip-reason (→
  `"skipped"`) as distinct `JobRun` outcomes instead of assuming success; `_fire_job_internal`'s
  stale docstring (still said "create message for watchdog to pick up") corrected. Finished.
- `hub/hub/api/v1/jobs.py` — `run_job()`'s `not success` branch rewritten to read back the
  `JobRun`'s actual status and return 409 (skipped) vs 500 (failed) with the real
  `error_summary`, instead of always 500 with a generic message and a duplicate persisted
  event. Finished.
- `hub/ui/src/components/jobs/JobCard.tsx` — `RunHistory`'s icon/color ternaries extended with
  a `"skipped"` branch (amber `pause` icon, matching the "deliberate, not a failure" amber
  convention this session established for `run_stopped`); `error_summary` display condition
  extended to also show for `"skipped"` runs (previously only shown for `"failed"`). Finished.
- `src/agentweave/watchdog.py` — removed the 4-line auto-trigger block from
  `_check_once_http()`; deleted `_trigger_agent_from_message()` (was lines 1025–1171, 147
  lines). Finished.
- `tests/test_watchdog_pilot.py` — **deleted entirely** (all 3 tests exercised the removed
  method directly).
- `tests/test_watchdog_self_registered.py` — 2 of 3 tests (which also called the removed
  method) deleted; the third (`test_watchdog_job_skips_self_registered_poll_agent`, testing
  `_fire_job`'s own separate local/git-transport guard, untouched by this task) kept and still
  passes; file docstring added explaining the split and pointing to
  `hub/tests/test_scheduler.py` for the Hub-side equivalents. Finished.
- `hub/tests/test_scheduler.py` — **new file**, 5 tests (see Verification below). Finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 3.10 checked off with a long
  findings entry (worth reading directly). 3.11 onward still original unstarted text.
- `hub/hub/static/ui/` (bundle assets + `index.html`) — rebuilt and redeployed once more this
  session (third time total — after 3.7's original stale-bundle bug, after 3.8's frontend
  changes, and now after `JobCard.tsx`), so the served bundle doesn't go stale again
  immediately. Folded into this task's own commit.

**Not touched, pre-existing untracked, not to be modified:** the six `.claude/handoffs/*.md`
files from earlier sessions (listed in every `git status` this session and every prior one).

## Key decisions

1. **Pilot-mode and self-registered-poll guards ported to a new Hub-side check
   (`_job_agent_skip_reason`), not added to the shared `trigger_agent_directly()`.** The
   latter also backs the already-shipped manual-trigger endpoint, which has never enforced
   either guard (confirmed by reading the pre-3.10 `trigger_agent()` body — no pilot check
   existed there at all). Adding the checks to the shared function would have silently changed
   manual-trigger semantics too, which is a bigger behavior change than this task asked for.
   *Rejected:* adding the guards to `trigger_agent_directly()` — simpler code, but expands
   scope beyond "route scheduled jobs" into "also start enforcing pilot mode on manual
   triggers," a separate decision nobody made.
2. **`JobRun.status` extended with `"skipped"` rather than reusing `"failed"`.** A deliberate,
   correct decision not to run a pilot-controlled agent is a fundamentally different fact than
   "an attempt was made and it broke" — conflating them would make the job's run history
   actively misleading. No schema migration needed since `status` was always an untyped
   `String` column with only an informal two-value comment, not an enum.
3. **Fixed `jobs.py`'s `run_job()` double-persist-on-failure bug and its `"skipped"`-as-500
   consequence in the same task, not filed separately.** This wasn't a pre-existing bug this
   task merely surfaced coincidentally — extending `_do_fire_job`'s outcome space from
   two-valued to three-valued directly *created* a new, concrete, user-visible misbehavior
   (pilot-agent "run now" → confusing 500) if `run_job()` were left as-is. Fixing the call site
   that consumes an outcome you just changed the shape of is normal scope for that change, not
   an unrelated cleanup.
4. **Live verification for this task relied entirely on the automated test suite, not a
   dev-Hub restart** — a deliberate departure from 3.7/3.8's "restart the real Hub and watch it
   happen" pattern (matching 3.9's earlier departure for the same underlying reason).
   `test_scheduler.py`'s tests call `JobScheduler._fire_job_internal` directly — the exact
   method both the real APScheduler cron callback and the manual "run now" HTTP endpoint
   actually invoke — using the same mocked-`PtySession.spawn` pattern already live-verified for
   the manual trigger endpoint back in task 3.5. Judged sufficient given how directly the tests
   exercise the real call graph, and the user wasn't asked this time since no live instance
   needed to be touched at all.
5. **No `JobRun`↔`Run` schema link added.** A fired job's `JobRun` row (job-specific fire
   history) and the `Run` row `trigger_agent_directly()` actually creates (task 3.3's general
   agent-process-run table) remain two separately-queryable records with no FK between them —
   cross-referencing a job's fire history with its run's live output/exit code still needs two
   lookups by agent+time, not one join. *Rejected:* adding a `JobRun.run_id` column — genuinely
   useful, but this task's own wording is about the *trigger mechanism*, not job/run
   observability parity; a schema change wasn't asked for and would need its own migration.

## Constraints and user directives (verbatim)

- User said **"keep going"** after this session's summary of 3.9 + the earlier stale-UI fix —
  confirms the sequence-following default (3.10 next, per `tasks.md`'s own order), not a
  detour into task 3.20 (stale UI) despite that being flagged as an open question in the 3.8/3.9
  handoffs.
- Carried forward, still in force: **"Yeah and always commit the changes."** — 3.10's 11 files
  committed immediately on completion (`2c99bf1`), staged explicitly by path, no fresh ask.
- Carried forward, still in force (from every prior handoff in this chain): "After every
  threshold of implementation you must run the skill `/handoff`" (this file is that). "Before
  starting a new implementation revise the entire session for the spec" — followed unusually
  literally this session: re-read `proposal.md`'s "Why" section in full (not just excerpts) and
  the current `watchdog.py`/`scheduler.py` code before touching anything, per the 3.9 handoff's
  own explicit recommendation to do this seriously for 3.10 specifically, since it was the
  first task to cross the CLI/Hub boundary. "let's make sure it works with claude and codex
  first locally" — Copilot second (unaffected by this session). Project `CLAUDE.md` rules still
  apply (never commit `.agentweave/tasks/`, `messages/`, `agents/`, `session.json`,
  `transport.json`; stage explicitly, never `git add -A`).
- **Carried forward from 3.9's handoff, as a concrete precedent, applied again this
  session:** when a task's real behavior can be fully exercised through the exact call graph a
  live restart would exercise, prefer that over restarting an instance the user might be
  actively using. Applied here identically to how 3.9 applied it.

## Dead ends

- **Considered whether `run_job()`'s 500-vs-409 distinction needed the endpoint to persist its
  own event** — it doesn't, and the old code's attempt to do so was itself the bug (a
  duplicate of what `_do_fire_job` already records). Realized this by tracing exactly what
  `_fire_job_internal` → `_do_fire_job` already persists on every path before touching
  `jobs.py` at all, not by trial and error.
- **Considered adding a `JobRun.run_id` FK to link job fires to their actual `Run`** — see Key
  Decision 5. Not pursued; would need a migration and isn't what this task's wording asks for.
- No other notable dead ends this task — the CLI/Hub boundary crossing that the 3.9 handoff
  flagged as the main risk turned out to be clean: `_trigger_agent_from_message` had exactly
  one call site, and the two watchdog test files that needed trimming were both quick, low-risk
  edits once the removed method's obsolescence was confirmed via grep.

## Verification

**Ran and passed:**
- `py -m pytest tests/ -q` from `hub/` → 335 passed, 4 skipped (was 330 after 3.9; +5 new
  tests, all in `test_scheduler.py`). Same pre-existing CWD-dependent `test_migrations.py`
  caveat every prior handoff in this chain has noted.
- `py -m pytest tests/ -q` from the **repo root** (the CLI-side suite, not `hub/tests/`) → 991
  passed, 4 skipped. 5 tests removed this task (3 in the deleted `test_watchdog_pilot.py`, 2 of
  3 in `test_watchdog_self_registered.py`) — not replaced 1:1 since their Hub-side equivalents
  in `hub/tests/test_scheduler.py` cover the same guards more directly, against real DB state
  rather than mocked watchdog internals.
- `py -m ruff check hub/ tests/` (from `hub/`) → clean (one import-sort auto-fix in the new
  test file, already applied and re-verified).
- `py -m ruff check src/agentweave/watchdog.py tests/test_watchdog_self_registered.py` (from
  repo root) → clean.
- `py -m black --check hub/ tests/` (from `hub/`) → clean (two files reformatted —
  `test_scheduler.py` and `agent_trigger.py` — already applied and re-verified).
- `py -m black --check src/agentweave/watchdog.py tests/test_watchdog_self_registered.py`
  (from repo root) → clean, no reformatting needed.
- `npx tsc --noEmit` (in `hub/ui/`) → clean, no type errors.
- `npx vitest run` (in `hub/ui/`) → 196 passed (unchanged count — `JobCard.tsx` had no
  dedicated test before or after, so this was a change with no test surface to update).
- **`hub/tests/test_scheduler.py`'s 5 new tests**, in detail — this *is* the live-equivalent
  verification for this task (see Key Decision 4):
  1. `test_fired_job_creates_a_run_via_direct_execution_not_a_message` — fires a job with a
     mocked `PtySession.spawn` (same pattern as every prior task's tests), awaits the
     background run, then asserts directly against the DB: exactly one `Run` row exists with
     `status="completed"`, and — the core architectural claim of this task — **zero** `Message`
     rows exist for that agent.
  2. `test_job_for_pilot_agent_is_skipped_not_fired` — a real `Agent` row with `pilot=True`;
     asserts the resulting `JobRun.status == "skipped"` with `"pilot"` in the reason, and that
     no `Run` row was created at all (the agent was genuinely never spawned).
  3. `test_job_for_self_registered_poll_agent_is_skipped` — same shape, for
     `self_registered=True, contact_mode="poll"`.
  4. `test_job_fire_failure_is_recorded_with_the_real_reason` — a same-agent `Run` row already
     `"running"` (deterministic 409 trigger, no CLI-availability mocking needed); asserts
     `JobRun.status == "failed"` with the actual `"already has a run in progress"` detail, not
     a generic message.
  5. `test_run_job_endpoint_returns_409_for_a_skipped_pilot_agent` — drives the real
     `POST /jobs/{id}/run` HTTP endpoint (injecting a `JobScheduler()` instance into the module
     global since the test harness's `app` fixture bypasses FastAPI's lifespan and never runs
     `init_scheduler()`), asserting the HTTP-level 409 fix from Key Decision 3/`jobs.py`.

**NOT tested this session:**
- The real APScheduler cron-matching itself (whether a given cron expression actually fires at
  the right wall-clock time) — untouched by this task, third-party library code, not
  re-verified.
- A live restart of the actual dev Hub exercising a *real* scheduled cron firing end-to-end —
  deliberately not done (see Key Decision 4); the automated tests call the identical function
  the real cron callback calls, one layer up from "did APScheduler decide to fire," which
  itself is unchanged.
- The frontend `JobCard.tsx` "skipped" styling was not visually confirmed in a browser this
  session (unlike 3.6/3.7/3.8's browser-driven Activity-tab verifications) — `tsc`/`vitest`
  confirm it compiles and doesn't break existing behavior, but no live click-through was done.
- Kimi/OpenCode/Copilot — still out of scope (watchdog local/git "timer duties" path, entirely
  unaffected by this task, not re-verified).
- Nothing from 3.11 (remove `agentweave switch`/`agent set-session` from the Hub-managed path)
  or anything past it was started or touched.

## Git state

- Branch `hub-native-experience`, **HEAD `2c99bf1`** — task 3.10's 11 files committed this
  session ("Complete Phase 3 task 3.10: route scheduled jobs through direct execution"), on
  top of `9a9a0d6` (the 3.9 handoff-tracking commit).
- Working tree clean except the six pre-existing untracked `.claude/handoffs/*.md` files from
  earlier sessions (unrelated) plus this new handoff file and `LATEST.md`'s pointer update —
  committed in a separate follow-up commit after this file is finalized, matching the chain's
  established two-commit-per-checkpoint pattern.
- No upstream configured — nothing pushed, not requested, unchanged from every prior handoff.

## Next steps

1. **Read `tasks.md`'s 3.11 entry in full before starting**: "Remove `agentweave switch` and
   `agentweave agent set-session` from the Hub-managed path; resolve provider environment and
   session continuity inside the Hub." This is proposal.md's complaint #2 ("Connecting an agent
   is manual") — a different kind of task again: removing CLI ceremony commands from the
   *supported* path for Hub-managed agents (per `proposal.md`: "Manual connection ceremony —
   `switch`, `eval $(…)`, `agent set-session` — is removed from the supported path for
   Hub-managed agents"), likely another CLI+Hub-crossing task like 3.10 was.
2. Locate `agentweave switch`'s implementation (`src/agentweave/cli.py`, per `proposal.md`'s
   own citation: "prints a command for the operator to copy and paste
   (`src/agentweave/cli.py:5128-5139`)") and `agent set-session` similarly — not investigated
   at all this session.
3. "Resolve provider environment and session continuity inside the Hub" suggests the Hub needs
   to take over env-var resolution (currently done via `eval $(agentweave switch <agent>)`,
   shell-side) and session-ID tracking (currently `agent set-session`, also CLI-side) — likely
   touches `hub/hub/launchability.py`'s `get_agent_config`/`probe_agent` (already the Hub's
   existing per-agent config resolution point, used throughout this session's `agent_trigger.py`
   work) and possibly needs new Hub-side state for "current session per agent," which may
   already partly exist via `Run.session_id`/`AgentOutput.session_id` from earlier tasks — check
   before building something new.
4. Per the standing directive, **commit 3.11's changes on completion without waiting for a
   fresh ask** — staged explicitly by path, same as every task in this chain so far.
5. **Rebuild and redeploy `hub/hub/static/ui/` again after any frontend changes** — task 3.20
   (stale-UI staleness) is still unfixed; this remains a required manual step until it's
   actually fixed systemically. Check `git diff --stat` against `hub/ui/src/` before finishing
   any future task to know whether this step applies.

## Open questions for the user

- Carried forward, unresolved, not urgent: should anything be pushed to a remote at this point?
  No remote/upstream is configured for this branch.
- Carried forward from 3.5–3.9, still not resolved: the "ability to question the user" comment
  from an earlier T3-parity discussion — confirm whether the user meant AgentWeave's existing
  `ask_user`/Questions-panel mechanism (unaffected by anything in Phase 3 so far) or something
  else.
- Carried forward from 3.8/3.9, still open, now further compounded: task 3.20 ("Stop the Hub
  silently serving a stale UI") — this is the **third** time this session a frontend change
  required a manual rebuild-and-copy to avoid re-introducing the exact bug the user reported
  earlier. The user chose to keep going in sequence rather than prioritize 3.20 when last asked
  — worth re-raising now that it's recurred twice more since that answer, purely as a "still
  true, getting more expensive to keep doing manually" data point, not to relitigate the
  decision.
- New this session: task 3.10's own text didn't mention job/run observability (linking `JobRun`
  to the `Run` it creates), but Key Decision 5 above notes the gap is now slightly more visible
  since jobs finally produce real `Run` rows worth linking to. Not urgent, but worth surfacing
  as a candidate for a future task if the user wants richer job-run drill-down in the UI.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 3.10's entry is very long;
  read it directly. 3.11's entry is short but, like 3.10, likely bigger than its one-line text
  suggests — read `proposal.md`'s complaint #2 section too before starting (cited above).
- `src/agentweave/cli.py` — `agentweave switch`'s implementation (proposal.md cites
  `:5128-5139`) and wherever `agent set-session` lives; entirely unread this session, first
  target for 3.11.
- `hub/hub/launchability.py` — `get_agent_config`/`probe_agent`, the Hub's existing per-agent
  config resolution point; 3.11's "resolve provider environment ... inside the Hub" will likely
  extend this.
- `hub/hub/api/v1/agent_trigger.py` — this session's `trigger_agent_directly()` is the shared
  core both manual and job triggers now use; 3.11 may need to touch how it resolves env vars
  per-agent, since that's currently sourced from `config.get(...)` via `get_agent_config`, not
  from anything `switch`/`eval $(...)` currently sets up.
- `hub/hub/scheduler.py` — this session's `_job_agent_skip_reason()`/rewritten `_do_fire_job()`;
  not directly relevant to 3.11 but the most recently-modified file in this chain, worth a
  fresh read if 3.11 turns out to touch job-triggered session continuity too.
