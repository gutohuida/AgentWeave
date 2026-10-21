import { Icon } from '@/components/common/Icon'
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import { TAB_LABELS, type ProjectTab } from '@/lib/navigation'
import { elidePathSegments } from '@/lib/pathDisplay'

/** One 48px bar for the whole project chrome.
 *
 *  Replaces a ~120px stack: a "CURRENT PROJECT" eyebrow, the name, "4 agents", a truncated path,
 *  then a tab row, then each page repeating its tab's name as a title. Here the project switcher
 *  (name, with the path in its menu and title), the tabs, search and the settings door share one
 *  row. Pages no longer print their own title; the active tab is the title.
 *
 *  The tab indicator is a 2px bar under the active tab; `aria-current="page"` marks it. A tab
 *  with something waiting for the operator carries a count.
 *
 *  A project whose folder is gone says so beside its name, in amber — the one fact about the
 *  directory that changes what the operator can do. The path itself lives in the switcher's menu,
 *  elided in the middle with the whole of it on hover, where it no longer competes with the name. */

export interface TopBarProject {
  id: string
  name: string
  path: string
}

export function TopBar({
  project,
  projects,
  tabs,
  active,
  counts,
  directoryAvailable = true,
  onSelectTab,
  onSelectProject,
  onAddProject,
  onOpenSetup,
  onOpenPalette,
  onOpenSettings,
  mode,
  onToggleMode,
  settingsActive,
}: {
  project: TopBarProject
  projects: TopBarProject[]
  tabs: readonly ProjectTab[]
  active: ProjectTab | null
  /** Per-tab attention counts (e.g. tasks awaiting review); zero or absent shows nothing. */
  counts?: Partial<Record<ProjectTab, number>>
  directoryAvailable?: boolean
  onSelectTab: (tab: ProjectTab) => void
  onSelectProject: (id: string) => void
  onAddProject?: () => void
  /** The Hub connection dialog (address and key), reached from the project menu. */
  onOpenSetup?: () => void
  onOpenPalette: () => void
  onOpenSettings: () => void
  mode: 'dark' | 'light'
  onToggleMode: () => void
  settingsActive?: boolean
}) {
  const segments = project.path ? elidePathSegments(project.path) : []
  return (
    <header className="aw-topbar" data-testid="topbar">
      <Menu>
        <MenuTrigger data-slot="project-switcher" data-testid="project-switcher" className="aw-project-switcher" title={project.path} aria-label={`Project: ${project.name}. Switch project`}>
          <Icon name="folder" size={15} className="aw-project-switcher-icon" />
          <span className="truncate">{project.name}</span>
          <Icon name="expand_more" size={13} className="aw-project-switcher-chevron" />
        </MenuTrigger>
        <MenuContent align="start" style={{ minWidth: 280 }}>
          <MenuLabel>Projects</MenuLabel>
          {projects.map((p) => (
            <MenuItem key={p.id} icon={p.id === project.id ? 'check' : 'folder'} onSelect={() => onSelectProject(p.id)}>
              {p.name}
            </MenuItem>
          ))}
          <MenuSeparator />
          {segments.length > 0 ? (
            <div className="aw-menu-path" title={project.path} data-testid="project-path">
              {segments.map((segment, index) => (
                <span key={index} className="aw-menu-path-segment">
                  {index > 0 ? <span aria-hidden="true" className="aw-menu-path-sep">›</span> : null}
                  <span className="truncate">{segment}</span>
                </span>
              ))}
            </div>
          ) : null}
          {project.path ? (
            <MenuItem icon="content_copy" onSelect={() => void navigator.clipboard?.writeText(project.path)}>
              Copy folder path
            </MenuItem>
          ) : null}
          <MenuItem icon="add" onSelect={() => onAddProject?.()}>
            Add project…
          </MenuItem>
          {onOpenSetup ? (
            <MenuItem icon="link" onSelect={onOpenSetup}>
              Hub connection…
            </MenuItem>
          ) : null}
        </MenuContent>
      </Menu>
      {directoryAvailable ? null : (
        <span role="status" className="aw-topbar-warning" title={project.path || undefined}>
          <Icon name="warning" size={13} />
          Directory unavailable
        </span>
      )}

      <nav aria-label="Project views" className="aw-topbar-tabs">
        {tabs.map((tab) => {
          const count = counts?.[tab]
          return (
            <button data-slot="topbar-tab"
              key={tab}
              type="button"
              data-testid={`project-tab-${tab}`}
              className="aw-topbar-tab"
              data-active={active === tab ? 'true' : 'false'}
              aria-current={active === tab ? 'page' : undefined}
              onClick={() => onSelectTab(tab)}
            >
              {TAB_LABELS[tab]}
              {count ? <span className="aw-topbar-tab-count">{count}</span> : null}
            </button>
          )
        })}
      </nav>

      <div className="aw-topbar-actions">
        <button data-slot="search-button" type="button" className="aw-search-button" onClick={onOpenPalette} aria-label="Search" title="Search (Ctrl K)">
          <Icon name="search" size={13} />
          <span>Search</span>
          <kbd className="aw-kbd">Ctrl K</kbd>
        </button>
        <button data-slot="topbar-icon"
          type="button"
          className="aw-topbar-icon"
          aria-label={mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          title={mode === 'dark' ? 'Light mode' : 'Dark mode'}
          onClick={onToggleMode}
        >
          <Icon name={mode === 'dark' ? 'light_mode' : 'dark_mode'} size={15} />
        </button>
        <button data-slot="topbar-icon"
          type="button"
          className="aw-topbar-icon"
          data-testid="topbar-settings"
          aria-label="Project settings"
          title="Project settings"
          data-active={settingsActive ? 'true' : 'false'}
          aria-current={settingsActive ? 'page' : undefined}
          onClick={onOpenSettings}
        >
          <Icon name="settings" size={15} />
        </button>
      </div>
    </header>
  )
}
