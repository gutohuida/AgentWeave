# Implementation plan

## Working protocol

1. Re-read `proposal.md`, `design.md`, and `specs/usage-accounting/spec.md` before each phase.
2. Add or update tests before implementation within each phase.
3. Mark tasks complete only after named verification passes.
4. Commit each completed phase and write a durable handoff at each phase boundary.

## 0. Durable accounting model

- [ ] 0.1 Add migration/model tests for project token budget, run initiator, and one-to-one turn
      usage with measured/unavailable status.
- [ ] 0.2 Implement the schema and migration.
- [ ] 0.3 Verify the durable per-turn accounting scenarios.
- [ ] 0.4 Write handoff and commit the phase.

## 1. Runner normalization and recording

- [ ] 1.1 Add fixture tests for Claude result usage/modelUsage, Codex turn and token-count shapes,
      OpenCode step telemetry, allowance, and malformed/missing telemetry.
- [ ] 1.2 Implement runner-neutral accounting samples without changing context-meter semantics.
- [ ] 1.3 Record exactly one measured or unavailable outcome when each Hub-owned run ends.
- [ ] 1.4 Verify parser and run-recording scenarios.
- [ ] 1.5 Write handoff and commit the phase.

## 2. Aggregation and API

- [ ] 2.1 Add API tests for project/agent totals, unavailable counts, allowance precedence,
      API-equivalent labelling, and budget validation.
- [ ] 2.2 Implement aggregation and project-scoped accounting routes.
- [ ] 2.3 Verify accounting presentation scenarios.
- [ ] 2.4 Write handoff and commit the phase.

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

