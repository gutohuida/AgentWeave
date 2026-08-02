import type { AgentSummary } from '@/api/agents'

export interface RailProject {
  id: string
  name: string
  agents: AgentSummary[]
}

export type WorkspaceDestination =
  | { kind: 'project'; projectId: string }
  | { kind: 'page'; page: string }
  | { kind: 'conversation'; projectId: string; agent: string; conversationId: string | null }

/** Collection-shaped from day one, even while one authenticated project is visible. */
export function buildRailProjects(
  project: { id: string; name: string } | null,
  agents: AgentSummary[],
): RailProject[] {
  return project ? [{ ...project, agents }] : []
}

export function projectDestination(
  projectId: string,
): Extract<WorkspaceDestination, { kind: 'project' }> {
  return { kind: 'project', projectId }
}

export function agentDestination(
  projectId: string,
  agent: string,
  conversationId: string | null = null,
): Extract<WorkspaceDestination, { kind: 'conversation' }> {
  return { kind: 'conversation', projectId, agent, conversationId }
}
