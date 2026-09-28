## 0. Rounds and decision

- [x] 0.1 R2: re-derive the proposal independently. Check every path that builds an `AccountingSample` (grep `AccountingSample(` and `_accounting_from_dimensions(`) and say which can carry a cost. Check every consumer of `api_equivalent_usd_micros` in `hub/` and `hub/ui/src`. Record the result in `design.md`'s round log
- [x] 0.2 R3: a second independent re-derivation. `openspec validate an-estimate-that-misses-turns-says-so --strict` passes
- [x] 0.3 The operator answers D7's Codex question (mark partial / price from tokens), recorded in `spec-queue/DECISIONS.md` — already answered, not by a fresh `DECISIONS.md` row: `spec-queue/APPROVALS.md:133` and `spec-queue/tracks/reviews/B7-2026-09-24.md` §1(c)/§2 record the operator's review approving the "excludes N turns" wording as it stands ("On `:8000` the label will read 'excludes 3 turns' (operator: fine)")

## 1. Tests first — each fails on today's code

- [x] 1.1 Design tests 1–3 in `hub/tests/test_accounting_api.py`
- [x] 1.2 Design test 4 in `hub/ui/src/__tests__/accountingPresentation.test.tsx`

## 2. The fix

- [x] 2.1 `usage_accounting.py`: add the `unpriced_turns` column and summary field, and the display field (design D1, D2)
- [x] 2.2 `accounting.ts` types and `accountingDisplayLabel`
- [x] 2.3 `py -3.11 -m pytest hub/tests/ -q` with `claude` stripped from PATH: first run **4 failed** (`test_surface_ceilings.py`, all four) — a real regression from tonight's already-archived `a-runner-choice-names-its-model` change, which added a second, unhandled `useModelCatalog()` call site (`AgentSettingsControls.tsx:228`, `RunnerPicker`) that neither this change nor that one had run this guard file against since (F392 rule 2: its guard-file union is `hub/tests/test_a_refused_first_send_leaves_no_exploration.py`, `hub/tests/test_failed_run_returns_input.py`, plus this change's own `hub/tests/test_accounting_api.py` — none of those three named this file, but the full `hub/tests/` run this task itself requires caught it anyway). Fixed by binding and rendering `catalogError` in `RunnerPicker` (same pattern as the existing `launchabilityError` notice), which makes the site `HANDLED` rather than unhandled — no ceiling raised. Second run: **5086 passed, 86 skipped, 0:30:31**. `py -3.11 -m pytest tests/ -q`: **553 passed, 3 skipped, 0:01:06**. `ruff check` + `black --check --target-version py311` on the two touched Python files: clean. `cd hub/ui && npm run lint`: clean. `npx vitest run`: **168 files, 1725 tests, all passing**. `npm run build` + `py -3.11 scripts/refresh_ui_bundle.py`: bundle refreshed and stamped. Committed `hub/ui/src` and `hub/hub/static/ui` together, plus the `AgentSettingsControls.tsx` regression fix

## 3. Drive

- [ ] 3.1 On the trial Hub `:8010`, read `GET /accounting` for a project with at least one `unavailable` turn, and record `unpriced_turns` and the rendered label on the Budgets settings section
