import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface ModelDescriptor {
  id: string
  label: string
  aliases: string[]
  context_window: number | null
  default: boolean
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

export function providerForRunner(runner: string | undefined | null): string | null {
  if (!runner) return null
  if (runner === 'claude' || runner === 'claude_proxy' || runner === 'native') return 'claude'
  if (runner === 'codex') return 'codex'
  return null
}
