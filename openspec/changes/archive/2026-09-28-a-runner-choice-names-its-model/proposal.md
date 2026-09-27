# Proposal — a runner choice names its model

Finding: **F268 (B)**. Bundle B7 (models and budget), R1, 2026-09-24. Needs no operator decision.

## Why

`runner-registry` blesses two runners of one provider that differ only in their model (*"Operator
creates a custom runner variant"*). The Hub accepts two runners with the same name: `RunnerCreate`
puts no uniqueness on `name` (`hub/hub/schemas/runners.py:13-17`), and the index on it is a plain
one (`hub/hub/db/models.py:341`). Every screen that asks the operator to *choose* a runner then
renders an option that leaves out the one fact the variant exists for:

| Select | Option text today | File |
|---|---|---|
| An agent's runner binding | `{runner.name} ({runner.cli})` | `hub/ui/src/components/agents/AgentSettingsControls.tsx:253` |
| Conversation title runner | `{runner.name}` | `hub/ui/src/components/environment/ProjectSettingsPanel.tsx:171` |
| Checkpoint runner | `{runner.name}` | `hub/ui/src/components/environment/ProjectSettingsPanel.tsx:279` |

So two `Claude Code` runners, one on `claude-opus-5-5` and one on `claude-haiku-4-5-20251001`,
read the same. Picking one silently decides which model every later turn, checkpoint or title runs
on. F268 measured the binding select. The two settings selects were not in F268, and they are
worse, because they omit the provider too. The Runners page itself does show the model
(`RunnersPage.tsx:107-118`). Only the choosers do not.

The Hub already knows that a runner's name should carry its model, but applies that only to the
runners it names itself: `f"{provider_entry.label} — {model_entry.label}"`
(`hub/hub/api/v1/agents.py:713`).

## What changes

- One helper, `runnerOptionLabel(runner, catalog)`, renders a runner as a choice. It gives the
  runner's name, then its model as the operator reads it, then the provider. The model is the
  catalog's label for a declared id, `Provider default` when the runner records no model, or the
  raw id marked `unrecognised` when the catalog does not declare it. All three selects use it. One format, `{name} — {model part} ({cli})`, and the model part is
  not repeated when the name already ends with it, as the names the Hub gives its own runners do
  (`agents.py:713`). The checkpoint-runner select names the project's checkpoint model when one is
  set, since that model is the one that runs (operator review 2026-09-24).
- No uniqueness constraint on runner names. Duplicate names are legitimate after this change,
  because the option text now tells them apart. A unique index would also need a migration that
  fails on the operator's existing duplicates (F268 recorded `D1 Seed` twice).

## Out of scope

- A warning in the create dialog about a name already in use. F268 names it, but it is a naming
  nudge, not the defect.
- How a model alias renders. `a-model-alias-is-a-model-choice` extends this helper if it ships.

## Capabilities

- **runner-registry**: ADDED, a runner offered for choosing names its model.

## Impact

UI only (`hub/ui/src`), so the committed bundle (`hub/hub/static/ui`) is refreshed with it. It
reaches the operator's `:8000` on their next reload. No API, schema or migration change.
