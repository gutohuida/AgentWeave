import type { ModelCatalogResponse } from '@/api/modelCatalog'
import type { Runner } from '@/api/runners'

function modelPartFor(
  modelId: string | null | undefined,
  cli: string,
  catalog: ModelCatalogResponse | undefined,
): string {
  if (!modelId) return 'Provider default'
  if (!catalog) return modelId
  const provider = catalog.providers.find((p) => p.provider === cli)
  const model = provider?.models.find((m) => m.id === modelId)
  if (model) return model.label
  // A declared alias names what the runner records, not what it currently resolves to — the
  // model pickers are where "now Opus 5.5" is shown (design.md D2).
  const aliasTarget = provider?.models.find((m) => m.aliases.includes(modelId))
  if (aliasTarget) return `${modelId} (latest)`
  return `${modelId} (unrecognised)`
}

/** Renders a runner as one choice among many — the format every select that offers a runner
 * uses (F268; `a-runner-choice-names-its-model`). `{name} — {model part} ({cli})`, with the model
 * part read from the catalog so it always agrees with `RunnerResponse.model_unrecognised`
 * (`hub/hub/schemas/runners.py`) rather than a second, possibly-disagreeing computation.
 *
 * `options.model` overrides which model the choice actually runs on — only the checkpoint-runner
 * select passes it, with the project's `checkpoint_model`, since that overrides `runner.model`
 * for the model that runs (`checkpoint_trigger.py`). A falsy override falls back to the runner's
 * own model.
 *
 * The model part is dropped when `name` already ends with it — true of every runner the Hub names
 * for itself (`agents.py`'s `f"{provider label} — {model label}"`) — so picking up a later model
 * change still reads as the truth rather than as a repeated word. */
export function runnerOptionLabel(
  runner: Runner,
  catalog: ModelCatalogResponse | undefined,
  options?: { model?: string | null },
): string {
  const modelId = options?.model || runner.model
  const modelPart = modelPartFor(modelId, runner.cli, catalog)
  const suffix = ` — ${modelPart}`
  const base = runner.name.endsWith(suffix) ? runner.name : `${runner.name}${suffix}`
  return `${base} (${runner.cli})`
}
