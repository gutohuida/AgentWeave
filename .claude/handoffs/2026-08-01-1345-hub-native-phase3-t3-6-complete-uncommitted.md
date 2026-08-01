# Handoff: Phase 3 task 3.6 complete (run-lifecycle SSE events); committed

**Date:** 2026-08-01T13:45:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `937702f`
**Agent:** Claude Code / Sonnet 5 (1M context)
**Previous handoff:** `.claude/handoffs/2026-08-01-1111-hub-native-phase3-t1-5-complete.md`
**Status:** chunk complete — session end. The commit-policy question this handoff originally
raised was answered by the user before this file was finalized: **"Yeah and always commit the
changes."** 3.6's changes are committed at `937702f`; the standing directive is recorded below
and this is no longer an open question.

## Goal

Rebuild the AgentWeave Hub into a local-first application that owns agent execution directly
(the `hub-native-experience` OpenSpec change). Phase 3 ("Native runtime, packaging, and crash
recovery") is in progress; 3.1–3.5 were done entering this session. This session did task 3.6:
"Emit run lifecycle and output events on the SSE channel; render them in the agent view."
Full reasoning lives in `openspec/changes/2026-07-30-hub-native-experience/` (`proposal.md`,
`design.md`, `tasks.md`).

## Current state

**Task 3.6 is functionally complete and live-verified, but not committed.** Three typed SSE
events (`run_started`, `run_completed`, `run_failed`) now fire from
`hub/hub/api/v1/agent_trigger.py`'s new `_broadcast_run_lifecycle()` helper — persisted to
`EventLog` (so `GET /api/v1/agents/{name}/timeline` picks them up) and broadcast over SSE (so
the frontend gets them live), following the same persist+broadcast pattern
`context_warning` already used. `run_started` fires once the PTY spawn succeeds (pid recorded);
`run_failed` fires both on spawn-time `FileNotFoundError` and on nonzero exit; `run_completed`
fires only on exit 0. The existing plain-text `agent_output`/`kind="status"` stopgap broadcast
from 3.5 is **kept alongside**, unchanged — `AgentOutputPanel.tsx`'s Handoff-completion
detection depends on it (`kind==="status" && payload.phase==="completed"` scanned out of
`useAgentOutput`'s `lines`), and removing it would have silently broken that feature.

**A second, unplanned, more consequential bug was found and fixed in the same task**, via the
same "verify against the real running Hub" discipline the 3.4/3.5 handoffs already flagged as
a recurring pattern in this codebase: a Hub direct-spawn run never posts an `AgentHeartbeat`
(that's the watchdog's mechanism, unused by this path), and `GET /api/v1/agents`'s `status`
field (`hub/hub/api/v1/agents.py`'s `list_agents()`) was computed from heartbeats only
(`effective_heartbeat_status`) — so a live direct-spawn run was invisible as "running"
*everywhere* the UI reads `agent.status`: the AgentCard badge, the Overview page, and
`AgentOutputPanel.tsx`'s `isRunning` gate (message box lock + pulsing badge). Confirmed live
before fixing: triggered a run, polled `GET /api/v1/agents` mid-run, got `"status":"idle"` the
whole time while output was actively streaming. Fixed by bulk-fetching agents with an active
(`status="running"`) `Run` row in `list_agents()` and overriding `effective_status` to
`"running"` for them — Run-table state now takes precedence over heartbeat state (strictly more
current for a direct-spawn agent). Live-verified after the fix: `"running"` mid-run, `"idle"`
immediately after. Without this, 3.6's "render lifecycle events in the agent view" would have
had no visible effect on the one piece of UI users actually look at to answer "is this agent
busy right now."

**Frontend wiring:** `useSSE.ts`'s `SSE_EVENT_TYPES` allowlist extended with the three new
event names (the "broadcast but not allowlisted → silently dropped" bug class the Phase-2
handoffs flagged twice — checked explicitly this time) plus an `invalidateQueries(['agents'])`
case so the status-badge fix reaches the UI live. `agents.ts`'s `eventBelongsToTimeline()`
extended for the same three events so the Activity tab's timeline query invalidates live too —
**this incidentally fixes the same live-update gap for 3.5's pre-existing
`run_triggered`/`run_completed` EventLog rows**, which had been silently only-visible-on-poll
since 3.5 landed (they're written via `persist_event` directly, never through the
CLI→Hub log-bridge endpoint that's the only other thing broadcasting the `log_event` SSE type
the timeline previously watched for). `AgentActivityTab.tsx`'s event-timeline row (previously
one fixed blue treatment for every `EventLog`-sourced entry, regardless of type) now colors
`run_failed` red, `run_completed` green, `run_started` blue, with matching icons. Backend's
`agent_timeline()` got a small `_run_lifecycle_summary()` helper so these three types render as
"Run started (claude)" / "Run completed (exit 0)" / "Run failed: <error>" instead of the bare
enum string every other timeline entry falls back to.

## Files touched

- `hub/hub/api/v1/agent_trigger.py` — added `_RUN_LIFECYCLE_EVENTS` tuple and
  `_broadcast_run_lifecycle()` helper; wired three call sites (`run_started` after pid assign,
  `run_failed` on `FileNotFoundError`, `run_completed`/`run_failed` at completion based on exit
  code). Finished.
- `hub/hub/api/v1/agents.py` — imported `Run`; added a bulk `running_run_q` fetch of agent
  names with an active `Run` row; `effective_status` overridden to `"running"` for those agents
  in `list_agents()`'s per-agent loop; added `_run_lifecycle_summary()` helper and wired it into
  `agent_timeline()`'s `EventLog`-row summary. Finished.
- `hub/ui/src/hooks/useSSE.ts` — three new entries in `SSE_EVENT_TYPES`; new `case` block
  invalidating `['agents']` for the three run-lifecycle events. Finished.
- `hub/ui/src/api/agents.ts` — `eventBelongsToTimeline()` extended with the three run-lifecycle
  event types (agent-name-matched, same as `log_event`/`agent_heartbeat`). Finished.
- `hub/ui/src/components/agents/AgentActivityTab.tsx` — `ActivityRow`'s `item.type === 'event'`
  branch: added `eventColor`/`eventBg`/`eventIcon` derivation by `item.eventType`, replacing the
  single hardcoded blue treatment. Finished. (Icon names verified against
  `hub/ui/src/components/common/Icon.tsx`'s lucide-react map before use — `play_circle` does
  NOT exist there, used `play_arrow` instead; confirmed via that file's silent-`null`-on-
  unmapped-name fallback, which would have made the `run_started` icon invisible with no error.)
- `hub/tests/test_agent_trigger.py` — added `import json`, `from hub.sse import sse_manager`,
  a `_drain()` helper, and 3 new tests: successful-run started+completed broadcast assertions
  (subscribes via `sse_manager.subscribe()`, drains the queue, checks payload fields and
  EventLog rows), nonzero-exit → `run_failed` not `run_completed`, spawn-failure →
  `run_failed`. Finished. (Reformatted by `black` after initial write — already accounted for.)
- `hub/tests/test_agents.py` — added `test_list_agents_shows_running_for_active_direct_spawn_run`
  (inserts a `Run` row with `status="running"` and zero heartbeat rows, asserts `GET
  /api/v1/agents` reports `"running"`). Finished.
- `hub/ui/src/__tests__/useSSE.test.tsx` — added a test mirroring the existing
  `job_created`/etc. allowlist test, for the three new run-lifecycle event types. Finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 3.6 checked off with a long
  findings entry (worth reading directly). 3.7 onward still original unstarted text.

**Not touched, pre-existing untracked, not to be modified:** the six `.claude/handoffs/*.md`
files from earlier sessions (listed in every `git status` this session), same as prior
handoffs note.

## Key decisions

1. **New typed events are additive, not a replacement for 3.5's `agent_output`/`kind="status"`
   stopgap.** The prior handoff explicitly flagged this as an undecided fork; resolved this
   session in favor of "kept alongside" because `AgentOutputPanel.tsx`'s Handoff feature
   depends on the stopgap's exact shape and removing it would be a silent regression to a
   working, tested feature. *Rejected:* replacing the stopgap entirely (simpler, but breaks
   Handoff without a compensating change to that feature, which was out of scope here).
2. **Fixed `effective_status`'s heartbeat-only blind spot for direct-spawn runs**, even though
   3.6's own task text doesn't mention it. Justified because without it, the task's own stated
   goal ("render [lifecycle events] in the agent view") would be unverifiable/pointless for the
   most visible piece of UI (the status badge) — found by literally trying to answer "is this
   agent busy" against the real running Hub, not by reading the spec. *Rejected:* scoping this
   out as "not literally asked for" — the fix is small, mechanical, and the bug it fixes was
   directly created by 3.5's own work (a direct-spawn agent that never posts heartbeats).
3. **`run_started` fires after PTY spawn succeeds (pid assigned), not at trigger-accept time.**
   `run_triggered` (already emitted by 3.5) already covers "a trigger request was accepted";
   `run_started` specifically means "a process now actually exists," which is the more useful
   signal for "is this agent doing something" UI.
4. **Persist+broadcast is one helper (`_broadcast_run_lifecycle`), not duplicated three times**
   — mirrors the existing `context_warning` pattern in `output_recording.py`'s
   `record_context_usage`, not a new pattern.
5. **`eventBelongsToTimeline()`'s fix for the three new events also fixes the same live-update
   gap for 3.5's pre-existing `run_triggered`/`run_completed` rows**, discovered as a side
   effect while implementing 3.6, not asked for separately — a small, safe, same-shaped fix
   left in rather than filed away for later, since fixing it for the new events and not the old
   ones in the exact same function would have been a stranger diff.

## Constraints and user directives (verbatim)

- **New standing directive from this session, to be carried in every future handoff:**
  *"One more work directive to be recorder[sic]. At resume (should write this on the handoff)
  verify the previous work done."* — i.e. a resumed session must not just trust a handoff's
  claims; it should live-verify the prior session's most recently completed work still
  functions (the exact thing this session did at its own start: re-triggered a real Hub-spawned
  run via curl and confirmed the run record/output/exit code before trusting 3.5's handoff).
  Also saved to persistent cross-session memory as `feedback_verify_on_resume.md` — but restate
  it here too since a resumed session should not have to depend on memory recall alone.
- User then said **"continue"** (approving proceeding into 3.6 after the verification + Q&A
  above), then asked to trigger a test run and explain sessions 2/3's testing scope — both
  done conversationally, not code changes.
- Carried forward, still in force (from the 3.5 handoff, itself carried from earlier): "After
  every threshold of implementation you must run the skill /handoff." "Before starting a new
  implementation revise the entire session for the spec." "let's make sure it works with claude
  and codex first locally" — Copilot second. Project `CLAUDE.md` rules still apply (never
  commit `.agentweave/tasks/`, `messages/`, `agents/`, `session.json`, `transport.json`; stage
  explicitly, never `git add -A`).
- **New standing directive, settling a question this handoff itself raised: "Yeah and always
  commit the changes."** Said in direct response to being asked whether to commit 3.6's changes
  and whether that should become the standing expectation for future tasks without re-asking
  each time. Resolved: **yes, always commit** — every completed task/checkpoint from here on
  should be committed without waiting for a fresh explicit ask, matching (and now formally
  confirming) the pattern every prior task in this chain (3.1–3.5) already followed implicitly.
  Still stage explicitly by path per `CLAUDE.md`'s rule against `git add -A` — that constraint
  is unchanged, only the "ask before every commit" part is lifted. This directive must be
  carried forward verbatim in every future handoff in this chain so it isn't lost to
  summarization or re-litigated per task.

## Dead ends

- **`play_circle` as the `run_started` icon name** — doesn't exist in
  `hub/ui/src/components/common/Icon.tsx`'s lucide-react `ICONS` map (only `play_arrow` does).
  The `Icon` component's fallback for an unmapped name is to render `null` and log a one-time
  console warning — not a build error, not a visible broken-glyph — so this would have shipped
  as a silently missing icon. Caught by grepping the map before using the name, not by seeing a
  runtime failure. Used `play_arrow` instead.
- **`${eventColor}20` for a translucent background**, copying an existing pattern already used
  a few lines below in the same file (`AgentActivityTab.tsx`'s log-item branch, pre-existing,
  not touched this session) — doesn't work: `eventColor` is a string like `"var(--red)"`, and
  `"var(--red)" + "20"` produces the invalid CSS value `var(--red)20`, which browsers silently
  ignore (falls through to inherited/transparent background, not a visible bug but not the
  intended translucent tint either). Not fixed in the pre-existing log-item branch (out of
  scope, not touched), but avoided in the new event-item branch by using explicit `rgba(...)`
  literals per color instead, matching how the surrounding component does it everywhere else
  that isn't the one `${x}20` spot.
- **Getting the dev Hub's live API key by checking `hub/.agentweave/transport.json`** — that
  file's key (`aw_live_fb660b62...`) is for a *different* project (`project_id: "proj-default"`)
  than the dev Hub's actual bootstrap project (`project_id: "Agentweave"`, key
  `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd`, from `hub/.env`'s `AW_BOOTSTRAP_API_KEY` — which
  matches what's actually in the dev DB's `api_keys` table). The transport.json key 401'd.
  Confirmed the correct key by querying `hub/data/agentweave-dev.db`'s `api_keys` table
  directly via `py -c "import sqlite3; ..."` (note: plaintext in that table, not hashed).
- **A stray empty `hub/hub/data/agentweave-dev.db` (0 bytes) got created this session** by an
  accidental `cd hub && ...` command chain running from an already-`hub/`-rooted cwd (Bash tool
  cwd persistence bit twice this session — first surfaced as `npm run dev` picking ports
  5173/5174 already in use from earlier sessions, still-running Vite instances). Deleted before
  finishing (`git status` confirmed it was untracked and harmless, not referenced by anything —
  the real dev DB used throughout was correctly `hub/data/agentweave-dev.db`, one level up).
- **Multiple stray Vite dev-server processes were already running** (ports 5173, 5174, 5175 all
  listening by the end of this session — 5173/5174 pre-existing from earlier sessions per the
  3.5 handoff's own note, 5175 newly started this session since 5173/5174 were occupied). Not
  cleaned up — noted here so a resuming session doesn't assume only one is running. This
  session's browser verification used **5175** specifically.

## Verification

**Ran and passed:**
- `py -m pytest tests/ -q` from `hub/` → 317 passed, 4 skipped (was 313 before this session;
  +4 new). Confirmed the CWD-dependent `test_migrations.py` failures only happen when pytest is
  run from the repo root, not from `hub/` — pre-existing, unrelated (matches the alembic.ini
  CWD issue noted in the 3.3/3.4 handoffs), not a regression.
- `py -m ruff check hub/` → clean. `py -m black --check hub/` → clean (after reformatting the
  new test file once).
- `npx tsc --noEmit` (in `hub/ui/`) → clean, no type errors.
- `npx vitest run` (in `hub/ui/`) → 196 passed (was 195; +1 new). The `ErrorBoundary.test.tsx`
  console "Error: boom" output is the test's own intentional throw, not a failure.
- **Live, end-to-end, against the real running dev Hub** (restarted first — killed the stale
  process on port 8000 and relaunched with the same command as prior sessions:
  `DATABASE_URL="sqlite+aiosqlite:///./data/agentweave-dev.db" py -m uvicorn hub.main:app --host
  127.0.0.1 --port 8000` from `hub/`): subscribed to the real SSE stream with a backgrounded
  `curl -sN .../api/v1/events`, triggered a real Claude run via `curl -X POST
  .../agent/trigger`, confirmed `run_started` (with correct `runner`/`model` fields) then
  `run_completed` (with correct `exit_code`/`session_id`) arrived on the stream in order;
  confirmed `GET /api/v1/agents` showed `"status":"running"` while the run was in flight and
  `"idle"` immediately after; confirmed `GET /api/v1/agents/claude/timeline` returned the new
  human-readable summaries.
- **Live, in an actual browser**, against the real Vite dev server (localhost:5175) pointed at
  the same real Hub: navigated to the claude agent's detail panel, clicked into the tab labeled
  "Messages" (which renders `AgentActivityTab` — a pre-existing label/component mismatch, not
  touched this session), read the rendered DOM directly via `preview_evaluate` (the click/
  navigate tool calls in this session's browser automation consistently threw a schema-
  validation error from the MCP layer despite the underlying action succeeding — worked around
  by driving clicks through `document.querySelector(...).click()` via `preview_evaluate`
  instead of the `preview_click`/`preview_navigate` tools, which is why this session's browser
  verification looks different in style from 3.4/3.5's): confirmed `run_started` and
  `run_completed` rows render with the correct blue/green `border-left` color and correct
  human-readable summary text.

**NOT tested this session:**
- No test of `run_failed`'s rendering in the browser specifically (only `run_started`/
  `run_completed` were produced by the live-trigger, since the test prompt succeeded) — the red
  styling was verified by reading the `AgentActivityTab.tsx` logic and confirming the color/icon
  branch exists and the vitest suite covers the event dispatch, but not visually confirmed in a
  live failed run.
- No test of the `AgentOutputPanel.tsx` Handoff feature specifically to confirm it still works
  end-to-end after this session's changes (the code path it depends on — the `agent_output`/
  `kind="status"` stopgap — was deliberately left untouched, and the existing test suite covering
  it stayed green, but no fresh live click-through of the Handoff button itself this session).
- Kimi/OpenCode/Copilot triggering — still out of scope (watchdog path, unaffected, not
  re-verified).
- Nothing from 3.7 (interrupt/stop), 3.8 (crash reconciliation), or 3.9 (process-group cleanup)
  was started or touched.

## Git state

- Branch `hub-native-experience`, **HEAD `937702f`** — task 3.6's 9 files committed this
  session ("Complete Phase 3 task 3.6: run-lifecycle SSE events and agent-view rendering"), on
  top of `5cd0863` (the previous handoff-tracking commit).
- Working tree clean except the seven pre-existing/new untracked `.claude/handoffs/*.md` files
  (the six from earlier sessions, unrelated, plus this handoff and `LATEST.md`'s pointer update
  — the handoff files themselves are committed in a separate follow-up commit after this file is
  finalized, matching the chain's established two-commit-per-checkpoint pattern: one for the
  implementation, one for "Track session handoff").
- No upstream configured — nothing pushed, not requested, unchanged from every prior handoff.

## Next steps

1. **Re-read `tasks.md`'s 3.7 entry** ("Implement interrupt and stop for an owned run") in full
   before starting — not yet read closely this session, no design work done on it.
2. 3.7 will need a way to actually stop a `PtySession` mid-run — check
   `hub/hub/pty_runner.py`'s existing `terminate(force=True)` (already built and tested per the
   3.4 handoff, just never wired to an HTTP endpoint) before building something new.
3. Frontend half of 3.7 will need a stop control somewhere in the UI — `AgentOutputPanel.tsx`'s
   header bar (next to the status chip) is the most natural spot, not yet investigated.
4. Per the new standing directive above, **commit 3.7's changes on completion without waiting
   for a fresh ask** — staged explicitly by path, same as this session's `937702f`.

## Open questions for the user

- Carried forward, unresolved, not urgent: should anything be pushed to a remote at this point?
  No remote/upstream is configured for this branch.
- Carried forward from the 3.5 handoff, still not resolved: the "ability to question the user"
  comment from an earlier T3-parity discussion — confirm whether the user meant AgentWeave's
  existing `ask_user`/Questions-panel mechanism (unaffected by anything in Phase 3 so far) or
  something else.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 3.6's entry is very long and
  detailed; read it directly. 3.7 onward is still the original unstarted task text.
- `hub/hub/api/v1/agent_trigger.py` — the file 3.7 (interrupt/stop) will extend; read fresh,
  especially the new `_broadcast_run_lifecycle()` helper this session added.
- `hub/hub/pty_runner.py` — has an existing, tested `terminate(force=True)` (built in 3.4) that
  3.7 will likely call; re-read its exact signature before wiring an endpoint to it.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — likely where 3.7's stop control lives;
  its header bar (status chip area) already has the layout this would slot into.
- `hub/hub/api/v1/agents.py` — the `list_agents()` Run-awareness fix this session added; if 3.7
  introduces new `Run.status` values (e.g. `"interrupted"`, `"stopping"`), check whether the
  `agents_with_active_run` set (currently `Run.status == "running"` only) needs updating too.
