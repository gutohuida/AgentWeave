import { useQuestions } from '@/api/questions'
import { useMessages } from '@/api/messages'
import { useAgents } from '@/api/agents'
import { useSessionSync } from '@/api/status'
import { SidebarItem, type SidebarBadge } from './SidebarItem'

type Page = 'overview' | 'messages' | 'tasks' | 'questions' | 'activity' | 'logs' | 'agents' | 'jobs' | 'quality' | 'instructions' | 'spec'

interface SidebarProps {
  activePage: Page
  onNavigate: (page: Page) => void
  onOpenSetup: () => void
}

interface NavItem {
  id: Page
  label: string
  icon: string
  section?: string
}

const NAV_ITEMS: NavItem[] = [
  { id: 'overview',  label: 'Overview',  icon: 'home' },
  { id: 'agents',    label: 'Agents',    icon: 'smart_toy' },
  { id: 'instructions', label: 'Instructions', icon: 'description' },
  { id: 'tasks',     label: 'Tasks',     icon: 'task_alt',     section: 'WORK' },
  { id: 'spec',      label: 'Spec',      icon: 'article',      section: 'WORK' },
  { id: 'jobs',      label: 'Jobs',      icon: 'schedule',     section: 'WORK' },
  { id: 'messages',  label: 'Messages',  icon: 'chat',         section: 'COMMUNICATION' },
  { id: 'questions', label: 'Questions', icon: 'help',         section: 'COMMUNICATION' },
  { id: 'logs',      label: 'Logs',      icon: 'terminal',     section: 'OBSERVE' },
  { id: 'activity',  label: 'Activity',  icon: 'monitoring',   section: 'OBSERVE' },
  { id: 'quality',   label: 'Quality',   icon: 'verified_user', section: 'OBSERVE' },
]

const SECTION_ORDER = ['WORK', 'COMMUNICATION', 'OBSERVE']

export function Sidebar({ activePage, onNavigate, onOpenSetup }: SidebarProps) {
  const { data: questions }    = useQuestions(false)
  const { data: messages }     = useMessages()
  const { data: agents }       = useAgents()
  const { data: sessionSync }  = useSessionSync()

  const unanswered   = questions?.length ?? 0
  const unread       = messages?.filter((m) => !m.read).length ?? 0
  const activeAgents = agents?.filter((a) => a.status === 'active').length ?? 0
  const qualityActive = !!(sessionSync?.data?.quality)

  function getBadge(id: Page): SidebarBadge | null {
    if (id === 'messages'  && unread > 0)        return { count: unread, danger: false }
    if (id === 'questions' && unanswered > 0)    return { count: unanswered, danger: true }
    if (id === 'agents'    && activeAgents > 0)  return { count: activeAgents, danger: false }
    if (id === 'quality'   && qualityActive)     return { count: 1, danger: false }
    return null
  }

  const sectionLabelStyle: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: 'var(--text-3)',
    padding: '8px 8px 4px',
    marginTop: 8,
  }

  // Group nav items by section
  const topItems = NAV_ITEMS.filter((i) => !i.section)
  const sectionedItems = SECTION_ORDER.map((sec) => ({
    section: sec,
    items: NAV_ITEMS.filter((i) => i.section === sec),
  }))

  return (
    <div
      className="flex h-full flex-col shrink-0"
      style={{
        width: 220,
        background: 'var(--surface)',
        borderRight: '1px solid var(--border)',
        padding: '12px 8px',
      }}
    >
      {/* Logo mark */}
      <div
        className="px-2 mb-2"
        style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)' }}
      >
        AW
      </div>

      {/* Top-level nav items */}
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
          />
        ))}
      </nav>

      {/* Sectioned nav items */}
      {sectionedItems.map(({ section, items }) => (
        <div key={section}>
          <div style={sectionLabelStyle}>{section}</div>
          <nav className="flex flex-col">
            {items.map(({ id, label, icon }) => (
              <SidebarItem
                key={id}
                label={label}
                icon={icon}
                active={activePage === id}
                badge={getBadge(id)}
                onClick={() => onNavigate(id)}
                testId={`nav-${id}`}
              />
            ))}
          </nav>
        </div>
      ))}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Settings — pinned bottom */}
      <div
        style={{ borderTop: '1px solid var(--border)', marginTop: 8, paddingTop: 8 }}
      >
        <SidebarItem
          label="Settings"
          icon="settings"
          active={false}
          onClick={onOpenSetup}
          testId="nav-settings"
        />
      </div>
    </div>
  )
}
