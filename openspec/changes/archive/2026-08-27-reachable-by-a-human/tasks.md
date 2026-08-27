## 1. Severity normalisation

- [x] 1.1 Add a test in `hub/tests/` that calls `persist_event` directly with `severity="warning"`
  (and one other made-up spelling, e.g. `severity="critical"`) and asserts the row written to
  `EventLog.severity` is `"warn"`, not the original string.
- [x] 1.2 Add a test asserting `persist_event` called with each of `"info"`, `"warn"`, `"error"`,
  `"debug"` writes that exact value unchanged (the enumerated set passes through).
- [x] 1.3 Implement normalisation in `persist_event` (`hub/hub/utils.py`): map any `severity` not in
  `{"info", "warn", "error", "debug"}` to `"warn"` before constructing the `EventLog` row.
- [x] 1.4 Change `hub/hub/run_divergence.py:613` from `severity="warning"` to `severity="warn"`.
- [x] 1.5 Add a test that posts to `POST /logs` with an out-of-vocabulary `severity` in the body and
  asserts the persisted severity is normalised.
- [x] 1.6 Add a test asserting `push_log`'s SSE broadcast (`sse_manager.broadcast` payload, not just
  the persisted row) carries the normalised severity for the same out-of-vocabulary request — found
  in Q1-R2: the broadcast dict in `logs.py:87-96` reads `body.severity` independently of the write
  and would otherwise still ship the raw spelling to a live subscriber.
- [x] 1.7 Implement: change `persist_event`'s return type from `None` to `str` and `return
  normalised_severity`; update `push_log` to capture that return value and use it (not
  `body.severity`) when building the broadcast payload.
- [x] 1.8 Run the new and existing tests covering `persist_event`, `run_divergence.py`, and
  `POST /logs`; confirm green. (`hub/tests/test_event_severity.py`, 4 passed.)
- [x] 1.9 Mutation check: temporarily revert 1.3's normalisation (or comment out the mapping) and
  confirm test 1.1 fails. Record whether it failed as predicted, then restore the fix. **Failed as
  predicted** (`test_persist_event_normalises_unknown_severity` — extra `'warn'` never appeared,
  raw `'warning'`/`'critical'` written through instead); fix restored and re-verified green.
- [x] 1.10 Mutation check: temporarily revert 1.7's broadcast fix (leave `push_log` reading
  `body.severity` for the broadcast) and confirm test 1.6 fails. Record whether it failed as
  predicted, then restore the fix. **Failed as predicted**
  (`test_push_log_broadcast_carries_normalised_severity` — `'critical' == 'warn'` assertion failed);
  fix restored and re-verified green.

## 2. Conversation-title settings control

- [x] 2.1 Update `hub/ui/src/__tests__/projectSettingsPanel.test.tsx` to render the panel with its
  existing `conversation_title_mode: 'generate'` / `conversation_title_runner_id: 'runner-titles'`
  fixture, select the new mode control, and assert it reflects `'generate'`; add a second case
  starting from `'truncate'` that changes the select to `'generate'`, submits, and asserts
  `useUpdateProjectSettings` was called with `conversation_title_mode: 'generate'`.
- [x] 2.2 Add a row to `ProjectSettingsPanel.tsx` ("Conversation titles") with a `Select` bound to
  `form.conversation_title_mode` (`truncate` / `generate`), modelled on the existing "Checkpoint
  runner" row's structure (label, description, `Select`, `set(...)` on change).
- [x] 2.3 Add a runner `Select` for `form.conversation_title_runner_id` in the same row group,
  populated from `useRunners()`, with a "None" option, modelled directly on the existing
  "Checkpoint runner" select (`ProjectSettingsPanel.tsx:243-256`).
- [x] 2.4 Run `cd hub/ui && npm run lint` and the vitest suite for `projectSettingsPanel.test.tsx`;
  confirm green. (13/13 vitest passed; eslint clean.)
- [x] 2.5 Mutation check: temporarily remove the new row's `onChange` wiring (or hardcode the select
  to always submit `'truncate'`) and confirm test 2.1's second case fails. Record the result, then
  restore the fix. **Failed as predicted** (`changes the conversation title mode and saves it` —
  `update` was called with `conversation_title_mode: 'truncate'` instead of `'generate'`); fix
  restored and re-verified 13/13 green.

## 3. Build, spec sync, and sweep

- [x] 3.1 `cd hub/ui && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`; confirm
  `hub/hub/static/ui/ui-build-stamp.json` was rewritten. (Bundle hash `index-awJ7Bmpi.js` unchanged
  across the rebuild, confirming source content matched; stamp re-recorded.)
- [x] 3.2 Commit `hub/ui/src` and `hub/hub/static/ui` together (per CLAUDE.md's UI-bundle rule) —
  covered by the normal end-of-iteration commit, not a separate one.
- [x] 3.3 Run `pytest hub/tests/ -v` (full Hub suite) and confirm green, or diagnose and fix any
  regression before proceeding.
- [x] 3.4 Run `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/
  hub/tests/ tests/`, and `mypy src/`; confirm clean. (All three clean.)
- [x] 3.5 Run `cd hub/ui && npm run lint`; confirm clean. (Clean.)
- [x] 3.6 `npx openspec validate reachable-by-a-human --strict`; confirm it passes. (Passes.)
