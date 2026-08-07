# Handoff: HUB_URL bug fixed and live-verified; Codex app-server transport built and tested, not yet wired into the live run path

**Date:** 2026-08-06T09:40 · **Branch:** hub-native-experience · **HEAD:** 55fbd33
**Agent:** Claude Sonnet 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0007-2026-08-06-0230-messaging-bug-and-ui-round-specced.md
**Status:** chunk complete. Seven commits, all product code + specs, all tested. The
highest-risk remaining piece (wiring the new transport into the live run lifecycle) was
deliberately deferred to a fresh session rather than rushed at the end of this one.

## Goal

Continue from handoff-0007: two openspec changes existed as specification only
(`2026-08-06-agent-messaging-delivery`, `2026-08-06-hub-composer-and-chrome-refinement`), both
`Approved: pending`, nothing implemented. This session's job was to actually implement the
messaging-delivery fix, in the order handoff-0007's "Next steps" laid out: sync a dependency
spec, land the small independent §3 fix first, verify §2's biggest open risk, then build §2 (the
Codex `app-server` transport rewrite) as far as could be done safely.

## Current state

**Both pending changes were approved** (operator decision, recorded in commit `ce07ed8`).

**§3 (HUB_URL mis-derivation) is fully implemented, tested, and live-verified — this part of the
bug is fixed.** `hub/hub/bound_address.py` (new) is populated by HTTP middleware in `main.py`
from `request.scope["server"]`; `agent_trigger.py` builds a run's `HUB_URL` from an explicit
operator override first, then this observed address, and refuses to start a run (typed error)
if neither is available. Live-verified: restarted the dev Hub on 8010 with the fix, confirmed a
stale Hub still answers on 8000, triggered a real Claude agent with no `HUB_URL` env var set, and
its `list_tasks` MCP call correctly reached 8010.

**§2 (Codex `app-server` transport) has its entire protocol layer built and tested, but nothing
calls it yet.** `hub/hub/codex_appserver.py` now contains:
- `decide_approval` — the approval decision logic (2.2-2.4), response shapes verified live.
- `map_item_to_events` / `map_token_usage_notification` / `map_turn_failure` — event mapping
  (2.5), built from live-captured notification sequences.
- `AppServerProcess` — the bidirectional JSON-RPC transport (2.1's first half): spawn, request/
  response correlation, notification queueing, answering server requests, close.
- `run_turn` — the per-turn orchestrator (2.1's second half): initialize → thread/start-or-resume
  → turn/start → notification loop → `TurnOutcome`. Handles session resume (2.6's mechanism),
  process death mid-turn, turn timeout, and `turn/interrupt` (2.7's mechanism) — all implemented
  and tested, but **nothing in `agent_trigger.py` calls any of this yet.**

**Task 2.8 — wiring `run_turn` into `agent_trigger.py`'s `_execute_run`, plus 2.14's live breach
test — is the explicit, deliberate stopping point.** The operator was asked whether to continue
into this or stop, and chose to stop: "this is the highest-risk part of this whole change and
deserves fresh context, not the tail of an already-long session."

**Also done this session, independent of the messaging fix:** synced
`2026-08-04-hub-model-control-and-provisioning`'s six capability deltas into the main specs
(new `model-catalog` spec; updates to `local-project-workspace`, `agent-conversation-workspace`,
`operator-agent-creation`, `runner-registry`, `agent-context-usage`). This was handoff-0007's
one hard ordering constraint (the UI change's delta extends a requirement that didn't exist in
main specs yet) and is now satisfied.

## Files touched

**§3 fix (commit `3df0375`):**
- `hub/hub/bound_address.py` — new. Module-level observed-address global, populated per-request.
- `hub/hub/main.py` — new `_observe_bound_address` HTTP middleware; imports `bound_address`.
- `hub/hub/api/v1/agent_trigger.py` — `HUB_URL` derivation rewritten (~line 356-372); removed the
  now-unused `from ...config import settings` import.
- `hub/tests/test_agent_trigger.py` — 4 new tests (`test_trigger_derives_hub_url_from_observed_address_not_configured_port`,
  `test_trigger_prefers_explicit_hub_url_over_observed_address`,
  `test_trigger_directly_refuses_when_no_address_is_known`, plus the regression-folded settings.aw_port poisoning check).

**§2 protocol layer (commits `be58dd7`, `55fbd33`):**
- `hub/hub/codex_appserver.py` — new, ~510 lines. Everything described above. Finished, not wired
  in anywhere.
- `hub/tests/test_codex_appserver.py` — new, 27 tests (`decide_approval`, `map_item_to_events`,
  `map_token_usage_notification`, `map_turn_failure`).
- `hub/tests/test_codex_appserver_process.py` — new, 7 tests (`AppServerProcess` against a real
  subprocess stand-in script).
- `hub/tests/test_codex_appserver_run_turn.py` — new, 9 tests (`run_turn` against a scripted fake
  session, since it hardcodes spawning `[cli, "app-server"]` and can't be pointed at a stand-in
  directly).

**Spec sync (commit `52e4023`):**
- `openspec/specs/model-catalog/spec.md` — new file.
- `openspec/specs/local-project-workspace/spec.md`,
  `openspec/specs/agent-conversation-workspace/spec.md`,
  `openspec/specs/operator-agent-creation/spec.md`, `openspec/specs/runner-registry/spec.md`,
  `openspec/specs/agent-context-usage/spec.md` — each extended with the relevant delta
  requirements from `2026-08-04-hub-model-control-and-provisioning`.

**openspec bookkeeping (commits `ce07ed8`, `1d1e26d`, `e00b2db`, and the tasks.md portions of
`3df0375`/`be58dd7`/`55fbd33`):**
- `openspec/changes/2026-08-06-agent-messaging-delivery/proposal.md`,
  `openspec/changes/2026-08-06-hub-composer-and-chrome-refinement/proposal.md` — `Approved:` line
  filled in.
- `openspec/changes/2026-08-06-agent-messaging-delivery/tasks.md` — §3 fully checked; §2.1-2.5 and
  2.9-2.13 checked with implementation notes; §2.6-2.8/2.14/2.15 still open, annotated with what's
  already mechanism-complete vs. what's genuinely unstarted.
- `openspec/changes/2026-08-06-agent-messaging-delivery/design.md` — Decision 1a extended with the
  live thread/resume verification; Decision 2 extended with the actual (lifespan-infeasible)
  implementation note.
- `openspec/changes/2026-08-06-agent-messaging-delivery/implications-codex-appserver.md` — §5
  updated from "open question" to "verified, resolved."

**Not committed, not product code (gitignored under `testbed/.gitignore:3` = `*`):**
- `testbed/scratch/probe_thread_resume.py`, `probe_appserver_turn.py`, `probe_appserver_approval.py`,
  `probe_appserver_mcp_config.py`, `throwaway_mcp_server.py` — the live probes that produced every
  measured shape in `codex_appserver.py`. Kept on disk (not deleted) in case the next session needs
  to re-probe something; safe to delete any time, they are pure scratch.

**Pre-existing dirty files, not touched this session** (carried across every handoff since
handoff-0001 — see "Open questions" below): `M .claude/handoffs/handoff-0001-...md`, `M Makefile`.

## Key decisions

1. **Live-restarted the dev Hub on 8010 to verify §3**, since the running process predated the
   code change (no `--reload`). Confirmed via `netstat`/process inspection before killing it —
   it was the handoff-0007-documented disposable dev server, not unexpected state.
2. **HUB_URL is derived from `request.scope["server"]` via middleware, not from the lifespan
   hook as `design.md` originally specified.** Verified against installed uvicorn 0.41.0 source:
   `Server.startup()` calls `await self.lifespan.startup()` *before* binding the socket in the
   standard host/port path, so lifespan-time capture is genuinely impossible, not just
   inconvenient. `design.md` Decision 2 was corrected to describe what was actually built, not
   left describing something that turned out not to exist.
3. **The observed host is always normalized to `127.0.0.1`; only the observed port is used.**
   The agent is always a local Hub subprocess (native mode; Docker not exercised per longstanding
   operator directive). Using the raw observed host would break if a request arrived from a
   non-loopback interface; the port is the only fact that was actually wrong before this fix.
4. **A module-level global (`bound_address.py`), not `app.state`, holds the observed address.**
   `trigger_agent_directly` is deliberately decoupled from any FastAPI `Request` — the scheduler
   calls it with no request in flight — so nothing tied to a `Request`/`app` object would be
   reachable from that call site.
5. **`decide_approval`'s response shapes were verified live, not taken from the schema alone.**
   `codex app-server generate-json-schema` exports two differently-shaped response types for the
   same-looking concept — `CommandExecutionRequestApprovalResponse`'s
   `{"decision":"accept"|"decline"}` vs. the older `ExecCommandApprovalResponse`'s
   `{"decision":"approved"|"denied"}`. Guessing wrong on a security boundary was judged
   unacceptable; a real out-of-workspace write attempt, declined with `{"decision":"decline"}`,
   produced no file and no protocol error — that's the one actually in effect.
6. **`item/permissions/requestApproval` grants a broad but explicit filesystem+network profile
   under yolo, and an empty grant otherwise** — this method was never actually observed live (no
   probe triggered it), so this is a considered default matching yolo's existing "approves
   everything" semantics elsewhere, not a measured shape. Flagged here in case it needs revisiting
   once actually exercised.
7. **`run_turn` spawns fresh per turn and closes at the end** (implications-codex-appserver.md
   §1's explicit recommendation) — not a long-lived per-agent process. Keeps this a transport
   swap verifiable one-for-one against `exec`, defers the process-registry/health-check/orphan-
   reaping cost to an explicit follow-on.
8. **`run_turn` is tested against a scripted fake session (patching `AppServerProcess.spawn`),
   not a real `codex` subprocess.** It hardcodes `[cli, "app-server"]` as the spawn command, so a
   stand-in script (the technique used for `AppServerProcess` itself) can't be substituted in
   without changing production code just to make it testable. The fake session replays real
   captured message sequences from the probes, not hand-guessed ones.
9. **Deferred wiring `run_turn` into `_execute_run` to a fresh session, on the operator's explicit
   choice**, after presenting it as a distinct, higher-risk category of change (production
   integration touching a path 708 tests cover) versus the isolated-module work done so far.

## Constraints and user directives (verbatim)

- **"Continue with these answers in mind"** (via AskUserQuestion), selecting: approve both
  pending changes and start the messaging fix; sync `hub-model-control-and-provisioning` first;
  then explicitly **"Continue into §2 now"** twice more at successive checkpoints, and finally
  **"Stop here for now (Recommended)"** at the third checkpoint — ending this session
  deliberately before the live `_execute_run` wiring.
- From `CLAUDE.md`, load-bearing throughout: never create `.agentweave/`, `agentweave.yml`, or
  `spec/` at the repo root — all exploratory execution happened in `testbed/scratch/`; stage paths
  explicitly, never `git add -A`; Icon is the only icon system (not touched this session).
- From memory (`feedback_always_commit_checkpoints`): commit each completed checkpoint without
  asking. All seven commits happened unprompted, each after its own test run.
- From memory (`feedback_verify_on_resume`): live-verify prior claimed work on resume. Done at
  session start — re-ran `openspec validate --strict` on all three changes rather than trusting
  the handoff's claim, and confirmed via `curl` that the dev Hub processes described in
  handoff-0007 were genuinely still running before touching anything. **Repeating the directive
  here for the next session**, per that memory's own instruction to record it in every handoff.
- **"Root-cause by experiment, not by reading code"** (a decision principle from handoff-0007,
  honored again this session): every shape in `codex_appserver.py` — approval response bodies,
  item taxonomy, token-usage fields, MCP config registration — was measured against a live
  `codex app-server`, not inferred from the schema or from `exec`'s parser.

## Dead ends

- **Capturing the Hub's bound address in the ASGI lifespan hook, as `design.md` originally
  specified, is not possible** in the standard uvicorn host/port path — the socket binds *after*
  lifespan startup returns. Confirmed by reading installed uvicorn 0.41.0's `Server.startup()`
  source directly, not by trial and error. Design was corrected rather than worked around
  silently.
- **The `openspec status --change <name>` CLI command rejects any change name starting with a
  digit** ("Change name must start with a letter"), even though `openspec list` and file-based
  reads of the same change work fine. This blocked the `openspec-sync-specs` skill's normal
  status-JSON-driven flow; worked around by reading delta spec files directly from
  `openspec/changes/<name>/specs/`, which the skill explicitly permits. Not investigated further
  — likely a CLI validation bug affecting only this repo's older date-prefixed change names.
- **My own first two live probes decoded `codex app-server`'s stdout with the wrong encoding**
  (`subprocess.Popen(..., text=True)` without `encoding="utf-8"` defaults to the Windows locale
  codepage, CP-1252) — every smart quote and em dash in captured output appeared as mojibame
  (`â€™`) throughout the early probe transcripts, and one probe's reader thread
  crashed outright on a byte CP-1252 can't decode. Not Codex's bug — `pty_runner.PipeSession`
  already guards against exactly this with `encoding="utf-8", errors="replace"`.
  `AppServerProcess` does the same; `test_codex_appserver_process.py` has a dedicated regression
  test for it.
- **Assuming `ExecCommandApprovalResponse`'s `{"decision":"approved"}` shape (matching schema's
  first-alphabetical or most-prominent-looking match) would have been wrong.** Only discovered
  by deliberately triggering a real approval request and testing the response live — see Key
  Decision 5.

## Verification

**Ran, with real output, this session:**
- `openspec validate --strict` on all three changes, multiple times, after every edit — all
  valid throughout.
- `hub/tests/` full suite, four times across the session as work landed: 692 → 699 → 708 passed
  (9 skipped throughout), zero failures at any point.
- Live HUB_URL reproduction: restarted the dev Hub on 8010 with the fix, confirmed the stale Hub
  on 8000 still answers, triggered `live-verify-claude` with no `HUB_URL` env var, its
  `list_tasks` MCP call returned `{"result":[]}` — correct for `proj-de54b547`, and reached 8010
  (verified no `HUB_URL` was set in the shell that started the Hub).
- Live `thread/resume` probe against a real, previously-recorded `Run.session_id`
  (`019fd481-71f1-7e90-98dc-9033753492bc`, from completed run `run-7c46ad24`) — full prior turn
  history came back, `source: "exec"` correctly identified.
- Live full-turn probe (fresh `thread/start` → `turn/start` → real shell command → completion) —
  captured the complete item/turn notification sequence `map_item_to_events` is built from.
- Live approval-response-shape probe: a real out-of-workspace write attempt, declined with
  `{"decision": "decline"}` — no file created, no protocol error, turn continued normally.
- Live MCP-config-registration probe: a throwaway one-tool server registered via `thread/start`'s
  `config.mcp_servers` reached `mcpServer/startupStatus/updated` status `"ready"`.

**Explicitly NOT run — do not assume:**
- **`run_turn` has never been exercised against a real `codex app-server` process.** Every test
  of it uses a scripted fake session (see Key Decision 8). The probes that informed its logic
  were separate standalone scripts, not `run_turn` itself.
- **Nothing in `agent_trigger.py` or `_execute_run` calls `codex_appserver` at all.** No Codex
  agent triggered through the real Hub has ever run a turn over `app-server`; every live Codex
  verification this session (thread/resume, item shapes, approval shapes, MCP config) used a
  standalone probe script talking to `codex app-server` directly, never through the Hub.
- **Task 2.14 (the live breach test through the Hub) has not been attempted** — it requires 2.8's
  wiring to exist first.
- **Task 2.15 (whether Claude has the same MCP-tool-approval defect Codex had) is still
  unstarted** — untouched since handoff-0007.
- The frontend suite was not run (no UI code changed this session).
- Whether an actual triggered Codex agent, run through `app-server` end-to-end via the Hub,
  produces output/timeline/usage records indistinguishable from the `exec` path (task 2.5's
  stated goal) has been verified at the *unit* level (event mapping tests) but never end-to-end.

## Git state

Branch `hub-native-experience`, HEAD `55fbd33`, **no upstream configured — nothing has ever been
pushed on this branch** (carried forward from every prior handoff).

Seven commits this session: `ce07ed8`, `52e4023`, `3df0375`, `1d1e26d`, `be58dd7`, `e00b2db`,
`55fbd33`.

Uncommitted, all pre-existing and none from this session (identical set to every handoff since
handoff-0001):
- `M .claude/handoffs/handoff-0001-...md`, `M Makefile`
- `?? data/`, `?? scripts/`, `?? .claude/skills/{handoff,resume,review-iteration}/`,
  `?? .claude/handoffs/*.md` (older, un-numbered handoffs plus `LATEST.md` and `reviews/`),
  `?? openspec/explorations/...`, `?? src/agentweave/templates/skills/{handoff,resume}.md`,
  `?? tests/test_handoff_resume_templates.py`

## Live environment

- **Hub dev server on `127.0.0.1:8010`** — restarted this session (`uvicorn hub.main:app --host
  127.0.0.1 --port 8010`, from `hub/` directory, background, no `--reload`) so it carries the §3
  fix. Log at `/tmp/hub-dev-8010.log`. API key in `hub/.env`'s `AW_BOOTSTRAP_API_KEY`; use
  `Authorization: Bearer <key>` (not `X-API-Key` — that header does not authenticate against this
  Hub, confirmed by trial). Disposable, kill any time.
- **Port 8000 still occupied by the old Dockerised Hub** (the "cosmic" theme one) — same as
  handoff-0007, kept deliberately for reproducing task 2.14's breach test later.
- **`Two Codex Mini`** (`proj-d9b5ed67`) and **`Live Verify`** (`proj-de54b547`) test projects,
  unchanged from handoff-0007. `codex-mini-1` still has `config.yolo = true` — reset before
  treating it as default-config.
- `testbed/scratch/probe_*.py` and `throwaway_mcp_server.py` — the live probe scripts, gitignored,
  safe to delete or reuse.

## Next steps

1. **Wire `codex_appserver.run_turn` into `agent_trigger.py`'s `_execute_run` (task 2.8).** Add a
   branch in `_execute_run` (around `hub/hub/api/v1/agent_trigger.py:729`, where it currently
   chooses `PipeSession` vs `PtySession` by `runner`) for an app-server-selected Codex run.
   Selector: an explicit opt-in with no schema change, e.g. checking for a sentinel in
   `runner_row.flags` (mirrors how `extra_flags` already flows into `build_command`) — do not
   make it the default; `exec` stays default per task 2.8.
2. Wire `run_turn`'s callbacks (`on_event`, `on_usage`, `on_accounting`) to the same
   `record_agent_output`/`record_context_usage` calls `_flush_line` already makes (see
   `agent_trigger.py:845-870` for the exact shape each expects), and its `TurnOutcome` to the
   same run-completion logic that currently reads `exit_code`/`session_id` after the PipeSession
   read loop (`agent_trigger.py:883-926`) — conversation binding conflict handling, worktree
   snapshot, `record_turn_usage`, lifecycle broadcast, and the trailing `schedule_agent` drain
   call all need to run for this path too, unchanged in behavior from `exec`.
3. Pass `resume_thread_id=known_session_id` when resuming a Codex conversation — the mechanism is
   proven (task 2.6), this is just threading the existing `Run.session_id` value through.
4. Wire `should_interrupt` to the existing `_stop_requested` set (task 2.7's remaining piece) so
   the stop endpoint reaches a running app-server turn the same way it reaches a PtySession today.
5. Write integration tests exercising this new `_execute_run` branch the way
   `test_agent_trigger.py`'s existing tests do (patch `codex_appserver.run_turn` or
   `AppServerProcess.spawn`, assert on the resulting `Run`/`AgentOutput` rows) — mirroring the
   pattern already established for the `exec` path in that same file.
6. **Task 2.14, live:** with the wiring done, run the exact breach test from `design.md` Decision
   1a through the real Hub — one turn that calls the AgentWeave MCP tool *and* attempts a write
   outside the workspace, selecting app-server. Tool call should succeed; write should be refused;
   no file should appear. This is the first time `run_turn` will run against a real `codex`
   process rather than a scripted fake.
7. Task 2.15 (Claude MCP-approval parity check) is still fully open and independent of 1-6.
8. The UI change (`2026-08-06-hub-composer-and-chrome-refinement`) remains untouched and can
   proceed in parallel — shares no files with any of the above.

## Open questions for the user

Carried forward, untouched, across eight handoffs now:
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

New this session:
8. `item/permissions/requestApproval`'s yolo-grant shape (Key Decision 6) was never actually
   observed live — worth deliberately triggering once, or acceptable to leave as a considered
   default until it's exercised for real?

## Read on resume

- `openspec/changes/2026-08-06-agent-messaging-delivery/tasks.md` — the implementation ledger;
  §1 and §3 done, §2.1-2.5/2.9-2.13 done, start at §2.6-2.8's remaining integration work.
- `hub/hub/codex_appserver.py` — the complete protocol layer next-step-1 will call into; read in
  full, it's ~700 lines but every function is small and independently documented.
- `hub/hub/api/v1/agent_trigger.py` — `_execute_run` (line ~705) and `_flush_line` (line ~795),
  the exact functions next-step-1/2 modify and must stay behaviorally equivalent to for the
  `exec` path.
- `openspec/changes/2026-08-06-agent-messaging-delivery/implications-codex-appserver.md` — §1
  and §2 in particular (process model, silence-becomes-deadlock) before touching the wiring.
- `hub/tests/test_agent_trigger.py` — the existing `exec`-path integration test patterns
  (`_fake_pty`, `_await_background_run`) that next-step-5's new tests should mirror.
