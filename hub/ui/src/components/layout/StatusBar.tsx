import { MessageSquare, CheckSquare, HelpCircle, Users } from 'lucide-react'
import { useStatus } from '@/api/status'

export function StatusBar() {
  const { data } = useStatus()

  const pendingMsgs = data?.message_counts?.pending ?? 0
  const activeTasks = data ? Object.values(data.task_counts).reduce((a, b) => a + b, 0) : 0
  const unanswered = data?.question_counts?.unanswered ?? 0
  const agentCount = data?.agents_active?.length ?? 0

  return (
    <div className="glass-bar flex items-center gap-4 py-1.5 px-4 text-xs font-mono shrink-0">
      <span className="font-semibold text-white/30 uppercase tracking-widest text-[10px]">AgentWeave Hub</span>
      <div className="flex items-center gap-1 text-white/40">
        <MessageSquare className="h-3.5 w-3.5" />
        <span><span className="text-white/80">{pendingMsgs}</span> pending msgs</span>
      </div>
      <div className="flex items-center gap-1 text-white/40">
        <CheckSquare className="h-3.5 w-3.5" />
        <span><span className="text-white/80">{activeTasks}</span> tasks</span>
      </div>
      <div className={`flex items-center gap-1 ${unanswered > 0 ? 'text-red-400 font-bold' : 'text-white/40'}`}>
        <HelpCircle className="h-3.5 w-3.5" />
        <span>
          <span className={unanswered > 0 ? 'text-red-300' : 'text-white/80'}>{unanswered}</span>
          {' '}question{unanswered !== 1 ? 's' : ''}{unanswered > 0 ? '!' : ''}
        </span>
      </div>
      <div className="flex items-center gap-1 text-white/40">
        <Users className="h-3.5 w-3.5" />
        <span><span className="text-white/80">{agentCount}</span> agent{agentCount !== 1 ? 's' : ''}</span>
      </div>
      {data?.project_name && (
        <span className="ml-auto text-white/25">{data.project_name}</span>
      )}
    </div>
  )
}
