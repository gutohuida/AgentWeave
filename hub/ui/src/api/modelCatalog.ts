import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { hubDate } from '@/lib/hubTime'

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

export interface CatalogSource {
  kind: 'cli_cache' | 'built_in'
  fetched_at: string | null
  client_version: string | null
  reason: string | null
}

export interface ProviderDescriptor {
  provider: string
  label: string
  models: ModelDescriptor[]
  controls: ControlDescriptor[]
  // Optional so a test's hand-built catalog fixture (most predate this field) still type-checks;
  // the Hub's real response always sends it (see `catalogSourceLine`, which treats a missing
  // source the same as no line to show).
  source?: CatalogSource
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

export function providerForRunner(runner: string | undefined | null): string | null {
  if (!runner) return null
  if (runner === 'claude' || runner === 'claude_proxy' || runner === 'native') return 'claude'
  if (runner === 'codex') return 'codex'
  return null
}

/** The descriptor *value* names, whether it is a declared id or one of a model's declared
 * aliases — the one resolution rule every UI reader of a stored model shares
 * (`a-model-alias-is-a-model-choice` D1/D2; mirrors `ProviderDescriptor.model` in
 * `hub/hub/model_catalog.py`, which every backend door already goes through). */
export function resolveCatalogModel(
  provider: ProviderDescriptor | null | undefined,
  value: string | null | undefined,
): ModelDescriptor | null {
  if (!provider || !value) return null
  return provider.models.find((m) => m.id === value || m.aliases.includes(value)) ?? null
}

/** The label for a stored value that resolved to *model*: the model's own label for a declared
 * id, or "{alias} — latest (now {model's current label})" for a declared alias — stated as the
 * catalog's present reading, not a promise (design.md D2). Used by the pickers that offer a
 * model choice (`RunnerForm`, `AgentCreateDialog`, the checkpoint-model select, `ModelPicker`) —
 * not by `runnerOptionLabel`, which names what a runner *records*, not what it currently
 * resolves to. */
export function catalogModelLabel(model: ModelDescriptor, value: string): string {
  return model.id === value ? model.label : `${value} — latest (now ${model.label})`
}

/** One line naming where a provider's offered models came from
 * (`the-codex-models-offered-are-the-ones-its-cli-lists` design D2). `cli_cache` names the
 * installed CLI version and when its cache was fetched; `built_in` states the reason the cache
 * was not used instead — the same reason string the Hub computed, not re-derived here. */
export function catalogSourceLine(source: CatalogSource | null | undefined): string | null {
  if (!source) return null
  if (source.kind === 'cli_cache') {
    const version = source.client_version ?? 'unknown version'
    const fetched = source.fetched_at ? hubDate(source.fetched_at) : null
    // Built by hand, not a single Intl.DateTimeFormat call: 'en-GB' abbreviates September as
    // "Sept" (four letters) where 'en-US' gives "Sep" (three) — the month token is pinned to
    // 'en-US' regardless of locale so the abbreviation stays fixed width, and "day month" order
    // is applied afterward rather than trusted to a locale that might reorder it back.
    const fetchedText =
      fetched && !Number.isNaN(fetched.getTime())
        ? `, fetched ${fetched.getUTCDate()} ${new Intl.DateTimeFormat('en-US', { month: 'short', timeZone: 'UTC' }).format(fetched)}`
        : ''
    return `As listed by your installed Codex CLI (${version}${fetchedText})`
  }
  return `Built-in list: ${source.reason ?? 'no CLI cache to read'}`
}
