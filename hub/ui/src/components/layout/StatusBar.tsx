import { MessageSquare, CheckSquare, HelpCircle, Users } from 'lucide-react'
import { useStatus } from '@/api/status'

export function StatusBar() {
  const { data } = useStatus()

  const pendingMsgs = data?.message_counts?.pending ?? 0
  const activeTasks = data ? Object.values(data.task_counts).reduce((a, b) => a + b, 0) : 0
  const unanswered = data?.question_counts?.unanswered ?? 0
  const agentCount = data?.agents_active?.length ?? 0

  return (
    <div className="flex items-center gap-4 border-b bg-muted/30 px-4 py-2 text-xs">
      <span className="font-semibold text-muted-foreground uppercase tracking-wider">AgentWeave Hub</span>
      <div className="flex items-center gap-1">
        <MessageSquare className="h-3.5 w-3.5" />
        <span>{pendingMsgs} pending msgs</span>
      </div>
      <div className="flex items-center gap-1">
        <CheckSquare className="h-3.5 w-3.5" />
        <span>{activeTasks} tasks</span>
      </div>
      <div className={`flex items-center gap-1 ${unanswered > 0 ? 'text-red-600 font-bold' : ''}`}>
        <HelpCircle className="h-3.5 w-3.5" />
        <span>{unanswered} question{unanswered !== 1 ? 's' : ''}{unanswered > 0 ? '!' : ''}</span>
      </div>
      <div className="flex items-center gap-1">
        <Users className="h-3.5 w-3.5" />
        <span>{agentCount} agent{agentCount !== 1 ? 's' : ''}</span>
      </div>
      {data?.project_name && (
        <span className="ml-auto text-muted-foreground">{data.project_name}</span>
      )}
    </div>
  )
}
