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

interface OverviewPageProps {
  onNavigate: (page: string) => void
}

function AgentHealthCard({ agent, onClick }: { agent: AgentSummary; onClick: () => void }) {
  const statusColor = agent.status === 'running' ? 'var(--green)' : agent.status === 'waiting' ? 'var(--amber)' : 'var(--text-3)'

  return (
    <button
      onClick={onClick}
      className="text-left"
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: 10,
        cursor: 'pointer',
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--border-hi)' }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}
    >
      <div className="flex items-center gap-2 mb-2">
        <span
          className="inline-flex rounded-full shrink-0"
          style={{
            width: 8,
            height: 8,
            background: statusColor,
            boxShadow: agent.status === 'running' ? `0 0 0 2px ${statusColor}40` : undefined,
          }}
        />
        <span className="font-medium text-sm truncate" style={{ color: 'var(--text)' }}>
          {agent.name}
        </span>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-3 mb-2" style={{ fontSize: 11, color: 'var(--text-3)' }}>
        <span>{agent.active_task_count} tasks</span>
        <span>{agent.message_count} msgs</span>
      </div>

      <ContextUsageIndicator value={agent.context_usage} compact />

      {/* Last seen + preview */}
      {agent.last_seen && (
        <p style={{ fontSize: 11, color: 'var(--text-3)' }}>
          {formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true })}
        </p>
      )}
      {agent.latest_status_msg && (
        <p className="truncate mt-1" style={{ fontSize: 11, color: 'var(--text-3)' }}>
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

  // Task counts by status
  const taskCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    tasks.forEach((t) => {
      counts[t.status] = (counts[t.status] || 0) + 1
    })
    return counts
  }, [tasks])

  // Recent SSE events
  const recentEvents = useMemo(() => {
    return getBufferedEvents().slice(-10).reverse()
  }, [agents, tasks, questions])

  if (agentsLoading) {
    return (
      <div className="p-6" style={{ color: 'var(--text-3)' }}>
        Loading…
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Overview</h1>
        <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>
          {agentCount} agent{agentCount !== 1 ? 's' : ''} · {taskCount} task{taskCount !== 1 ? 's' : ''}
          {status?.project_name ? ` · ${status.project_name}` : ''}
        </p>
      </div>

      <AccountingPanel />

      {/* Agent health grid */}
      {agents.length > 0 ? (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
            gap: 8,
          }}
        >
          {agents.map((agent) => (
            <AgentHealthCard
              key={agent.name}
              agent={agent}
              onClick={() => onNavigate(`agent:${agent.name}`)}
            />
          ))}
        </div>
      ) : (
        <div
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            padding: 24,
            textAlign: 'center',
            color: 'var(--text-2)',
          }}
        >
          No agents connected. Run <code>agentweave start</code> to connect agents.
        </div>
      )}

      <div className="grid gap-2 sm:grid-cols-3" aria-label="Project workspace summary">
        {[
          { page: 'tasks', label: 'Tasks', detail: `${taskCount} total` },
          { page: 'spec', label: 'Spec', detail: 'Requirements and evidence' },
          { page: 'jobs', label: 'Jobs', detail: 'Scheduled agent work' },
        ].map((item) => (
          <button key={item.page} type="button" onClick={() => onNavigate(item.page)} className="lifted-surface flex items-center justify-between px-4 py-3 text-left">
            <span className="text-xs font-semibold" style={{ color: 'var(--text)' }}>{item.label}</span>
            <span className="text-[11px]" style={{ color: 'var(--text-3)' }}>{item.detail}</span>
          </button>
        ))}
      </div>

      {/* Question interrupt */}
      {unanswered > 0 && (
        <QuestionInterruptCard
          questions={questions}
          onNavigateToQuestions={() => onNavigate('questions')}
        />
      )}

      {/* Task summary */}
      <div>
        <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 8 }}>
          Tasks
        </h2>
        {Object.keys(taskCounts).length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {Object.entries(taskCounts).map(([status, count]) => {
              const color = status === 'in_progress' ? 'var(--blue)' :
                status === 'under_review' ? 'var(--amber)' :
                status === 'approved' ? 'var(--green)' :
                status === 'revision_needed' || status === 'rejected' ? 'var(--red)' :
                'var(--text-2)'
              return (
                <button
                  key={status}
                  onClick={() => onNavigate('tasks')}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    background: 'var(--surface-2)',
                    border: '1px solid var(--border)',
                    borderRadius: 9999,
                    padding: '3px 10px',
                    fontSize: 12,
                    color: 'var(--text-2)',
                    cursor: 'pointer',
                  }}
                >
                  <span className="inline-flex rounded-full" style={{ width: 6, height: 6, background: color }} />
                  <span style={{ textTransform: 'capitalize' }}>{status.replace(/_/g, ' ')}</span>
                  <span style={{ color: 'var(--text)', fontWeight: 500 }}>{count}</span>
                </button>
              )
            })}
          </div>
        ) : (
          <p style={{ fontSize: 12, color: 'var(--text-3)' }}>No tasks yet.</p>
        )}
      </div>

      {/* Activity ticker */}
      {recentEvents.length > 0 && (
        <div>
          <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 8 }}>
            Activity
          </h2>
          <div
            className="flex items-center gap-2 overflow-x-auto"
            style={{
              height: 28,
              padding: '0 4px',
            }}
          >
            {recentEvents.map((evt, idx) => {
              const isWarning = evt.severity === 'warning' || evt.type === 'context_warning'
              const agentName = (evt.data as Record<string, unknown>)?.agent ?? ''
              return (
                <div
                  key={`${evt.timestamp}-${idx}`}
                  className="flex items-center gap-1.5 shrink-0"
                  style={{
                    background: 'var(--surface-2)',
                    border: '1px solid var(--border)',
                    borderRadius: 9999,
                    padding: '2px 8px',
                    fontSize: 11,
                    color: 'var(--text-2)',
                  }}
                >
                  <span
                    className="inline-flex rounded-full shrink-0"
                    style={{
                      width: 5,
                      height: 5,
                      background: isWarning ? 'var(--amber)' : 'var(--green)',
                    }}
                  />
                  {agentName && <span className="font-medium" style={{ color: 'var(--text)' }}>{String(agentName)}</span>}
                  <span className="truncate max-w-[160px]">{evt.type.replace(/_/g, ' ')}</span>
                  <span style={{ color: 'var(--text-3)' }}>
                    {formatDistanceToNow(new Date(evt.timestamp), { addSuffix: true })}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
