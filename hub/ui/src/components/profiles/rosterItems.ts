/**
 * The roster as the Profiles page reads it: each profile's status, its index row, and the run it is
 * on. Pure, so the rules are tested without React.
 */
import type { AgentSummary } from '@/api/agents'
import type { ModelCatalogResponse } from '@/api/modelCatalog'
import type { Task } from '@/api/tasks'
import { cliLabel, entryLabel } from '@/components/agents/pool/poolModel'
import type { ProfileListItem, ProfileStatus } from './profilesModel'

/** The run a profile is on now, if any: the first of its running runs that names a task, else its first. */
export function currentRun(agent: AgentSummary) {
  const runs = agent.running_runs ?? []
  return runs.find((run) => run.task_id) ?? runs[0] ?? null
}

function hasModel(agent: AgentSummary): boolean {
  return (agent.pool?.length ?? 0) > 0 || Boolean(agent.runner_id)
}

/** Working or reviewing, and on what; Held, and why; Idle; No model. A run on a task under review
 *  that the profile did not build is a review. Held is work waiting that cannot start: the queue
 *  route's `waiting_reason` (an allowance, a budget, a missing CLI...), read only while nothing runs. */
export function profileStatus(
  agent: AgentSummary,
  taskOf: (id: string) => Task | undefined,
  heldReason: string | null = null,
): ProfileStatus {
  const run = currentRun(agent)
  const live = run !== null || agent.status === 'running' || agent.status === 'working'
  if (live) {
    const task = run?.task_id ? taskOf(run.task_id) : undefined
    const reviewing = task?.status === 'under_review' && (task.builder ?? task.assignee) !== agent.name
    return { kind: reviewing ? 'reviewing' : 'working', detail: task?.title ?? (run?.task_id ? null : run ? 'a thread' : null) }
  }
  if (!hasModel(agent)) return { kind: 'no-model' }
  if (heldReason) return { kind: 'held', detail: heldReason }
  return { kind: 'idle' }
}

/** A roster entry as an index row: its default model by display name, the rest of its pool counted. */
export function profileItem(
  agent: AgentSummary,
  {
    catalog,
    charterName,
    spend,
    taskOf,
    heldReason = null,
  }: {
    catalog: ModelCatalogResponse | undefined
    charterName: string | null
    spend: number | null | undefined
    taskOf: (id: string) => Task | undefined
    /** The queue's reason its waiting work has not started, if any. */
    heldReason?: string | null
  },
): ProfileListItem {
  const pool = agent.pool ?? []
  const entry = pool.find((e) => e.default) ?? pool[0]
  const provider = entry?.cli ?? (agent.runner_id && agent.runner && agent.runner !== 'native' ? agent.runner : null)
  return {
    name: agent.name,
    colorIndex: agent.color_index ?? null,
    charterName,
    provider,
    providerLabel: provider ? cliLabel(provider) : null,
    model: entry ? entryLabel(catalog, entry) : agent.runner_id ? (agent.display_model ?? null) : null,
    moreModels: Math.max(0, pool.length - 1),
    status: profileStatus(agent, taskOf, heldReason),
    spendUsd: spend,
    lastActiveAt: agent.last_seen ?? null,
    archived: agent.lifecycle === 'archived',
  }
}
