import { useState } from 'react'
import { useAgents } from '@/api/agents'
import { useSessionSync, useStatus } from '@/api/status'
import { agentColorVars } from '@/lib/agentColors'
import { buildRailProjects } from '@/lib/navigation'
import { SidebarItem, type SidebarBadge } from './SidebarItem'

export type SidebarPage =
  | 'tasks' | 'questions' | 'activity' | 'logs' | 'jobs' | 'quality' | 'instructions' | 'spec'
  | 'runners'
  | 'charters'

interface SidebarProps {
  activePage: SidebarPage | 'overview' | null
  activeAgent?: string | null
  onNavigate: (page: SidebarPage) => void
  onOpenProject: (projectId: string) => void
  onOpenAgent: (projectId: string, agent: string) => void
  onOpenSetup: () => void
  compact?: boolean
  width?: number
}

export const SIDEBAR_WIDTH = 220
export const SIDEBAR_COMPACT_WIDTH = 52
export const SIDEBAR_MIN_WIDTH = 180
export const SIDEBAR_MAX_WIDTH = 420

interface NavItem {
  id: SidebarPage
  label: string
  icon: string
  section?: string
}

const NAV_ITEMS: NavItem[] = [
  { id: 'instructions', label: 'Instructions', icon: 'description' },
  { id: 'charters', label: 'Charters', icon: 'assignment_ind' },
  { id: 'runners', label: 'Runners', icon: 'dns' },
  { id: 'tasks', label: 'Tasks', icon: 'task_alt', section: 'WORK' },
  { id: 'spec', label: 'Spec', icon: 'article', section: 'WORK' },
  { id: 'jobs', label: 'Jobs', icon: 'schedule', section: 'WORK' },
  { id: 'questions', label: 'Questions', icon: 'help', section: 'COMMUNICATION' },
  { id: 'logs', label: 'Logs', icon: 'terminal', section: 'OBSERVE' },
  { id: 'activity', label: 'Activity', icon: 'monitoring', section: 'OBSERVE' },
  { id: 'quality', label: 'Quality', icon: 'verified_user', section: 'OBSERVE' },
]

const SECTION_ORDER = ['WORK', 'COMMUNICATION', 'OBSERVE']

export function Sidebar({
  activePage,
  activeAgent = null,
  onNavigate,
  onOpenProject,
  onOpenAgent,
  onOpenSetup,
  compact = false,
  width = SIDEBAR_WIDTH,
}: SidebarProps) {
  const { data: agents = [] } = useAgents()
  const { data: status } = useStatus()
  const { data: sessionSync } = useSessionSync()
  const projects = buildRailProjects(
    status ? { id: status.project_id, name: status.project_name } : null,
    agents,
  )
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const qualityActive = !!sessionSync?.data?.quality

  function getBadge(id: SidebarPage): SidebarBadge | null {
    if (id === 'quality' && qualityActive) return { count: 1, danger: false }
    return null
  }

  const topItems = NAV_ITEMS.filter((item) => !item.section)
  const sectionedItems = SECTION_ORDER.map((section) => ({
    section,
    items: NAV_ITEMS.filter((item) => item.section === section),
  }))
  const sectionLabelStyle: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: 'var(--text-3)',
    padding: '8px 8px 4px',
    marginTop: 8,
  }

  return (
    <div
      className="flex h-full flex-col shrink-0"
      data-testid="sidebar"
      data-compact={compact ? 'true' : 'false'}
      style={{
        width: compact ? SIDEBAR_COMPACT_WIDTH : width,
        background: 'transparent',
        padding: compact ? '12px 4px' : '12px 8px',
      }}
    >
      <div
        className={compact ? 'mb-2 text-center' : 'px-2 mb-2'}
        style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)' }}
      >
        AW
      </div>

      {!compact && projects.map((project) => {
        const expanded = !collapsed[project.id]
        return (
          <div key={project.id} className="mb-2">
            <div className="flex items-center gap-1">
              <button
                type="button"
                aria-label={`${expanded ? 'Collapse' : 'Expand'} ${project.name}`}
                data-testid={`project-expander-${project.id}`}
                onClick={() => setCollapsed((state) => ({ ...state, [project.id]: expanded }))}
                className="w-6 h-7 text-xs"
                style={{ color: 'var(--text-3)' }}
              >
                {expanded ? '▾' : '▸'}
              </button>
              <button
                type="button"
                data-testid={`project-name-${project.id}`}
                onClick={() => onOpenProject(project.id)}
                className="flex-1 truncate text-left px-1 py-1 text-sm font-medium"
                style={{ color: activePage === 'overview' ? 'var(--text)' : 'var(--text-2)' }}
              >
                {project.name}
              </button>
            </div>
            {expanded && (
              <div className="ml-7 flex flex-col gap-0.5">
                {project.agents.map((agent) => {
                  const colors = agentColorVars(agent.color_index)
                  return (
                    <button
                      key={agent.name}
                      type="button"
                      data-testid={`rail-agent-${agent.name}`}
                      onClick={() => onOpenAgent(project.id, agent.name)}
                      className="flex items-center gap-2 rounded px-2 py-1 text-left text-xs"
                      style={{
                        color: activeAgent === agent.name ? 'var(--text)' : 'var(--text-2)',
                        background: activeAgent === agent.name ? 'var(--surface-2)' : 'transparent',
                      }}
                    >
                      <span
                        data-testid={`rail-agent-color-${agent.name}`}
                        className="h-2 w-2 rounded-full shrink-0"
                        style={{ background: colors.accent }}
                      />
                      <span className="truncate">{agent.name}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}

      <nav className="flex flex-col">
        {topItems.map(({ id, label, icon }) => (
          <SidebarItem
            key={id}
            label={label}
            icon={icon}
            active={activePage === id}
            badge={getBadge(id)}
            onClick={() => onNavigate(id)}
            testId={`nav-${id}`}
            compact={compact}
          />
        ))}
      </nav>

      {sectionedItems.map(({ section, items }) => (
        <div key={section}>
          {!compact && <div style={sectionLabelStyle}>{section}</div>}
          <nav className="flex flex-col">
            {items.map(({ id, label, icon }) => (
              <SidebarItem
                key={id}
                label={label}
                icon={icon}
                active={activePage === id}
                badge={getBadge(id)}
                onClick={() => onNavigate(id)}
                compact={compact}
                testId={`nav-${id}`}
              />
            ))}
          </nav>
        </div>
      ))}

      <div className="flex-1" />
      <div style={{ borderTop: '1px solid var(--border)', marginTop: 8, paddingTop: 8 }}>
        <SidebarItem
          label="Settings"
          icon="settings"
          active={false}
          onClick={onOpenSetup}
          testId="nav-settings"
          compact={compact}
        />
      </div>
    </div>
  )
}
