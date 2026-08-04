import { Icon } from '@/components/common/Icon'
import { useConfigStore } from '@/store/configStore'

interface ProjectHeaderProps {
  projectName: string
  pathDisplay?: string | null
  agentCount?: number
  directoryAvailable: boolean
  onAddAgent: () => void
  onOpenSettings: () => void
  onOpenSetup: () => void
}

export function ProjectHeader({
  projectName,
  pathDisplay,
  agentCount = 0,
  directoryAvailable,
  onAddAgent,
  onOpenSettings,
  onOpenSetup,
}: ProjectHeaderProps) {
  const { mode, setMode } = useConfigStore()

  const toggleMode = () => {
    const next = mode === 'light' ? 'dark' : 'light'
    setMode(next)
    document.documentElement.dataset.mode = next
  }

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 px-5" style={{ background: 'var(--top)', borderBottom: '1px solid var(--border-region)' }}>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-sm font-semibold" style={{ color: 'var(--text)' }}>{projectName}</h1>
        {directoryAvailable ? (
          <p className="truncate text-[10px]" style={{ color: 'var(--text-3)' }}>{agentCount} agent{agentCount === 1 ? '' : 's'}{pathDisplay ? ` · ${pathDisplay}` : ''}</p>
        ) : (
          <p role="status" className="truncate text-[10px]" style={{ color: 'var(--amber)' }}>
            Directory unavailable
          </p>
        )}
      </div>
      <button type="button" onClick={onAddAgent} className="flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-semibold" style={{ background: 'var(--primary)', color: 'var(--primary-foreground)' }}>
        <Icon name="person_add" size={14} />
        Add agent
      </button>
      <button type="button" onClick={onOpenSettings} aria-label="Project settings" title="Project settings" className="flex h-8 w-8 items-center justify-center rounded-md" style={{ color: 'var(--text-2)' }}><Icon name="settings" size={16} /></button>
      <button type="button" onClick={toggleMode} aria-label={mode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'} title={mode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'} className="flex h-8 w-8 items-center justify-center rounded-md" style={{ color: 'var(--text-2)' }}><Icon name={mode === 'light' ? 'dark_mode' : 'light_mode'} size={16} /></button>
      <button type="button" onClick={onOpenSetup} aria-label="Hub setup" title="Hub setup" className="flex h-8 w-8 items-center justify-center rounded-md" style={{ color: 'var(--text-2)' }}><Icon name="more_vert" size={16} /></button>
    </header>
  )
}
