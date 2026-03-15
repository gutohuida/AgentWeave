import { MessageSquare, CheckSquare, HelpCircle, Activity, Settings, Terminal, Bot } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useQuestions } from '@/api/questions'
import { useMessages } from '@/api/messages'
import { useAgents } from '@/api/agents'

type Page = 'messages' | 'tasks' | 'questions' | 'activity' | 'logs' | 'agents'

interface SidebarProps {
  activePage: Page
  onNavigate: (page: Page) => void
  onOpenSetup: () => void
}

export function Sidebar({ activePage, onNavigate, onOpenSetup }: SidebarProps) {
  const { data: questions } = useQuestions(false)
  const { data: messages } = useMessages()
  const { data: agents } = useAgents()

  const unanswered = questions?.length ?? 0
  const unread = messages?.filter((m) => !m.read).length ?? 0
  const activeAgents = agents?.filter((a) => a.status === 'active').length ?? 0

  const navItems: { id: Page; label: string; icon: React.ElementType; badge?: number; danger?: boolean }[] = [
    { id: 'messages',  label: 'Messages',  icon: MessageSquare, badge: unread },
    { id: 'tasks',     label: 'Tasks',     icon: CheckSquare },
    { id: 'questions', label: 'Questions', icon: HelpCircle,    badge: unanswered, danger: unanswered > 0 },
    { id: 'activity',  label: 'Activity',  icon: Activity },
    { id: 'logs',      label: 'Logs',      icon: Terminal },
    { id: 'agents',    label: 'Agents',    icon: Bot,           badge: activeAgents },
  ]

  return (
    <div className="glass flex h-full w-48 flex-col rounded-xl shrink-0">
      {/* Logo */}
      <div className="px-4 py-3.5" style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center text-[10px] font-black text-white"
               style={{ background: 'linear-gradient(135deg, hsl(var(--primary)), hsl(var(--primary) / 0.6))' }}>
            AW
          </div>
          <div>
            <div className="font-semibold text-sm text-white">AgentWeave</div>
            <div className="text-[10px] text-white/30">Hub</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 p-2.5">
        {navItems.map(({ id, label, icon: Icon, badge, danger }) => (
          <button
            key={id}
            onClick={() => onNavigate(id)}
            className={cn(
              'flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors',
              activePage === id
                ? 'border-l-2 border-primary bg-white/[0.07] text-white font-medium'
                : 'text-white/50 hover:text-white/80 hover:bg-white/[0.05]'
            )}
          >
            <span className="flex items-center gap-2">
              <Icon className="h-4 w-4" />
              {label}
            </span>
            {badge !== undefined && badge > 0 && (
              <span className={cn(
                'rounded-full px-1.5 py-0.5 text-xs font-bold',
                danger
                  ? 'bg-red-500/15 text-red-400 ring-1 ring-red-500/20'
                  : 'bg-primary/15 text-primary ring-1 ring-primary/20'
              )}>
                {badge}
              </span>
            )}
          </button>
        ))}
      </nav>

      {/* Setup */}
      <div className="p-2.5" style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
        <button
          onClick={onOpenSetup}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-white/40 hover:bg-white/[0.05] hover:text-white/70 transition-colors"
        >
          <Settings className="h-4 w-4" />
          Setup
        </button>
      </div>
    </div>
  )
}
