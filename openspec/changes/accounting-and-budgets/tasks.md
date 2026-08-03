# Implementation plan

## Working protocol

1. Re-read `proposal.md`, `design.md`, and `specs/usage-accounting/spec.md` before each phase.
2. Add or update tests before implementation within each phase.
3. Mark tasks complete only after named verification passes.
4. Commit each completed phase and write a durable handoff at each phase boundary.

## 0. Durable accounting model

- [x] 0.1 Add migration/model tests for project token budget, run initiator, and one-to-one turn
      usage with measured/unavailable status.
- [x] 0.2 Implement the schema and migration. `Project.token_budget`, `Run.initiator`, and
      `TurnUsage` are added by migration 0018 with availability and one-row-per-run constraints.
- [x] 0.3 Verify the durable per-turn accounting scenarios. Accounting-model and migration suites:
      15 passed, 1 skipped; targeted Ruff and `git diff --check` pass.
- [x] 0.4 Write handoff and commit the phase. Handoff:
      `.claude/handoffs/2026-08-03-0124-accounting-phase0-model.md`.

## 1. Runner normalization and recording

- [x] 1.1 Add fixture tests for Claude result usage/modelUsage, Codex turn and token-count shapes,
      OpenCode step telemetry, allowance, and malformed/missing telemetry.
- [x] 1.2 Implement runner-neutral accounting samples without changing context-meter semantics.
      `AccountingSample` is separate from `ContextUsageSample`; Codex rollout request deltas
      supersede potentially cumulative stdout totals.
- [x] 1.3 Record exactly one measured or unavailable outcome when each Hub-owned run ends.
      `record_turn_usage` is idempotent and the direct-run completion/spawn-failure paths call it.
- [x] 1.4 Verify parser and run-recording scenarios. Targeted runner, model, and direct-trigger
      suites: 72 passed; targeted Ruff, `git diff --check`, and strict change validation pass.
- [x] 1.5 Write handoff and commit the phase. Handoff:
      `.claude/handoffs/2026-08-03-0131-accounting-phase1-runner-usage.md`.

## 2. Aggregation and API

- [x] 2.1 Add API tests for project/agent totals, unavailable counts, allowance precedence,
      API-equivalent labelling, and budget validation.
- [x] 2.2 Implement aggregation and project-scoped accounting routes. `GET /api/v1/accounting`
      derives facts from immutable rows; `PATCH /api/v1/accounting/budget` accepts positive or null.
- [x] 2.3 Verify accounting presentation scenarios. Focused API suite: 5 passed; full Hub suite:
      425 passed, 4 skipped; targeted Ruff and `git diff --check` pass.
- [x] 2.4 Write handoff and commit the phase. Handoff:
      `.claude/handoffs/2026-08-03-0135-accounting-phase2-api.md`.

## 3. Autonomous budget enforcement

- [ ] 3.1 Add scheduler tests proving agent and scheduled-job entries pause at exhaustion while
      operator turns still start and queued entries remain durable.
- [ ] 3.2 Add explicit job origin and persisted run initiator; enforce the budget before delivery.
- [ ] 3.3 Verify autonomous/operator budget scenarios.
- [ ] 3.4 Write handoff and commit the phase.

## 4. Operator UI and integration

- [ ] 4.1 Add frontend tests for totals, unavailable usage, allowance/API-equivalent wording, and
      exhausted-budget messaging.
- [ ] 4.2 Add the accounting API hook and project/conversation presentation.
- [ ] 4.3 Run full Hub backend tests, full frontend tests, production build, and strict OpenSpec
      validation.
- [ ] 4.4 Sync the authoritative capability spec, archive this change, annotate umbrella phase 9,
      write final slice handoff, and commit.
