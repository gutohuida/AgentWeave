# Accounting and budgets — phase 2 complete

## Objective and protocol

Continue to completion of the entire active Hub-native umbrella. The focused successor
`accounting-and-budgets` now has phases 0–2 complete. Work directly with OpenSpec in this framework
repo; never initialize AgentWeave here. Commit every verified phase and preserve unrelated work.

## Phase 2 result

- `GET /api/v1/accounting` is project-auth scoped and returns:
  - project token/cost totals with measured and unavailable turn counts;
  - alphabetized per-agent totals;
  - optional budget limit, used, remaining, and exhausted state;
  - bounded recent immutable turn outcomes;
  - a preferred display: latest allowance first, otherwise runner-reported
    `API-equivalent estimate`, otherwise tokens, otherwise unavailable.
- `PATCH /api/v1/accounting/budget` enables a positive token limit or disables it with null;
  zero/negative values return 422.
- Aggregation is derived with SQL from `TurnUsage`; no mutable counters, price catalog, historical
  guess, or cross-project data.
- An agent with only unavailable outcomes has `total_tokens: null`, never zero.

## Verification

```text
.venv\Scripts\python.exe -m pytest hub/tests/test_accounting_api.py -q
5 passed

.venv\Scripts\python.exe -m pytest hub/tests -q
425 passed, 4 skipped

targeted Ruff + git diff --check
passed
```

## Next exact work — phase 3

Implement autonomous budget enforcement, tests first.

1. Extend queue origin to `job` with migration 0019. Update its check constraints and
   `new_entry` validation/formatting: operator forbids origin_agent, agent requires it, job forbids
   it. Scheduled jobs must enqueue `origin_type="job"` instead of the current misleading operator.
2. In `turn_scheduler.schedule_agent`, after selecting the same-conversation batch:
   - initiator is `operator` if any selected entry has origin `operator`, otherwise `autonomous`;
   - fetch accounting budget state before delivery;
   - if exhausted and autonomous, return `token budget exhausted` without changing entry state;
   - operator selection bypasses this gate only.
3. Pass the initiator into `trigger_agent_directly` and persist it on `Run`.
4. Add scheduler/job tests proving:
   - agent-origin batch stays queued and no Run exists at exhaustion;
   - job-origin batch behaves identically and is not operator-labelled;
   - operator input starts even while exhausted and resulting Run.initiator is operator;
   - an autonomous run below budget persists autonomous;
   - disabling/increasing the budget lets retained work start.
5. Update every queue-origin assertion/fixture affected by the new enum, run targeted suites and
   full Hub tests, hand off, and commit phase 3.

