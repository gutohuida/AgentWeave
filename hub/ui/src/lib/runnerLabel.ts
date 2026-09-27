import type { ModelCatalogResponse } from '@/api/modelCatalog'
import type { Runner } from '@/api/runners'

function modelPartFor(
  modelId: string | null | undefined,
  cli: string,
  catalog: ModelCatalogResponse | undefined,
): string {
  if (!modelId) return 'Provider default'
  if (!catalog) return modelId
  const model = catalog.providers.find((provider) => provider.provider === cli)?.models.find((m) => m.id === modelId)
  return model ? model.label : `${modelId} (unrecognised)`
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
