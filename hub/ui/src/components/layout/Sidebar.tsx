import { useEffect, useMemo, useState } from 'react'
import { useProjects } from '@/api/projects'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import {
  ENVIRONMENT_SECTIONS,
  isConfigurationDestination,
  type EnvironmentSection,
  type WorkspaceDestination,
} from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'
import { AgentTree } from './AgentTree'

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
  onOpenEnvironment?: (projectId: string, section: EnvironmentSection) => void
  onAddAgent?: (projectId: string) => void
  onOpenExisting: () => void
  onCreateProject: () => void
  compact?: boolean
  width?: number
}

export const SIDEBAR_WIDTH = 252
export const SIDEBAR_COMPACT_WIDTH = 52
export const SIDEBAR_MIN_WIDTH = 180
export const SIDEBAR_MAX_WIDTH = 420

const COLLAPSED_KEY = 'aw.projectRailCollapsed'
const AGENTS_EXPANDED_KEY = 'aw.railAgentsExpanded'
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
  onOpenEnvironment,
  onAddAgent,
  onOpenExisting,
  onCreateProject,
  compact = false,
  width = SIDEBAR_WIDTH,
}: SidebarProps) {
  const { data: projects = [] } = useProjects()
  const selectedProjectId = useConfigStore((state) => state.selectedProjectId)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => loadFlags(COLLAPSED_KEY))
  const [expandedAgents, setExpandedAgents] = useState<Record<string, boolean>>(() =>
    loadFlags(AGENTS_EXPANDED_KEY),
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

  return (
    <aside
      className="workspace-rail flex h-full shrink-0 flex-col"
      data-testid="sidebar"
      data-compact={compact ? 'true' : 'false'}
      data-mode={configuration ? 'section' : 'project'}
      style={{
        width: compact ? SIDEBAR_COMPACT_WIDTH : width,
        background: 'var(--rail)',
        borderRight: '1px solid var(--border-region)',
        padding: compact ? '14px 4px' : '16px 12px',
      }}
    >
      <div className={compact ? 'mb-3 text-center' : 'mb-5 flex items-center gap-2 px-2'} style={{ fontSize: 13, fontWeight: 700 }}>
        <span className="inline-flex h-6 w-6 items-center justify-center rounded-md text-[10px]" style={{ background: 'var(--primary)', color: 'var(--primary-foreground)' }}>AW</span>
        {!compact && <span>AgentWeave</span>}
      </div>

      {!compact && configuration ? (
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
            <div className="truncate text-[11px]" style={{ color: 'var(--text-3)' }}>{configuredProject?.name ?? configuration.projectId}</div>
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
      ) : !compact ? (
        <>
          <div className="flex items-center justify-between px-1 pb-2">
            <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-3)' }}>Projects</span>
            <Button variant="ghost" size="icon-xs" data-testid="open-existing-project" onClick={onOpenExisting} aria-label="Open existing project" title="Open existing project">
              <Icon name="folder_open" size={15} />
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
                      <span className="min-w-0 flex-1">
                        <span className="block truncate">{project.name}</span>
                        {duplicateName && <span className="block truncate text-[10px]" style={{ color: 'var(--text-3)' }}>{project.path_display ?? 'Directory unavailable'}</span>}
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
                  {expanded && (
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
                      onAddAgent={onAddAgent}
                    />
                  )}
                </div>
              )
            })}
          </div>

          <Button variant="outline" size="md" data-testid="create-new-project" onClick={onCreateProject} aria-label="Add project" className="mt-3 w-full">
            <Icon name="folder_plus" size={15} />
            Add project
          </Button>
        </>
      ) : null}
    </aside>
  )
}
