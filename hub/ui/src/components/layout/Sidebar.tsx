import { useEffect, useMemo, useState } from 'react'
import { useProjects, type ProjectSummary } from '@/api/projects'
import { BrandLoop } from '@/components/common/BrandLoop'
import { Icon } from '@/components/common/Icon'
import { agentColorVars } from '@/lib/agentColors'
import type { AgentSettingsSection, EnvironmentSection } from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'
import { useSSEConnectionState, type SSEConnectionState } from '@/hooks/useSSE'
import { AgentTree } from './AgentTree'
import { RecencyView } from './RecencyView'

/** The rail: projects → agents → conversations, and nothing else.
 *
 *  It used to change into three other things — an Environment section list, an agent-settings
 *  section list and the Spec document tree — whenever the page beside it had sections of its own.
 *  Each of those now carries its own navigation in-page (Project settings, Agent settings, the
 *  Spec document list), so the rail stays where the operator left it and is never a second,
 *  disagreeing copy of the page's nav.
 *
 *  The look follows the ui-finesse mock (`shell.css`, `aw-rail-*`): one status signal per row,
 *  carried by the row's own text; row actions fade into the slot the age leaves so the row never
 *  changes width; full-row hit targets. */

interface SidebarProps {
  activeAgent?: string | null
  activeConversation?: string | null
  onOpenProject: (projectId: string) => void
  onOpenAgent: (projectId: string, agent: string) => void
  onOpenConversation?: (projectId: string, agent: string, conversationId: string) => void
  /** `agent` is null when the operator started from the recency view, where no agent is
   *  implied — the surface asks for one before the first message can be sent. */
  onNewConversation?: (projectId: string, agent: string | null) => void
  onOpenEnvironment?: (projectId: string, section: EnvironmentSection) => void
  onOpenAgentSettings?: (projectId: string, agent: string, section: AgentSettingsSection) => void
  onAddAgent?: (projectId: string) => void
  /** Open a folder as a project. `open_existing` initialises it if it is not one yet,
   *  so this single action covers both opening and creating. */
  onAddProject: () => void
  /** The operator's own settings (sound, appearance, the Hub): in the footer on every screen, so
   *  they are reachable with no project open, where no other settings entry exists. */
  onOpenAppSettings?: () => void
  appSettingsActive?: boolean
  /** Collapsed to an icon rail. The operator's choice and only theirs — no destination writes
   *  it (`hub-workspace-shell`: "Navigation collapses only when the operator asks"). */
  compact?: boolean
  onCompactChange?: (compact: boolean) => void
  width?: number
}

export const SIDEBAR_WIDTH = 248
export const SIDEBAR_COMPACT_WIDTH = 52
export const SIDEBAR_MIN_WIDTH = 180
export const SIDEBAR_MAX_WIDTH = 420

const COLLAPSED_KEY = 'aw.projectRailCollapsed'
const AGENTS_EXPANDED_KEY = 'aw.railAgentsExpanded'
const RAIL_VIEW_KEY = 'aw.railView'

/** The tree is the default: the agent roster is what AgentWeave has that a two-level chat
 *  sidebar does not. The recency view recovers the flat scan the extra level costs. */
export type RailView = 'tree' | 'recency'

/**
 * What the dot beside the wordmark actually reports.
 *
 * It used to be rendered unconditionally, `aria-hidden`, and filled with `--green` — a
 * permanently-"live" mark bound to nothing. IDENTITY.md: semantic colour is earned, and
 * green/amber/red carry state. The Hub stream is a real signal and this corner is the only
 * place it shows.
 *
 * `closed` is deliberately neutral rather than red — not configured yet, or nothing subscribed,
 * is not a fault, and colouring it as one is the same mistake in the other direction.
 */
const CONNECTION_LABEL: Record<SSEConnectionState, string> = {
  open: 'Live — receiving updates from the Hub',
  connecting: 'Connecting to the Hub…',
  reconnecting: 'Live updates interrupted — reconnecting',
  closed: 'Not connected to the Hub',
}

function loadFlags(key: string): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(key) ?? '{}') as Record<string, boolean>
  } catch {
    return {}
  }
}

/** Agents are keyed by project too — two projects may both have an agent called `claude`, and
 *  expanding one must not expand the other. */
function agentKey(projectId: string, agent: string): string {
  return `${projectId}/${agent}`
}

export function Sidebar({
  activeAgent = null,
  activeConversation = null,
  onOpenProject,
  onOpenAgent,
  onOpenConversation,
  onNewConversation,
  onOpenEnvironment,
  onOpenAgentSettings,
  onAddAgent,
  onAddProject,
  onOpenAppSettings,
  appSettingsActive = false,
  compact = false,
  onCompactChange,
  width = SIDEBAR_WIDTH,
}: SidebarProps) {
  const { data: projects = [] } = useProjects()
  const selectedProjectId = useConfigStore((state) => state.selectedProjectId)
  const connection = useSSEConnectionState()
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => loadFlags(COLLAPSED_KEY))
  const [expandedAgents, setExpandedAgents] = useState<Record<string, boolean>>(() =>
    loadFlags(AGENTS_EXPANDED_KEY),
  )
  const [railView, setRailView] = useState<RailView>(() => {
    try {
      return (localStorage.getItem(RAIL_VIEW_KEY) as RailView | null) ?? 'tree'
    } catch {
      return 'tree'
    }
  })
  /** The tree component keys its agents by bare name; the store keys them by project too. */
  const agentExpansionFor = (projectId: string): Record<string, boolean> => {
    const prefix = `${projectId}/`
    const scoped: Record<string, boolean> = {}
    for (const [key, value] of Object.entries(expandedAgents)) {
      if (key.startsWith(prefix)) scoped[key.slice(prefix.length)] = value
    }
    return scoped
  }
  const duplicateNames = useMemo(() => {
    const counts = new Map<string, number>()
    for (const project of projects) counts.set(project.name, (counts.get(project.name) ?? 0) + 1)
    return counts
  }, [projects])

  // The open conversation is always visible: arriving at an agent from anywhere — the palette, a
  // link, the Overview — opens its branch here, so the rail never points at a collapsed row.
  useEffect(() => {
    if (!selectedProjectId || !activeAgent) return
    const key = agentKey(selectedProjectId, activeAgent)
    setExpandedAgents((state) => (state[key] ? state : { ...state, [key]: true }))
  }, [selectedProjectId, activeAgent])

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSED_KEY, JSON.stringify(collapsed))
    } catch {
      // Persistence is optional.
    }
  }, [collapsed])

  useEffect(() => {
    try {
      localStorage.setItem(AGENTS_EXPANDED_KEY, JSON.stringify(expandedAgents))
    } catch {
      // Persistence is optional.
    }
  }, [expandedAgents])

  useEffect(() => {
    try {
      localStorage.setItem(RAIL_VIEW_KEY, railView)
    } catch {
      // Persistence is optional.
    }
  }, [railView])

  return (
    <aside
      className="aw-rail workspace-rail"
      data-testid="sidebar"
      data-collapsed={compact ? 'true' : 'false'}
      data-compact={compact ? 'true' : 'false'}
      aria-label="Projects and agents"
      style={compact ? undefined : { width }}
    >
      <div className="aw-rail-head">
        {!compact && (
          <span className="aw-wordmark">
            {/* Brand order: the loop leads, then the name, then the live dot. */}
            <BrandLoop testId="rail-brand-loop" />
            <span className="aw-wordmark-name">AgentWeave</span>
            {/* Not `aria-hidden`: it is the only report of the stream's health on this screen, so
                it carries a name and a tooltip rather than being decoration with a colour. */}
            <span
              className="aw-wordmark-dot rail-live-dot"
              data-testid="rail-live-dot"
              data-state={connection}
              role="img"
              aria-label={CONNECTION_LABEL[connection]}
              title={CONNECTION_LABEL[connection]}
            />
          </span>
        )}
        <span className="aw-rail-head-actions">
          {!compact && (
            <button
              data-slot="icon-button"
              type="button"
              className="aw-icon-button"
              data-testid="rail-view-toggle"
              data-view={railView}
              aria-pressed={railView === 'recency'}
              onClick={() => setRailView((view) => (view === 'tree' ? 'recency' : 'tree'))}
              aria-label={railView === 'tree' ? 'Switch to recent conversations' : 'Switch to agent tree'}
              title={railView === 'tree' ? 'Recent conversations' : 'Agent tree'}
            >
              <Icon name={railView === 'tree' ? 'schedule' : 'smart_toy'} size={15} />
            </button>
          )}
          {onCompactChange && (
            <button
              data-slot="icon-button"
              type="button"
              className="aw-icon-button"
              data-testid="rail-collapse-toggle"
              aria-pressed={compact}
              aria-label={compact ? 'Expand navigation' : 'Collapse navigation'}
              title={compact ? 'Expand navigation' : 'Collapse navigation'}
              onClick={() => onCompactChange(!compact)}
            >
              <Icon name="right_panel_close" size={15} className={compact ? undefined : 'rotate-180'} />
            </button>
          )}
        </span>
      </div>

      {compact ? (
        <CompactRail
          projects={projects}
          selectedProjectId={selectedProjectId}
          activeAgent={activeAgent}
          connection={connection}
          onOpenProject={onOpenProject}
          onOpenAgent={onOpenAgent}
          onAddProject={onAddProject}
          onOpenAppSettings={onOpenAppSettings}
          appSettingsActive={appSettingsActive}
        />
      ) : (
        <>
          <div className="aw-rail-scroll">
            {projects.map((project) => {
              const expanded = !collapsed[project.id]
              const activeProject = selectedProjectId === project.id
              const duplicateName = (duplicateNames.get(project.name) ?? 0) > 1
              const missing = project.directory_state !== 'available'
              const live = project.agents.some((agent) => agent.status === 'running' || agent.status === 'working')
              return (
                <div key={project.id} className="aw-rail-project" data-testid={`rail-project-${project.id}`}>
                  <div className="aw-rail-row aw-rail-project-row aw-reveal-host" data-active={activeProject ? 'true' : 'false'}>
                    <button
                      data-slot="rail-chevron"
                      type="button"
                      className="aw-rail-chevron-button"
                      aria-label={`${expanded ? 'Collapse' : 'Expand'} ${project.name}`}
                      aria-expanded={expanded}
                      data-testid={`project-expander-${project.id}`}
                      onClick={() => setCollapsed((state) => ({ ...state, [project.id]: expanded }))}
                    >
                      <span className="aw-rail-chevron" data-open={expanded ? 'true' : 'false'}>
                        <Icon name="chevron_right" size={13} />
                      </span>
                    </button>
                    <button
                      data-slot="rail-row-main"
                      type="button"
                      className="aw-rail-row-main"
                      data-testid={`project-name-${project.id}`}
                      data-active={activeProject ? 'true' : 'false'}
                      /* Level 1 of the rail's selection ladder: the project is marked by weight
                       * alone — which one is current is already stated by the subtree hanging
                       * open beneath it. */
                      data-depth="project"
                      aria-current={activeProject ? 'true' : undefined}
                      // Navigation, not expansion: the two stay independent (the chevron folds).
                      onClick={() => onOpenProject(project.id)}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate">{project.name}</span>
                        {duplicateName && (
                          <span className="aw-rail-subline block truncate">
                            {project.path_display ?? 'Directory unavailable'}
                          </span>
                        )}
                      </span>
                      {missing ? (
                        <span
                          className="aw-rail-missing"
                          data-testid={`project-state-${project.id}`}
                          role="img"
                          title="Directory unavailable"
                          aria-label="Directory unavailable"
                        >
                          <Icon name="warning" size={12} />
                        </span>
                      ) : live ? (
                        <span className="aw-live-dot aw-pulse" title="An agent is working" />
                      ) : null}
                    </button>
                    <span className="aw-rail-row-end">
                      <span className="aw-reveal aw-rail-actions">
                        <button
                          data-slot="icon-button"
                          type="button"
                          className="aw-icon-button"
                          data-testid={`rail-add-agent-${project.id}`}
                          aria-label={`Add agent to ${project.name}`}
                          title="Add agent"
                          onClick={() => onAddAgent?.(project.id)}
                        >
                          <Icon name="person_add" size={13} />
                        </button>
                        <button
                          data-slot="icon-button"
                          type="button"
                          className="aw-icon-button"
                          aria-label={`Configure ${project.name}`}
                          title="Project settings"
                          onClick={() => onOpenEnvironment?.(project.id, 'settings')}
                        >
                          <Icon name="settings" size={13} />
                        </button>
                      </span>
                    </span>
                  </div>
                  {expanded && railView === 'recency' && (
                    <RecencyView
                      projectId={project.id}
                      agents={project.agents}
                      activeProject={activeProject}
                      activeConversation={activeConversation}
                      onOpenConversation={onOpenConversation}
                      onNewConversation={onNewConversation}
                    />
                  )}
                  {expanded && railView === 'tree' && (
                    <AgentTree
                      projectId={project.id}
                      agents={project.agents}
                      activeProject={activeProject}
                      activeAgent={activeAgent}
                      activeConversation={activeConversation}
                      expandedAgents={agentExpansionFor(project.id)}
                      onToggleAgent={(agent: string) =>
                        setExpandedAgents((state) => {
                          const key = agentKey(project.id, agent)
                          return { ...state, [key]: !state[key] }
                        })
                      }
                      onOpenAgent={onOpenAgent}
                      onOpenConversation={onOpenConversation}
                      onNewConversation={onNewConversation}
                      onOpenAgentSettings={(id, agent) => onOpenAgentSettings?.(id, agent, 'identity')}
                      onAddAgent={onAddAgent}
                    />
                  )}
                </div>
              )
            })}
          </div>

          {/* One action, not two: `open_existing` resolves a known path, a marked directory, or a
              plain folder it initialises, and the OS folder dialog has its own "New folder"
              button, so creating never needed an entry point of its own (operator, 2026-08-18). */}
          <div className="aw-rail-foot">
            <button
              data-slot="rail-foot-button"
              type="button"
              className="aw-rail-foot-button"
              data-testid="add-project"
              onClick={onAddProject}
              aria-label="Add project"
              title="Open a folder — it is initialised as a project if it is not one yet"
            >
              <Icon name="folder_plus" size={14} />
              Add project
            </button>
            {onOpenAppSettings ? (
              <button
                data-slot="rail-foot-button"
                type="button"
                className="aw-rail-foot-button aw-rail-foot-settings"
                data-testid="rail-app-settings"
                data-active={appSettingsActive ? 'true' : 'false'}
                aria-current={appSettingsActive ? 'page' : undefined}
                aria-label="App settings"
                title="App settings: sound and notifications, appearance, the Hub connection"
                onClick={onOpenAppSettings}
              >
                <Icon name="settings" size={14} />
                Settings
              </button>
            ) : null}
          </div>
        </>
      )}
    </aside>
  )
}

/**
 * The rail while collapsed.
 *
 * It renders destinations, not decoration: every project and agent reachable when expanded is
 * reachable here, each with an accessible name, and the active one is marked. Conversations are
 * deliberately not here — 52px cannot name one. The agent leads to its most recent conversation.
 */
function CompactRail({
  projects,
  selectedProjectId,
  activeAgent,
  connection,
  onOpenProject,
  onOpenAgent,
  onAddProject,
  onOpenAppSettings,
  appSettingsActive,
}: {
  projects: ProjectSummary[]
  selectedProjectId: string | null
  activeAgent: string | null
  connection: SSEConnectionState
  onOpenProject: (projectId: string) => void
  onOpenAgent: (projectId: string, agent: string) => void
  onAddProject: () => void
  onOpenAppSettings?: () => void
  appSettingsActive: boolean
}) {
  return (
    <>
      <nav aria-label="Projects and agents" className="aw-rail-icons">
        <span
          className="aw-wordmark-dot rail-live-dot"
          data-testid="rail-live-dot"
          data-state={connection}
          role="img"
          aria-label={CONNECTION_LABEL[connection]}
          title={CONNECTION_LABEL[connection]}
        />
        {projects.map((project) => {
          const activeProject = selectedProjectId === project.id
          return (
            <div key={project.id} className="aw-rail-icon-group">
              <button
                data-slot="rail-icon"
                type="button"
                className="aw-rail-icon aw-rail-project-icon"
                data-testid={`rail-compact-project-${project.id}`}
                data-active={activeProject ? 'true' : 'false'}
                aria-current={activeProject ? 'page' : undefined}
                aria-label={project.name}
                title={project.name}
                onClick={() => onOpenProject(project.id)}
              >
                {project.name.slice(0, 2).toUpperCase()}
              </button>
              {project.agents.map((agent) => {
                const colors = agentColorVars(agent.color_index)
                const active = activeProject && activeAgent === agent.name
                const running = agent.status === 'running' || agent.status === 'working'
                return (
                  <button
                    data-slot="rail-icon"
                    key={agent.name}
                    type="button"
                    className="aw-rail-icon"
                    data-testid={`rail-compact-agent-${project.id}-${agent.name}`}
                    data-active={active ? 'true' : 'false'}
                    aria-current={active ? 'page' : undefined}
                    aria-label={agent.name}
                    title={agent.name}
                    onClick={() => onOpenAgent(project.id, agent.name)}
                    style={{ '--agent-accent': colors.accent, '--agent-tint': colors.tint } as React.CSSProperties}
                  >
                    {agent.name.slice(0, 2)}
                    {running ? <span className="aw-rail-icon-dot" data-attention="running" /> : null}
                  </button>
                )
              })}
            </div>
          )
        })}
      </nav>
      <div className="aw-rail-foot aw-rail-foot-compact">
        <button
          data-slot="icon-button"
          type="button"
          className="aw-icon-button"
          data-testid="add-project"
          onClick={onAddProject}
          aria-label="Add project"
          title="Open a folder — it is initialised as a project if it is not one yet"
        >
          <Icon name="folder_plus" size={15} />
        </button>
        {onOpenAppSettings ? (
          <button
            data-slot="icon-button"
            type="button"
            className="aw-icon-button"
            data-testid="rail-app-settings"
            data-active={appSettingsActive ? 'true' : 'false'}
            aria-current={appSettingsActive ? 'page' : undefined}
            onClick={onOpenAppSettings}
            aria-label="App settings"
            title="App settings: sound and notifications, appearance, the Hub connection"
          >
            <Icon name="settings" size={15} />
          </button>
        ) : null}
      </div>
    </>
  )
}
