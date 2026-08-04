import { PROJECT_TABS, type ProjectTab } from '@/lib/navigation'

const LABELS: Record<ProjectTab, string> = {
  overview: 'Overview',
  tasks: 'Tasks',
  spec: 'Spec',
  jobs: 'Jobs',
  activity: 'Activity',
  environment: 'Environment',
}

export function ProjectTabs({ active, onSelect }: { active: ProjectTab; onSelect: (tab: ProjectTab) => void }) {
  return (
    <nav aria-label="Project views" className="flex shrink-0 gap-1 overflow-x-auto px-4 pt-3" style={{ borderBottom: '1px solid var(--border)', scrollbarWidth: 'thin' }}>
      {PROJECT_TABS.map((tab) => (
        <button
          key={tab}
          type="button"
          data-testid={`project-tab-${tab}`}
          aria-current={active === tab ? 'page' : undefined}
          onClick={() => onSelect(tab)}
          className="shrink-0 px-3 py-2 text-xs font-medium"
          style={{
            color: active === tab ? 'var(--text)' : 'var(--text-3)',
            borderBottom: active === tab ? '2px solid var(--blue)' : '2px solid transparent',
          }}
        >
          {LABELS[tab]}
        </button>
      ))}
    </nav>
  )
}
