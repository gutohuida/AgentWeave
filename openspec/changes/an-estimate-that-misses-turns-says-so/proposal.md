# Proposal — an estimate that misses turns says so

Finding: **F62 (C)**. Bundle B7 (models and budget), R1, 2026-09-24. Built on the recommended
answer to **D7's second question** (*"Is Codex priced from tokens, or are totals marked
partial?"*): **marked partial. Nothing is priced from tokens.**

## Why

The money figure the Hub shows is summed from whatever each CLI reported:
`func.sum(TurnUsage.api_equivalent_usd_micros)` (`hub/hub/usage_accounting.py:95`). SQL `SUM`
skips `NULL`, so every turn with no reported cost is **silently left out**, and the total still
renders as though it were complete: `$X API-equivalent estimate` (`accountingDisplay.ts:42-43`,
reached from `preferred_display` at `usage_accounting.py:170-175`).

Which turns have no cost, re-verified against the code today:

- **Every Codex turn.** Neither Codex path passes a cost. The exec JSON stream uses
  `_accounting_from_dimensions(usage, …)` with no `cost_usd` (`runner_parsing.py:578-585`). The
  app-server uses `_accounting_from_token_usage`, which builds an `AccountingSample` with no cost
  field (`codex_appserver.py:353-368`). *F62 cites `runner_parsing.py:641` as Codex's `cost`, but
  that line is OpenCode's `step_finish` (`part.get("cost")`, `:620-642`). The conclusion stands
  and the citation is corrected here.*
- **Every turn whose telemetry was unavailable** (`status = 'unavailable'`). These are counted, but
  not in the money figure.
- Any Claude turn whose result carried no `total_cost_usd`.

F62 measured 10 of 65 turns excluded on `proj-18e5d4e0`. On a Codex-heavy project the figure would
be mostly missing and would still read as complete.

## Why not price Codex from tokens

- **A shipped requirement forbids it.** `usage-accounting`, *"Allowance and currency presentation
  cannot imply billing"*: *"The system MUST NOT invent a monetary figure from a model price
  catalog."*
- **It would be a second hand-kept literal with F267's exact failure.** Prices change with models.
  The model catalog's own list went stale within four weeks (F174). A price table would go stale
  the same way, and it would be *money*, not a picker.
- **It cannot be checked here.** Codex is undrivable on this machine (2026-08-29), so no priced
  Codex turn could ever be compared against a real bill or a CLI-reported cost.
- **It would not fix the other two causes** (unavailable telemetry, a Claude result with no cost).
  Marking the figure partial fixes all three.

## What changes

- Each usage summary (project, per agent, per conversation) carries `unpriced_turns`: the turns
  in it that reported no cost, whatever their status.
- `preferred_display` of kind `api_equivalent` carries `unpriced_turns`. The interface renders
  `$0.0421 API-equivalent estimate — excludes 10 turns with no reported cost` whenever that count
  is above zero.
- Nothing is priced. No price table is added to the model catalog or anywhere else.

## Capabilities

- **usage-accounting**: MODIFIED, *"Allowance and currency presentation cannot imply billing"*.
  It adds that a monetary figure which leaves out any turn says so and says how many.

## Impact

`hub/hub/usage_accounting.py`, `hub/ui/src/api/accounting.ts`,
`hub/ui/src/components/accounting/accountingDisplay.ts`, and a UI bundle refresh. No migration
(derived from existing columns). This change is independent of
`worker-spend-counts-against-the-budget`. If that change ships, its worker lines carry the same
count (see its design).
