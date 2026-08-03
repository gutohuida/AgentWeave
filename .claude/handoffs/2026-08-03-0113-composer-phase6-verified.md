# Handoff: composer-intelligence phase 6 verified

**Date:** 2026-08-03T01:13:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `60c0de9`
**Agent:** Codex GPT-5.6
**Previous handoff:** `.claude/handoffs/2026-08-03-0101-composer-phase5-complete.md`
**Status:** chunk complete

## Goal
Finish and archive the `composer-intelligence` slice, then continue through every genuinely
remaining slice of the active `2026-07-30-hub-native-experience` umbrella until it is verified and
archived.

## Current state
Composer-intelligence phases 0–6 are implemented and verified. All functional tasks are complete;
only spec sync, strict OpenSpec validation, archival, and umbrella reconciliation remain. Live T3
preview verification under `testbed/scratch` found and fixed the generated-skill directory naming
case. The pre-existing `agentChat.test.tsx` transient-state flake was replaced with deterministic
request-gating coverage.

## Files touched
- `hub/ui/src/lib/composerTriggerSources.ts` — maps `<skill>/SKILL.md` to `<skill>` while retaining flat-file support; finished.
- `hub/ui/src/__tests__/composerTriggerSources.test.ts` — real generated directory-layout fixture; finished.
- `hub/ui/src/__tests__/composerTriggerMenu.test.tsx` — real generated directory-layout fixture; finished.
- `hub/ui/src/__tests__/agentChat.test.tsx` — deterministic enabled/disabled request assertions; finished.
- `openspec/changes/composer-intelligence/specs/agent-composer/spec.md` — generated skill-directory scenario; finished as delta.
- `openspec/changes/composer-intelligence/tasks.md` — 6.1–6.3 checked with evidence; 6.4 checked in the handoff commit.

## Key decisions
1. Support both `.claude/skills/<name>/SKILL.md` and legacy flat `.md` skills; supporting only the
   proposal's flat example was rejected after live testbed evidence showed the shipped generator
   uses directories.
2. Replace the flaky query-status timing assertion with URL-specific fetch evidence. Waiting for a
   transient `fetching` state was rejected because a fast request legitimately transitions to idle.
3. Do not send a real cross-agent message during manual verification; automated integration tests
   already assert the request body and immutable scope, while live verification safely confirmed
   real roster, launchability, search, and selection behavior.

## Constraints and user directives (verbatim)
- "Go"
- "I want you to work on the entire umbrella project with the same parameters that we discussed previously"
- "Ignore the aw-spec skills. I'm using openspec only."
- "This is not a project where we user agentweave is a project where we develop agentweave."
- "commit each completed task/checkpoint without asking first"

## Dead ends
- `testbed/scratch` initially inherited the repository's parent Git root and is entirely ignored,
  so workspace listing returned no paths. Initializing a disposable nested Git repository there
  provided realistic tracked/generated paths without polluting the framework root.
- T3 preview `type` with `clear: true` leaves the cursor behavior unsuitable for trigger detection;
  Ctrl+A followed by literal typing correctly emits the real keyboard/input sequence.
- The shell default Python lacks pytest. Use `.venv/Scripts/python.exe`.

## Verification
- `npm test -- --run` from `hub/ui`: 35 files, 285 tests passed.
- `.venv/Scripts/python.exe -m pytest hub/tests -q`: 405 passed, 4 skipped, 16 warnings.
- `npm run build` from `hub/ui`: passed; unrelated duplicate-case warning remains in `eventSummary.ts`.
- T3 preview against Hub 8000 + Vite 5173 from `testbed/scratch`: `@agent` real paths; `$aw`
  generated names; `/mod` → Tab → `/model` with cursor/focus retained; agent launchability and
  search/selection verified.
- Not yet run: strict OpenSpec validation after main-spec sync; archive command.

## Git state
Branch `hub-native-experience`, HEAD `60c0de9`, clean before this handoff. No upstream tracking
branch; not pushed. Testbed contents are ignored. Stage paths explicitly; never use `git add -A`.

## Next steps
1. Copy the completed ADDED requirements from `openspec/changes/composer-intelligence/specs/agent-composer/spec.md` into a new authoritative `openspec/specs/agent-composer/spec.md` with a Purpose section.
2. Run `openspec validate --all --strict --no-interactive`, archive with `--skip-specs -y`, and verify the resulting archive directory name before committing.
3. Read the umbrella design slice table and tasks, reconcile completed/superseded work against archived changes, then start the next genuinely open slice.

## Open questions for the user
None.

## Read on resume
- `openspec/changes/composer-intelligence/tasks.md`
- `openspec/changes/composer-intelligence/specs/agent-composer/spec.md`
- `openspec/changes/2026-07-30-hub-native-experience/design.md`
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md`
- `openspec/specs/agent-conversation-workspace/spec.md`
