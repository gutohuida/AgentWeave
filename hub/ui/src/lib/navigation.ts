import type { AgentSummary } from '@/api/agents'
import { NEW_SESSION_ID } from './constants'

/** What a destination's `conversationId` holds when the operator has deliberately asked for a new
 *  conversation — a record that does not exist yet, because a conversation is created by its first
 *  message and not by the "new" action (design.md).
 *
 *  Distinct from `null`, which means "no conversation named": that one resolves to the agent's most
 *  recent. Collapsing the two is what would make the conversation list, once it loads, silently
 *  replace the empty composer the operator just asked for. */
export const NEW_CONVERSATION_ID = NEW_SESSION_ID

export interface RailProject {
  id: string
  name: string
  agents: AgentSummary[]
}

export const PROJECT_TABS = ['overview', 'tasks', 'spec', 'jobs', 'activity'] as const
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
  | { kind: 'project'; projectId: string; tab: ProjectTab }
  | { kind: 'project'; projectId: string; tab: 'environment'; environmentSection: EnvironmentSection }
  // `agent` is null only on the new-conversation surface reached from the recency view, where
  // no agent is implied by where the operator started — that surface asks for one.
  | { kind: 'conversation'; projectId: string; agent: string | null; conversationId: string | null }
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

/** The composer-primary surface for a conversation that does not exist yet.
 *
 * `agent` is null when the operator started from the recency view: no agent is implied there, so
 * the surface requires one to be chosen before the first message can be sent. */
export function newConversationDestination(
  projectId: string,
  agent: string | null = null,
): Extract<WorkspaceDestination, { kind: 'conversation' }> {
  return { kind: 'conversation', projectId, agent, conversationId: NEW_CONVERSATION_ID }
}

export function isNewConversationDestination(destination: WorkspaceDestination): boolean {
  return destination.kind === 'conversation' && destination.conversationId === NEW_CONVERSATION_ID
}

export interface SelectableConversation {
  id: string
  agent: string
}

/** Which conversation a destination actually opens.
 *
 * `AgentOutputPanel` used to answer this itself: it held `selectedConversationId`, seeded it from
 * the destination, auto-selected `conversations[0]` once the list loaded, and reported changes back
 * upward — two sources of truth kept in step by effects.
 *
 * The auto-select is not deleted along with that state; it is what makes activating an agent open
 * something. It moves here, where it can also be made *not* to fire for the new-conversation
 * surface — otherwise the operator's empty composer is replaced by their most recent thread the
 * moment the conversation list resolves.
 *
 * `conversations` must already be ordered most recent activity first; the project listing endpoint
 * orders it, and re-sorting here would put the destination and the rail out of step. */
export function resolveConversationSelection(
  destination: WorkspaceDestination,
  conversations: SelectableConversation[],
): string | null {
  if (destination.kind !== 'conversation') return null
  if (destination.conversationId === NEW_CONVERSATION_ID) return null
  if (destination.conversationId) return destination.conversationId
  return conversations.find((conversation) => conversation.agent === destination.agent)?.id ?? null
}

/** Returns true when the destination has entered an area with its own
 *  navigation (configuration). The Sidebar derives its section mode from
 *  this; the destination itself still uses `tab: 'environment'` so deep
 *  links continue to resolve. */
export function isConfigurationDestination(
  destination: WorkspaceDestination,
): destination is Extract<WorkspaceDestination, { kind: 'project'; tab: 'environment' }> {
  return destination.kind === 'project' && destination.tab === 'environment'
}

/** Serializes a destination into a URL search string (including the leading
 *  `?`, or `''` for the zero-project state). No provider session identifier is
 *  ever part of this shape — only AgentWeave's own project/agent/conversation
 *  identity. */
export function serializeDestination(destination: WorkspaceDestination): string {
  if (destination.kind === 'zero') return ''
  const params = new URLSearchParams()
  params.set('project', destination.projectId)
  if (destination.kind === 'conversation') {
    if (destination.agent) params.set('agent', destination.agent)
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
 *  project is named at all (the zero-project / unspecified case). Unknown or
 *  missing tab/section values are coerced to their defaults; validating the
 *  project ID itself against the registered collection is `resolveDestination`'s
 *  job, not this function's — parsing must not require knowing what projects
 *  exist. */
export function parseDestination(search: string): WorkspaceDestination | null {
  const params = new URLSearchParams(search)
  const projectId = params.get('project')
  if (!projectId) return null

  const agent = params.get('agent')
  const conversation = params.get('conversation')
  // The agentless new-conversation surface has no `agent` to key on, so the sentinel is what
  // identifies it — otherwise a reload there would land on the project overview.
  if (agent || conversation === NEW_CONVERSATION_ID) {
    return { kind: 'conversation', projectId, agent, conversationId: conversation }
  }

  const rawTab = params.get('tab')
  if (rawTab === 'environment') {
    const rawSection = params.get('section')
    const section: EnvironmentSection = (ENVIRONMENT_SECTIONS as readonly string[]).includes(
      rawSection ?? '',
    )
      ? (rawSection as EnvironmentSection)
      : DEFAULT_ENVIRONMENT_SECTION
    return environmentDestination(projectId, section)
  }
  const tab: ProjectTab = (PROJECT_TABS as readonly string[]).includes(rawTab ?? '')
    ? (rawTab as ProjectTab)
    : DEFAULT_TAB
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
