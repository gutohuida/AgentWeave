import { useEffect, useMemo, useState } from 'react'
import { useProjects } from '@/api/projects'
import { agentColorVars } from '@/lib/agentColors'
import { useConfigStore } from '@/store/configStore'

export type SidebarPage =
  | 'tasks' | 'questions' | 'activity' | 'logs' | 'jobs' | 'quality' | 'instructions' | 'spec'
  | 'runners' | 'charters' | 'worktrees' | 'diagnostics' | 'budgets' | 'settings'

interface SidebarProps {
  activePage: SidebarPage | 'overview' | null
  activeAgent?: string | null
  onOpenProject: (projectId: string) => void
  onOpenAgent: (projectId: string, agent: string) => void
  onOpenExisting: () => void
  onCreateProject: () => void
  compact?: boolean
  width?: number
}

export const SIDEBAR_WIDTH = 220
export const SIDEBAR_COMPACT_WIDTH = 52
export const SIDEBAR_MIN_WIDTH = 180
export const SIDEBAR_MAX_WIDTH = 420

const COLLAPSED_KEY = 'aw.projectRailCollapsed'

function loadCollapsed(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(COLLAPSED_KEY) ?? '{}') as Record<string, boolean>
  } catch {
    return {}
  }
}

export function Sidebar({
  activeAgent = null,
  onOpenProject,
  onOpenAgent,
  onOpenExisting,
  onCreateProject,
  compact = false,
  width = SIDEBAR_WIDTH,
}: SidebarProps) {
  const { data: projects = [] } = useProjects()
  const selectedProjectId = useConfigStore((state) => state.selectedProjectId)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(loadCollapsed)
  const duplicateNames = useMemo(() => {
    const counts = new Map<string, number>()
    for (const project of projects) counts.set(project.name, (counts.get(project.name) ?? 0) + 1)
    return counts
  }, [projects])

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSED_KEY, JSON.stringify(collapsed))
    } catch {
      // Persistence is optional.
    }
  }, [collapsed])

  return (
    <aside
      className="flex h-full shrink-0 flex-col"
      data-testid="sidebar"
      data-compact={compact ? 'true' : 'false'}
      style={{
        width: compact ? SIDEBAR_COMPACT_WIDTH : width,
        background: 'transparent',
        padding: compact ? '12px 4px' : '12px 8px',
      }}
    >
      <div className={compact ? 'mb-2 text-center' : 'mb-2 px-2'} style={{ fontSize: 12, fontWeight: 700 }}>
        AW
      </div>

      {!compact && (
        <>
          <div className="flex items-center justify-between px-1 pb-2">
            <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-3)' }}>
              Projects
            </span>
            <div className="flex gap-1">
              <button type="button" data-testid="open-existing-project" onClick={onOpenExisting} aria-label="Open existing project" className="px-1 text-sm">+</button>
              <button type="button" data-testid="create-new-project" onClick={onCreateProject} aria-label="Create new project" className="px-1 text-sm">â—‡</button>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-auto">
            {projects.map((project) => {
              const expanded = !collapsed[project.id]
              const duplicateName = (duplicateNames.get(project.name) ?? 0) > 1
              return (
                <div key={project.id} className="mb-2" data-testid={`rail-project-${project.id}`}>
                  <div className="flex items-start gap-1">
                    <button
                      type="button"
                      aria-label={`${expanded ? 'Collapse' : 'Expand'} ${project.name}`}
                      data-testid={`project-expander-${project.id}`}
                      onClick={() => setCollapsed((state) => ({ ...state, [project.id]: expanded }))}
                      className="h-7 w-6 text-xs"
                      style={{ color: 'var(--text-3)' }}
                    >
                      {expanded ? 'â–¾' : 'â–¸'}
                    </button>
                    <button
                      type="button"
                      data-testid={`project-name-${project.id}`}
                      onClick={() => onOpenProject(project.id)}
                      className="min-w-0 flex-1 px-1 py-1 text-left text-sm font-medium"
                      style={{ color: selectedProjectId === project.id ? 'var(--text)' : 'var(--text-2)' }}
                    >
                      <span className="block truncate">{project.name}</span>
                      {duplicateName && <span className="block truncate text-[10px]" style={{ color: 'var(--text-3)' }}>{project.path_display ?? 'Directory unavailable'}</span>}
                    </button>
                    <span
                      className="mt-2 h-2 w-2 shrink-0 rounded-full"
                      data-testid={`project-state-${project.id}`}
                      title={project.directory_state}
                      style={{ background: project.directory_state === 'available' ? 'var(--green)' : 'var(--red)' }}
                    />
                  </div>
                  {expanded && (
                    <div className="ml-7 flex flex-col gap-0.5">
                      {project.agents.map((agent) => {
                        const colors = agentColorVars(agent.color_index)
                        const active = selectedProjectId === project.id && activeAgent === agent.name
                        return (
                          <button
                            key={agent.id}
                            type="button"
                            data-testid={`rail-agent-${project.id}-${agent.name}`}
                            onClick={() => onOpenAgent(project.id, agent.name)}
                            className="flex items-center gap-2 rounded px-2 py-1 text-left text-xs"
                            style={{ color: active ? 'var(--text)' : 'var(--text-2)', background: active ? 'var(--surface-2)' : 'transparent' }}
                          >
                            <span data-testid={`rail-agent-color-${project.id}-${agent.name}`} className="h-2 w-2 shrink-0 rounded-full" style={{ background: colors.accent }} />
                            <span className="min-w-0 flex-1 truncate">{agent.name}</span>
                            <span className="h-1.5 w-1.5 rounded-full" title={agent.status} style={{ background: agent.status === 'running' ? 'var(--green)' : 'var(--text-3)' }} />
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}
    </aside>
  )
}
