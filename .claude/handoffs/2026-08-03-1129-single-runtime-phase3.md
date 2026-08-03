# Handoff: Single runtime phase 3 spec reconciliation complete

**Date:** 2026-08-03T11:29:00+01:00 · **Branch:** hub-native-experience · **HEAD:** f384df8
**Agent:** Codex gpt-5.6-sol
**Previous handoff:** .claude/handoffs/2026-08-03-0245-agent-capability-plane-closed.md
**Status:** chunk complete

## Goal

Complete the Hub-native-experience umbrella one independently proposed successor at a time. The
current successor, `single-runtime`, makes the native Hub the only runtime and deletes the legacy
watchdog, local/git transports, and collaboration CLI surface.

## Current state

Single-runtime phases 0–2 are committed. Phase 3 merged all nine delta specs into the authoritative
main specs, created `app-lifecycle`, retired the obsolete `opencode-runner` main spec, and passes
strict OpenSpec validation. Scenario review exposed two semantic gaps that phase 4 must resolve
before archive: `doctor` does not yet implement the new app-lifecycle readiness contract, and
retained requirements in two main specs still name deleted commands.

## Files touched

- `openspec/changes/single-runtime/tasks.md` — phase 3 checked off with explicit non-conformance notes; finished.
- `openspec/specs/app-lifecycle/spec.md` — new authoritative lifecycle spec; finished merge.
- `openspec/specs/agent-context-onboarding/spec.md` — applied Hub-trigger wording delta; merge finished, one retained `activate` scenario remains stale.
- `openspec/specs/agent-context-usage/spec.md` — removed OpenCode/Copilot/watchdog requirements per delta; finished.
- `openspec/specs/agent-stream-events/spec.md` — applied single-runtime removals/modifications; finished.
- `openspec/specs/agent-tool-surface/spec.md` — removed CLI adapter requirements; finished.
- `openspec/specs/opencode-runner/spec.md` — deleted because the delta removes all requirements; finished.
- `openspec/specs/project-instructions/spec.md` — removed init/local-file requirements; finished.
- `openspec/specs/runtime-diagnostics/spec.md` — applied Hub-owned diagnostic deltas; merge finished, retained activate/switch/run scenarios remain stale.
- `openspec/specs/spec-manifest-sync/spec.md` — removed watchdog/manual push synchronization requirements; finished.
- `openspec/specs/trace-timeline/spec.md` — removed watchdog wording; finished.
- `.claude/handoffs/2026-08-03-1129-single-runtime-phase3.md` — this handoff.
- `.claude/handoffs/LATEST.md` — advanced to this handoff.

## Key decisions

- Phase 3 was not treated as successful merely because OpenSpec parsed. The scenario audit recorded
  the semantic failures explicitly so phase 4 cannot archive a false contract.
- Existing edits from the interrupted prior run were preserved and verified rather than recreated.
- The stale retained requirements were not silently deleted outside the approved delta; phase 4
  must reconcile their spec intent and implementation together.

## Constraints and user directives (verbatim)

> "I want you to work on the entire umbrella project with the same parameters that we discussed previously"

> "Ignore the aw-spec skills. I'm using openspec only."

> "At the end of every implementation run handoff aaand spawn a new run with the skill resume."

No root AgentWeave state. Run product-state tests only under `testbed/` or a throwaway directory.
Never mark implementation complete from a plan alone.

## Dead ends

- Ruff remains unavailable.
- Hub and CLI files named `test_mcp_server.py` collide if collected in one pytest process; run suites separately.
- `hub/ui` has no ESLint flat config; use Vitest and the TypeScript/Vite build.

## Verification

- `openspec validate single-runtime --strict` — passed.
- `openspec validate --all --strict` — 19 passed, 0 failed.
- `git diff --check` — passed.
- Scenario grep/code inspection confirmed the five-command parser, deleted transports/watchdog,
  Hub launchability CLI detection, and typed 409 refusal.
- Not run in this phase: Python, Hub, or frontend regressions; live app launch; real agent spawn.

## Git state

Branch `hub-native-experience`, pre-phase-3-commit HEAD `f384df8`. Phase-3 spec and handoff files are
staged/committed by the commit that contains this handoff. Upstream status was unavailable.

## Next steps

1. Reconcile `openspec/specs/app-lifecycle/spec.md`'s doctor requirements with
   `src/agentweave/diagnostics.py`: replace deleted local-session/project-config checks with the
   specified Python, runner CLI, port, database, and permission readiness checks and add tests first.
2. Amend the single-runtime delta and authoritative specs for retained `activate`/`switch`/`run`
   scenarios in `agent-context-onboarding` and `runtime-diagnostics`, mapping them to Hub-owned flows
   or removing obsolete requirements with explicit OpenSpec deltas.
3. Run phase 4 full regressions, real throwaway live verification, docs cleanup, strict validation,
   then archive the successor and annotate umbrella task 16.2.

## Open questions for the user

None.

## Read on resume

- openspec/changes/single-runtime/tasks.md
- openspec/changes/single-runtime/specs/app-lifecycle/spec.md
- openspec/specs/runtime-diagnostics/spec.md
- openspec/specs/agent-context-onboarding/spec.md
- src/agentweave/diagnostics.py
- tests/test_diagnostics.py
