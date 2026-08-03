# Handoff: composer-intelligence phase 5 complete

**Date:** 2026-08-03T01:01:55.1215218+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `f38e2a9`
**Agent:** Codex GPT-5.6
**Previous handoff:** `.claude/handoffs/2026-08-02-2331-agent-conversation-workspace-archived.md`
**Status:** chunk complete

## Goal
Finish the entire active `2026-07-30-hub-native-experience` umbrella. The immediate tranche is to
finish, verify, spec-sync, and archive `openspec/changes/composer-intelligence/`; afterward reconcile
and implement every genuinely remaining umbrella slice until the umbrella itself can be archived.

## Current state
Composer-intelligence phases 0–5 are implemented and committed. Phase 5 adds a searchable in-place
agent selector backed by the existing launchability endpoint. A cross-agent submission omits the
open conversation ID, targets the chosen agent, and asks the App workspace to navigate to the new
agent/conversation; the original conversation scope remains immutable. Phase 6 integration, full
verification, live testbed testing, spec sync, and archival remain.

## Files touched
- `hub/ui/src/api/agents.ts` — launchability response types and React Query hook; finished.
- `hub/ui/src/components/agents/ComposerAgentSelector.tsx` — searchable selector with visible launchability states; finished.
- `hub/ui/src/components/agents/Composer.tsx` — selector embedded in composer chrome; finished.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — target-agent state and cross-agent submission routing; finished.
- `hub/ui/src/App.tsx` — navigates to the new agent/conversation after redirected submission; finished.
- `hub/ui/src/__tests__/composerAgentSelector.test.tsx` — list/state/search/select coverage; finished.
- `hub/ui/src/__tests__/conversationControls.test.tsx` — cross-agent request and immutable old-conversation assertion; finished.
- `hub/ui/src/__tests__/agentHandoff.test.tsx` — mocks new composer data hooks; finished.
- `hub/ui/src/__tests__/agentRunningComposer.test.tsx` — mocks new composer data hooks; finished.
- `openspec/changes/composer-intelligence/tasks.md` — phase 5 checked with verification evidence; finished through 5.4.

## Key decisions
1. Cross-agent selection starts a new conversation with no `conversation_id`; mutating the old
   conversation was rejected because it violates the shipped immutable-scope contract.
2. `AgentOutputPanel` owns transient target-agent state while `App` owns navigation after successful
   redirection. Keeping the new conversation ID under the old agent panel was rejected because its
   chat queries are agent-scoped.
3. The selector shows non-launchable agents with an explanatory state; hiding them was rejected by
   the OpenSpec requirement.
4. Continue through the whole umbrella after composer archival; the user explicitly expanded the
   earlier composer-only terminal scope.

## Constraints and user directives (verbatim)
- "Go"
- "I want you to work on the entire umbrella project with the same parameters that we discussed previously"
- "At the end of every implementation run handoff aaand spawn a new run with the skill resume."
- "Ignore the aw-spec skills. I'm using openspec only."
- "This is not a project where we user agentweave is a project where we develop agentweave."
- "commit each completed task/checkpoint without asking first"

## Dead ends
- Raw detached `Start-Process codex exec` probes split quoted prompt arguments on Windows. The
  foreground `codex exec` mechanism works, but this run is continuing in T3 with durable handoffs
  and automatic context compaction rather than recursive background processes.
- Running `npm` from the repository root fails because `package.json` is under `hub/ui`; always use
  the `hub/ui` working directory.
- The shell's default `python` points to a Hermes environment without pytest. Use
  `.venv/Scripts/python.exe -m pytest` from the repository root.
- Phase-4 production wiring initially broke older panel unit tests because the new query hook was
  not mocked. Phase 5 corrected the affected suites; full-suite verification must confirm no other
  missed mocks.

## Verification
- `npm test -- --run src/__tests__/composerAgentSelector.test.tsx src/__tests__/conversationControls.test.tsx src/__tests__/agentHandoff.test.tsx src/__tests__/agentRunningComposer.test.tsx` from `hub/ui`: 4 files, 17 tests passed.
- `.venv/Scripts/python.exe -m pytest hub/tests/test_conversation_contract.py -q` from repo root: 8 passed.
- `npm run build` from `hub/ui`: passed; existing duplicate-case warning in `src/lib/eventSummary.ts` remains unrelated.
- Full UI suite was run once: 281/285 passed. Three failures were missing hook mocks and are now fixed; the fourth was the known nondeterministic `agentChat.test.tsx` timing assertion. Full suite has not yet been rerun after the mock fixes.
- Not tested: full Hub backend suite; live browser/testbed flow; OpenSpec strict validation; spec sync/archive.

## Git state
Branch `hub-native-experience`, HEAD `f38e2a9`, clean before writing this handoff. No upstream
tracking branch; commits are not pushed. Stage paths explicitly; never use `git add -A`.

## Next steps
1. From `hub/ui`, rerun `npm test -- --run`; classify any remaining failures and fix real regressions.
2. Complete phase 6 integration evidence, run the full Hub suite with `.venv/Scripts/python.exe`, and run `npm run build`.
3. Start the Hub/UI only under `testbed/`, use T3 preview tools for the manual `@`, `$`, `/`, and agent-selector flow, and fix findings.
4. Check phase 6 tasks, sync `agent-composer` into `openspec/specs/`, validate strictly, archive `composer-intelligence`, then reconcile the umbrella.

## Open questions for the user
None.

## Read on resume
- `openspec/changes/composer-intelligence/tasks.md`
- `openspec/changes/composer-intelligence/design.md`
- `openspec/changes/composer-intelligence/specs/agent-composer/spec.md`
- `hub/ui/src/components/agents/AgentOutputPanel.tsx`
- `hub/ui/src/components/agents/Composer.tsx`
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md`
