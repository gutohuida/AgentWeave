# Accounting and budgets — phase 0 complete

## Scope and intent

The terminal objective is the entire active `2026-07-30-hub-native-experience` umbrella. The
current dependency-safe successor is `openspec/changes/accounting-and-budgets/`; its proposal,
design, task plan, and `usage-accounting` delta validated strictly and were committed as `720d35d`.
Do not use AgentWeave `aw-*` workflows in this framework repository. Continue directly with
OpenSpec, commit each verified phase, and keep root free of `.agentweave/`, `agentweave.yml`, and
`spec/` state.

## Completed phase 0

- `Project.token_budget`: nullable integer; `null` means disabled.
- `Run.initiator`: constrained `operator | autonomous`, default/backfill `operator`.
- `TurnUsage`: one row per `Run.id`, measured or unavailable, normalized token dimensions,
  runner/model, API-equivalent USD micros, allowance JSON, and timestamp.
- Database constraints reject a second usage row for a run and prevent unavailable outcomes from
  containing fabricated token operands.
- Alembic `0018_add_turn_accounting.py` upgrades an existing 0017 database defensively and also
  leaves the additive fresh-Alembic path valid.
- Migration expectations in `test_migrations.py` now point to head 0018.

## Verification

```text
.venv\Scripts\python.exe -m pytest hub/tests/test_accounting_model.py hub/tests/test_migrations.py -q
15 passed, 1 skipped

.venv\Scripts\python.exe -m ruff check hub/hub/db/models.py \
  hub/hub/migrations/versions/0018_add_turn_accounting.py \
  hub/tests/test_accounting_model.py hub/tests/test_migrations.py
All checks passed

git diff --check
passed
```

## Next exact work

Start phase 1 with tests in `hub/tests/test_runner_parsing.py` for a new accounting sample separate
from `ContextUsageSample`:

1. Claude final `result.usage` preferred over partial assistant usage; `modelUsage` fallback;
   preserve top-level `total_cost_usd` and rate-limit allowance when reported.
2. Codex `turn.completed.usage` plus persisted `event_msg.payload.type=token_count` request-delta
   normalization.
3. OpenCode completed-step `tokens`/`cost` telemetry normalization (parser only; Hub launch remains
   out of scope).
4. `_execute_run` retains the final accounting sample and writes exactly once after exit; if none,
   write an unavailable `TurnUsage`. The existing context-warning recording path must remain
   unchanged.

Use a small helper module (for example `hub/hub/usage_accounting.py`) for idempotent record creation
and later aggregation. Add run-recording tests by invoking the helper directly and, where valuable,
the existing mocked direct-run path. Then mark phase 1, run targeted tests/Ruff, hand off, and
commit.

