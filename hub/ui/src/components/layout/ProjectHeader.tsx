import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { useConfigStore } from '@/store/configStore'

interface ProjectHeaderProps {
  projectName: string
  pathDisplay?: string | null
  agentCount?: number
  directoryAvailable: boolean
  onOpenSetup: () => void
}

export function ProjectHeader({
  projectName,
  pathDisplay,
  agentCount = 0,
  directoryAvailable,
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
      <Button variant="ghost" size="icon-sm" onClick={toggleMode} aria-label={mode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'} title={mode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}><Icon name={mode === 'light' ? 'dark_mode' : 'light_mode'} size={16} /></Button>
      <Button variant="ghost" size="icon-sm" onClick={onOpenSetup} aria-label="Hub setup" title="Hub setup"><Icon name="more_vert" size={16} /></Button>
    </header>
  )
}
