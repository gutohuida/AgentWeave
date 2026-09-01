## 1. The API can clear a runner's model

- [x] 1.1 `RunnerUpdate` distinguishes an absent `model` from an explicit `null`. `update_runner`
      (`hub/hub/api/v1/runners.py:120-147`) applies `model` when the field was *sent*, not when it
      is `is not None`, so `PATCH {"model": null}` clears the model and `PATCH {}` leaves it. Use
      `model_fields_set` or an equivalent sentinel; do not change the `is not None` gates on `name`
      or `flags` (design.md says why).
- [x] 1.2 `_reject_undeclared_model` is not called for a cleared model — `None` already returns
      early. `""` stays refused.
- [x] 1.3 `update_runner` does not refuse a model **identical to the one the runner already
      records**. Today `_reject_undeclared_model(runner.cli, body.model)` cannot see the stored
      model, so re-submitting a legacy runner's own unrecognised model is answered `400` — which
      the new picker does on every save (design.md, "a legacy runner cannot be saved unchanged").
      A *different* undeclared model, and any undeclared model on create, stay refused. Update the
      function's docstring, which already claims this behaviour and does not have it.
- [x] 1.4 `hub/tests/test_runners_api.py`: `PATCH {"model": null}` clears and the response body
      carries `model: null` (scenario "The provider's default is a choice, and clearing is
      honoured"); `PATCH {"name": "x"}` alone leaves the model untouched (scenario "A request
      carrying no model at all leaves the model alone");
      `PATCH {"model": ""}` is still `400`. The first of these fails against today's code with
      `200` and the old model — check that it does before writing the fix.
- [x] 1.5 `hub/tests/test_runners_api.py`: a runner whose stored model the catalog does not declare
      accepts a `PATCH` re-submitting that same model (`200`, model unchanged), and still refuses a
      `PATCH` moving it to a *different* undeclared model (`400`). This one also fails today —
      `scripts/drive/t_r2_runner_update_semantics.py` Q5 is the live reproduction. The row cannot
      be created through the API, so the test builds it through the session as that harness does
      through sqlite.

**Section 1 built and driven, 2026-09-01 (night window, N-2).** Both predicted failures were
watched red first: `PATCH {"model": null}` answered `200` with `'claude-sonnet-5'` still in the body,
and re-submitting a legacy runner's own stored model answered `400`. `update_runner` now gates
`model` on `"model" in body.model_fields_set` (the `is not None` gates on `name` and `flags` are
untouched), and `_reject_undeclared_model` takes the runner's `current` model and returns early when
the submitted one equals it. Five tests added to `hub/tests/test_runners_api.py` (21 passed).
Driven live on `:8011` against a fresh fixture project, deleted afterwards:
`scripts/drive/t_r2_runner_update_semantics.py` is now **19 passed / 0 failed**, which is task 5.6's
target already met at the API level. That harness's Q4 asserted the *defect* ("the request did
nothing"); it now asserts the requirement, and says in a comment why it was flipped.

## 2. The model is chosen from the catalog

- [x] 2.1 `Runner` (`hub/ui/src/api/runners.ts:6-15`) declares `model_unrecognised: boolean`.
      `RunnerCreate` and `RunnerUpdate` allow `model?: string | null`.
- [x] 2.2 `RunnerForm` (`RunnersPage.tsx:165-254`) reads `useModelCatalog()`, resolves the provider
      entry for the selected CLI, and replaces the free-text `<Input>` with a `<Select>` carrying:
      a `Provider default` option (unset), one option per declared model, and — when editing a
      runner whose `model_unrecognised` is true — its stored model, selected, labelled as
      unrecognised.
- [x] 2.3 Submitting sends `model: undefined` on create when unset, and `model: null` on edit when
      the operator moves a runner back to the provider default. The edit path currently sends
      `{ name, model }` (`RunnersPage.tsx:149`) and must keep sending `model` explicitly.
- [x] 2.4 Changing the CLI while creating resets the model selection to the **unset** `Provider
      default` option — *not* to that provider's default model. Copy the shape of
      `AgentCreateDialog.tsx:176-181` but not its value: that dialog resets to a concrete model id
      because an agent must have one, and a runner must not have one chosen on its behalf
      (design.md says why). The CLI select is already disabled when editing.
- [x] 2.5 While the catalog is unavailable the model select is disabled and says so; Save stays
      enabled, because a runner with no model is valid.
- [x] 2.6 The runner list row marks a runner whose `model_unrecognised` is true, beside the
      model it already renders (`RunnersPage.tsx:109-113`). Round 3 added the clause and the
      scenario `AND` this implements; before that it was a task no requirement asked for.

**Section 2 built and driven, 2026-09-02 (night window, N-3).** `Runner` carries
`model_unrecognised`; `RunnerForm`'s free-text `<Input>` is a `<Select>` fed by `useModelCatalog()`,
offering "Provider default" plus the models the catalog declares for the selected CLI, plus the
runner's own stored model — selected and labelled `— unrecognised` — when the catalog does not
declare it. Changing the CLI on create resets to **unset**. The edit path always sends `model`,
`null` when the operator moves back to Provider default. The list row carries an amber
`Unrecognised` chip.

Driven through a browser against the `:8011` Hub, fixture project `proj-3ad9e80184e1` (created and
deleted, count back to `0`): `scripts/drive/t_n3_runner_model_picker_ui.py`, **25 passed / 0
failed**, including the wire payloads (`{"model": null}` on clearing, the legacy model re-submitted
and accepted `200`) and `GET /runners/{id}` reporting `model: null` afterwards. That is the
substance of tasks 5.1 and 5.2 — but against the **Vite dev server**, because
`hub/hub/static/ui` is a committed build artefact this section deliberately does not rebuild
(section 5 does, once). Section 5's drive still has to run against the served bundle.

**Tasks 4.1, 4.2, 4.4 and 4.5 were done here rather than in section 4**, because leaving them
would have left the vitest suite knowingly red between sittings: replacing the model `<Input>`
breaks `runnersUi.test.tsx`'s `getByPlaceholderText('e.g. claude-sonnet-5')` immediately, and
repairing it needs the fixture's model list (4.1) in the same edit. 4.1's stated blast radius was
measured and is zero — **142 files / 1473 tests pass**, and no test depended on the empty list.
4.4's "check that it fails first, against the API" was honoured in N-2, which watched that exact
`400` before writing section 1's fix; the acceptance half is re-proved live above rather than only
against a mock. **4.3 and 4.6 stay open** — both are assertions about section 3's error surface,
which does not exist yet.

## 3. A refusal reaches the operator

- [x] 3.1 Delete `extractErrorDetail` (`RunnersPage.tsx:19-30`) and use `readableApiError` from
      `@/api/client` — it handles the Pydantic array body the local helper does not.
- [x] 3.2 `RunnerForm` renders `readableApiError(error, …)` in a `role="alert"` block inside the
      dialog, fed by `createRunner.error` / `updateRunner.error`. Follow
      `AgentCreateDialog.tsx:235`'s placement and tokens — and **not** its helper: line 235 calls a
      private `errorDetail` (lines 10-18) that is a twin of the one task 3.1 deletes.
- [x] 3.3 The dialog already stays open on failure (it closes only in the per-call `onSuccess` at
      `RunnersPage.tsx:136` and `:150`, and `RunnerForm` holds its own `useState`, so the entered
      values survive) — assert it rather than changing it.
- [x] 3.4 The mutation is `reset()` when the dialog opens and when it is cancelled. The mutations
      live in `RunnersPage` and outlive `RunnerForm`, so without this a reopened "New Runner"
      shows the previous refusal before anything has been submitted (design.md, "the error surface
      must be reset").
- [x] 3.5 The existing `deleteError` alert keeps working and now reads through `readableApiError`.
      `useDeleteRunner` throws a real `ApiError` (checked — `fetchWithAuth`, `client.ts:24-27`), so
      the refusal's sentence naming the bound agents survives the swap rather than degrading to the
      fallback.

**Section 3 built and driven, 2026-09-02 (night window, N-4).** `extractErrorDetail` is gone;
`handleDelete` and the dialog both read through `readableApiError`. `RunnerForm` takes the save
mutation's `error` and renders it in a `role="alert"` inside the dialog, above the buttons, with
`AgentCreateDialog`'s tokens. Both mutations are `reset()` when their dialog opens *and* when it is
cancelled — the Edit button resets too, not only "New Runner".

Driven live against the `:8011` Hub through the Vite dev server, fixture project
`proj-efa763e8945f` (created and deleted, count back to `0`):
`scripts/drive/t_n4_runner_refusal_reaches_the_operator.py`, **24 passed / 0 failed**, over three
deliberately different refusal shapes — a Pydantic `422` whose `detail` is a *list* (which the
deleted helper returned raw, as an array of objects React cannot render), the Hub's own `400`
`'opus' is not a model 'claude' declares`, and the `409` naming the agents holding a runner. The
model refusal can no longer be *produced* from the screen — task 5.1's inversion, asserted rather
than assumed — so the sentence was reached by rewriting the request body on the wire; the refusal
and its words are the Hub's.

Both halves were mutation-checked against the vitest suite rather than argued: with the alert
block removed 3 tests fail, and with only the two `reset()` calls removed exactly the 4.6 test
fails.

## 4. Tests

- [x] 4.1 `modelCatalogFixture.ts` declares a small model list per provider. Re-run the whole vitest
      suite: 9 files import this fixture. If any test depends on the empty list, give that test its
      own fixture rather than leaving the shared one in a state the Hub cannot produce.
- [x] 4.2 `runnersUi.test.tsx`: **one** `getByPlaceholderText` assertion goes — line 85,
      `'e.g. claude-sonnet-5'`, the model input. Line 84's `'e.g. Claude Opus'` is the **Name**
      field and must stay: `Save` is `disabled` on `!name.trim()` (`RunnersPage.tsx:246`), so
      dropping it leaves the button disabled and the test's own `createMutate` assertion fails.
      Replace line 85 with — the select offers exactly `Provider default` plus the fixture's
      models for the chosen CLI; choosing one submits that model id; there is no free-text model
      field on screen.
- [x] 4.3 A refused create renders the refusal's sentence and leaves the dialog open with its
      values. Drive it through a mocked `useCreateRunner` whose mutation reports an `ApiError`
      carrying `{"detail": "'opus' is not a model 'claude' declares"}`.
- [x] 4.4 Editing a runner whose `model_unrecognised` is true offers its stored model, selected and
      marked, and saving unchanged submits that same model **and is accepted**. This assertion is
      unsatisfiable without task 1.3 — check that it fails first, against the API, not only against
      a mock.
- [x] 4.5 Changing the CLI on create resets the model selection to `Provider default`.
- [x] 4.6 A refused create, then Cancel, then reopening "New Runner" shows **no** alert. Fails
      without task 3.4.

**Section 4 finished, 2026-09-02 (night window, N-4).** 4.1/4.2/4.4/4.5 landed with section 2;
4.3 and 4.6 landed with section 3, in the same sitting, because both are assertions about a surface
section 3 creates. A third test was added beside them: a `422` whose `detail` is a Pydantic *array*
renders as its sentence, which is the behaviour task 3.1's swap exists for and which no other test
covered. vitest is **142 files / 1476 tests** green (1473 before), `npm run lint` and
`tsc --noEmit` clean.

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
- [ ] 5.6 Re-run `py -3.11 scripts/drive/t_r2_runner_update_semantics.py` and confirm **19 passed
      / 0 failed** — Q5's legacy runner now saves unchanged, and Q1–Q4's negatives still hold.
- [ ] 5.7 Mark F173, F219 and F220 retired in `scripts/drive/FINDINGS.md` only after 5.1, 5.2 and
      5.6 pass. **F221 stays open** — the alias refusal is named out of scope in design.md.
