# Accounting and budgets — phase 1 complete

## Current objective

Continue through the entire `2026-07-30-hub-native-experience` umbrella. The active successor is
`openspec/changes/accounting-and-budgets/`; phases 0 and 1 are complete. Do not run AgentWeave or
`aw-*` workflows at repo root. Use OpenSpec directly, test first, commit verified phase boundaries,
and keep `.claude/handoffs/LATEST.md` current.

## What phase 1 delivered

- `hub/hub/runner_events.py`: `AccountingSample`, intentionally independent of the existing
  context-window `ContextUsageSample`; merge retains allowance while final totals supersede partial
  telemetry.
- `hub/hub/runner_parsing.py`:
  - Claude final `result.usage` is authoritative; sums distinct cache input into normalized input;
    `modelUsage` is a fallback; top-level cost becomes integer USD micros.
  - Claude `rate_limit_event` preserves runner allowance.
  - Codex `turn.completed.usage` normalizes stdout, and `event_msg/token_count` normalizes
    `last_token_usage`, never cumulative `total_token_usage`.
  - `read_codex_rollout_accounting` resolves the matching session under `CODEX_HOME/sessions` and
    selects the latest request delta. The direct execution loop prefers this over cumulative
    resumed-thread stdout.
  - OpenCode `step_finish.part.tokens` normalization retains cache/reasoning/cost. This parser is
    ready for its future direct runner; launchability itself remains out of scope.
- `hub/hub/usage_accounting.py`: idempotent one-row-per-run recorder; missing telemetry writes an
  unavailable outcome with null operands.
- `hub/hub/api/v1/agent_trigger.py`: writes accounting atomically with terminal run state for normal
  completion and writes unavailable on spawn failure.
- Tests assert measured direct Codex execution, unavailable Claude execution, parser fixtures,
  rollout delta precedence, OpenCode telemetry, allowance merging, and recorder idempotence.

## Verification

```text
.venv\Scripts\python.exe -m pytest hub/tests/test_runner_parsing.py \
  hub/tests/test_accounting_model.py hub/tests/test_agent_trigger.py -q
72 passed

.venv\Scripts\python.exe -m ruff check <all phase-1 Python files>
All checks passed

git diff --check
passed

openspec validate accounting-and-budgets --strict --no-interactive
valid
```

## Next exact work — phase 2

Build aggregation and the project-scoped API, tests first.

1. Add `hub/tests/test_accounting_api.py` covering:
   - measured sums by agent and project;
   - measured/unavailable counts;
   - recent turn serialization (`unavailable` has null total, not zero);
   - allowance display precedence over cost;
   - cost display labelled exactly `API-equivalent estimate`;
   - budget state for disabled/configured/exhausted;
   - PATCH accepts positive integer or null and rejects zero/negative;
   - auth/project isolation.
2. Add a focused aggregation service (likely extend `usage_accounting.py`) using SQL aggregates
   from `TurnUsage`, not mutable counters.
3. Add `hub/hub/api/v1/accounting.py`, register it in `api/v1/__init__.py`, and keep all routes
   behind `Depends(get_project)`.
4. Return project totals, sorted agent totals, budget state, preferred display, and bounded recent
   turns. Do not introduce a model price catalog.
5. Run targeted tests/Ruff, update tasks, hand off, and commit phase 2.

