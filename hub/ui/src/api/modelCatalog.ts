import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** One selectable context window for a model, and the exact model id that selects it.
 *
 * A variant *is* a model id, so choosing one is expressed as the ordinary model override — the
 * composer, the trigger payload and the Hub all keep working on the one concept they already had.
 */
export interface WindowVariant {
  id: string
  label: string
  context_window: number | null
  default: boolean
}

export interface ModelDescriptor {
  id: string
  label: string
  aliases: string[]
  context_window: number | null
  default: boolean
  /** Empty for a model that offers one window. Only rendered as a control where there is more
   *  than one, because a control offering one choice is not a choice. */
  windows: WindowVariant[]
}

export interface ControlValue {
  id: string
  label: string
}

export interface ApplySpec {
  style: 'flag' | 'config' | 'none'
  template: string
}

export interface ControlDescriptor {
  id: string
  label: string
  kind: 'enum' | 'boolean' | 'number'
  values: ControlValue[]
  default: string | null
  apply: ApplySpec
}

export interface ProviderDescriptor {
  provider: string
  label: string
  models: ModelDescriptor[]
  controls: ControlDescriptor[]
}

export interface ModelCatalogResponse {
  providers: ProviderDescriptor[]
}

/** The provider/model/control catalog — instance-scoped, not project-scoped: it is static
 * and identical for every project (2026-08-04-hub-model-control-and-provisioning), so its
 * query key deliberately carries no project ID, matching useProjects's own rationale. */
export function useModelCatalog() {
  const { isConfigured } = useConfigStore()
  return useQuery<ModelCatalogResponse>({
    queryKey: ['model-catalog'],
    queryFn: () => getJson<ModelCatalogResponse>('/api/v1/model-catalog'),
    enabled: isConfigured,
    staleTime: Infinity,
  })
}

export const PERMISSION_MODE_CONTROL = 'permission_mode'

/** Every posture any provider declares, deduplicated by id, in catalog order.
 *
 * The agent-level *default* is a property of the agent, and an agent may have no runner bound —
 * so unlike a per-run override there is no one provider to read the control off. Both providers
 * declare the same four values with the same labels on purpose; taking the union keeps that true
 * without restating them here. Mirrors `permission_mode_values()` in hub/hub/model_catalog.py. */
export function permissionModeValues(catalog: ModelCatalogResponse | undefined): ControlValue[] {
  const seen = new Map<string, ControlValue>()
  for (const provider of catalog?.providers ?? []) {
    const control = provider.controls.find((c) => c.id === PERMISSION_MODE_CONTROL)
    for (const value of control?.values ?? []) {
      if (!seen.has(value.id)) seen.set(value.id, value)
    }
  }
  return [...seen.values()]
}

/** The model *modelId* names — by its own id, or by one of its selectable windows.
 *
 * Mirrors `ProviderDescriptor.model` in hub/hub/model_catalog.py. Without this the model pill
 * reads "—" whenever a window variant is selected, because the selected id is not the base
 * model's. */
export function modelForId(
  provider: ProviderDescriptor,
  modelId: string | null,
): ModelDescriptor | undefined {
  if (!modelId) return undefined
  return provider.models.find(
    (m) => m.id === modelId || m.windows.some((w) => w.id === modelId),
  )
}

/** The window currently in force for *modelId*: the variant it names, or the model's own default
 *  variant when it names the base id. Undefined when the model declares no variants. */
export function windowForId(
  provider: ProviderDescriptor,
  modelId: string | null,
): WindowVariant | undefined {
  const model = modelForId(provider, modelId)
  if (!model || model.windows.length < 2) return undefined
  return (
    model.windows.find((w) => w.id === modelId)
    ?? model.windows.find((w) => w.default)
    ?? model.windows[0]
  )
}

export function providerForRunner(runner: string | undefined | null): string | null {
  if (!runner) return null
  if (runner === 'claude' || runner === 'claude_proxy' || runner === 'native') return 'claude'
  if (runner === 'codex') return 'codex'
  return null
}
