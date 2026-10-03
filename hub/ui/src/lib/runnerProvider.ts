import type { Runner } from '@/api/runners'
import type { ModelCatalogResponse } from '@/api/modelCatalog'

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
