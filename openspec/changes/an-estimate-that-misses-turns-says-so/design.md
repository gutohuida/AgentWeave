# Design — an estimate that misses turns says so

**Built on the recommended answer to D7 (second question): totals are marked partial, and Codex is
not priced from tokens.** If the operator answers *"price Codex from tokens"*, this change still
ships unchanged, because unavailable turns and cost-less Claude results stay unpriced either way.
A pricing change would be a separate change that first MODIFIES the `usage-accounting` sentence
*"MUST NOT invent a monetary figure from a model price catalog"*, which it would be contradicting.

## The options for D7's Codex question, with evidence

| Option | What it releases | What it breaks or costs |
|---|---|---|
| **A. Silent partial sum (today)** | Nothing to build | A figure presented as complete that is not (F62) |
| **B. Price Codex from tokens** | One dollar figure across providers | Contradicts `usage-accounting` (*MUST NOT invent a monetary figure from a model price catalog*). Adds a price literal with F267's staleness and no machine-readable source. It is unverifiable here, because Codex is undrivable. It leaves the other two causes of a partial figure in place |
| **C. Mark partial (recommended)** | A figure that says what it covers. Small; no migration | The operator sees a caveat, not a complete figure. For Codex-only work the figure stays absent (tokens are shown instead, as today: `preferred_display` falls through to `tokens` when the sum is `NULL`, `usage_accounting.py:176-177`) |

## D1 — `unpriced_turns`

In `_aggregate_columns()` (`usage_accounting.py:87-96`), add
`func.sum(case((TurnUsage.api_equivalent_usd_micros.is_(None), 1), else_=0)).label("unpriced_turns")`.
`_summary_from_row` emits it as an int. It flows to `project`, to each entry of `agents`, and to
`GET /accounting/conversations/{id}` (`conversation_usage` uses the same columns,
`usage_accounting.py:195-201`).

**Status is deliberately ignored.** An `unavailable` turn has no cost either, and the money figure
leaves it out just the same. Counting it here is what makes the count mean *"turns this figure does
not cover"*.

## D2 — the display

`preferred_display` of kind `api_equivalent` gains `unpriced_turns: int`, copied from the project
summary. `AccountingDisplay` (`accounting.ts:27`) gains the field. `accountingDisplayLabel`
(`accountingDisplay.ts:42-43`) appends ` — excludes N turn(s) with no reported cost` when
`N > 0`. The `allowance`, `tokens` and `unavailable` kinds are unchanged.

## What each route returns when what it calls raises

`GET /accounting` and `GET /accounting/conversations/{id}` gain one aggregate column in a query they
already run. If `accounting_snapshot` raises `ValueError` (project missing), the route has no
handler (`api/v1/accounting.py:26-31`). But `get_project` has already answered 404 for an unknown
project before it runs, so the case is unreachable, and this change leaves it as it is.
`PATCH /accounting/budget` calls `accounting_snapshot(…, recent_limit=0)` and reads only
`total_tokens`, so it is unaffected.

## Tests that can fail

`hub/tests/test_accounting_api.py` (extend):

1. Seed three `TurnUsage` rows in one project: a Claude turn with cost 1000, a Codex-shaped turn
   with tokens and no cost, and an `unavailable` turn. `GET /accounting` gives
   `project.api_equivalent_usd_micros == 1000`, `project.unpriced_turns == 2`, and
   `preferred_display == {"kind": "api_equivalent", …, "unpriced_turns": 2}`. **Fails today** (no
   such key).
2. Per agent: the two agents' `unpriced_turns` are their own. The `agents` list is ordered by agent
   name (`usage_accounting.py:126`), and the test asserts by position in that order, so reversing
   the order fails it.
3. All three turns priced gives `unpriced_turns == 0`, and the display carries 0.

`hub/ui/src/__tests__/accountingPresentation.test.tsx` (extend):

4. `accountingDisplayLabel({kind:'api_equivalent', …, usd_micros: 42157, unpriced_turns: 10})`
   contains `excludes 10 turns`. With `unpriced_turns: 0` it is today's string exactly. The first
   fails today.

## Round log

- R1 (2026-09-24): written.
