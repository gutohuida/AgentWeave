# Handoff: Conversation-first navigation phase complete

**Date:** 2026-08-02T21:37:44+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `b443a8a`
**Agent:** T3 Code Codex / GPT-5.6-sol
**Previous handoff:** `.claude/handoffs/2026-08-02-2005-conversation-phase0-green-phase1-started.md`
**Status:** chunk complete

## Goal

Implement the approved T3-like AgentWeave conversation identity and conversation-first workspace.
AgentWeave owns durable conversation identity synchronously; provider session IDs remain subordinate
continuation metadata. Phase 1 replaces the intermediate agent browser with direct project/agent
navigation so the conversation is the primary work surface.

## Current state

Phase 0's stable conversation backend and UI retention are implemented and regression-green. Phase
1 is complete: the sidebar renders a collection-shaped project tree, project name and expander are
separate controls, rail and overview agent activation open the full-height conversation directly,
the shell renders exactly one conversation header with one-action back-to-project, identity colours
match the timeline helper, and the Agents/Messages navigation destinations are removed without
removing their APIs or stored data. A live T3 preview verified the rail-to-conversation-to-project
flow; its temporary backend, Vite process, and preview database were stopped/removed.

OpenSpec task boxes 0.2–0.10 and 1.1–1.8 reflect verified implementation and completed handoffs.
Task 0.1 intentionally remains open: the dedicated `test_conversations.py` suite does not explicitly
cover every clause named by that umbrella test task (notably deterministic backfill, binding
conflict, and reset-only deletion), even though the implementation and broader regressions are
green. Do not check 0.1 on the strength of the implementation plan.

## Files touched

- `.claude/handoffs/LATEST.md` — updated to this checkpoint; finished.
- `.claude/handoffs/2026-08-02-2137-conversation-phase1-complete.md` — this checkpoint; finished.
- `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md` — pre-existing untracked historical handoff; untouched.
- `.claude/handoffs/2026-07-29-2110-spec-navigation-t1-t9-implemented.md` — pre-existing untracked historical handoff; untouched.
- `.claude/handoffs/2026-07-30-0004-agentweave-strategy-discussion-resolved.md` — pre-existing untracked historical handoff; untouched.
- `.claude/handoffs/2026-07-30-1912-spec-navigation-closed-r1-audit-next.md` — pre-existing untracked historical handoff; untouched.
- `.claude/handoffs/2026-07-31-2049-hub-native-phase1-feel-foundation.md` — pre-existing untracked historical handoff; untouched.
- `.claude/handoffs/2026-07-31-2112-hub-native-phase1-complete.md` — pre-existing untracked historical handoff; untouched.
- `.claude/handoffs/2026-08-01-2038-phase4-identity-access-path-complete.md` — pre-existing untracked historical handoff; untouched.
- `.claude/handoffs/2026-08-01-2151-phase5-workspace-isolation-complete.md` — pre-existing untracked historical handoff; untouched.
- `.claude/handoffs/2026-08-01-2239-phase6-inbound-queue-complete.md` — pre-existing untracked historical handoff; untouched.
- `.claude/handoffs/2026-08-02-0140-phase7-agent-tool-surface-complete.md` — pre-existing untracked historical handoff; untouched.
- `.claude/handoffs/2026-08-02-0300-hub-native-phase8-timeline-complete.md` — pre-existing untracked historical handoff; untouched.
- `.claude/handoffs/2026-08-02-1130-phase8-mock-fidelity-and-live-test-env.md` — pre-existing untracked historical handoff; untouched.
- `.claude/handoffs/2026-08-02-1330-waiting-reason-fix-and-phase9-next.md` — pre-existing untracked historical handoff; untouched.
- `.claude/handoffs/2026-08-02-1908-spec-readiness-and-conversation-identity.md` — pre-existing handoff carried forward; untouched this chunk.
- `.claude/handoffs/2026-08-02-2005-conversation-phase0-green-phase1-started.md` — previous checkpoint; untouched this chunk.
- `hub/hub/conversations.py` — conversation creation and scoped lookup helpers; phase 0 finished.
- `hub/hub/migrations/versions/0017_add_conversations.py` — schema and deterministic legacy backfill; phase 0 finished.
- `hub/hub/db/models.py` — Conversation and record associations; phase 0 finished.
- `hub/hub/api/v1/agent_trigger.py` — synchronous allocation, scheduling, binding/conflict, and response contract; phase 0 finished.
- `hub/hub/api/v1/agent_chat.py` — conversation list/history routes; phase 0 finished.
- `hub/hub/api/v1/agents.py` — conversation attribution for agent requests; phase 0 finished.
- `hub/hub/api/v1/messages.py` — peer-message conversation attribution; phase 0 finished.
- `hub/hub/api/v1/questions.py` — reply conversation attribution; phase 0 finished.
- `hub/hub/inbound_queue.py` — conversation-scoped queue operations; phase 0 finished.
- `hub/hub/output_recording.py` — output conversation resolution and stamping; phase 0 finished.
- `hub/hub/scheduler.py` — conversation-aware scheduled work; phase 0 finished.
- `hub/hub/turn_scheduler.py` — oldest-conversation selection and isolated draining; phase 0 finished.
- `hub/tests/conftest.py` — Conversation table cleanup in test isolation; finished.
- `hub/tests/test_conversations.py` — core stable-identity tests; implemented but task 0.1 coverage remains incomplete as noted above.
- `hub/tests/test_agent_chat.py` — conversation-routed history regressions; finished.
- `hub/tests/test_agent_output_stream.py` — conversation output/history regression; finished.
- `hub/tests/test_bola.py` — conversation-aware authorization fixture; finished.
- `hub/tests/test_inbound_queue.py` — conversation-isolated scheduling regressions; finished.
- `hub/tests/test_migrations.py` — migration head updated to 0017; broader deterministic-backfill assertion still needed for task 0.1.
- `hub/ui/src/api/agentChat.ts` — conversation types/list/history and trigger response handling; phase 0 finished.
- `hub/ui/src/lib/navigation.ts` — collection-shaped rail and typed workspace destinations; phase 1 finished.
- `hub/ui/src/App.tsx` — destination view model and full-height direct conversation route; phase 1 finished.
- `hub/ui/src/components/layout/Sidebar.tsx` — project tree, separate controls, direct agent destinations, and identity colours; phase 1 finished.
- `hub/ui/src/components/overview/OverviewPage.tsx` — roster opens conversations directly; phase 1 finished.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — parent conversation selection, single header, and back-to-project control; phase 1 finished.
- `hub/ui/src/__tests__/conversationNavigation.test.ts` — navigation adapter contracts; finished.
- `hub/ui/src/__tests__/conversationShell.test.tsx` — shell integration contracts; finished.
- `hub/ui/src/__tests__/App-mount.test.tsx` — updated reachable-page and wrapper regressions; finished.
- `hub/ui/src/__tests__/agentHandoff.test.tsx` — successor identity and single-header regression; finished.
- `openspec/changes/2026-08-02-agent-conversation-workspace/.openspec.yaml` — approved change metadata; finished.
- `openspec/changes/2026-08-02-agent-conversation-workspace/proposal.md` — approved scope and identity direction; finished.
- `openspec/changes/2026-08-02-agent-conversation-workspace/design.md` — identity, scheduling, navigation, composer, and lifecycle design; finished for current phases.
- `openspec/changes/2026-08-02-agent-conversation-workspace/tasks.md` — evidence-backed task state through phase 1; finished for current phase.
- `openspec/changes/2026-08-02-agent-conversation-workspace/specs/agent-conversation-workspace/spec.md` — workspace delta; finished.
- `openspec/changes/2026-08-02-agent-conversation-workspace/specs/agent-conversation-handoff/spec.md` — handoff delta; finished.
- `openspec/changes/2026-07-30-hub-native-experience/design.md` — pre-existing umbrella reconciliation edit; preserve.
- `openspec/changes/2026-07-30-hub-native-experience/proposal.md` — pre-existing umbrella reconciliation edit; preserve.
- `openspec/changes/2026-07-30-hub-native-experience/specs/agent-identity-and-skills/spec.md` — pre-existing umbrella delta edit; preserve.
- `openspec/changes/2026-07-30-hub-native-experience/specs/agent-tool-surface/spec.md` — pre-existing umbrella delta edit; preserve.
- `openspec/changes/2026-07-30-hub-native-experience/specs/spec-traceability/spec.md` — pre-existing umbrella delta edit; preserve.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — pre-existing umbrella task reconciliation; preserve.
- `openspec/changes/dependencies.yaml` — pre-existing deletion from corpus audit; preserve.
- `openspec/config.yaml` — pre-existing audit configuration edit; preserve.
- `openspec/explorations/2026-08-02-product-direction.md` — pre-existing product direction edit; preserve.
- `openspec/explorations/2026-08-02-spec-corpus-readiness-audit.md` — pre-existing untracked readiness audit; preserve.
- `openspec/specs/aw-spec-workflow/spec.md` — pre-existing current-spec correction; preserve.

## Key decisions

1. The App owns a typed project/page/conversation destination rather than encoding agent selection
   as an Agents-page detail state. This makes direct rail and overview navigation possible and keeps
   `conversation_id` in the workspace view model.
2. The sidebar consumes `RailProject[]` even though authentication currently exposes one project.
   A second project therefore changes adapter data, not the rail component.
3. Project expansion and project navigation are separate buttons. A single overloaded disclosure
   control was rejected because it made the required project activation ambiguous.
4. `AgentOutputPanel` remains the only conversation header owner. Adding an App-level shell header
   was rejected because it would duplicate identity and controls.
5. Agents and Messages remain implemented APIs/components but are no longer top-level navigation
   destinations. Deleting records or endpoints was outside the approved UI change.
6. Phase 0 task 0.1 remains open because explicit named test coverage matters independently of a
   green implementation. Plans and broad regressions are not substitutes for the missing assertions.

## Constraints and user directives (verbatim)

- "Great continue with what needs to be done related to specs and start phase 1"
- "Great. Let's go with that"
- "Ignore the aw-spec skills. I'm using openspec only."
- "This is not a project where we user agentweave is a project where we develop agentweave."
- "This will become local only like T3 but with spec and inter agent comunications."
- "Continue here"

## Dead ends

- Alembic batch foreign keys failed on SQLite and migration-only databases without `projects`;
  migration 0017 uses additive SQLite columns while fresh ORM schemas retain foreign keys.
- An initial `Start-Process npm` preview command failed on Windows; `npm.cmd` is required.
- `npm test -- --runInBand` is invalid for Vitest; use `npm test`.
- `ruff` and `python -m ruff` are unavailable in this environment.
- The first phase-one shell test correctly failed five assertions against the old App/Sidebar before
  implementation. It is now green; do not restore the intermediate Agents-page route.
- Broad `rg` output for phase-zero coverage was truncated. Narrow searches established that task
  0.1 still lacks explicit deterministic-backfill, binding-conflict, and reset-only-deletion tests.

## Verification

- `npm test` in `hub/ui` — 28 files, 232 tests passed.
- `npm run build` in `hub/ui` — passed; existing duplicate `case 'task_created'` warning in
  `src/lib/eventSummary.ts` remains.
- `pytest hub/tests/test_conversations.py hub/tests/test_agent_chat.py hub/tests/test_inbound_queue.py hub/tests/test_agent_output_stream.py -q` — 28 passed.
- Earlier phase-0 full Hub run: `pytest hub/tests -q` — 389 passed, 4 skipped.
- `openspec validate --all --strict --no-interactive` — 14 passed, 0 failed.
- `git diff --check` — passed; only existing CRLF-to-LF warnings for two umbrella files.
- T3 collaborative browser preview — verified project expander/name separation, direct rail agent
  activation, full-height single-header conversation, absent Agents/Messages destinations, and
  one-action back to Overview. A manually synced `claude` agent supplied the live rail row.
- Temporary preview PIDs 4356 and 23344 were stopped and
  `testbed/phase1-preview.db` was removed; post-cleanup path check returned false.

Not tested: ruff/lint (not installed); PostgreSQL migration; real provider CLI execution;
task-0.1's missing explicit lifecycle/backfill/reset contract cases. The full Hub suite was not
rerun after phase-one-only UI changes; the focused 28-test Hub set was rerun.

## Git state

Branch `hub-native-experience`, HEAD `b443a8a`, dirty and uncommitted. No upstream tracking output
was available. Product changes, OpenSpec audit edits, and historical handoffs remain mixed in the
working tree as enumerated above. No commit or push was requested. Never use `git add -A`; historical
untracked `.claude/handoffs/` files would be swept in.

## Next steps

1. Re-read `proposal.md`, `design.md`, and the workspace delta, then add failing phase-2 tests in
   `hub/ui/src/__tests__/agentHandoff.test.tsx` or a new focused composer suite asserting that the
   composer stays enabled while an agent is running, queued server responses render immediately in
   order, and failed submissions restore the typed text.
2. Implement tasks 2.2–2.3 in `AgentOutputPanel.tsx`: remove running state from submission disablement,
   always call the trigger endpoint, render the server-recorded queued entry, and restore text on failure.
3. Run the focused phase-2 suite, full UI tests/build, strict OpenSpec validation, and diff checks;
   then update only evidenced task boxes and write the phase-2 handoff.
4. Separately close phase-0 task 0.1 by adding the named backend/migration lifecycle tests; do not
   let this delay phase-2 UI work unless those tests expose an implementation defect.

## Open questions for the user

None.

## Read on resume

- `openspec/changes/2026-08-02-agent-conversation-workspace/tasks.md`
- `openspec/changes/2026-08-02-agent-conversation-workspace/design.md`
- `openspec/changes/2026-08-02-agent-conversation-workspace/specs/agent-conversation-workspace/spec.md`
- `hub/ui/src/components/agents/AgentOutputPanel.tsx`
- `hub/ui/src/__tests__/agentHandoff.test.tsx`
- `hub/ui/src/api/agentChat.ts`
