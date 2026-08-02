# Handoff: Phase 6 durable inbound queue complete

**Date:** 2026-08-01T22:39:34+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `de5c143`
**Agent:** Codex (GPT-5.6)
**Previous handoff:** `.claude/handoffs/2026-08-01-2151-phase5-workspace-isolation-complete.md`
**Status:** chunk complete

## Goal

Ship the `hub-native-experience` OpenSpec change in
`openspec/changes/2026-07-30-hub-native-experience/`. This chunk completed Phase 6 so every
operator or peer input is durably queued, attributed, budgeted, and delivered through one
turn-scheduling path instead of inbox polling or ad hoc direct triggers.

## Current state

Phase 5 was reviewed first and its trust of pre-existing worktree paths was hardened in `27b6c59`.
Phase 6 tasks 6.1–6.12 are implemented and committed in `de5c143`. Queue entries have typed origins,
strict arrival order, hop depth, lifecycle state, exact delivered Run references, and optional
operator session controls. The per-project/agent scheduler starts idle agents, queues arrivals while
busy, drains up to the configured cap atomically with Run creation, continues after turn completion,
suspends over-budget peer chains, and resets the chain on operator input.

Operator triggers, peer messages, and scheduled jobs all enter the queue. Prompts inline every
drained entry with attribution; watchdog inbox indirection is gone. Spawn failure and crash
reconciliation return undelivered work, while an explicit stop keeps already delivered work attached
to the stopped turn and preserves later queued work. Queue settings/status/list/withdraw endpoints,
SSE lifecycle events, Hub UI cache invalidation, migration 0014, production assets, documentation,
and tests are complete. The only remaining Phase 6 ledger item is 6.13, which must be checked and
committed after this handoff is written.

## Files touched

- `docs/reference/hub-api.md` — documents queue semantics, defaults, endpoints, trigger outcomes,
  and lifecycle events. Finished.
- `hub/hub/api/v1/__init__.py` — mounts the inbound-queue router. Finished.
- `hub/hub/api/v1/agent_chat.py` — derives operator chat entries from exact typed queue delivery and
  Run/session links; removes user-sender and time/tag heuristics. Finished.
- `hub/hub/api/v1/agent_trigger.py` — enqueues operator input, supports scheduler-owned direct starts,
  atomically delivers entries with Runs, propagates turn depth, requeues spawn failures, and schedules
  follow-up work. Finished.
- `hub/hub/api/v1/agents.py` — rejects the reserved `user` identity. Finished.
- `hub/hub/api/v1/inbound_queue.py` — adds settings, status, listing, and queued-entry withdrawal
  endpoints. Finished.
- `hub/hub/api/v1/messages.py` — persists peer messages and queue entries atomically, validates source
  Run identity, advances hop depth, emits events, and schedules recipients. Finished.
- `hub/hub/db/models.py` — adds project limits, Run turn depth, and the typed inbound queue model,
  indexes, constraints, and relationships. Finished.
- `hub/hub/inbound_queue.py` — implements validation, ordered reads, prompt assembly, atomic delivery,
  interruption return, and withdrawal primitives. Finished.
- `hub/hub/mcp_server.py` — includes the Hub-bound Run ID with outbound messages. Finished.
- `hub/hub/migrations/versions/0014_add_inbound_queue.py` — migrates project limits, Run depth, and
  inbound queue schema with guarded fresh/legacy deployment behavior. Finished.
- `hub/hub/run_reconciliation.py` — returns entries from interrupted Runs and reschedules recovered
  queues. Finished.
- `hub/hub/scheduler.py` — routes scheduled-job input through the durable queue and scheduler. Finished.
- `hub/hub/schemas/messages.py` — accepts the bound outbound `run_id`. Finished.
- `hub/hub/static/ui/assets/index-eSEyloge.js` — rebuilt production UI bundle with queue-event handling.
  Finished; replaces `index-rifmKIui.js`.
- `hub/hub/static/ui/index.html` — points at the rebuilt production bundle. Finished.
- `hub/hub/turn_scheduler.py` — implements serialized per-agent scheduling, launchability checks,
  budget/cap rules, and session selection. Finished.
- `hub/hub/worktrees.py` — rejects the reserved `user` agent identity. Finished.
- `hub/tests/test_agent_chat.py` — verifies exact delivered operator history and literal session-tag
  content behavior. Finished.
- `hub/tests/test_agent_trigger.py` — verifies queued/busy/unlaunchable triggers, stop preservation,
  scheduler continuation, identity rejection, and spawn-failure recovery. Finished.
- `hub/tests/test_inbound_queue.py` — covers typed ordering, atomic drain, recovery, inline attribution,
  limits, withdrawal, hop suspension/operator reset, and delivery caps. Finished.
- `hub/tests/test_migrations.py` — covers migration 0014 on supported schema paths. Finished.
- `hub/tests/test_run_reconciliation.py` — verifies interrupted queue work is returned. Finished.
- `hub/tests/test_runtime_diagnostics.py` — expects unlaunchable inputs to queue visibly. Finished.
- `hub/tests/test_scheduler.py` — verifies jobs enqueue and preserve existing polling behavior. Finished.
- `hub/tests/test_worktrees.py` — verifies reserved identity rejection. Finished.
- `hub/ui/src/__tests__/useSSE.test.tsx` — verifies queue events invalidate relevant UI queries.
  Finished.
- `hub/ui/src/hooks/useSSE.ts` — recognizes queue lifecycle events and invalidates agent/queue caches.
  Finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — closes 6.1–6.12 with verification
  evidence. Finished except the post-handoff 6.13 checkbox.
- `src/agentweave/config.py` — rejects reserved agent identities in YAML configuration. Finished.
- `src/agentweave/constants.py` — centralizes case-insensitive reserved-name validation. Finished.
- `src/agentweave/session.py` — rejects reserved identities during session creation. Finished.
- `src/agentweave/tool_surface.py` — removes instructions that tell agents to retrieve already-inline
  messages from an inbox. Finished.
- `src/agentweave/transport/http.py` — supplies `AW_RUN_ID` on outbound Hub messages. Finished.
- `src/agentweave/watchdog.py` — inlines attributed message content and archives it instead of
  prompting `get_inbox()`. Finished.
- `tests/test_config.py` — covers case-insensitive reserved-name rejection. Finished.
- `tests/test_session.py` — covers reserved-name rejection at session creation. Finished.
- `tests/test_watchdog_session.py` — verifies inline message prompt delivery. Finished.
- `.claude/handoffs/LATEST.md` — updated to point to this handoff; session-note state, deliberately not
  included in implementation commits.
- `.claude/handoffs/2026-08-01-2239-phase6-inbound-queue-complete.md` — this handoff. Finished.

## Key decisions

1. **Queue order uses a database integer sequence, not timestamp plus random ID.** Windows/SQLite
   clock granularity produced equal arrival timestamps, and random logical IDs could reverse inputs.
   A global autoincrement sequence supplies deterministic arrival order while logical IDs remain
   opaque API identifiers.
2. **Run creation and delivery stamping share one commit.** Delivering before a Run exists could lose
   work on crash; creating the Run first could launch an empty turn. The atomic helper writes both,
   and execution is registered immediately afterward before observability events are persisted.
3. **Legacy peer messages without a bound running Run are accepted but suspended over budget.** Hard
   rejection would break existing clients; treating them as depth zero would bypass autonomy limits.
   Assigning `hop_budget + 1` preserves the message while requiring operator input to resume.
4. **Operator input resets the effective batch depth.** When an operator entry is present, the
   scheduler may drain suspended peer entries with it and start at depth zero. This preserves queued
   peer work and implements explicit human resumption without rewriting its provenance.
5. **Explicit stop does not requeue delivered entries.** The stopped Run remains the durable record
   of what was handed to that process; only later queued entries launch next. Re-delivery was rejected
   because a stopped process may already have acted on its prompt.
6. **Chat history uses exact queue-entry/Run joins.** Timestamp windows, subject text, sender `user`,
   and `[Session: ...]` parsing were rejected as ambiguous control channels. Literal tag-shaped input
   now remains ordinary content.
7. **`user` is reserved case-insensitively throughout config/session/Hub boundaries.** Typed
   `origin_type=operator` replaces the former magic sender name and prevents future identity clashes.

## Constraints and user directives (verbatim)

- "$resume Review the changes of phase 5 and execute phase 6"
- "Yeah and always commit the changes."
- "After every threshold of implementation you must run the skill `/handoff`"
- "Only stop if there is actually a blocking issue... don't need to be conservative on the changes...
  if there is genuinely a best approach you can scrap anything that already exists. Also apply these
  new rules when creating handoffs. Do a little bit less handoffs then previously but still do them."
- Repository rule: never commit runtime `.agentweave/` state; stage exact paths rather than
  `git add -A`.
- The task ledger protocol requires re-reading the proposal, design, and affected spec; scenario
  verification; and one handoff at each phase boundary.

## Dead ends

- AgentWeave Hub startup/orientation calls hung, so collaboration inbox/task state was unavailable.
  The prescribed local fallback established the backend developer/implementer role and no active
  quality configuration.
- The resumed UI test cell no longer existed, so the focused SSE test and production build were
  rerun rather than assuming success.
- Initial queue ordering by arrival timestamp plus logical ID failed on Windows because equal
  timestamps made random IDs determine order. The integer sequence fixed this deterministically.
- Migration 0014 initially assumed the `projects` table existed in Alembic-only fresh-database tests.
  Inspector guards made the migration safe for both create-all-first runtime initialization and the
  isolated migration test path.
- Full `mypy` pulls in the Hub's existing typing and missing-stub debt. A focused skipped-import run
  passed for the three new queue modules; the broader errors were not introduced or repaired here.
- Repository-wide Ruff found an unrelated existing import-order error in `tests/test_cli_watch.py`.
  Phase 6 files pass. The UI `npm run lint` script is also pre-existingly unusable with ESLint 9
  because the repository has no `eslint.config.js` flat config.
- `mkdocs` is not installed in the active environment, so strict docs build verification was not
  available. The edited reference page was reviewed and the application suites passed.

## Verification

Ran and passed:

- `pytest tests -q` — **995 passed, 4 skipped**.
- `cd hub; pytest tests -q` — **407 passed, 4 skipped**, with four Alembic deprecation warnings.
- `cd hub/ui; npm test` — **23 files, 200 tests passed**.
- `cd hub/ui; npm test -- --run src/__tests__/useSSE.test.tsx` — **7 passed**.
- `cd hub/ui; npm run build` — TypeScript and Vite production build passed; generated assets were
  synchronized to `hub/hub/static/ui/`.
- Post-format Hub focus (`test_inbound_queue`, `test_agent_trigger`, `test_run_reconciliation`,
  `test_scheduler`, `test_agent_chat`) — **47 passed**.
- Post-format CLI focus (`test_config`, `test_session`, `test_watchdog_session`, `test_http_transport`)
  — **109 passed**.
- `.venv/Scripts/ruff.exe check` over all 32 touched Python files — passed.
- `.venv/Scripts/black.exe --check` over all 32 touched Python files — passed after formatting three.
- `.venv/Scripts/mypy.exe --python-version 3.10 --follow-imports skip --ignore-missing-imports`
  over `hub/hub/inbound_queue.py`, `hub/hub/turn_scheduler.py`, and
  `hub/hub/api/v1/inbound_queue.py` — passed.
- `git diff --cached --check` immediately before commit — passed.

Not tested:

- No two real external CLI agents were spawned to ping-pong messages. The integration tests model
  bound running source turns, depth advancement/suspension, operator reset, busy arrivals, stops,
  spawn failure, and crash recovery with mocked process sessions.
- No live browser session inspected the queue events; React hook tests and the production build cover
  the Phase 6 UI change.
- `npm run lint` could not run because the existing ESLint 9 setup lacks a flat configuration file.
- `mkdocs build --strict` could not run because `mkdocs` is absent from the environment.

## Git state

- Branch: `hub-native-experience`.
- HEAD: `de5c143 Phase 6: add durable inbound turn queue`.
- No upstream branch is configured; `58` commits at HEAD are not reachable from configured remotes.
- Implementation and tasks 6.1–6.12 are committed. Tracked `.claude/handoffs/LATEST.md` is dirty;
  this handoff, several older `.claude/handoffs/*.md` notes, and `.claude/skills/aw-spec-reindex/`
  are untracked session/tooling artifacts. After writing this file, stage only the Phase 6 task-6.13
  checkbox for the checkpoint commit; do not stage `.claude` artifacts.

## Next steps

1. Re-read `openspec/changes/2026-07-30-hub-native-experience/design.md` Decisions 4–6 and
   `openspec/changes/2026-07-30-hub-native-experience/specs/agent-tool-surface/spec.md`, then inventory
   every registration in `hub/hub/mcp_server.py` and `src/agentweave/mcp/server.py` against tasks
   7.1–7.6 before deleting the Phase 7 bypass tools.
2. Execute Phase 7 as one chunk: converge the tool surfaces, add budgeted `request_agent`, route
   command and protocol outbound actions through the queue, inject spawned-agent tool config, and
   verify a multi-agent session with the tool-protocol server disabled.
3. Run `/handoff` once at the Phase 7 boundary (task 7.7).

## Open questions for the user

None.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md`
- `openspec/changes/2026-07-30-hub-native-experience/design.md`
- `openspec/changes/2026-07-30-hub-native-experience/specs/agent-tool-surface/spec.md`
- `hub/hub/mcp_server.py`
- `src/agentweave/mcp/server.py`
- `hub/hub/turn_scheduler.py`
