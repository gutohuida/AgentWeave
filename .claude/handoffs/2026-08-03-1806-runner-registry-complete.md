# Handoff: Runner registry complete; charter phase next

**Date:** 2026-08-03T18:06:16+01:00 · **Branch:** hub-native-experience · **HEAD:** c6ec436
**Agent:** Codex gpt-5.6-sol (T3 Code)
**Previous handoff:** .claude/handoffs/2026-08-03-1615-runner-agent-charter-proposed.md
**Status:** chunk complete

## Goal

Complete the entire Hub-native-experience umbrella, one independently proposed successor at a
time. The active successor is `runner-agent-charter-separation`: separate reusable execution
capability (Runner), addressable identity (Agent), and authored behavior (Charter), then remove the
legacy role system.

## Current state

The prior handoff was stale when resumed: HEAD had advanced through phase 0 (`6538a95`) and runner
registry tasks 1.1–1.3 (`610870c`), while Claude had left task 1.4's UI/API integration partially
written and uncommitted. This session reconciled that partial work, completed the missing runner
picker, fixed the directly affected frontend test setup, ran focused and full regressions, updated
tasks 1.4–1.5 as verified, and committed phase 1 as `c6ec436`.

Phases 0 and 1 of `runner-agent-charter-separation` are complete. Phase 2 (Agent charter) has not
started. Its first action is task 2.1: add failing charter CRUD and seed tests before implementing
the API or seed path.

## Files touched

- `hub/hub/api/v1/agents.py` — finished; agent-list summaries expose bound `runner_id` and
  `charter_id`.
- `hub/hub/schemas/agents.py` — finished; `AgentSummary` declares the two binding IDs.
- `hub/tests/test_runners_api.py` — finished; regression asserts list responses surface an agent's
  bound runner ID.
- `hub/ui/src/App.tsx` — finished; registers the Runners page.
- `hub/ui/src/__tests__/conversationControls.test.tsx` — finished; mocks runner hooks for the
  isolated agent-details test, which does not mount the app-level QueryClient provider.
- `hub/ui/src/api/agents.ts` — finished; frontend `AgentSummary` includes runner/charter bindings.
- `hub/ui/src/api/runners.ts` — finished; React Query hooks for runner CRUD and agent binding.
- `hub/ui/src/components/agents/AgentInfoTab.tsx` — finished; runner picker supports bind, unbind,
  loading, pending, and error states.
- `hub/ui/src/components/layout/Sidebar.tsx` — finished; adds Runners navigation.
- `hub/ui/src/components/runners/RunnersPage.tsx` — finished; runner list/create/edit/delete UI.
- `openspec/changes/runner-agent-charter-separation/tasks.md` — finished for phase 1; tasks 1.4 and
  1.5 now record implementation and actual verification.
- `src/agentweave/templates/skills/handoff.md` — pre-existing unrelated untracked file, untouched;
  preserve for its owning session.
- `src/agentweave/templates/skills/resume.md` — pre-existing unrelated untracked file, untouched;
  preserve for its owning session.
- `tests/test_handoff_resume_templates.py` — pre-existing unrelated untracked file, untouched;
  preserve for its owning session.

## Key decisions

- Preserved Claude's partial phase 1.4 work rather than restarting it because the live diff clearly
  matched the next unchecked task and only this Codex process plus its host were active.
- The runner picker lives in the existing agent detail view and binds through the Hub API; it does
  not mutate legacy `agent.config` runner keys. This follows phase 1.3's decision that the explicit
  Runner binding is authoritative.
- Added `runner_id` and `charter_id` to agent list summaries because the detail UI consumes the
  roster `AgentSummary`; creating a separate per-agent fetch would duplicate server state and add
  an unnecessary request.
- Kept CLI immutable in the edit form. Runner creation chooses `claude` or `codex`; editing changes
  operator-facing name/model only. The API remains the source of validation.
- Did not fix the repository-wide ESLint configuration during this phase. `npm run lint` cannot
  start under installed ESLint 9 because no `eslint.config.*` exists; this is unrelated tooling
  debt, while TypeScript production build and all frontend tests pass.

## Constraints and user directives (verbatim)

> "I want you to work on the entire umbrella project with the same parameters that we discussed
> previously"

> "Ignore the aw-spec skills. I'm using openspec only."

> "At the end of every implementation run handoff aaand spawn a new run with the skill resume."

> "I launched it to continue on your work because I ran out of token. ... I'm in control right now"

No root AgentWeave state. Exercise product commands only in `testbed/`. Never mark a task complete
from a plan; only verified implementation closes it. Do not overlap sessions in this working tree;
the user controls when the follow-on session starts.

## Dead ends

- The inherited UI referenced `RunnerPicker` without defining it, so `npm run build` initially
  failed with TS2304 and unused-import errors. Defining the picker completed the partial work.
- The first full frontend test run failed one conversation-controls test because that isolated test
  rendered agent details without a QueryClient provider. It was not a product bug: the real app
  mounts the provider in `main.tsx`. Mocking the newly introduced runner hooks in that isolated test
  restored the intended boundary; the full suite then passed.
- `npm run lint` cannot start: ESLint 9 reports that it cannot find `eslint.config.js|mjs|cjs`.
  Do not report lint as passed. Fix only if a later task explicitly takes on frontend tooling.
- Calling `python -m pytest` used the Hermes agent virtual environment, which lacks pytest. Use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\Scripts\pytest.exe` in this environment.

## Verification

- `pytest.exe hub/tests/test_runners_api.py -q` — 11 passed.
- `pytest.exe hub/tests -q` — 470 passed, 4 skipped, 10 warnings in 107.80s.
- `npm run build` in `hub/ui` — passed (`tsc && vite build`); existing duplicate-case warning in
  `src/lib/eventSummary.ts` remains unrelated.
- `npm run test` in `hub/ui` — 36 files passed, 289 tests passed.
- `git diff --check` and `git diff --cached --check` — passed before commit.
- `npm run lint` — did not run tests; command failed before linting due missing ESLint 9 flat config.

Not tested in this phase: browser/manual UI interaction, live Hub boot in `testbed/`, charter
behavior, full CLI suite, or strict OpenSpec validation. Those remain for later tasks (especially
phase 5).

## Git state

Branch `hub-native-experience`, HEAD `c6ec436` (`runner/agent/charter phase 1.4-1.5: runner UI and
verification`). No tracked diff. The only working-tree entries are the three pre-existing unrelated
untracked handoff-template files listed above. `origin/hub-native-experience` was not available (the
ahead query returned no commits), so pushed/unpushed status is unknown.

## Next steps

1. Re-read the three delta specs under
   `openspec/changes/runner-agent-charter-separation/specs/`, then add failing charter API and seed
   tests for task 2.1 in a new `hub/tests/test_charters_api.py`; cover CRUD, seed-from-every
   `hub/data/roles/*.md` guide, and restart idempotence before changing production code.
2. Implement `/api/v1/charters` schemas/router plus the one-time seed in Hub DB initialization,
   keeping seed source files until legacy deletion phase 4.
3. Rewire Hub agent context resolution to bound `charter_id`, including the no-charter notice, then
   build Charter UI and the agent charter picker.
4. Verify phase 2 with focused/full Hub and frontend regressions, update tasks 2.1–2.5, commit, and
   write the next durable handoff.

## Open questions for the user

None.

## Read on resume

- `openspec/changes/runner-agent-charter-separation/tasks.md`
- `openspec/changes/runner-agent-charter-separation/specs/agent-charter/spec.md`
- `openspec/changes/runner-agent-charter-separation/specs/agent-context-onboarding/spec.md`
- `hub/hub/db/engine.py`
- `hub/hub/api/v1/agents.py`
- `hub/tests/test_runners_api.py`
