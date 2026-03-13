import { MessageSquare, CheckSquare, HelpCircle, Activity, Settings } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useQuestions } from '@/api/questions'
import { useMessages } from '@/api/messages'

type Page = 'messages' | 'tasks' | 'questions' | 'activity'

interface SidebarProps {
  activePage: Page
  onNavigate: (page: Page) => void
  onOpenSetup: () => void
}

export function Sidebar({ activePage, onNavigate, onOpenSetup }: SidebarProps) {
  const { data: questions } = useQuestions(false)
  const { data: messages } = useMessages()

  const unanswered = questions?.length ?? 0
  const unread = messages?.filter((m) => !m.read).length ?? 0

  const navItems: { id: Page; label: string; icon: React.ElementType; badge?: number; danger?: boolean }[] = [
    { id: 'messages', label: 'Messages', icon: MessageSquare, badge: unread },
    { id: 'tasks', label: 'Tasks', icon: CheckSquare },
    { id: 'questions', label: 'Questions', icon: HelpCircle, badge: unanswered, danger: unanswered > 0 },
    { id: 'activity', label: 'Activity', icon: Activity },
  ]

  return (
    <div className="flex h-full w-48 flex-col border-r bg-muted/20">
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map(({ id, label, icon: Icon, badge, danger }) => (
          <button
            key={id}
            onClick={() => onNavigate(id)}
            className={cn(
              'flex w-full items-center justify-between rounded-md px-3 py-2 text-sm transition-colors',
              activePage === id
                ? 'bg-primary text-primary-foreground'
                : 'hover:bg-accent text-muted-foreground hover:text-foreground'
            )}
          >
            <span className="flex items-center gap-2">
              <Icon className="h-4 w-4" />
              {label}
            </span>
            {badge !== undefined && badge > 0 && (
              <span
                className={cn(
                  'rounded-full px-1.5 py-0.5 text-xs font-bold',
                  danger ? 'bg-red-500 text-white' : 'bg-primary/20 text-primary'
                )}
              >
                {badge}
              </span>
            )}
          </button>
        ))}
      </nav>
      <div className="border-t p-3">
        <button
          onClick={onOpenSetup}
          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <Settings className="h-4 w-4" />
          Setup
        </button>
      </div>
    </div>
  )
}
