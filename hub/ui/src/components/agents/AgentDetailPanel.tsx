import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { AgentSummary } from '@/api/agents'
import { useTasks } from '@/api/tasks'
import { AgentOutputPanel } from './AgentOutputPanel'
import { AgentActivityTab } from './AgentActivityTab'
import { AgentInfoTab } from './AgentInfoTab'
import { EmptyState } from '@/components/common/EmptyState'
import { StatusBadge } from '@/components/common/Badge'
import { StatusDot } from '@/lib/agentStatus'
import { ContextUsageIndicator } from '@/components/context/ContextUsageIndicator'

interface AgentDetailPanelProps {
  agent: AgentSummary
}

type DetailTab = 'output' | 'tasks' | 'messages' | 'info'

export function AgentDetailPanel({ agent }: AgentDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<DetailTab>('output')
  const { data: tasks = [] } = useTasks()
  const agentTasks = tasks.filter((t) => t.assignee === agent.name)

  const tabs: { id: DetailTab; label: string }[] = [
    { id: 'output', label: 'Output' },
    { id: 'tasks', label: `Tasks (${agentTasks.length})` },
    { id: 'messages', label: 'Messages' },
    { id: 'info', label: 'Info' },
  ]

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div
        className="shrink-0 px-4 py-3"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-3">
          {/* Status dot + name */}
          <StatusDot status={agent.status} size="md" />
          <span className="font-semibold text-sm" style={{ color: 'var(--text)' }}>
            {agent.name}
          </span>

          <div className="flex-1" />

          {/* Context state + actions */}
          <ContextUsageIndicator value={agent.context_usage} />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex shrink-0" style={{ borderBottom: '1px solid var(--border)' }}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className="px-4 py-2 text-xs font-medium transition-colors"
            style={{
              color: activeTab === tab.id ? 'var(--text)' : 'var(--text-3)',
              borderBottom: activeTab === tab.id ? '1px solid var(--text)' : '1px solid transparent',
              marginBottom: -1,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'output' && <AgentOutputPanel agent={agent} />}
        {activeTab === 'tasks' && (
          <div className="h-full overflow-auto p-4">
            {agentTasks.length > 0 ? (
              <div className="space-y-2">
                {agentTasks.map((task) => (
                  <div
                    key={task.id}
                    style={{
                      background: 'var(--surface-2)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius)',
                      padding: 10,
                    }}
                  >
                    <p className="text-sm font-medium" style={{ color: 'var(--text)' }}>{task.title}</p>
                    <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                      <StatusBadge status={task.status} />
                      <StatusBadge status={task.priority} />
                    </div>
                    <p className="text-xs mt-1.5" style={{ color: 'var(--text-3)' }}>
                      {formatDistanceToNow(new Date(task.updated), { addSuffix: true })}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState icon="task_alt" title="No tasks" description={`No tasks assigned to ${agent.name}.`} />
            )}
          </div>
        )}
        {activeTab === 'messages' && <AgentActivityTab agent={agent} />}
        {activeTab === 'info' && <AgentInfoTab agent={agent} />}
      </div>
    </div>
  )
}
