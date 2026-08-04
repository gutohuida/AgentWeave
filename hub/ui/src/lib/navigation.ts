import type { AgentSummary } from '@/api/agents'

export interface RailProject {
  id: string
  name: string
  agents: AgentSummary[]
}

export const PROJECT_TABS = ['overview', 'tasks', 'spec', 'jobs', 'activity', 'environment'] as const
export type ProjectTab = (typeof PROJECT_TABS)[number]

export const ENVIRONMENT_SECTIONS = [
  'quality',
  'instructions',
  'runners',
  'charters',
  'worktrees',
  'diagnostics',
  'budgets',
  'settings',
] as const
export type EnvironmentSection = (typeof ENVIRONMENT_SECTIONS)[number]

const DEFAULT_TAB: ProjectTab = 'overview'
const DEFAULT_ENVIRONMENT_SECTION: EnvironmentSection = ENVIRONMENT_SECTIONS[0]

export type WorkspaceDestination =
  | { kind: 'project'; projectId: string; tab: ProjectTab; environmentSection?: EnvironmentSection }
  | { kind: 'conversation'; projectId: string; agent: string; conversationId: string | null }
  | { kind: 'zero' }

/** Collection-shaped from day one, even while one authenticated project is visible. */
export function buildRailProjects(
  project: { id: string; name: string } | null,
  agents: AgentSummary[],
): RailProject[] {
  return project ? [{ ...project, agents }] : []
}

export function projectDestination(
  projectId: string,
  tab: ProjectTab = DEFAULT_TAB,
): Extract<WorkspaceDestination, { kind: 'project' }> {
  if (tab === 'environment') {
    return { kind: 'project', projectId, tab, environmentSection: DEFAULT_ENVIRONMENT_SECTION }
  }
  return { kind: 'project', projectId, tab }
}

export function environmentDestination(
  projectId: string,
  section: EnvironmentSection = DEFAULT_ENVIRONMENT_SECTION,
): Extract<WorkspaceDestination, { kind: 'project' }> {
  return { kind: 'project', projectId, tab: 'environment', environmentSection: section }
}

export function agentDestination(
  projectId: string,
  agent: string,
  conversationId: string | null = null,
): Extract<WorkspaceDestination, { kind: 'conversation' }> {
  return { kind: 'conversation', projectId, agent, conversationId }
}

/** Serializes a destination into a URL search string (including the leading
 * `?`, or `''` for the zero-project state). No provider session identifier is
 * ever part of this shape — only AgentWeave's own project/agent/conversation
 * identity. */
export function serializeDestination(destination: WorkspaceDestination): string {
  if (destination.kind === 'zero') return ''
  const params = new URLSearchParams()
  params.set('project', destination.projectId)
  if (destination.kind === 'conversation') {
    params.set('agent', destination.agent)
    if (destination.conversationId) params.set('conversation', destination.conversationId)
    return `?${params.toString()}`
  }
  params.set('tab', destination.tab)
  if (destination.tab === 'environment') {
    params.set('section', destination.environmentSection ?? DEFAULT_ENVIRONMENT_SECTION)
  }
  return `?${params.toString()}`
}

/** Parses a URL search string into a requested destination, or `null` when no
 * project is named at all (the zero-project / unspecified case). Unknown or
 * missing tab/section values are coerced to their defaults; validating the
 * project ID itself against the registered collection is `resolveDestination`'s
 * job, not this function's — parsing must not require knowing what projects
 * exist. */
export function parseDestination(search: string): WorkspaceDestination | null {
  const params = new URLSearchParams(search)
  const projectId = params.get('project')
  if (!projectId) return null

  const agent = params.get('agent')
  if (agent) {
    return agentDestination(projectId, agent, params.get('conversation'))
  }

  const rawTab = params.get('tab')
  const tab: ProjectTab = (PROJECT_TABS as readonly string[]).includes(rawTab ?? '')
    ? (rawTab as ProjectTab)
    : DEFAULT_TAB
  if (tab === 'environment') {
    const rawSection = params.get('section')
    const section: EnvironmentSection = (ENVIRONMENT_SECTIONS as readonly string[]).includes(
      rawSection ?? '',
    )
      ? (rawSection as EnvironmentSection)
      : DEFAULT_ENVIRONMENT_SECTION
    return environmentDestination(projectId, section)
  }
  return projectDestination(projectId, tab)
}

export interface ResolveDestinationOptions {
  /** `null` means the project collection has not finished loading yet — a
   * requested project ID is trusted provisionally rather than treated as
   * unknown, so the URL doesn't flicker to a fallback before the real
   * collection arrives. */
  availableProjectIds: string[] | null
  lastOpenedProjectId: string | null
}

/** Applies design.md's fallback order: keep a requested destination whose
 * project is registered, else the last-opened available project, else the
 * first available project, else the zero-project state. */
export function resolveDestination(
  requested: WorkspaceDestination | null,
  { availableProjectIds, lastOpenedProjectId }: ResolveDestinationOptions,
): WorkspaceDestination {
  if (requested && requested.kind !== 'zero') {
    if (availableProjectIds === null || availableProjectIds.includes(requested.projectId)) {
      return requested
    }
  }
  if (availableProjectIds === null) {
    return lastOpenedProjectId ? projectDestination(lastOpenedProjectId) : { kind: 'zero' }
  }
  if (lastOpenedProjectId && availableProjectIds.includes(lastOpenedProjectId)) {
    return projectDestination(lastOpenedProjectId)
  }
  if (availableProjectIds.length > 0) {
    return projectDestination(availableProjectIds[0])
  }
  return { kind: 'zero' }
}
