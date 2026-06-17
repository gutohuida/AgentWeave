import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { AgentSummary } from '@/api/agents'
import { useTasks } from '@/api/tasks'
import { requestCompact, requestNewSession } from '@/api/context'
import { AgentOutputPanel } from './AgentOutputPanel'
import { AgentActivityTab } from './AgentActivityTab'
import { AgentInfoTab } from './AgentInfoTab'
import { EmptyState } from '@/components/common/EmptyState'
import { StatusBadge } from '@/components/common/Badge'
import { contextBarColor, StatusDot, DevRoleTagList } from '@/lib/agentStatus'

interface AgentDetailPanelProps {
  agent: AgentSummary
}

type DetailTab = 'output' | 'tasks' | 'messages' | 'info'

export function AgentDetailPanel({ agent }: AgentDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<DetailTab>('output')
  const [compacting, setCompacting] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const { data: tasks = [] } = useTasks()
  const agentTasks = tasks.filter((t) => t.assignee === agent.name)

  const ctx = agent.context_usage
  const ctxPct = ctx?.percent ?? 0
  const ctxColor = ctx ? contextBarColor(ctxPct, !!ctx.warning) : 'var(--text-3)'

  async function handleCompact() {
    setCompacting(true)
    try {
      await requestCompact(agent.name)
      setActionMsg('Compact request sent')
    } catch {
      setActionMsg('Failed to send')
    } finally {
      setCompacting(false)
      setTimeout(() => setActionMsg(null), 3000)
    }
  }

  async function handleReset() {
    setResetting(true)
    try {
      await requestNewSession(agent.name)
      setActionMsg('Context reset requested')
    } catch {
      setActionMsg('Failed to send')
    } finally {
      setResetting(false)
      setTimeout(() => setActionMsg(null), 3000)
    }
  }

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

          {/* Role tags */}
          <div className="flex flex-wrap gap-1">
            <DevRoleTagList agent={agent} />
          </div>

          <div className="flex-1" />

          {/* Context % + bar + actions */}
          {ctx && (
            <div className="flex items-center gap-3">
              <span className="text-xs font-medium" style={{ color: ctxColor }}>
                {ctxPct}%
              </span>
              <div className="w-12 rounded-full overflow-hidden" style={{ height: 4, background: 'var(--surface-3)' }}>
                <div
                  className="h-full rounded-full"
                  style={{ width: `${Math.min(100, Math.max(0, ctxPct))}%`, background: ctxColor }}
                />
              </div>
            </div>
          )}

          {agent.runner === 'codex' ? (
            <span className="text-xs" style={{ color: 'var(--green)' }}>Auto-managed</span>
          ) : (
            <button
              onClick={handleCompact}
              disabled={compacting}
              className="text-xs font-medium px-2.5 py-1 rounded transition-opacity disabled:opacity-50"
              style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--text-2)' }}
            >
              {compacting ? '…' : 'Compact'}
            </button>
          )}
          <button
            onClick={handleReset}
            disabled={resetting}
            className="text-xs font-medium px-2.5 py-1 rounded transition-opacity disabled:opacity-50"
            style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--text-2)' }}
          >
            {resetting ? '…' : 'Reset'}
          </button>
        </div>
        {actionMsg && (
          <p className="text-xs mt-1.5 text-center" style={{ color: 'var(--blue)' }}>
            {actionMsg}
          </p>
        )}
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
