import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { useConfigStore } from '@/store/configStore'
import { elidePathSegments } from '@/lib/pathDisplay'

interface ProjectHeaderProps {
  projectId?: string
  projectName: string
  projects?: Array<{ id: string; name: string; path_display?: string | null }>
  pathDisplay?: string | null
  agentCount?: number
  directoryAvailable: boolean
  onSelectProject?: (projectId: string) => void
  onOpenSetup: () => void
}

export function ProjectHeader({
  projectId,
  projectName,
  projects = [],
  pathDisplay,
  agentCount = 0,
  directoryAvailable,
  onSelectProject,
  onOpenSetup,
}: ProjectHeaderProps) {
  const { mode, setMode } = useConfigStore()

  const toggleMode = () => {
    const next = mode === 'light' ? 'dark' : 'light'
    setMode(next)
    document.documentElement.dataset.mode = next
  }

  const pathSegments = pathDisplay ? elidePathSegments(pathDisplay) : []

  return (
    <header className="project-header flex h-16 shrink-0 items-center gap-3 px-5 sm:h-20" style={{ background: 'var(--bg)' }}>
      <div className="min-w-0 flex-1">
        <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]" style={{ color: 'var(--text-3)' }}>
          Current project
        </div>
        {projectId && projects.length > 0 && onSelectProject ? (
          <label className="project-switcher control-select-wrap inline-flex max-w-full items-center" data-testid="project-switcher">
            <Icon name="folder_open" size={14} />
            <span className="sr-only">Switch project</span>
            <select
              aria-label="Switch project"
              data-testid="project-switcher-select"
              value={projectId}
              onChange={(event) => onSelectProject(event.target.value)}
              className="min-w-0 appearance-none bg-transparent pr-5 text-sm font-semibold outline-none"
              style={{ color: 'var(--text)' }}
            >
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
            <Icon name="expand_more" size={13} className="control-select-icon" />
          </label>
        ) : (
          <h1 className="truncate text-sm font-semibold" style={{ color: 'var(--text)' }}>{projectName}</h1>
        )}
        {directoryAvailable ? (
          <>
            <p className="mt-0.5 truncate text-[11px]" style={{ color: 'var(--text-3)' }}>
              {agentCount} agent{agentCount === 1 ? '' : 's'}
            </p>
            {/* Structure, not a joined string (composer/chrome refinement §5): each segment
                is its own element so it can be styled or truncated independently, rather
                than a `pathSegments.join(' › ')` blob competing with the project name for
                the same line. Not rendered as links — this project's navigation has no
                per-segment destination to send a click to (design.md Decision 5: a segment
                that navigates nowhere should not look interactive). */}
            {pathSegments.length > 0 && (
              <p
                className="hidden min-w-0 items-center overflow-hidden text-[11px] sm:flex"
                title={pathDisplay ?? undefined}
                style={{ color: 'var(--text-3)' }}
              >
                {pathSegments.map((segment, index) => (
                  <span key={index} className="flex min-w-0 shrink items-center">
                    {index > 0 && (
                      <span aria-hidden="true" className="mx-1 shrink-0">
                        ›
                      </span>
                    )}
                    <span className="truncate">{segment}</span>
                  </span>
                ))}
              </p>
            )}
          </>
        ) : (
          <p role="status" className="truncate text-[11px]" style={{ color: 'var(--amber)' }}>
            Directory unavailable
          </p>
        )}
      </div>
      <Button variant="ghost" size="icon-sm" onClick={toggleMode} aria-label={mode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'} title={mode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}><Icon name={mode === 'light' ? 'dark_mode' : 'light_mode'} size={16} /></Button>
      <Button variant="ghost" size="icon-sm" onClick={onOpenSetup} aria-label="Hub setup" title="Hub setup"><Icon name="more_vert" size={16} /></Button>
    </header>
  )
}
