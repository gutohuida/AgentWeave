## 1. The API can clear a runner's model

- [ ] 1.1 `RunnerUpdate` distinguishes an absent `model` from an explicit `null`. `update_runner`
      (`hub/hub/api/v1/runners.py:120-147`) applies `model` when the field was *sent*, not when it
      is `is not None`, so `PATCH {"model": null}` clears the model and `PATCH {}` leaves it. Use
      `model_fields_set` or an equivalent sentinel; do not change the `is not None` gates on `name`
      or `flags` (design.md says why).
- [ ] 1.2 `_reject_undeclared_model` is not called for a cleared model — `None` already returns
      early. `""` stays refused.
- [ ] 1.3 `hub/tests/test_runners_api.py`: `PATCH {"model": null}` clears and the response body
      carries `model: null`; `PATCH {"name": "x"}` alone leaves the model untouched;
      `PATCH {"model": ""}` is still `400`. The first of these fails against today's code with
      `200` and the old model — check that it does before writing the fix.

## 2. The model is chosen from the catalog

- [ ] 2.1 `Runner` (`hub/ui/src/api/runners.ts:6-15`) declares `model_unrecognised: boolean`.
      `RunnerCreate` and `RunnerUpdate` allow `model?: string | null`.
- [ ] 2.2 `RunnerForm` (`RunnersPage.tsx:165-254`) reads `useModelCatalog()`, resolves the provider
      entry for the selected CLI, and replaces the free-text `<Input>` with a `<Select>` carrying:
      a `Provider default` option (unset), one option per declared model, and — when editing a
      runner whose `model_unrecognised` is true — its stored model, selected, labelled as
      unrecognised.
- [ ] 2.3 Submitting sends `model: undefined` on create when unset, and `model: null` on edit when
      the operator moves a runner back to the provider default. The edit path currently sends
      `{ name, model }` (`RunnersPage.tsx:149`) and must keep sending `model` explicitly.
- [ ] 2.4 Changing the CLI while creating resets the model selection to that provider's default
      option. Copy `AgentCreateDialog.tsx:180`. The CLI select is already disabled when editing.
- [ ] 2.5 While the catalog is unavailable the model select is disabled and says so; Save stays
      enabled, because a runner with no model is valid.
- [ ] 2.6 The runner list row marks a runner whose `model_unrecognised` is true.

## 3. A refusal reaches the operator

- [ ] 3.1 Delete `extractErrorDetail` (`RunnersPage.tsx:19-30`) and use `readableApiError` from
      `@/api/client` — it handles the Pydantic array body the local helper does not.
- [ ] 3.2 `RunnerForm` renders `readableApiError(error, …)` in a `role="alert"` block inside the
      dialog, fed by `createRunner.error` / `updateRunner.error`. Follow
      `AgentCreateDialog.tsx:235`'s placement and tokens.
- [ ] 3.3 The dialog already stays open on failure (it closes only in `onSuccess`) — assert it
      rather than changing it, and keep the entered values.
- [ ] 3.4 The existing `deleteError` alert keeps working and now reads through `readableApiError`.

## 4. Tests

- [ ] 4.1 `modelCatalogFixture.ts` declares a small model list per provider. Re-run the whole vitest
      suite: 9 files import this fixture. If any test depends on the empty list, give that test its
      own fixture rather than leaving the shared one in a state the Hub cannot produce.
- [ ] 4.2 `runnersUi.test.tsx`: the two `getByPlaceholderText` assertions on the model input
      (lines 84-85) go. Replace with — the select offers exactly `Provider default` plus the
      fixture's models for the chosen CLI; choosing one submits that model id; there is no
      free-text model field on screen.
- [ ] 4.3 A refused create renders the refusal's sentence and leaves the dialog open with its
      values. Drive it through a mocked `useCreateRunner` whose mutation reports an `ApiError`
      carrying `{"detail": "'opus' is not a model 'claude' declares"}`.
- [ ] 4.4 Editing a runner whose `model_unrecognised` is true offers its stored model, selected and
      marked, and saving unchanged submits that same model.
- [ ] 4.5 Changing the CLI on create resets the model selection.

## 5. Drive it, then ship the bundle

- [ ] 5.1 Against the `:8011` Hub in a fresh project (never `proj-5e960453` or `proj-18e5d4e0`),
      reproduce F173's exact sequence — New Runner, Claude, model `opus`, Save — and confirm the
      operator now reads `'opus' is not a model 'claude' declares`. The model field must no longer
      accept the typed value at all, so the reproduction becomes: the refusal is unreachable from
      the screen, and the *edit* of a legacy runner is where the refusal surface is proved.
- [ ] 5.2 Clear a runner's model back to Provider default in the UI, then confirm through
      `GET /runners/{id}` that it is `null` — the API half, proved through the screen.
- [ ] 5.3 `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/
      hub/tests/ tests/`, `mypy src/`, `cd hub/ui && npm run lint`.
- [ ] 5.4 `pytest hub/tests/ -v` under `py -3.11`, and `cd hub/ui && npm test`.
- [ ] 5.5 `cd hub/ui && npm run build`, then `python scripts/refresh_ui_bundle.py`. Commit
      `hub/ui/src` and `hub/hub/static/ui` together.
- [ ] 5.6 Mark F173 and F219 retired in `scripts/drive/FINDINGS.md` only after 5.1 and 5.2 pass.
