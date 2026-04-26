import { Icon } from '@/components/common/Icon'
import { useQuestions } from '@/api/questions'
import { useMessages } from '@/api/messages'
import { useAgents } from '@/api/agents'
import { useSessionSync } from '@/api/status'

type Page = 'overview' | 'messages' | 'tasks' | 'questions' | 'activity' | 'logs' | 'agents' | 'jobs' | 'quality'

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
  { id: 'tasks',     label: 'Tasks',     icon: 'task_alt',     section: 'WORK' },
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

  function getBadge(id: Page): { count: number; danger: boolean } | null {
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

  const navItemStyle = (active: boolean): React.CSSProperties => ({
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    width: '100%',
    padding: '6px 8px',
    borderRadius: 'var(--radius-sm)',
    fontSize: 13,
    fontWeight: 500,
    color: active ? 'var(--text)' : 'var(--text-2)',
    background: active ? 'rgba(255,255,255,0.06)' : 'transparent',
    transition: 'background 0.15s, color 0.15s',
    cursor: 'pointer',
    border: 'none',
    textAlign: 'left',
  })

  const navItemBefore = (active: boolean): React.CSSProperties => ({
    content: '""',
    position: 'absolute',
    left: 0,
    top: '50%',
    transform: 'translateY(-50%)',
    width: 2,
    height: active ? 16 : 0,
    background: 'var(--text)',
    borderRadius: '0 2px 2px 0',
    transition: 'height 0.15s',
  })

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
        {topItems.map(({ id, label, icon }) => {
          const active = activePage === id
          const badge = getBadge(id)
          return (
            <button
              key={id}
              onClick={() => onNavigate(id)}
              className="group"
              style={navItemStyle(active)}
              onMouseEnter={(e) => {
                if (!active) {
                  e.currentTarget.style.background = 'rgba(255,255,255,0.04)'
                  e.currentTarget.style.color = 'var(--text)'
                }
              }}
              onMouseLeave={(e) => {
                if (!active) {
                  e.currentTarget.style.background = 'transparent'
                  e.currentTarget.style.color = 'var(--text-2)'
                }
              }}
            >
              <span style={navItemBefore(active)} />
              <Icon name={icon} size={18} />
              <span className="flex-1">{label}</span>
              {badge && (
                <span
                  className="shrink-0"
                  style={{
                    fontSize: 10,
                    borderRadius: 9999,
                    padding: '1px 5px',
                    background: badge.danger ? 'var(--red)' : 'var(--surface-3)',
                    color: badge.danger ? '#fff' : 'var(--text-2)',
                    fontWeight: 600,
                  }}
                >
                  {badge.count}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {/* Sectioned nav items */}
      {sectionedItems.map(({ section, items }) => (
        <div key={section}>
          <div style={sectionLabelStyle}>{section}</div>
          <nav className="flex flex-col">
            {items.map(({ id, label, icon }) => {
              const active = activePage === id
              const badge = getBadge(id)
              return (
                <button
                  key={id}
                  onClick={() => onNavigate(id)}
                  className="group"
                  style={navItemStyle(active)}
                  onMouseEnter={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = 'rgba(255,255,255,0.04)'
                      e.currentTarget.style.color = 'var(--text)'
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = 'transparent'
                      e.currentTarget.style.color = 'var(--text-2)'
                    }
                  }}
                >
                  <span style={navItemBefore(active)} />
                  <Icon name={icon} size={18} />
                  <span className="flex-1">{label}</span>
                  {badge && (
                    <span
                      className="shrink-0"
                      style={{
                        fontSize: 10,
                        borderRadius: 9999,
                        padding: '1px 5px',
                        background: badge.danger ? 'var(--red)' : 'var(--surface-3)',
                        color: badge.danger ? '#fff' : 'var(--text-2)',
                        fontWeight: 600,
                      }}
                    >
                      {badge.count}
                    </span>
                  )}
                </button>
              )
            })}
          </nav>
        </div>
      ))}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Settings — pinned bottom */}
      <div
        style={{ borderTop: '1px solid var(--border)', marginTop: 8, paddingTop: 8 }}
      >
        <button
          onClick={onOpenSetup}
          className="group"
          style={navItemStyle(false)}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(255,255,255,0.04)'
            e.currentTarget.style.color = 'var(--text)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent'
            e.currentTarget.style.color = 'var(--text-2)'
          }}
        >
          <Icon name="settings" size={18} />
          <span>Settings</span>
        </button>
      </div>
    </div>
  )
}
