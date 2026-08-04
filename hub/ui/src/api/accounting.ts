import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, patchJson } from './client'
import { useConfigStore } from '@/store/configStore'

export interface UsageSummary {
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
  measured_turns: number
  unavailable_turns: number
  api_equivalent_usd_micros: number | null
}

export interface AgentUsageSummary extends UsageSummary {
  agent: string
}

export interface TokenBudgetState {
  limit_tokens: number | null
  used_tokens: number
  remaining_tokens: number | null
  exhausted: boolean
}

export type AccountingDisplay =
  | { kind: 'allowance'; label: 'Rate-limit allowance'; allowance: Record<string, unknown> }
  | { kind: 'api_equivalent'; label: 'API-equivalent estimate'; usd_micros: number }
  | { kind: 'tokens'; label: 'Tokens'; total_tokens: number }
  | { kind: 'unavailable'; label: 'Usage unavailable' }

export interface TurnUsage {
  id: string
  run_id: string
  agent: string
  status: 'measured' | 'unavailable'
  runner: string | null
  model: string | null
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
  cache_read_tokens: number | null
  cache_write_tokens: number | null
  reasoning_tokens: number | null
  api_equivalent_usd_micros: number | null
  allowance: Record<string, unknown> | null
  observed_at: string
}

export interface AccountingSnapshot {
  project: UsageSummary
  agents: AgentUsageSummary[]
  budget: TokenBudgetState
  preferred_display: AccountingDisplay
  recent_turns: TurnUsage[]
}

export function useAccounting() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<AccountingSnapshot>({
    queryKey: ['project', projectId, 'accounting'],
    queryFn: () => getJson<AccountingSnapshot>(`/api/v1/projects/${projectId}/accounting`),
    enabled: isConfigured && !!projectId,
  })
}

export function useUpdateTokenBudget() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation<TokenBudgetState, Error, number | null>({
    mutationFn: (tokenBudget) => patchJson<TokenBudgetState>(
      `/api/v1/projects/${projectId}/accounting/budget`,
      { token_budget: tokenBudget },
    ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'accounting'] })
    },
  })
}
