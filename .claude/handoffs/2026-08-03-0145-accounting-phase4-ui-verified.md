# Accounting and budgets — phase 4 implementation verified

## Current state

`accounting-and-budgets` implementation is complete and fully verified. Only closeout remains:
sync the authoritative capability spec, archive the change, annotate umbrella phase 9, write the
final slice handoff, and commit those boundaries. Then continue to the next dependency-safe umbrella
successor; do not stop at this slice.

## UI/API result

- `hub/ui/src/api/accounting.ts`: typed GET/PATCH React Query hooks.
- `AccountingPanel`: Overview shows measured tokens, measured/unavailable turn counts, per-agent
  totals, preferred allowance or explicitly labelled API-equivalent estimate, budget editing, and
  the full exhausted explanation.
- `BudgetExhaustionNotice`: compact status-bar warning keeps the exhausted state visible throughout
  the conversation shell; it states operator messages can still run and does not affect composer
  enablement.
- `run_completed` and other terminal run SSE events invalidate accounting; budget updates now emit
  `accounting_budget_updated` and invalidate it across browser sessions.
- Presentation tests cover allowance precedence, exact cost wording, unavailable not zero, budget
  mutation, and compact/full exhausted messaging.

## Verification

```text
frontend focused: 4 passed
frontend full: 36 files, 289 passed
npm run build: passed (existing unrelated duplicate case warning in eventSummary.ts)
backend full: 432 passed, 4 skipped
openspec validate --all --strict --no-interactive: 16 passed
git diff --check: passed
```

`npm run lint` is not currently a usable check in this repository: installed ESLint 9 requires
`eslint.config.*`, but the project has none. This pre-existing tool configuration error occurs
before linting any file. TypeScript (`npm run build`) and all Vitest suites passed.

## Exact closeout

1. Copy the complete delta requirements from
   `openspec/changes/accounting-and-budgets/specs/usage-accounting/spec.md` into a new authoritative
   `openspec/specs/usage-accounting/spec.md`, adding a concise Purpose and removing `## ADDED` delta
   framing.
2. Strictly validate all OpenSpec items and commit the authoritative spec.
3. Archive with `openspec archive accounting-and-budgets --skip-specs -y`; validate all again.
4. In umbrella `tasks.md` phase 9, add a dated update saying the entire phase is closed by archived
   `2026-08-03-accounting-and-budgets`, while leaving superseded 9.1–9.5 checkboxes unchanged.
5. Mark task 4.4, write final handoff/LATEST, commit archive/reconciliation explicitly.
6. Re-read the archived conversation-workspace slice table and choose the next ready independent
   successor (runner/agent/charter separation or agent capability plane are likely candidates;
   account for dependency ordering before selecting).

