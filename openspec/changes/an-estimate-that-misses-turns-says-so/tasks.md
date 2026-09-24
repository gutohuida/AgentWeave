## 0. Rounds and decision

- [x] 0.1 R2: re-derive the proposal independently. Check every path that builds an `AccountingSample` (grep `AccountingSample(` and `_accounting_from_dimensions(`) and say which can carry a cost. Check every consumer of `api_equivalent_usd_micros` in `hub/` and `hub/ui/src`. Record the result in `design.md`'s round log
- [ ] 0.2 R3: a second independent re-derivation. `openspec validate an-estimate-that-misses-turns-says-so --strict` passes
- [ ] 0.3 The operator answers D7's Codex question (mark partial / price from tokens), recorded in `spec-queue/DECISIONS.md`

## 1. Tests first — each fails on today's code

- [ ] 1.1 Design tests 1–3 in `hub/tests/test_accounting_api.py`
- [ ] 1.2 Design test 4 in `hub/ui/src/__tests__/accountingPresentation.test.tsx`

## 2. The fix

- [ ] 2.1 `usage_accounting.py`: add the `unpriced_turns` column and summary field, and the display field (design D1, D2)
- [ ] 2.2 `accounting.ts` types and `accountingDisplayLabel`
- [ ] 2.3 Run `py -3.11 -m pytest hub/tests/ -q` with `claude` stripped from PATH, then the lint block, then `make ui`. Commit `hub/ui/src` and `hub/hub/static/ui` together

## 3. Drive

- [ ] 3.1 On the trial Hub `:8010`, read `GET /accounting` for a project with at least one `unavailable` turn, and record `unpriced_turns` and the rendered label on the Budgets settings section
