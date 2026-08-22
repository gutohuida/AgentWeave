import { useMemo } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { useAgents, AgentSummary } from '@/api/agents'
import { useQuestions } from '@/api/questions'
import { useTasks } from '@/api/tasks'
import { useStatus } from '@/api/status'
import { getBufferedEvents } from '@/hooks/useSSE'
import { QuestionInterruptCard } from '@/components/questions/QuestionInterruptCard'
import { ContextUsageIndicator } from '@/components/context/ContextUsageIndicator'
import { AccountingPanel } from '@/components/accounting/AccountingPanel'
import { Icon } from '@/components/common/Icon'
import { getStatusConfig } from '@/lib/agentStatusConfig'
import { hubDate } from '@/lib/hubTime'

interface OverviewPageProps {
  onNavigate: (page: string) => void
}

function AgentHealthCard({ agent, onClick }: { agent: AgentSummary; onClick: () => void }) {
  // Deliberately not <StatusDot /> — this card uses a static 8x8 dot with a glow
  // shadow instead of StatusDot's animate-ping halo (see lib/agentStatus.tsx).
  const statusCfg = getStatusConfig(agent.status)
  const statusColor = statusCfg.dotColor

  return (
    <button
      onClick={onClick}
      className="overview-agent-card"
      aria-label={`Open ${agent.name}, ${statusCfg.label}`}
    >
      <div className="mb-2 flex items-center gap-2">
        <span
          className="inline-flex shrink-0 rounded-full"
          title={statusCfg.label}
          style={{
            width: 8,
            height: 8,
            background: statusColor,
            boxShadow: statusCfg.pulse ? `0 0 0 2px ${statusColor}40` : undefined,
          }}
        />
        <span className="truncate text-sm font-medium" style={{ color: 'var(--text)' }}>
          {agent.name}
        </span>
      </div>
      <div className="mb-2 flex items-center gap-3" style={{ fontSize: 11, color: 'var(--text-3)' }}>
        <span>{agent.active_task_count} tasks</span>
        <span>{agent.message_count} msgs</span>
      </div>
      <ContextUsageIndicator value={agent.context_usage} compact />
      {agent.last_seen && (
        <p style={{ fontSize: 11, color: 'var(--text-3)' }}>
          {formatDistanceToNow(hubDate(agent.last_seen), { addSuffix: true })}
        </p>
      )}
      {agent.latest_status_msg && (
        <p className="mt-1 truncate" style={{ fontSize: 11, color: 'var(--text-3)' }}>
          {agent.latest_status_msg}
        </p>
      )}
    </button>
  )
}

export function OverviewPage({ onNavigate }: OverviewPageProps) {
  const { data: agents = [], isLoading: agentsLoading } = useAgents()
  const { data: questions = [] } = useQuestions(false)
  const { data: tasks = [] } = useTasks()
  const { data: status } = useStatus()

  const unanswered = questions.length
  const agentCount = agents.length
  const taskCount = tasks.length
  const taskCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    tasks.forEach((task) => { counts[task.status] = (counts[task.status] || 0) + 1 })
    return counts
  }, [tasks])

  // getBufferedEvents reads a module-level buffer. Query changes are the available signal that
  // the same SSE event moved that buffer, so these dependencies are deliberate.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const recentEvents = useMemo(() => getBufferedEvents().slice(-10).reverse(), [agents, tasks, questions])

  if (agentsLoading) {
    return (
      <div className="space-y-4" aria-label="Loading overview">
        <div className="trust-state-skeleton w-28" />
        <div className="overview-agent-grid">
          {[0, 1, 2].map((item) => (
            <div key={item} className="lifted-surface p-3" aria-hidden="true">
              <div className="trust-state-skeleton w-2/3" />
              <div className="trust-state-skeleton mt-3 w-1/2" />
              <div className="trust-state-skeleton mt-3 w-full" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div>
      <section className="overview-group" aria-labelledby="overview-heading">
        <h1 id="overview-heading" className="text-lg font-semibold" style={{ color: 'var(--text)' }}>Overview</h1>
        <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>
          {agentCount} agent{agentCount !== 1 ? 's' : ''} · {taskCount} task{taskCount !== 1 ? 's' : ''}
          {status?.project_name ? ` · ${status.project_name}` : ''}
        </p>
        <div className="overview-accounting mt-5"><AccountingPanel /></div>
      </section>

      <section className="overview-group" aria-labelledby="overview-attention">
        <h2 id="overview-attention" className="overview-group-label">Attention</h2>
        {agents.length > 0 ? (
          <div className="overview-agent-grid">
            {agents.map((agent) => (
              <AgentHealthCard key={agent.name} agent={agent} onClick={() => onNavigate(`agent:${agent.name}`)} />
            ))}
          </div>
        ) : (
          <div className="lifted-surface flex flex-col items-center px-6 py-7 text-center">
            <Icon name="smart_toy" size={26} style={{ color: 'var(--text-3)' }} />
            <h3 className="mt-2 text-[13px] font-semibold" style={{ color: 'var(--text)' }}>No agents connected</h3>
            <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
              Run <code className="rounded-[var(--radius-sm)] bg-[var(--surface-2)] px-1.5 py-0.5">agentweave start</code> to connect agents.
            </p>
          </div>
        )}
      </section>

      <section className="overview-group" aria-labelledby="overview-navigate">
        <h2 id="overview-navigate" className="overview-group-label">Navigate</h2>
        <div className="grid gap-2 sm:grid-cols-3" aria-label="Project workspace summary">
          {[
            { page: 'tasks', label: 'Tasks', detail: `${taskCount} total`, icon: 'task_alt' },
            { page: 'spec', label: 'Spec', detail: 'Requirements and evidence', icon: 'description' },
            { page: 'jobs', label: 'Jobs', detail: 'Scheduled agent work', icon: 'schedule' },
          ].map((item) => (
            <button key={item.page} type="button" onClick={() => onNavigate(item.page)} className="lifted-surface overview-workspace-card flex items-center gap-3 px-4 py-3 text-left">
              <Icon name={item.icon} size={17} style={{ color: 'var(--text-2)' }} />
              <span className="min-w-0 flex-1">
                <span className="block text-xs font-semibold" style={{ color: 'var(--text)' }}>{item.label}</span>
                <span className="block truncate text-[11px]" style={{ color: 'var(--text-3)' }}>{item.detail}</span>
              </span>
            </button>
          ))}
        </div>

        {unanswered > 0 && (
          <div className="mt-5">
            <QuestionInterruptCard questions={questions} onNavigateToQuestions={() => onNavigate('questions')} />
          </div>
        )}

        <div className="mt-5">
          <h2 className="mb-2 text-[13px] font-semibold" style={{ color: 'var(--text)' }}>Tasks</h2>
          {Object.keys(taskCounts).length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {Object.entries(taskCounts).map(([taskStatus, count]) => {
                const color = taskStatus === 'in_progress' ? 'var(--amber)' :
                  taskStatus === 'under_review' ? 'var(--amber)' :
                  taskStatus === 'approved' ? 'var(--green)' :
                  taskStatus === 'revision_needed' || taskStatus === 'rejected' ? 'var(--red)' :
                  'var(--text-2)'
                const label = taskStatus.replace(/_/g, ' ')
                return (
                  <button
                    key={taskStatus}
                    onClick={() => onNavigate('tasks')}
                    aria-label={`${count} tasks ${label}`}
                    className="aw-chip inline-flex items-center gap-1.5 bg-[var(--surface-2)] px-2.5 py-1 text-xs hover:bg-[var(--row-hover)]"
                    style={{ border: '1px solid var(--border)', color: 'var(--text-2)' }}
                  >
                    <span className="inline-flex rounded-full" style={{ width: 6, height: 6, background: color }} />
                    <span style={{ textTransform: 'capitalize' }}>{label}</span>
                    <span style={{ color: 'var(--text)', fontWeight: 500 }}>{count}</span>
                  </button>
                )
              })}
            </div>
          ) : (
            <p style={{ fontSize: 12, color: 'var(--text-3)' }}>No tasks yet.</p>
          )}
        </div>

        {recentEvents.length > 0 && (
          <div className="mt-5">
            <h2 className="mb-2 text-[13px] font-semibold" style={{ color: 'var(--text)' }}>Activity</h2>
            <div className="overview-activity">
              <div className="flex h-7 items-center gap-2 overflow-x-auto px-1">
                {recentEvents.map((event, index) => {
                  const isWarning = event.severity === 'warning' || event.type === 'context_warning'
                  const agentName = (event.data as Record<string, unknown>)?.agent ?? ''
                  return (
                    <div
                      key={`${event.timestamp}-${index}`}
                      className="overview-activity-pill flex shrink-0 items-center gap-1.5"
                      style={{
                        animationDelay: `${index * 30}ms`,
                        background: 'var(--surface-2)',
                        border: '1px solid var(--border)',
                        borderRadius: 9999,
                        padding: '2px 8px',
                        fontSize: 11,
                        color: 'var(--text-2)',
                      }}
                    >
                      <span className="inline-flex shrink-0 rounded-full" style={{ width: 5, height: 5, background: isWarning ? 'var(--amber)' : 'var(--green)' }} />
                      {agentName && <span className="font-medium" style={{ color: 'var(--text)' }}>{String(agentName)}</span>}
                      <span className="max-w-[160px] truncate">{event.type.replace(/_/g, ' ')}</span>
                      <span style={{ color: 'var(--text-3)' }}>{formatDistanceToNow(hubDate(event.timestamp), { addSuffix: true })}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
