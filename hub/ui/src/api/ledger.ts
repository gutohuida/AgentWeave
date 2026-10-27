import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** `GET /projects/{id}/ledger` (slice project-ledger). Lanes are newest first; `spend.by_day` is
 *  oldest first so it draws left to right. The UI renders each in the order it arrives. */
export interface ProjectLedger {
  merges: Array<{
    id: string
    task_id: string
    task_title: string | null
    outcome: string
    commit_sha: string | null
    source_branch: string | null
    target_branch: string | null
    reason: string | null
    actor_kind: string
    actor: string | null
    at: string | null
  }>
  spend: {
    /** From the work tally. Null: no record reports a cost, which is unknown and never $0. */
    total_usd: number | null
    total_tokens: number
    worker_usd: number
    /** Runs counted beside the cost because no cost was reported for them. */
    unpriced?: number
    by_day: Array<{ day: string; usd: number | null; worker_usd: number; tokens: number }>
    by_agent: Array<{ agent: string; usd: number | null; tokens: number; turns: number; unpriced?: number }>
    by_task: Array<{ task_id: string; task_title: string | null; usd: number | null; tokens: number; turns: number }>
  }
  divergences: Array<{
    id: string
    run_id: string
    agent: string
    task_id: string | null
    task_title: string | null
    task_status_at_end: string | null
    run_exit_status: string | null
    policy_applied: string | null
    outcome: string | null
    at: string | null
    resolved_at: string | null
  }>
  messages: Array<{
    id: string
    sender: string
    recipient: string
    subject: string | null
    excerpt: string
    task_id: string | null
    task_title: string | null
    at: string | null
  }>
  origins: { spec: number; loop: number; agent: number; operator: number }
  notices: Array<{
    kind: string
    count: number
    first_at: string | null
    last_at: string | null
    by_agent: Array<{ agent: string | null; count: number }>
  }>
  totals: { merged: number; integrations: number; divergences: number; open_divergences: number; tasks: number }
}

export function useProjectLedger() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ProjectLedger>({
    queryKey: ['project', projectId, 'ledger'],
    queryFn: () => getJson<ProjectLedger>(`/api/v1/projects/${projectId}/ledger`),
    enabled: isConfigured && !!projectId,
  })
}
