import { Button } from '@/components/ui/button'
import { PROJECT_TABS, type ProjectTab } from '@/lib/navigation'

const LABELS: Record<ProjectTab, string> = {
  overview: 'Overview',
  tasks: 'Tasks',
  spec: 'Spec',
  jobs: 'Jobs',
  activity: 'Activity',
}

export function ProjectTabs({ active, onSelect }: { active: ProjectTab; onSelect: (tab: ProjectTab) => void }) {
  return (
    <nav aria-label="Project views" className="flex h-10 shrink-0 gap-1 overflow-x-auto px-5" style={{ background: 'var(--top)', borderBottom: '1px solid var(--border-region)', scrollbarWidth: 'thin' }}>
      {PROJECT_TABS.map((tab) => (
        <Button
          key={tab}
          variant="ghost"
          size="sm"
          data-testid={`project-tab-${tab}`}
          data-active={active === tab ? 'true' : 'false'}
          aria-current={active === tab ? 'page' : undefined}
          onClick={() => onSelect(tab)}
          className="row-item w-auto shrink-0 rounded-t-md px-3 text-xs font-medium"
        >
          {LABELS[tab]}
        </Button>
      ))}
    </nav>
  )
}
