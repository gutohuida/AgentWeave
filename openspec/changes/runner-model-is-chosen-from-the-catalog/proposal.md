## Why

`openspec/specs/runner-registry/spec.md:72-73` is a **shipped** requirement, not a proposal:

> Runner management SHALL offer the catalog's models for the chosen provider rather than accepting
> free-typed text.

The backend honours it. The screen does not, and when the backend refuses what the screen let the
operator type, the screen says nothing at all.

**F173 (A), driven** (`scripts/drive/t_sweep_row2_ui.py`, `row2-04-after-save.png`):

```
New Runner -> Name "Row 2 typed model", CLI Claude, Model "opus" -> Save
  POST /api/v1/projects/<p>/runners  ->  400  {"detail": "'opus' is not a model 'claude' declares"}
  [PASS] the dialog stays open rather than closing on a failure
  [FAIL] the operator is told the runner was not created, and why
         — no alert, no message, nothing changed on screen
```

`RunnersPage.tsx:228-238` renders the model as a free-text `<Input placeholder="e.g.
claude-sonnet-5">`. `useCreateRunner` / `useUpdateRunner` (`api/runners.ts:67-88`) declare
`onSuccess` and no `onError`. `RunnersPage` renders exactly one error surface — `deleteError`, set
only by `handleDelete` (`RunnersPage.tsx:42-49`). `main.tsx:8-15` configures no `MutationCache`
`onError` and no toast. A refused create or edit reaches nothing, and the operator's only feedback
is that pressing Save does nothing, forever.

The same requirement's third scenario says *"the operator is told the model is unrecognised when
editing it"*. `RunnerResponse.model_unrecognised` (`schemas/runners.py:44-58`) computes exactly
that, and it is not even declared on the UI's `Runner` type (`api/runners.ts:6-15`), let alone
rendered. **Two of that requirement's three scenarios are unimplemented on the screen.**

### What round 1 measured that F173 did not know

Driven live against the `:8011` Hub, fixture project `proj-876a250f7a16`, created and deleted
(`scripts/drive/t_f219_runner_model_clear.py`, 10 passed / 2 failed, twice):

| call | answer |
|---|---|
| `POST /runners {"model":"opus"}` | **400** `'opus' is not a model 'claude' declares` |
| `POST /runners {"model":"claude-haiku-4-5-20251001"}` | 201, `model_unrecognised: false` |
| `PATCH /runners/{id} {"model": null}` | **200 — and the model is unchanged** |
| `PATCH /runners/{id} {"model": ""}` | 400 `'' is not a model 'claude' declares` |
| `GET /model-catalog` | claude: 4 models, codex: 6 |

Round 2 re-derived this against the code and measured what round 1 did not ask
(`scripts/drive/t_r2_runner_update_semantics.py`, **18 passed / 1 failed**):

| call | answer |
|---|---|
| `PATCH {"name":"x","model":"opus"}` then `GET` | **400**, and the name is *unchanged* — nothing half-applied |
| `POST` with an undeclared model, then `GET /runners` | **400**, and no row created |
| `PATCH {"flags":[]}` / `PATCH {"flags":null}` | `[]` / **no-op** — `flags` has `model`'s defect too |
| `PATCH {"model":"<the runner's own unrecognised model>"}` | **400** `'claude-3-legacy-9' is not a model 'claude' declares` |

**That last row is what round 2 changed the proposal for.** `_reject_undeclared_model` cannot see a
runner's stored model, so re-submitting it is refused — and the picker submits it on every save.
Round 1's design would have shipped a screen on which a legacy runner cannot be saved at all, which
breaches the shipped "Existing runners keep working" scenario the change otherwise strengthens. The
free-text box hides this only because an untouched field is dropped by `JSON.stringify`.

**A runner's model cannot be cleared back to the provider's default, and the attempt is answered
`200` with the runner's old model in the response body.** `update_runner`
(`hub/hub/api/v1/runners.py:136-141`) gates every field on `is not None`, so an explicit `null` is
indistinguishable from an absent field; `""` is refused by the catalog check. Once a runner has a
model, "Model (optional)" is a one-way door — filed as **F219 (C)**.

That matters here rather than separately, because a picker forces the question. A free-text box let
the operator *believe* they had cleared the field (they had not — an empty string became
`model: undefined`, which `JSON.stringify` drops). A select has to name the unset choice out loud,
and the moment it does, the API must be able to honour it. An unset model is a real, spawnable
state: `_build_claude_command` emits `--model` only `if model` (`runner_commands.py:199-200`), so
no model means the CLI's own default.

## What Changes

- Runner management chooses its model from the catalog: a select over the declared models for the
  runner's CLI, plus an explicit **Provider default** choice. The free-text input goes.
- A runner already carrying a model the catalog does not declare keeps it, offered as a marked
  choice so the operator can keep or replace it, and is marked as unrecognised in the runner list.
  `model_unrecognised` is declared on the UI's `Runner` type and read. **The Hub accepts that model
  being re-submitted unchanged**, which today it refuses — so a legacy runner becomes editable at
  all, not merely legible.
- A refused create or edit presents the refusal's own sentence in the dialog, through the
  `readableApiError` idiom the rest of the app already uses. The bespoke `extractErrorDetail` in
  `RunnersPage.tsx:19-30` is replaced by it.
- `PATCH /runners/{id}` honours an explicit `model: null` as *clear back to the provider default*,
  and stops answering `200` to a request it did not act on.

## Impact

- Specs: `runner-registry` — one requirement modified, one added.
- Code: `hub/hub/api/v1/runners.py`, `hub/hub/schemas/runners.py`,
  `hub/ui/src/components/runners/RunnersPage.tsx`, `hub/ui/src/api/runners.ts`.
- Tests: `hub/tests/test_runners_api.py`, `hub/ui/src/__tests__/runnersUi.test.tsx`,
  `hub/ui/src/__tests__/support/modelCatalogFixture.ts` (shared by 9 test files — see design.md).
- Bundle: `hub/hub/static/ui` is a committed build artefact and must be refreshed with the source.
- Retires **F173 (A)** and **F219 (C)**.
