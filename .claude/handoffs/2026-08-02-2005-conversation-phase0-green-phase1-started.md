# Handoff: Stable conversations green; navigation phase started

**Date:** 2026-08-02T20:05:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `b443a8a`
**Agent:** T3 Code Codex / GPT-5.6-sol
**Previous handoff:** `.claude/handoffs/2026-08-02-1908-spec-readiness-and-conversation-identity.md`
**Status:** chunk complete

## Goal

Implement the approved T3-like AgentWeave conversation identity, then build the conversation-first
project/agent UI. AgentWeave owns durable identity synchronously; provider session IDs are
late-bound continuation metadata, never normal UI identity.

## Current state

The conversation OpenSpec contains the approved identity, binding, scheduling, history,
migration/reset, handoff, and UI contracts and passes strict validation. Phase 0 is implemented:
`Conversation`, migration 0017, trigger allocation/binding, conversation-only queue draining,
producer propagation, conversation-scoped history/list endpoints, test isolation, and main-chat UI
retention of returned `conversation_id`. Full Hub and UI regressions are green. Phase 1 has started
with a typed collection-shaped rail/destination adapter and contract tests; actual App/Sidebar/
Overview routing and shell replacement remain unimplemented.

## Files touched

- `hub/hub/conversations.py` — new creation/lookup helpers; phase 0 finished.
- `hub/hub/migrations/versions/0017_add_conversations.py` — schema/backfill migration; finished.
- `hub/hub/db/models.py` — Conversation and message/queue/run/output associations; finished.
- `hub/hub/api/v1/agent_trigger.py` — allocation, request/response, binding/conflict; finished.
- `hub/hub/api/v1/agent_chat.py` — conversation list/history routes; finished.
- `hub/hub/api/v1/messages.py`, `questions.py`, `agents.py` — producer attribution; finished.
- `hub/hub/inbound_queue.py`, `turn_scheduler.py`, `scheduler.py` — isolated scheduling and jobs; finished.
- `hub/hub/output_recording.py` — output conversation resolution/creation; finished.
- `hub/tests/conftest.py` — per-test database reset; finished.
- `hub/tests/test_conversations.py` — new phase-0 contract suite; finished.
- `hub/tests/test_agent_chat.py`, `test_agent_output_stream.py`, `test_bola.py`, `test_inbound_queue.py`, `test_migrations.py` — conversation/migration regression updates; finished.
- `hub/ui/src/api/agentChat.ts` — conversation type/list/history hooks; finished.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — conversation picker and trigger-response switching; finished for phase 0.
- `hub/ui/src/__tests__/agentHandoff.test.tsx` — successor conversation assertion; finished.
- `hub/ui/src/lib/navigation.ts` — new phase-1 project/destination model; foundation only.
- `hub/ui/src/__tests__/conversationNavigation.test.ts` — initial navigation contract tests; task 1.1 remains incomplete.
- `openspec/changes/2026-08-02-agent-conversation-workspace/` — approved proposal/design/tasks, metadata, workspace delta, and new handoff delta; phase 0 implemented but task boxes not yet audited.
- `openspec/changes/2026-07-30-hub-native-experience/` — pre-existing umbrella reconciliation edits carried forward; do not overwrite.
- `openspec/config.yaml`, `openspec/explorations/2026-08-02-product-direction.md`, `openspec/explorations/2026-08-02-spec-corpus-readiness-audit.md`, `openspec/specs/aw-spec-workflow/spec.md`, deleted `openspec/changes/dependencies.yaml` — pre-existing audit work, unchanged this chunk.
- `.claude/handoffs/LATEST.md` and historical untracked `.claude/handoffs/*.md` — session artifacts; historical files are pre-existing and must not be swept into a commit.

## Key decisions

1. Allocate `conversation_id` with the first queue entry; waiting for provider output recreates the
   rapid-follow-up race.
2. One provider turn drains one conversation. Mixing queued entries across conversations is invalid.
3. Self-reported output resolves by run, provider binding, then latest/open-or-new conversation.
4. Unknown/cross-project concrete conversation history returns non-disclosing 404.
5. Phase 1 begins with a collection-shaped project adapter despite one authenticated project.

## Constraints and user directives (verbatim)

- "Great continue with what needs to be done related to specs and start phase 1"
- "Great. Let's go with that"
- "Ignore the aw-spec skills. I'm using openspec only."
- "This is not a project where we user agentweave is a project where we develop agentweave."
- "This will become local only like T3 but with spec and inter agent comunications."

## Dead ends

- Alembic batch foreign keys failed on SQLite and migration-only DBs without `projects`; SQLite now
  uses additive columns while fresh ORM schemas retain FKs.
- Index creation collided with current-model `create_all`; migration now checks existing indexes.
- Old session-history tests failed correctly and were rewritten instead of adding provider-ID routing.
- `npm test -- --runInBand` is invalid for Vitest; use `npm test`.
- `ruff` and `python -m ruff` are unavailable in this environment.
- First full Hub run found two obsolete history assertions; corrected rerun is fully green.

## Verification

- `pytest hub/tests -q` — 389 passed, 4 skipped; 5 Alembic deprecation warnings.
- `npm test` in `hub/ui` — 27 files, 227 tests passed.
- `npm run build` in `hub/ui` — passed; existing duplicate-case warning remains.
- `openspec validate --all --strict --no-interactive` — 14 passed, 0 failed.
- `python -m compileall -q hub/hub hub/tests` — passed.
- `git diff --check` — passed with only existing CRLF warnings.

Not tested: ruff/lint (not installed); live browser; PostgreSQL migration; provider CLI end-to-end.
Phase-1 shell behavior is not implemented.

## Git state

Branch `hub-native-experience`, HEAD `b443a8a`, dirty and uncommitted. No upstream tracking branch.
Do not use `git add -A`: many historical handoffs are untracked. No commit/push was requested.

## Next steps

1. Add failing UI integration tests for task 1.1, then wire `WorkspaceDestination` through
   `App.tsx`, `Sidebar.tsx`, and `OverviewPage.tsx` for direct agent conversation and one-step back.
2. Render the project/agent rail from `buildRailProjects`, with stable identity colours and text.
3. Add full-height conversation rendering, then remove Agents/Messages destinations after tests pass.
4. Audit phase-0 task checkboxes against evidence; update only genuinely completed items.
5. Re-run full UI/build, focused Hub, strict OpenSpec, and diff checks.

## Open questions for the user

None.

## Read on resume

- `openspec/changes/2026-08-02-agent-conversation-workspace/tasks.md`
- `openspec/changes/2026-08-02-agent-conversation-workspace/design.md`
- `hub/ui/src/lib/navigation.ts`
- `hub/ui/src/App.tsx`
- `hub/ui/src/components/layout/Sidebar.tsx`
- `hub/ui/src/components/agents/AgentOutputPanel.tsx`
