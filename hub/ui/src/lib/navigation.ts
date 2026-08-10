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

/** No `spec` tab. A specification is reached from the composer's Spec pill, in the conversation
 *  the operator is already in — not by leaving it, going to the project, and choosing a tab. A URL
 *  still carrying `tab=spec` is unknown here and coerces to the default tab, which is what should
 *  happen to a link to a place that no longer exists. */
export const PROJECT_TABS = ['overview', 'tasks', 'jobs', 'activity'] as const
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

/** Named for what an operator is trying to do, not for the shape of the data. *Context* and
 *  *Access* are defined here ahead of the checkpoint change that fills them; a section with
 *  nothing in it yet renders whatever settings exist at the time. */
export const AGENT_SETTINGS_SECTIONS = [
  'identity',
  'execution',
  'charter',
  'interaction',
  'context',
  'access',
  'workspace',
] as const
export type AgentSettingsSection = (typeof AGENT_SETTINGS_SECTIONS)[number]

const DEFAULT_TAB: ProjectTab = 'overview'
const DEFAULT_ENVIRONMENT_SECTION: EnvironmentSection = ENVIRONMENT_SECTIONS[0]
const DEFAULT_AGENT_SETTINGS_SECTION: AgentSettingsSection = AGENT_SETTINGS_SECTIONS[0]

/** The frontend twin of the Hub's `validate_spec_path` (`hub/hub/spec_manifest.py`), kept in
 *  step by hand as that file's own twin already is.
 *
 *  It belongs here because the document arrives as an opaque URL parameter: a destination is the
 *  first thing to see it and the last thing that can refuse it before it becomes a fetch. */
const SPEC_PATH_MAX_LENGTH = 255
const SPEC_PATH_CONTROL_CHARS = /[\x00-\x1f\x7f]/

export function isSpecDocumentPath(value: string): boolean {
  if (!value || value.length > SPEC_PATH_MAX_LENGTH) return false
  // Percent-encoding is never used by manifest paths, and allowing it here would let an encoded
  // traversal segment past the checks below — `specBridge`'s link resolution refuses it likewise.
  if (value.includes('\\') || value.includes('%')) return false
  if (value !== value.toLowerCase()) return false
  if (!value.startsWith('spec/') || !value.endsWith('.html')) return false
  return value
    .split('/')
    .every(
      (segment) =>
        segment.length > 0 && !segment.startsWith('.') && !SPEC_PATH_CONTROL_CHARS.test(segment),
    )
}

/** An illegal or absent value is *no document*, never an error: someone arriving on a mangled
 *  link should land in the conversation, not on a dead end. */
export function parseSpecDocument(value: string | null | undefined): string | null {
  return typeof value === 'string' && isSpecDocumentPath(value) ? value : null
}

export type WorkspaceDestination =
  | { kind: 'project'; projectId: string; tab: ProjectTab }
  | { kind: 'project'; projectId: string; tab: 'environment'; environmentSection: EnvironmentSection }
  // `agent` is null only on the new-conversation surface reached from the recency view, where
  // no agent is implied by where the operator started — that surface asks for one.
  //
  // `document` is the specification document open *beside* this conversation. It lives in the
  // destination rather than in component state so any conversation can open one, and so a reload
  // restores what the operator was looking at — the same property the conversation itself has.
  | {
      kind: 'conversation'
      projectId: string
      agent: string | null
      conversationId: string | null
      document: string | null
    }
  // Its own kind rather than an `ENVIRONMENT_SECTIONS` entry: those address a project and carry no
  // subject, so they cannot say *which* agent is being configured. `agent` is non-null by
  // construction — there is no such thing as configuring no agent.
  | { kind: 'agent-settings'; projectId: string; agent: string; section: AgentSettingsSection }
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

/** `document` defaults to null — most navigations to a conversation are not carrying one. The
 *  callers that are (opening a document, and the specification entry point) pass it explicitly,
 *  and `withDocument` below is what keeps an already-open one across a conversation change. */
export function agentDestination(
  projectId: string,
  agent: string,
  conversationId: string | null = null,
  document: string | null = null,
): Extract<WorkspaceDestination, { kind: 'conversation' }> {
  return { kind: 'conversation', projectId, agent, conversationId, document: parseSpecDocument(document) }
}

/** Open, change, or close the document beside a conversation without disturbing anything else
 *  about where the operator is. `null` closes it. */
export function withDocument(
  destination: Extract<WorkspaceDestination, { kind: 'conversation' }>,
  document: string | null,
): Extract<WorkspaceDestination, { kind: 'conversation' }> {
  return { ...destination, document: parseSpecDocument(document) }
}

export function agentSettingsDestination(
  projectId: string,
  agent: string,
  section: AgentSettingsSection = DEFAULT_AGENT_SETTINGS_SECTION,
): Extract<WorkspaceDestination, { kind: 'agent-settings' }> {
  return { kind: 'agent-settings', projectId, agent, section }
}

/** Where the back control on the settings page goes: a *fixed* target, the agent's most recent
 *  conversation, matching `App.tsx`'s fixed "Back to {project}" rather than remembering an origin.
 *
 *  `conversationId: null` is what makes it the most recent one — `resolveConversationSelection`
 *  already resolves null to the agent's newest, so this needs no lookup of its own. */
export function agentSettingsBackDestination(
  destination: Extract<WorkspaceDestination, { kind: 'agent-settings' }>,
): Extract<WorkspaceDestination, { kind: 'conversation' }> {
  return agentDestination(destination.projectId, destination.agent)
}

/** The composer-primary surface for a conversation that does not exist yet.
 *
 * `agent` is null when the operator started from the recency view: no agent is implied there, so
 * the surface requires one to be chosen before the first message can be sent. */
export function newConversationDestination(
  projectId: string,
  agent: string | null = null,
  document: string | null = null,
): Extract<WorkspaceDestination, { kind: 'conversation' }> {
  return {
    kind: 'conversation',
    projectId,
    agent,
    conversationId: NEW_CONVERSATION_ID,
    document: parseSpecDocument(document),
  }
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

/** The agent-scoped counterpart. Kept separate from `isConfigurationDestination` rather than
 *  widened into it: that one is a type guard onto the environment shape, and callers narrow on it
 *  to read `environmentSection`. */
export function isAgentSettingsDestination(
  destination: WorkspaceDestination,
): destination is Extract<WorkspaceDestination, { kind: 'agent-settings' }> {
  return destination.kind === 'agent-settings'
}

/** True in either configuration area. The Sidebar swaps into section-list-plus-back mode on this,
 *  because the shell is the same whichever subject is being configured. */
export function isSectionedDestination(destination: WorkspaceDestination): boolean {
  return isConfigurationDestination(destination) || isAgentSettingsDestination(destination)
}

/** Serializes a destination into a URL search string (including the leading
 *  `?`, or `''` for the zero-project state). No provider session identifier is
 *  ever part of this shape — only AgentWeave's own project/agent/conversation
 *  identity. */
export function serializeDestination(destination: WorkspaceDestination): string {
  if (destination.kind === 'zero') return ''
  const params = new URLSearchParams()
  params.set('project', destination.projectId)
  if (destination.kind === 'agent-settings') {
    params.set('agent', destination.agent)
    params.set('settings', destination.section)
    return `?${params.toString()}`
  }
  if (destination.kind === 'conversation') {
    if (destination.agent) params.set('agent', destination.agent)
    if (destination.conversationId) params.set('conversation', destination.conversationId)
    // Re-checked on the way out as well as on the way in: a destination is constructed in more
    // places than it is parsed, and an illegal path must never reach the URL to be pasted on.
    if (destination.document && isSpecDocumentPath(destination.document)) {
      params.set('document', destination.document)
    }
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

  // Checked *before* the conversation branch, and deliberately so: that branch claims any URL
  // carrying an `agent`, so testing it first would resolve every settings link to a chat.
  // `settings` without an `agent` is not a destination — there is no agent to configure — so it
  // falls through rather than being coerced to one.
  const rawSettingsSection = params.get('settings')
  if (agent && rawSettingsSection !== null) {
    const section: AgentSettingsSection = (
      AGENT_SETTINGS_SECTIONS as readonly string[]
    ).includes(rawSettingsSection)
      ? (rawSettingsSection as AgentSettingsSection)
      : DEFAULT_AGENT_SETTINGS_SECTION
    return agentSettingsDestination(projectId, agent, section)
  }

  // The agentless new-conversation surface has no `agent` to key on, so the sentinel is what
  // identifies it — otherwise a reload there would land on the project overview.
  if (agent || conversation === NEW_CONVERSATION_ID) {
    return {
      kind: 'conversation',
      projectId,
      agent,
      conversationId: conversation,
      // An illegal path resolves to "no document", never to an error page.
      document: parseSpecDocument(params.get('document')),
    }
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
