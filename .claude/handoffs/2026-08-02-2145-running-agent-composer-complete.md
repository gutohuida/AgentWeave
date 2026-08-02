# Handoff: Running-agent composer phase complete

**Date:** 2026-08-02T21:45:03+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `b443a8a`
**Agent:** T3 Code Codex / GPT-5.6-sol
**Previous handoff:** `.claude/handoffs/2026-08-02-2137-conversation-phase1-complete.md`
**Status:** chunk complete

## Goal

Make the AgentWeave conversation the primary workspace and allow operators to add turns while an
agent is already running. Durable AgentWeave `conversation_id` remains the routing identity while
the server, not client running-state guesses, decides whether submitted input starts or queues.

## Current state

Phases 0–2 are implemented and regression-green, except phase-0 test umbrella task 0.1 remains open
for missing explicit lifecycle/backfill/reset cases. Phase 2 added a focused running-composer suite
and changed submission so running state no longer disables input or send. Input clears
optimistically, only the submission's in-flight state locks the composer, failures restore the
exact typed text and render an alert banner, and queued entries remain sourced exclusively from the
recorded chat query refreshed by `queue_entry_queued` SSE invalidation. Two rapid queued turns retain
the same conversation and render in recorded sequence order. Tasks 2.1–2.5 are complete.

## Files touched

- `.claude/handoffs/LATEST.md` — points to this checkpoint; finished.
- `.claude/handoffs/2026-08-02-2145-running-agent-composer-complete.md` — this checkpoint; finished.
- `.claude/handoffs/2026-08-02-2137-conversation-phase1-complete.md` — previous checkpoint; unchanged.
- `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-07-29-2110-spec-navigation-t1-t9-implemented.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-07-30-0004-agentweave-strategy-discussion-resolved.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-07-30-1912-spec-navigation-closed-r1-audit-next.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-07-31-2049-hub-native-phase1-feel-foundation.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-07-31-2112-hub-native-phase1-complete.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-08-01-2038-phase4-identity-access-path-complete.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-08-01-2151-phase5-workspace-isolation-complete.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-08-01-2239-phase6-inbound-queue-complete.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-08-02-0140-phase7-agent-tool-surface-complete.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-08-02-0300-hub-native-phase8-timeline-complete.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-08-02-1130-phase8-mock-fidelity-and-live-test-env.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-08-02-1330-waiting-reason-fix-and-phase9-next.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-08-02-1908-spec-readiness-and-conversation-identity.md` — pre-existing untracked history; unchanged.
- `.claude/handoffs/2026-08-02-2005-conversation-phase0-green-phase1-started.md` — pre-existing untracked history; unchanged.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — phase-2 submission locking, optimistic clear, failure restore, and failure banner; finished.
- `hub/ui/src/__tests__/agentRunningComposer.test.tsx` — phase-2 contract suite for running, ordering, recorded-only rendering, and failure restore; finished.
- `hub/ui/src/App.tsx` — phase-1 destination model; unchanged this phase, preserve.
- `hub/ui/src/__tests__/App-mount.test.tsx` — phase-1 shell regression update; unchanged this phase, preserve.
- `hub/ui/src/__tests__/agentHandoff.test.tsx` — conversation handoff regression; unchanged this phase, preserve.
- `hub/ui/src/api/agentChat.ts` — conversation query and queue-event invalidation; unchanged this phase, preserve.
- `hub/ui/src/components/layout/Sidebar.tsx` — phase-1 project/agent rail; unchanged this phase, preserve.
- `hub/ui/src/components/overview/OverviewPage.tsx` — phase-1 direct agent activation; unchanged this phase, preserve.
- `hub/ui/src/__tests__/conversationNavigation.test.ts` — phase-1 adapter contracts; unchanged this phase, preserve.
- `hub/ui/src/__tests__/conversationShell.test.tsx` — phase-1 shell contracts; unchanged this phase, preserve.
- `hub/ui/src/lib/navigation.ts` — phase-1 typed destinations; unchanged this phase, preserve.
- `hub/hub/conversations.py` — phase-0 identity helpers; unchanged this phase, preserve.
- `hub/hub/migrations/versions/0017_add_conversations.py` — phase-0 migration; unchanged this phase, preserve.
- `hub/hub/api/v1/agent_chat.py` — phase-0 conversation history; unchanged this phase, preserve.
- `hub/hub/api/v1/agent_trigger.py` — phase-0 trigger contract; unchanged this phase, preserve.
- `hub/hub/api/v1/agents.py` — phase-0 producer association; unchanged this phase, preserve.
- `hub/hub/api/v1/messages.py` — phase-0 producer association; unchanged this phase, preserve.
- `hub/hub/api/v1/questions.py` — phase-0 producer association; unchanged this phase, preserve.
- `hub/hub/db/models.py` — phase-0 Conversation model/associations; unchanged this phase, preserve.
- `hub/hub/inbound_queue.py` — phase-0 queue routing; unchanged this phase, preserve.
- `hub/hub/output_recording.py` — phase-0 output association; unchanged this phase, preserve.
- `hub/hub/scheduler.py` — phase-0 scheduler association; unchanged this phase, preserve.
- `hub/hub/turn_scheduler.py` — phase-0 isolated conversation draining; unchanged this phase, preserve.
- `hub/tests/conftest.py` — phase-0 test isolation; unchanged this phase, preserve.
- `hub/tests/test_conversations.py` — partial task-0.1 contract suite; unchanged this phase, still incomplete.
- `hub/tests/test_agent_chat.py` — phase-0 history regressions; unchanged this phase, preserve.
- `hub/tests/test_agent_output_stream.py` — phase-0 output regression; unchanged this phase, preserve.
- `hub/tests/test_bola.py` — phase-0 authorization fixture; unchanged this phase, preserve.
- `hub/tests/test_inbound_queue.py` — phase-0 scheduling regressions; unchanged this phase, preserve.
- `hub/tests/test_migrations.py` — migration head update; unchanged this phase, preserve.
- `openspec/changes/2026-08-02-agent-conversation-workspace/tasks.md` — phase-2 tasks marked from passing evidence; finished for this phase.
- `openspec/changes/2026-08-02-agent-conversation-workspace/.openspec.yaml` — approved metadata; unchanged, preserve.
- `openspec/changes/2026-08-02-agent-conversation-workspace/proposal.md` — approved proposal; unchanged this phase, preserve.
- `openspec/changes/2026-08-02-agent-conversation-workspace/design.md` — approved design; unchanged this phase, preserve.
- `openspec/changes/2026-08-02-agent-conversation-workspace/specs/agent-conversation-workspace/spec.md` — approved workspace delta; unchanged this phase, preserve.
- `openspec/changes/2026-08-02-agent-conversation-workspace/specs/agent-conversation-handoff/spec.md` — approved handoff delta; unchanged, preserve.
- `openspec/changes/2026-07-30-hub-native-experience/design.md` — pre-existing umbrella reconciliation; preserve.
- `openspec/changes/2026-07-30-hub-native-experience/proposal.md` — pre-existing umbrella reconciliation; preserve.
- `openspec/changes/2026-07-30-hub-native-experience/specs/agent-identity-and-skills/spec.md` — pre-existing umbrella delta; preserve.
- `openspec/changes/2026-07-30-hub-native-experience/specs/agent-tool-surface/spec.md` — pre-existing umbrella delta; preserve.
- `openspec/changes/2026-07-30-hub-native-experience/specs/spec-traceability/spec.md` — pre-existing umbrella delta; preserve.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — pre-existing umbrella reconciliation; preserve.
- `openspec/changes/dependencies.yaml` — pre-existing deletion; preserve.
- `openspec/config.yaml` — pre-existing audit edit; preserve.
- `openspec/explorations/2026-08-02-product-direction.md` — pre-existing direction edit; preserve.
- `openspec/explorations/2026-08-02-spec-corpus-readiness-audit.md` — pre-existing untracked audit; preserve.
- `openspec/specs/aw-spec-workflow/spec.md` — pre-existing spec correction; preserve.

## Key decisions

1. Composer submission lock is separate from conversation-control lock. Running may still disable
   session switching/handoff, but it cannot disable typing or submit; only the current HTTP
   submission can do that.
2. The text is captured, cleared before awaiting the trigger, and restored verbatim on failure.
   Clearing only after success was rejected because it violates the approved optimistic algorithm.
3. No queued timeline row is synthesized from the trigger response. The existing SSE invalidation
   causes the conversation chat endpoint's recorded queue row to become visible, preventing phantom
   entries and retaining server sequence order.
4. Phase 2 introduces a minimal `role="alert"` failure banner. Phase 3 should generalize this into
   the specified stable banner stack rather than creating a second failure surface.

## Constraints and user directives (verbatim)

- "Ignore the aw-spec skills. I'm using openspec only."
- "This is not a project where we user agentweave is a project where we develop agentweave."
- "This will become local only like T3 but with spec and inter agent comunications."
- "continue without using resume"

## Dead ends

- The first phase-2 run failed both tests as intended: running status disabled the textarea, and
  text was not cleared during the in-flight request.
- The first implementation patch changed the selector's disabled prop instead of the textarea's
  matching prop. A focused rerun exposed it; selector uses `interactionLocked`, composer uses
  `submissionLocked`.
- The initial failure test exposed that continuity text was not an accessible banner. A dedicated
  alert region was added before closing the phase.
- `npm test -- --runInBand` remains invalid for Vitest; use `npm test`.
- `ruff` remains unavailable in this environment.

## Verification

- `npm test -- agentRunningComposer.test.tsx agentHandoff.test.tsx agentChat.test.tsx` — 3 files,
  11 tests passed after the submission change.
- Final `npm test` in `hub/ui` — 29 files, 234 tests passed.
- Final `npm run build` in `hub/ui` — passed; existing duplicate `task_created` case warning remains.
- `openspec validate --all --strict --no-interactive` — 14 passed, 0 failed.
- `git diff --check` — passed; only existing CRLF warnings for two umbrella files.

Not tested this phase: live browser running-agent interaction; real provider CLI; backend tests
(backend was unchanged); PostgreSQL migration; ruff/lint. The phase-0 task-0.1 coverage gap remains.

## Git state

Branch `hub-native-experience`, HEAD `b443a8a`, dirty and uncommitted. No upstream tracking output
was available. No commit/push was requested. Never use `git add -A`; historical untracked handoffs
remain in the tree.

## Next steps

1. Re-read the approved phase-3 composer sections, then create
   `hub/ui/src/__tests__/conversationComposer.test.tsx` with failing tests for a 3-row resting
   textarea, growth through at least 12 rows before internal scrolling, project-and-conversation
   draft isolation, navigation/reload restoration, success clearing without delayed-write races,
   and storage-unavailable degradation.
2. Extract the footer composer from `AgentOutputPanel.tsx` into a dedicated component and implement
   the namespaced project/conversation draft store.
3. Add the control-placement/overflow tests and implementation, moving the current selector,
   handoff, fold-all, and details actions into one keyboard-operable menu.
4. Complete autoscroll, context indicator, and ordered banner-stack tasks, run full verification,
   then write the phase-3 threshold handoff.
5. Separately close phase-0 task 0.1 with explicit backend/migration lifecycle tests.

## Open questions for the user

None.

## Read on resume

- `openspec/changes/2026-08-02-agent-conversation-workspace/tasks.md`
- `openspec/changes/2026-08-02-agent-conversation-workspace/design.md`
- `openspec/changes/2026-08-02-agent-conversation-workspace/specs/agent-conversation-workspace/spec.md`
- `hub/ui/src/components/agents/AgentOutputPanel.tsx`
- `hub/ui/src/__tests__/agentRunningComposer.test.tsx`
- `hub/ui/src/api/agentChat.ts`
