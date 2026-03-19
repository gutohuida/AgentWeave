import { Icon } from '@/components/common/Icon'
import { useQuestions } from '@/api/questions'
import { useMessages } from '@/api/messages'
import { useAgents } from '@/api/agents'

type Page = 'messages' | 'tasks' | 'questions' | 'activity' | 'logs' | 'agents'

interface SidebarProps {
  activePage: Page
  onNavigate: (page: Page) => void
  onOpenSetup: () => void
}

const NAV_ITEMS: { id: Page; label: string; icon: string }[] = [
  { id: 'messages',  label: 'Messages',  icon: 'chat' },
  { id: 'tasks',     label: 'Tasks',     icon: 'task_alt' },
  { id: 'questions', label: 'Questions', icon: 'help' },
  { id: 'activity',  label: 'Activity',  icon: 'monitoring' },
  { id: 'logs',      label: 'Logs',      icon: 'terminal' },
  { id: 'agents',    label: 'Agents',    icon: 'smart_toy' },
]

export function Sidebar({ activePage, onNavigate, onOpenSetup }: SidebarProps) {
  const { data: questions } = useQuestions(false)
  const { data: messages }  = useMessages()
  const { data: agents }    = useAgents()

  const unanswered   = questions?.length ?? 0
  const unread       = messages?.filter((m) => !m.read).length ?? 0
  const activeAgents = agents?.filter((a) => a.status === 'active').length ?? 0

  function getBadge(id: Page): { count: number; danger: boolean } | null {
    if (id === 'messages'  && unread > 0)      return { count: unread, danger: false }
    if (id === 'questions' && unanswered > 0)  return { count: unanswered, danger: true }
    if (id === 'agents'    && activeAgents > 0) return { count: activeAgents, danger: false }
    return null
  }

  return (
    <div className="m3-nav-rail flex h-full w-20 flex-col items-center shrink-0 py-3 gap-1">
      {/* Logo */}
      <div
        className="w-12 h-12 rounded-[18px] flex items-center justify-center text-[10px] font-black mb-3 shrink-0"
        style={{ background: 'var(--primary)', color: 'var(--primary-foreground)' }}
      >
        AW
      </div>

      {/* Nav items */}
      <nav className="flex flex-col items-center gap-0.5 flex-1 w-full px-2">
        {NAV_ITEMS.map(({ id, label, icon }) => {
          const active = activePage === id
          const badge  = getBadge(id)
          return (
            <button
              key={id}
              onClick={() => onNavigate(id)}
              title={label}
              className="relative flex flex-col items-center gap-1 w-full py-1.5 px-1 text-center transition-colors"
              style={{ color: active ? 'var(--on-p-cont)' : 'var(--on-sv)' }}
            >
              {/* Pill indicator */}
              <div className="relative flex items-center justify-center w-14 h-8">
                {active && (
                  <div
                    className="absolute inset-0 rounded-full"
                    style={{ background: 'var(--p-cont)' }}
                  />
                )}
                <Icon
                  name={icon}
                  size={22}
                  fill={active ? 1 : 0}
                  className="relative z-10"
                  style={{ color: active ? 'var(--on-p-cont)' : 'var(--on-sv)' } as React.CSSProperties}
                />
                {badge && (
                  <span
                    className="absolute top-0 right-0 min-w-[16px] h-4 rounded-full px-1 text-[9px] font-bold flex items-center justify-center leading-none z-20"
                    style={{
                      background: badge.danger ? 'var(--destructive)' : 'var(--primary)',
                      color:      badge.danger ? 'var(--destructive-fg)' : 'var(--primary-foreground)',
                    }}
                  >
                    {badge.count}
                  </span>
                )}
              </div>
              <span
                className="m3-label-small"
                style={{ color: active ? 'var(--on-p-cont)' : 'var(--on-sv)', opacity: active ? 1 : 0.72 }}
              >
                {label}
              </span>
            </button>
          )
        })}
      </nav>

      {/* Setup */}
      <button
        onClick={onOpenSetup}
        title="Setup"
        className="flex flex-col items-center gap-1 w-full py-1.5 px-1"
        style={{ color: 'var(--on-sv)' }}
      >
        <div className="flex items-center justify-center w-14 h-8">
          <Icon name="settings" size={22} />
        </div>
        <span className="m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.72 }}>Setup</span>
      </button>
    </div>
  )
}
