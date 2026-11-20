import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { SetupCount } from '@/components/overview/SetupList'
import { useProjects, type ProjectSummary } from '@/api/projects'
import { BrandLoop } from '@/components/common/BrandLoop'
import { Icon } from '@/components/common/Icon'
import type { EnvironmentSection } from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'
import { useSSEConnectionState, type SSEConnectionState } from '@/hooks/useSSE'
import { useBuildsNeedingYouOf } from '@/api/projectBuilds'
import { ProjectThreadsAndBuilds } from './ProjectThreadsAndBuilds'

/** The rail: projects, and under each the builds that are running or need the operator, then the
 *  operator's own threads (profiles-threads-and-builds-everywhere FR-1, FR-3). Task, review and
 *  mender runs are reached through their build, not listed here.
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
  activeConversation?: string | null
  /** The build whose build view is open, if one is. */
  activeBuild?: string | null
  onOpenProject: (projectId: string) => void
  onOpenConversation?: (projectId: string, agent: string, conversationId: string) => void
  /** The sidebar's New thread implies no profile (`agent` is null): the surface asks for one
   *  before the first message can be sent. */
  onNewConversation?: (projectId: string, agent: string | null) => void
  onOpenBuild?: (projectId: string, buildId: string) => void
  onOpenEnvironment?: (projectId: string, section: EnvironmentSection) => void
  onAddAgent?: (projectId: string) => void
  /** Open a folder as a project. `open_existing` initialises it if it is not one yet,
   *  so this single action covers both opening and creating. */
  onAddProject: () => void
  /** The operator's own settings (sound, appearance, the Hub): in the footer on every screen, so
   *  they are reachable with no project open, where no other settings entry exists. */
  onOpenAppSettings?: () => void
  appSettingsActive?: boolean
  /** What each project still needs (`a-project-says-what-it-still-needs`), as item titles; a
   *  project with none left has an empty list. Absent: no count is shown. The count sits inside
   *  the project's row, beside its name like the missing-folder mark, so the actions revealed on
   *  hover never cover it; the row itself opens Overview, where the list is. */
  setupFor?: (projectId: string) => string[]
  /** Collapsed to an icon rail. The operator's choice and only theirs — no destination writes
   *  it (`hub-workspace-shell`: "Navigation collapses only when the operator asks"). */
  compact?: boolean
  onCompactChange?: (compact: boolean) => void
  width?: number
  /** What hangs under an open project, in place of the Hub-fed threads and builds: the mock
   *  passes its fixtures here. */
  projectBody?: (project: ProjectSummary, activeProject: boolean) => ReactNode
  /** The titles of a project's builds that need the operator, for the collapsed rail's mark, in
   *  place of the Hub's rows: the mock passes its fixtures here. */
  buildsNeedingYou?: (projectId: string) => string[]
}

export const SIDEBAR_WIDTH = 248
export const SIDEBAR_COMPACT_WIDTH = 52
export const SIDEBAR_MIN_WIDTH = 180
export const SIDEBAR_MAX_WIDTH = 420

const COLLAPSED_KEY = 'aw.projectRailCollapsed'

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

export function Sidebar({
  activeConversation = null,
  activeBuild = null,
  onOpenProject,
  onOpenConversation,
  onNewConversation,
  onOpenBuild,
  onOpenEnvironment,
  onAddAgent,
  onAddProject,
  onOpenAppSettings,
  appSettingsActive = false,
  setupFor,
  compact = false,
  onCompactChange,
  width = SIDEBAR_WIDTH,
  projectBody,
  buildsNeedingYou,
}: SidebarProps) {
  const { data: projects = [] } = useProjects()
  const selectedProjectId = useConfigStore((state) => state.selectedProjectId)
  const connection = useSSEConnectionState()
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => loadFlags(COLLAPSED_KEY))
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
      className="aw-rail workspace-rail"
      data-testid="sidebar"
      data-collapsed={compact ? 'true' : 'false'}
      data-compact={compact ? 'true' : 'false'}
      aria-label="Projects, builds and threads"
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
          connection={connection}
          onOpenProject={onOpenProject}
          onAddProject={onAddProject}
          onOpenAppSettings={onOpenAppSettings}
          appSettingsActive={appSettingsActive}
          setupFor={setupFor}
          buildsNeedingYou={buildsNeedingYou}
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
                      /* The project is marked by weight alone — which one is current is already
                       * stated by the list hanging open beneath it. */
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
                      <SetupCount titles={setupFor?.(project.id) ?? []} />
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
                          onClick={() => onOpenEnvironment?.(project.id, 'general')}
                        >
                          <Icon name="settings" size={13} />
                        </button>
                      </span>
                    </span>
                  </div>
                  {expanded &&
                    (projectBody ? (
                      projectBody(project, activeProject)
                    ) : (
                      <ProjectThreadsAndBuilds
                        project={project}
                        activeProject={activeProject}
                        activeConversation={activeConversation}
                        activeBuild={activeBuild}
                        onOpenThread={(id, profile, conversationId) => onOpenConversation?.(id, profile, conversationId)}
                        onNewThread={(id) => onNewConversation?.(id, null)}
                        onOpenBuild={(id, buildId) => onOpenBuild?.(id, buildId)}
                      />
                    ))}
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
 * The rail while collapsed: the projects only (FR-14).
 *
 * 52px cannot name a thread or a profile, so neither is here. A project with a build that needs
 * the operator carries a hand as well as amber, and its accessible name says how many.
 */
function CompactRail({
  projects,
  selectedProjectId,
  connection,
  onOpenProject,
  onAddProject,
  onOpenAppSettings,
  appSettingsActive,
  setupFor,
  buildsNeedingYou,
}: {
  setupFor?: (projectId: string) => string[]
  buildsNeedingYou?: (projectId: string) => string[]
  projects: ProjectSummary[]
  selectedProjectId: string | null
  connection: SSEConnectionState
  onOpenProject: (projectId: string) => void
  onAddProject: () => void
  onOpenAppSettings?: () => void
  appSettingsActive: boolean
}) {
  return (
    <>
      <nav aria-label="Projects" className="aw-rail-icons">
        <span
          className="aw-wordmark-dot rail-live-dot"
          data-testid="rail-live-dot"
          data-state={connection}
          role="img"
          aria-label={CONNECTION_LABEL[connection]}
          title={CONNECTION_LABEL[connection]}
        />
        {projects.map((project) =>
          buildsNeedingYou ? (
            <CompactProject
              key={project.id}
              project={project}
              active={selectedProjectId === project.id}
              needs={buildsNeedingYou(project.id)}
              setup={setupFor?.(project.id) ?? []}
              onOpen={onOpenProject}
            />
          ) : (
            <LiveCompactProject
              key={project.id}
              project={project}
              active={selectedProjectId === project.id}
              setup={setupFor?.(project.id) ?? []}
              onOpen={onOpenProject}
            />
          ),
        )}
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

interface CompactProjectProps {
  project: ProjectSummary
  active: boolean
  setup: string[]
  onOpen: (projectId: string) => void
}

/** A collapsed project fed from the Hub's build rows, the same ones the expanded list reads. */
function LiveCompactProject(props: CompactProjectProps) {
  const needs = useBuildsNeedingYouOf(props.project.id)
  return <CompactProject {...props} needs={needs} />
}

function CompactProject({ project, active, needs, setup, onOpen }: CompactProjectProps & { needs: string[] }) {
  const count = needs.length
  const name = count > 0 ? `${project.name}: ${count} build${count === 1 ? '' : 's'} need${count === 1 ? 's' : ''} you` : project.name
  return (
    <div className="aw-rail-icon-group">
      <button
        data-slot="rail-icon"
        type="button"
        className="aw-rail-icon aw-rail-project-icon"
        data-testid={`rail-compact-project-${project.id}`}
        data-active={active ? 'true' : 'false'}
        aria-current={active ? 'page' : undefined}
        aria-label={name}
        title={count > 0 ? [name, ...needs].join('. ') : project.name}
        onClick={() => onOpen(project.id)}
      >
        {project.name.slice(0, 2).toUpperCase()}
        <SetupCount titles={setup} />
        {/* A hand as well as amber: the mark is not colour alone (vault note P21). */}
        {count > 0 ? (
          <span className="aw-rail-compact-mark" data-testid={`rail-compact-needs-${project.id}`} aria-hidden="true">
            <Icon name="hand" size={8} />
          </span>
        ) : null}
      </button>
    </div>
  )
}
