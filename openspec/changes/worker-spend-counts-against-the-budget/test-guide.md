# Test guide — worker spend counts against the budget

## Agent-verifiable

1. Group 1 fails and passes as recorded in `tasks.md`.
2. After drive 3.1, in the trial database (`mode=ro`),
   `sum(turn_usage.total_tokens where status='measured') + sum(worker_invocations.total_tokens)`
   equals `GET /accounting`'s `project.total_tokens` and `budget.used_tokens`.
3. Drive 3.2 shows no title spawn at exhaustion (a `budget_exhausted` row, the title unchanged) and
   an operator checkpoint that ran (an `ok` row, counted).
4. Migration `0106` on a copy of a real database: `total_tokens` is backfilled for every row with
   usage and null for the rest, and the row count is unchanged. **Never run it against `:8000`'s
   database.** Copy the file first.

## Human-only

1. Settings, then Budgets: are the worker lines (checkpoint, probe, titles) understandable next to
   the agent chips, without knowing what a "worker" is?
2. With the budget exhausted, the notice still reads *"Autonomous turns are paused; operator
   messages can still run."* Is that now true of everything you see spending?
3. After your `:8000` restarts on this migration, your LoopEngine total rises by about 962k tokens,
   which is the backfilled checkpoint spend. Is that surprising, or expected?
