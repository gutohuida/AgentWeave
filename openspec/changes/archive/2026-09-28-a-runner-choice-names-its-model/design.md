# Design — a runner choice names its model

## Operator review, 2026-09-24

Opus adversarial review, recorded in `spec-queue/tracks/reviews/B7-2026-09-24.md` §1: APPROVE, with
two LOW notes applied here:

- **The label format was not pinned, and it doubled the model for Hub-created runners.** D1 now pins
  one format, `{name} — {model part} ({cli})`, and omits the model part when the name already ends
  with it, as every runner the Hub names does (`agents.py:713`: `f"{provider_entry.label} —
  {model_entry.label}"`). Task 1.1b tests a Hub-created runner.
- **The checkpoint-runner select could name the wrong model.** When `project.checkpoint_model` is
  set, that model runs, not `runner.model` (`checkpoint_trigger.py:153`). The helper takes an
  optional model override, and the checkpoint select passes the form's `checkpoint_model` (D1).

No operator decision is assumed. This change is independent of D2 and D7 and can ship first.

## D1 — one label for every chooser

`runnerOptionLabel(runner: Runner, catalog: ModelCatalog | undefined, options?: { model?: string |
null }): string`, in `hub/ui/src/lib/runnerLabel.ts`.

**The one format, pinned (operator review):** `{name} — {model part} ({cli})`. The em dash with
spaces is the separator the Hub itself uses when it names a runner (`agents.py:713`), and the cli in
parentheses is what `RunnerPicker` shows today (`AgentSettingsControls.tsx:253`). No other spelling
(such as the bundle notes' `name · provider · model`) is used anywhere.

**No doubled model.** A runner the Hub creates for an agent is named `{provider label} — {model
label}` (`agents.py:713`), so the plain format would print `Claude Code — Opus 5.5 — Opus 5.5
(claude)`. Rule: when `name` already ends with ` — {model part}`, exactly, the model part is not
repeated and the label is `{name} ({cli})`. It is a suffix match on the model part the helper just
computed, so a runner whose model was later changed (named `… — Opus 5.5`, now running Haiku) does
not match and reads `Claude Code — Opus 5.5 — Haiku 4.5 (claude)`, which is the truth.

**The model the choice will run.** `options.model`, when non-empty, replaces `runner.model` as the
model part's source. Only the checkpoint-runner select passes it, with the form's current
`checkpoint_model`: when that is set it is the model checkpoints run on, whichever runner is chosen
(`checkpoint_trigger.py:153`, `project.checkpoint_model or runner.model`). The title-runner select
passes nothing, since titles run the runner's own model.

| Runner records | Renders |

| Runner records | Renders |
|---|---|
| a model the catalog declares for `runner.cli` | `Claude Code — Opus 5.5 (claude)` |
| no model | `Claude Code — Provider default (claude)` |
| a model the catalog does not declare | `Claude Code — claude-opus-4 (unrecognised) (claude)` |
| the catalog has not loaded, or failed to | `Claude Code — claude-opus-5-5 (claude)` (the raw id, never blank) |
| a Hub-created runner, named `Claude Code — Opus 5.5`, on that model | `Claude Code — Opus 5.5 (claude)` (not repeated) |
| the same runner, in the checkpoint select with `checkpoint_model` = Haiku | `Claude Code — Opus 5.5 — Haiku 4.5 (claude)` |

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

- `hub/ui/src/__tests__/runnerOptionLabel.test.ts` (new) covers every row of D1's table, including
  the Hub-created runner (its label contains the model label exactly once) and the override. Two
  runners with the same name and cli and different models produce different strings. **It fails if
  the model part is dropped**, which is today's text.
- `hub/ui/src/__tests__/runnerPickerCannotRun.test.tsx` (existing, extended) renders `RunnerPicker`
  with `GET /runners` answering two same-named runners **in `created_at` order, the order
  `list_runners` returns** (`hub/hub/api/v1/runners.py:82`). It asserts that the two option texts
  differ and that each contains its model's label. It fails on today's `{name} ({cli})`.
- `hub/ui/src/__tests__/projectSettingsPanel.test.tsx` (existing, extended) checks that both
  settings selects' options contain the model label. It fails on today's `{runner.name}`. Its
  fixture already sets `checkpoint_model: 'claude-haiku-4-5-20251001'` (`:46`), so it also asserts
  the checkpoint select's options name Haiku whatever each runner records, and the title select's
  name each runner's own model.

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
