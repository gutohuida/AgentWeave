import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson, patchJson, fetchWithAuth } from './client'
import { useConfigStore } from '@/store/configStore'

export type RunnerCli = 'claude' | 'codex' | 'copilot'

/** A Copilot runner's model provider (BYOK, `a-copilot-agent-uses-hooks-and-its-own-agents` D7):
 * the provider's address and the *name* of a variable in the Hub's environment that holds its key.
 * The key itself is never sent, stored or returned. */
export interface ProviderConfig {
  type: 'anthropic'
  base_url: string
  api_key_var: string
}

/** What the dialog submits. `base_url` is omitted for the provider's own address. */
export interface ProviderConfigInput {
  type: 'anthropic'
  base_url?: string
  api_key_var: string
}

export interface Runner {
  id: string
  project_id: string
  name: string
  cli: RunnerCli
  model?: string | null
  flags?: string[] | null
  /** Set on a Copilot runner whose runs go to a model provider; its model is then a Claude API id
   * and every run uses it (design D7). A damaged stored value reads as null here. */
  provider_config?: ProviderConfig | null
  created_at: string
  updated_at: string
  /** True when `model` is set but the catalog does not declare it for `cli` — a runner created
   * before the catalog existed, or naming a model a newer CLI release added. Computed by the API
   * (`RunnerResponse._flag_unrecognised_model`), not recomputed here, so the browser and the Hub
   * cannot disagree about which models are recognised. */
  model_unrecognised: boolean
}

export interface RunnerCreate {
  name: string
  cli: RunnerCli
  model?: string | null
  provider_config?: ProviderConfigInput
}

/** `model` is omitted to leave it alone and sent as `null` to clear it back to the provider's
 * default — two different requests the Hub distinguishes (`model_fields_set` in `update_runner`). */
export interface RunnerUpdate {
  name?: string
  model?: string | null
  /** As `model`: omitted leaves it alone, `null` removes the provider. */
  provider_config?: ProviderConfigInput | null
}

export interface RunnerLaunchability {
  runner?: string
  present: boolean
  authorized: boolean
  runnable: boolean
  reason?: string | null
}

export function useRunners() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<Runner[]>({
    queryKey: ['project', projectId, 'runners'],
    queryFn: () => getJson<Runner[]>(`/api/v1/projects/${projectId}/runners`),
    enabled: isConfigured && !!projectId,
  })
}

export function useRunnerLaunchability() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ runners: Record<string, RunnerLaunchability> }>({
    queryKey: ['project', projectId, 'runners', 'launchability'],
    queryFn: () => getJson(`/api/v1/projects/${projectId}/runners/launchability`),
    enabled: isConfigured && !!projectId,
    staleTime: 30_000,
  })
}

/** Launchability per catalog provider, independent of whether a runner row exists yet —
 * backs agent creation by provider and model (2026-08-04-hub-model-control-and-provisioning),
 * where no runner exists to probe before the operator has chosen one. */
export function useProviderLaunchability() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<{ providers: Record<string, RunnerLaunchability> }>({
    queryKey: ['project', projectId, 'runners', 'launchability-by-provider'],
    queryFn: () => getJson(`/api/v1/projects/${projectId}/runners/launchability-by-provider`),
    enabled: isConfigured && !!projectId,
    staleTime: 30_000,
  })
}

export function useCreateRunner() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (runner: RunnerCreate) =>
      postJson<Runner>(`/api/v1/projects/${projectId}/runners`, runner),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'runners'] }),
  })
}

export function useUpdateRunner() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: RunnerUpdate }) =>
      patchJson<Runner>(`/api/v1/projects/${projectId}/runners/${id}`, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'runners'] })
      // A bound agent's verdict is read from its runner, and lives under `agents` with a 30 s
      // stale time, so it would outlive the edit (F178). Create and delete need nothing: a new
      // runner has no agent, and the Hub refuses to delete one that has (409).
      return queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agents', 'launchability'] })
    },
  })
}

export function useDeleteRunner() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await fetchWithAuth(`/api/v1/projects/${projectId}/runners/${id}`, {
        method: 'DELETE',
      })
      return res.ok
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'runners'] }),
  })
}

/** How long this agent waits on the operator. `null` clears back to the built-in default.
 *
 * Bounds match the API's, which is the real guard — the inputs' min/max are a convenience on top
 * of it rather than the only thing standing between a typo and a run that waits ten minutes. */
export const MIN_WAITING_SECONDS = 10
export const MAX_WAITING_SECONDS = 600

export function useUpdateAgentWaiting() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({
      agent,
      field,
      seconds,
    }: {
      agent: string
      field: 'permission_timeout_seconds' | 'question_timeout_seconds'
      seconds: number | null
    }) => patchJson(`/api/v1/projects/${projectId}/agents/${agent}`, { [field]: seconds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agents'] })
    },
  })
}

export function useBindAgentRunner() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ agent, runnerId }: { agent: string; runnerId: string | null }) =>
      patchJson(`/api/v1/projects/${projectId}/agents/${agent}`, { runner_id: runnerId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'agents'] })
    },
  })
}
