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
  unpriced_turns: number
  /** Copilot's reported charge (nano-AIU), summed; null where no turn reported one. */
  ai_nano_aiu?: number | null
  premium_requests?: number | null
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
  | {
      kind: 'allowance'
      label: 'Rate-limit allowance'
      allowance: Record<string, unknown>
      /** The runner whose reading this is (`"claude"`, `"copilot"`). */
      runner?: string | null
    }
  | {
      kind: 'api_equivalent'
      label: 'API-equivalent estimate'
      usd_micros: number
      unpriced_turns: number
    }
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
  ai_nano_aiu?: number | null
  premium_requests?: number | null
}

/** What the Hub spent for the project outside the turns, one line per worker kind (F240):
 *  checkpoints, their probes, conversation titles, the vault jobs. Its tokens are already in
 *  `project` and `budget`; the agents' figures stay turns only. */
export interface WorkerUsageLine {
  kind: string
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
  /** Calls that reported a token count. */
  measured_calls: number
  /** Calls that ran and reported none. A call that never ran is neither. */
  unmeasured_calls: number
  api_equivalent_usd_micros: number | null
}

export interface AccountingSnapshot {
  project: UsageSummary
  agents: AgentUsageSummary[]
  /** Absent from a Hub older than F240. */
  workers?: WorkerUsageLine[]
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

/** The whole-conversation rollup — not capped like `AccountingSnapshot.recent_turns`, which
 *  only holds the project's most recent 50 turns across every conversation and agent. */
export function useConversationAccounting(conversationId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<UsageSummary>({
    queryKey: ['project', projectId, 'accounting', 'conversation', conversationId],
    queryFn: () =>
      getJson<UsageSummary>(
        `/api/v1/projects/${projectId}/accounting/conversations/${conversationId}`,
      ),
    enabled: isConfigured && !!projectId && !!conversationId,
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
