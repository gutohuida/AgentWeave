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
    // No background of its own. It used to paint `--top`, a plane one step off `--bg` that was
    // defined for this element and nothing else — in light mode pure white against an off-white
    // page, so the strip read as a band laid over the screen rather than part of it (operator:
    // "it pops up in a bad way… make it the same color"). The active tab's own fill is what
    // marks position; the strip does not need to mark itself as a region.
    <nav aria-label="Project views" className="flex h-10 shrink-0 gap-1 overflow-x-auto px-5" style={{ scrollbarWidth: 'thin' }}>
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
