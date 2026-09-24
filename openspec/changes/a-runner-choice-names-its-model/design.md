# Design — a runner choice names its model

No operator decision is assumed. This change is independent of D2 and D7 and can ship first.

## D1 — one label for every chooser

`runnerOptionLabel(runner: Runner, catalog: ModelCatalog | undefined): string`, in
`hub/ui/src/lib/runnerLabel.ts`:

| Runner records | Renders |
|---|---|
| a model the catalog declares for `runner.cli` | `Claude Code — Opus 5.5 (claude)` |
| no model | `Claude Code — Provider default (claude)` |
| a model the catalog does not declare | `Claude Code — claude-opus-4 (unrecognised) (claude)` |
| the catalog has not loaded, or failed to | `Claude Code — claude-opus-5-5 (claude)` (the raw id, never blank) |

The model part reads the catalog (`useModelCatalog`, `hub/ui/src/api/modelCatalog.ts:46`) and not
`runner.model_unrecognised`, so that no chooser's label depends on which response field its query
carried. The two agree by construction, because `schemas/runners.py:50-58` uses the same
`get_provider(...).model(...)` lookup.

**Why not show the id as well.** Two runners with the same name *and* model are the same choice.
The id would only tell apart rows that do not need telling apart.

## D2 — the three selects

`AgentSettingsControls.tsx:253`, `ProjectSettingsPanel.tsx:171` and `ProjectSettingsPanel.tsx:279`
call the helper. Nothing else in those components changes, and each option's `value` stays
`runner.id`.

## What each route returns when what it calls raises

No route changes. If `GET /model-catalog` fails, the helper's catalog is `undefined` and the label
falls back to the raw id (D1's last row) rather than rendering nothing.

## Tests that can fail

- `hub/ui/src/__tests__/runnerOptionLabel.test.ts` (new) covers the four rows of D1's table. Two
  runners with the same name and cli and different models produce different strings. **It fails if
  the model part is dropped**, which is today's text.
- `hub/ui/src/__tests__/runnerPickerCannotRun.test.tsx` (existing, extended) renders `RunnerPicker`
  with `GET /runners` answering two same-named runners **in `created_at` order, the order
  `list_runners` returns** (`hub/hub/api/v1/runners.py:82`). It asserts that the two option texts
  differ and that each contains its model's label. It fails on today's `{name} ({cli})`.
- `hub/ui/src/__tests__/projectSettingsPanel.test.tsx` (existing, extended) checks that both
  settings selects' options contain the model label. It fails on today's `{runner.name}`.

## Round log

- R1 (2026-09-24): written.
- R2 (2026-09-24): confirmed. `hub/ui/src` renders runner options in exactly the three places
  named (grep `runners.map`/`runner.name`, outside `RunnersPage`), `list_runners` orders by
  `created_at` (`runners.py:82`), `RunnerResponse.model_unrecognised` uses the same
  `get_provider().model()` lookup (`schemas/runners.py:50-58`), `useModelCatalog` is at
  `modelCatalog.ts:46`, and `agents.py:713` names Hub-made runners `label — model label`. **File
  overlap, not finding overlap:** `a-runner-that-cannot-collaborate-says-so-where-it-is-bound`
  (another bundle) edits the same `RunnerPicker` (`AgentSettingsControls.tsx:225-275`); whichever
  lands second rebases its option text onto the other's.
