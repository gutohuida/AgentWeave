import type { Runner } from '@/api/runners'
import { providerForRunner, resolveCatalogModel, type ModelCatalogResponse } from '@/api/modelCatalog'

/** The catalog a provider runner's models come from: the Claude API ids, which the `claude`
 * catalog declares (`hub/hub/runner_provider.py::provider_model_ids`). */
export const PROVIDER_RUNNER_CATALOG = 'claude'

/** The label of a provider runner's model, or undefined when the catalog does not declare it. */
export function providerRunnerModelLabel(
  catalog: ModelCatalogResponse | undefined,
  model: string | null,
): string | undefined {
  const provider = catalog?.providers.find((p) => p.provider === PROVIDER_RUNNER_CATALOG)
  return provider?.models.find((m) => m.id === model)?.label
}

/** Whether *runner* sends its runs to a model provider (`a-copilot-agent-uses-hooks-and-its-own-agents`
 * design D7). Its model is then the runner's for every run: the composer offers no model choice, and
 * the Hub refuses a run's `model` override with a 400. */
export function runnerSetsModel(runner: Pick<Runner, 'provider_config'> | null | undefined): boolean {
  return !!runner?.provider_config
}

/** The stored model *model* when the Hub will not pass it to a run on *cli*, else null
 * (`rebinding-an-agents-runner-starts-clean` D4/D7; mirrors `model_applies_to_cli` in
 * `hub/hub/model_catalog.py`). A conversation can store a model its agent's CLI does not offer,
 * Claude's `haiku` on an agent since rebound to Copilot: the Hub then runs the runner's own model,
 * and the composer says so. It is withheld only when another CLI declares it (by id or alias) and
 * this one does not; a model no CLI declares runs as stored. A display rule only, the backend
 * decides; the stored model is never removed from the overrides, which the composer sends back with
 * every message and the Hub refuses to see changed. */
export function withheldStoredModel(
  catalog: ModelCatalogResponse | undefined,
  cli: string | null | undefined,
  model: string | null | undefined,
): string | null {
  const providerId = providerForRunner(cli)
  if (!catalog || !providerId || !model) return null
  const declares = (provider: ModelCatalogResponse['providers'][number]) =>
    resolveCatalogModel(provider, model) !== null
  const own = catalog.providers.find((p) => p.provider === providerId)
  if (!own || declares(own)) return null
  return catalog.providers.some(declares) ? model : null
}

/** The overrides a run on *runner* may carry. A conversation can hold a `model` stored before its
 * agent's runner gained a provider; the Hub keeps it (rebinding back restores it) but refuses it on
 * a new run, so it is left out of the request rather than sent to be refused. */
export function overridesForRunner(
  overrides: Record<string, string>,
  runner: Pick<Runner, 'provider_config'> | null | undefined,
): Record<string, string> {
  if (!runnerSetsModel(runner) || !('model' in overrides)) return overrides
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { model, ...rest } = overrides
  return rest
}
