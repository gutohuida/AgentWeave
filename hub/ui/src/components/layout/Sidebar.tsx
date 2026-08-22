import { useEffect, useMemo, useState } from 'react'
import { useProjects, type ProjectSummary } from '@/api/projects'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { agentColorVars } from '@/lib/agentColors'
import {
  AGENT_SETTINGS_SECTIONS,
  ENVIRONMENT_SECTIONS,
  isAgentSettingsDestination,
  isConfigurationDestination,
  isSpecDestination,
  type AgentSettingsSection,
  type EnvironmentSection,
  type WorkspaceDestination,
} from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'
import { SpecRailNav } from '@/components/spec/SpecRailNav'
import { AgentTree } from './AgentTree'
import { RecencyView } from './RecencyView'

export type SidebarPage =
  | 'tasks' | 'questions' | 'activity' | 'logs' | 'jobs' | 'quality' | 'instructions' | 'spec'
  | 'runners' | 'charters' | 'worktrees' | 'diagnostics' | 'budgets' | 'settings'

interface SidebarProps {
  destination?: WorkspaceDestination
  activePage: SidebarPage | 'overview' | null
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
  /** Where the settings page's back control goes — a fixed target, the agent's most recent
   *  conversation, mirroring "Back to {project}" rather than remembering an origin. */
  onBackFromAgentSettings?: (projectId: string, agent: string) => void
  /** Opening a specification document while the rail is standing in for the project tree. */
  onOpenSpecDocument?: (projectId: string, path: string) => void
  onAddAgent?: (projectId: string) => void
  /** Open a folder as a project. `open_existing` initialises it if it is not one yet,
   *  so this single action covers both opening and creating. */
  onAddProject: () => void
  /** Collapsed to an icon rail. The operator's choice and only theirs — no destination writes
   *  it (`hub-workspace-shell`: "Navigation collapses only when the operator asks"). */
  compact?: boolean
  onCompactChange?: (compact: boolean) => void
  width?: number
}

export const SIDEBAR_WIDTH = 252
export const SIDEBAR_COMPACT_WIDTH = 52
export const SIDEBAR_MIN_WIDTH = 180
export const SIDEBAR_MAX_WIDTH = 420

const COLLAPSED_KEY = 'aw.projectRailCollapsed'
const AGENTS_EXPANDED_KEY = 'aw.railAgentsExpanded'
const RAIL_VIEW_KEY = 'aw.railView'

/** The tree is the default: the agent roster is what AgentWeave has that a two-level chat
 *  sidebar does not. The recency view recovers the flat scan the extra level costs. */
export type RailView = 'tree' | 'recency'
const AGENT_SECTION_LABELS: Record<AgentSettingsSection, string> = {
  identity: 'Identity',
  execution: 'Execution',
  charter: 'Charter',
  interaction: 'Interaction',
  context: 'Context',
  access: 'Access',
  workspace: 'Workspace',
}
const SECTION_LABELS: Record<EnvironmentSection, string> = {
  quality: 'Quality',
  instructions: 'Instructions',
  runners: 'Runners',
  charters: 'Charters',
  worktrees: 'Worktrees',
  diagnostics: 'Diagnostics',
  budgets: 'Budgets',
  settings: 'Settings',
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
  destination,
  activeAgent = null,
  activeConversation = null,
  onOpenProject,
  onOpenAgent,
  onOpenConversation,
  onNewConversation,
  onOpenEnvironment,
  onOpenAgentSettings,
  onBackFromAgentSettings,
  onOpenSpecDocument,
  onAddAgent,
  onAddProject,
  compact = false,
  onCompactChange,
  width = SIDEBAR_WIDTH,
}: SidebarProps) {
  const { data: projects = [] } = useProjects()
  const selectedProjectId = useConfigStore((state) => state.selectedProjectId)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => loadFlags(COLLAPSED_KEY))
  const [expandedAgents, setExpandedAgents] = useState<Record<string, boolean>>(() =>
    loadFlags(AGENTS_EXPANDED_KEY),
  )
  const [railView, setRailView] = useState<RailView>(
    () => (localStorage.getItem(RAIL_VIEW_KEY) as RailView | null) ?? 'tree',
  )
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
  const configuration = destination && isConfigurationDestination(destination) ? destination : null
  const configuredProject = configuration
    ? projects.find((project) => project.id === configuration.projectId)
    : null
  const agentSettings =
    destination && isAgentSettingsDestination(destination) ? destination : null
  const spec = destination && isSpecDestination(destination) ? destination : null
  const specProject = spec ? projects.find((project) => project.id === spec.projectId) : null

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
      className="workspace-rail flex h-full shrink-0 flex-col"
      data-testid="sidebar"
      data-compact={compact ? 'true' : 'false'}
      data-mode={configuration || agentSettings || spec ? 'section' : 'project'}
      style={{
        width: compact ? SIDEBAR_COMPACT_WIDTH : width,
        background: 'var(--rail)',
        borderRight: '1px solid var(--border-region)',
        padding: compact ? '10px 4px' : '10px 8px',
      }}
    >
      <div
        className={compact ? 'mb-3 flex flex-col items-center gap-1' : 'mb-3 flex items-center gap-2 px-1.5 py-1'}
        style={{ fontSize: 13, fontWeight: 600 }}
      >
        <span className="rail-live-dot" aria-hidden="true" />
        {!compact && <span className="flex-1">AgentWeave</span>}
        {onCompactChange && (
          <Button
            variant="ghost"
            size="icon-xs"
            data-testid="rail-collapse-toggle"
            aria-pressed={compact}
            aria-label={compact ? 'Expand navigation' : 'Collapse navigation'}
            title={compact ? 'Expand navigation' : 'Collapse navigation'}
            onClick={() => onCompactChange(!compact)}
          >
            <Icon name={compact ? 'chevron_right' : 'right_panel_close'} size={15} />
          </Button>
        )}
      </div>

      {compact ? (
        <CompactRail
          projects={projects}
          selectedProjectId={selectedProjectId}
          activeAgent={activeAgent}
          onOpenProject={onOpenProject}
          onOpenAgent={onOpenAgent}
          onAddProject={onAddProject}
        />
      ) : spec ? (
        <SpecRailNav
          projectName={specProject?.name ?? 'project'}
          currentPath={spec.document ?? null}
          onSelect={(path) => onOpenSpecDocument?.(spec.projectId, path)}
          onBack={() => onOpenProject(spec.projectId)}
        />
      ) : agentSettings ? (
        <>
          <Button
            variant="ghost"
            size="sm"
            className="mb-3 w-full justify-start"
            data-testid="agent-settings-back"
            aria-label={`Back to ${agentSettings.agent}`}
            onClick={() =>
              onBackFromAgentSettings?.(agentSettings.projectId, agentSettings.agent)
            }
          >
            <Icon name="arrow_left" size={15} />
            {agentSettings.agent}
          </Button>
          <div className="mb-3 px-2">
            <div className="text-sm font-semibold" style={{ color: 'var(--text)' }}>Agent settings</div>
            <div className="truncate text-[12px]" style={{ color: 'var(--text-3)' }}>{agentSettings.agent}</div>
          </div>
          <nav aria-label="Agent settings sections" className="flex flex-col gap-0.5">
            {AGENT_SETTINGS_SECTIONS.map((section) => (
              <button
                key={section}
                type="button"
                className="row-item"
                data-testid={`agent-settings-section-${section}`}
                data-active={agentSettings.section === section ? 'true' : 'false'}
                aria-current={agentSettings.section === section ? 'page' : undefined}
                onClick={() =>
                  onOpenAgentSettings?.(agentSettings.projectId, agentSettings.agent, section)
                }
              >
                {AGENT_SECTION_LABELS[section]}
              </button>
            ))}
          </nav>
        </>
      ) : configuration ? (
        <>
          <Button
            variant="ghost"
            size="sm"
            className="mb-3 w-full justify-start"
            data-testid="rail-section-back"
            aria-label={`Back to ${configuredProject?.name ?? 'project'}`}
            onClick={() => onOpenProject(configuration.projectId)}
          >
            <Icon name="arrow_left" size={15} />
            Environment
          </Button>
          <div className="mb-3 px-2">
            <div className="text-sm font-semibold" style={{ color: 'var(--text)' }}>Configuration</div>
            <div className="truncate text-[12px]" style={{ color: 'var(--text-3)' }}>{configuredProject?.name ?? configuration.projectId}</div>
          </div>
          <nav aria-label="Environment sections" className="flex flex-col gap-0.5">
            {ENVIRONMENT_SECTIONS.map((section) => (
              <button
                key={section}
                type="button"
                className="row-item"
                data-testid={`environment-section-${section}`}
                data-active={configuration.environmentSection === section ? 'true' : 'false'}
                aria-current={configuration.environmentSection === section ? 'page' : undefined}
                onClick={() => onOpenEnvironment?.(configuration.projectId, section)}
              >
                {SECTION_LABELS[section]}
              </button>
            ))}
          </nav>
        </>
      ) : (
        <>
          <div className="flex items-center justify-between px-1 pb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-3)' }}>Projects</span>
            <Button
              variant="ghost"
              size="icon-xs"
              data-testid="rail-view-toggle"
              data-view={railView}
              aria-pressed={railView === 'recency'}
              onClick={() => setRailView((view) => (view === 'tree' ? 'recency' : 'tree'))}
              aria-label={railView === 'tree' ? 'Switch to recent conversations' : 'Switch to agent tree'}
              title={railView === 'tree' ? 'Recent conversations' : 'Agent tree'}
            >
              <Icon name={railView === 'tree' ? 'schedule' : 'smart_toy'} size={15} />
            </Button>
          </div>

          <div className="min-h-0 flex-1 overflow-auto">
            {projects.map((project) => {
              const expanded = !collapsed[project.id]
              const activeProject = selectedProjectId === project.id
              const duplicateName = (duplicateNames.get(project.name) ?? 0) > 1
              return (
                <div key={project.id} className="mb-2" data-testid={`rail-project-${project.id}`}>
                  <div className="row-group flex items-start gap-1">
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      aria-label={`${expanded ? 'Collapse' : 'Expand'} ${project.name}`}
                      data-testid={`project-expander-${project.id}`}
                      onClick={() => setCollapsed((state) => ({ ...state, [project.id]: expanded }))}
                    >
                      <span style={{ transform: expanded ? 'rotate(90deg)' : undefined, transition: 'transform var(--dur-fast) var(--ease)' }}><Icon name="chevron_right" size={14} /></span>
                    </Button>
                    <button
                      type="button"
                      data-testid={`project-name-${project.id}`}
                      data-active={activeProject ? 'true' : 'false'}
                      onClick={() => onOpenProject(project.id)}
                      className="row-item min-w-0 flex-1"
                    >
                      <span className="row-selection-indicator" aria-hidden="true" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate">{project.name}</span>
                        {duplicateName && <span className="block truncate text-[11px]" style={{ color: 'var(--text-3)' }}>{project.path_display ?? 'Directory unavailable'}</span>}
                      </span>
                      <span className="h-2 w-2 shrink-0 rounded-full" data-testid={`project-state-${project.id}`} title={project.directory_state} style={{ background: project.directory_state === 'available' ? 'var(--green)' : 'var(--red)' }} />
                    </button>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      className="row-action"
                      data-persistent={activeProject ? 'true' : undefined}
                      aria-label={`Configure ${project.name}`}
                      title={`Configure ${project.name}`}
                      onClick={() => onOpenEnvironment?.(project.id, 'quality')}
                    >
                      <Icon name="settings" size={14} />
                    </Button>
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
                      // Navigates to the agent's settings destination. It used to open a dialog
                      // hosted here; configuration outgrew a 520px modal, and a destination is
                      // also linkable and survives reload, which a dialog never was.
                      onOpenAgentSettings={(id, agent) => onOpenAgentSettings?.(id, agent, 'identity')}
                      onAddAgent={onAddAgent}
                    />
                  )}
                </div>
              )
            })}
          </div>

          {/* One action, not two. "Open existing" and "Add project" both opened the same modal
              onto the same folder picker; the only difference was whether the folder had to exist
              already, which is a mode rather than a second feature — and asking the operator to
              pick between them happened at the exact moment they knew least. `open_existing`
              already resolves all three cases on its own (a path the Hub knows, a directory
              carrying a project marker, or a plain folder it initialises), and the OS folder
              dialog has its own "New folder" button, so creating never needed an entry point of
              its own. Operator, 2026-08-18: "Is 2 buttons the right call? Shouldn't this be
              decided differently?" */}
          <div className="mt-3">
            <Button variant="outline" size="md" data-testid="add-project" onClick={onAddProject} aria-label="Add project" title="Open a folder — it is initialised as a project if it is not one yet" className="w-full">
              <Icon name="folder_open" size={15} />
              Add project
            </Button>
          </div>
        </>
      )}
    </aside>
  )
}

/**
 * The rail while collapsed.
 *
 * It renders destinations, not decoration. The previous compact mode gated every branch on
 * `!compact` and so drew the AW mark and nothing else — no projects, no agents, no way back —
 * which is a hidden rail, not a collapsed one. Every project and agent reachable when expanded is
 * reachable here, each with an accessible name, and the active one is marked.
 *
 * Conversations are deliberately not here: 40px of width cannot name a conversation, and an
 * unnamed row is not a destination anyone can choose. The agent leads to its most recent one.
 */
function CompactRail({
  projects,
  selectedProjectId,
  activeAgent,
  onOpenProject,
  onOpenAgent,
  onAddProject,
}: {
  projects: ProjectSummary[]
  selectedProjectId: string | null
  activeAgent: string | null
  onOpenProject: (projectId: string) => void
  onOpenAgent: (projectId: string, agent: string) => void
  /** Open a folder as a project. `open_existing` initialises it if it is not one yet,
   *  so this single action covers both opening and creating. */
  onAddProject: () => void
}) {
  return (
    <>
      <nav aria-label="Projects and agents" className="flex min-h-0 flex-1 flex-col items-center gap-2 overflow-y-auto">
        {projects.map((project) => {
          const activeProject = selectedProjectId === project.id
          return (
            <div key={project.id} className="flex flex-col items-center gap-1">
              <button
                type="button"
                data-testid={`rail-compact-project-${project.id}`}
                data-active={activeProject ? 'true' : 'false'}
                aria-current={activeProject ? 'page' : undefined}
                aria-label={project.name}
                title={project.name}
                onClick={() => onOpenProject(project.id)}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-[11px] font-semibold"
                style={{
                  background: activeProject ? 'var(--surface-3)' : 'var(--surface-2)',
                  border: `1px solid ${activeProject ? 'var(--border-hi)' : 'var(--border)'}`,
                  color: 'var(--text-2)',
                  cursor: 'pointer',
                }}
              >
                {project.name.slice(0, 2).toUpperCase()}
              </button>
              {project.agents.map((agent) => {
                const colors = agentColorVars(agent.color_index)
                const active = activeProject && activeAgent === agent.name
                return (
                  <button
                    key={agent.name}
                    type="button"
                    data-testid={`rail-compact-agent-${project.id}-${agent.name}`}
                    data-active={active ? 'true' : 'false'}
                    aria-current={active ? 'page' : undefined}
                    aria-label={agent.name}
                    title={agent.name}
                    onClick={() => onOpenAgent(project.id, agent.name)}
                    className="inline-flex h-6 w-6 items-center justify-center rounded-full"
                    style={{
                      background: active ? colors.tint : 'transparent',
                      border: `1px solid ${active ? colors.border : 'var(--border)'}`,
                      cursor: 'pointer',
                    }}
                  >
                    <span className="h-2 w-2 rounded-full" style={{ background: colors.accent }} />
                  </button>
                )
              })}
            </div>
          )
        })}
      </nav>
      {/* Collapsed rail: the same single action as the expanded one. */}
      <div className="mt-2 flex flex-col items-center gap-1">
        <Button
          variant="ghost"
          size="icon-sm"
          data-testid="add-project"
          onClick={onAddProject}
          aria-label="Add project"
          title="Open a folder — it is initialised as a project if it is not one yet"
        >
          <Icon name="folder_open" size={15} />
        </Button>
      </div>
    </>
  )
}
