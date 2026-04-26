import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { useAgents, AgentSummary } from '@/api/agents'
import { useQuestions } from '@/api/questions'
import { AgentCard } from './AgentCard'
import { AgentDetailPanel } from './AgentDetailPanel'
import { QuestionInterruptCard } from '@/components/questions/QuestionInterruptCard'
import { EmptyState } from '@/components/common/EmptyState'

type AgentFilter = 'all' | 'active' | 'idle'

function contextBarColor(percent: number, warning: boolean): string {
  if (warning || percent >= 70) return 'var(--red)'
  if (percent >= 40) return 'var(--amber)'
  return 'var(--green)'
}

function GridCard({ agent, onClick }: { agent: AgentSummary; onClick: () => void }) {
  const statusColor = agent.status === 'running' ? 'var(--green)' : agent.status === 'waiting' ? 'var(--amber)' : 'var(--text-3)'
  const ctx = agent.context_usage
  const ctxColor = ctx ? contextBarColor(ctx.percent ?? 0, !!ctx.warning) : 'var(--text-3)'

  return (
    <button
      onClick={onClick}
      className="text-left"
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: 12,
        cursor: 'pointer',
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--border-hi)' }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="relative flex h-2 w-2 shrink-0">
          {agent.status === 'running' && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: statusColor }} />
          )}
          <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: statusColor }} />
        </span>
        <span className="font-medium text-sm truncate" style={{ color: 'var(--text)' }}>{agent.name}</span>
      </div>
      {(agent.dev_roles?.length || agent.dev_role) && (
        <div className="flex flex-wrap gap-1 mb-2">
          {agent.dev_roles?.slice(0, 2).map((role, idx) => (
            <span key={role} style={{ fontSize: 10, fontWeight: 500, padding: '1px 5px', borderRadius: 9999, background: 'rgba(168,85,247,0.1)', color: 'var(--purple)' }}>
              {agent.dev_role_labels?.[idx] ?? role}
            </span>
          ))}
          {!agent.dev_roles?.length && agent.dev_role && (
            <span style={{ fontSize: 10, fontWeight: 500, padding: '1px 5px', borderRadius: 9999, background: 'rgba(168,85,247,0.1)', color: 'var(--purple)' }}>
              {agent.dev_role_label ?? agent.dev_role}
            </span>
          )}
        </div>
      )}
      <div className="flex items-center gap-3 mb-2" style={{ fontSize: 11, color: 'var(--text-3)' }}>
        <span>{agent.active_task_count} tasks</span>
        <span>{agent.message_count} msgs</span>
      </div>
      {ctx && ctx.percent != null && (
        <div className="w-full rounded-full overflow-hidden" style={{ height: 3, background: 'var(--surface-3)' }}>
          <div className="h-full rounded-full" style={{ width: `${Math.min(100, Math.max(0, ctx.percent))}%`, background: ctxColor }} />
        </div>
      )}
      {agent.last_seen && (
        <p className="mt-1" style={{ fontSize: 11, color: 'var(--text-3)' }}>
          {formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true })}
        </p>
      )}
    </button>
  )
}

export function AgentsPage() {
  const { data: agents = [], isLoading } = useAgents()
  const { data: questions = [] } = useQuestions(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [filter, setFilter] = useState<AgentFilter>('all')
  const [gridView, setGridView] = useState(false)

  const selectedAgent = agents.find((a) => a.name === selected) ?? null
  const unanswered = questions.length

  const filteredAgents = agents.filter((a) => {
    if (filter === 'all') return true
    if (filter === 'active') return a.status === 'running' || a.status === 'active'
    return a.status === 'idle' || a.status === 'waiting'
  })

  const activeCount = agents.filter((a) => a.status === 'running' || a.status === 'active').length
  const idleCount = agents.filter((a) => a.status === 'idle' || a.status === 'waiting').length

  if (isLoading) {
    return <div className="p-6" style={{ color: 'var(--text-3)' }}>Loading agents…</div>
  }

  if (agents.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState
          icon="smart_toy"
          title="No agents connected"
          description="Run 'agentweave init' in your project, then 'agentweave start' to connect agents."
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div
        className="shrink-0 flex items-center justify-between px-4 py-3"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div>
          <h1 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>Agents</h1>
          <p className="text-xs" style={{ color: 'var(--text-3)' }}>
            {agents.length} agents · {activeCount} active
          </p>
        </div>
        <button
          onClick={() => setGridView(!gridView)}
          className="text-xs font-medium px-3 py-1.5 rounded transition-opacity"
          style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--text-2)' }}
        >
          {gridView ? 'Detail view' : 'Grid view'}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex shrink-0 px-4" style={{ borderBottom: '1px solid var(--border)' }}>
        {([
          { key: 'all' as AgentFilter, label: 'All agents' },
          { key: 'active' as AgentFilter, label: `Active (${activeCount})` },
          { key: 'idle' as AgentFilter, label: `Idle (${idleCount})` },
        ]).map((t) => (
          <button
            key={t.key}
            onClick={() => setFilter(t.key)}
            className="px-4 py-2 text-xs font-medium transition-colors"
            style={{
              color: filter === t.key ? 'var(--text)' : 'var(--text-3)',
              borderBottom: filter === t.key ? '1px solid var(--text)' : '1px solid transparent',
              marginBottom: -1,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel */}
        <div
          className="w-60 overflow-auto shrink-0"
          style={{ background: 'var(--surface)', borderRight: '1px solid var(--border)' }}
        >
          <div className="p-2">
            {/* Question interrupt */}
            {unanswered > 0 && (
              <QuestionInterruptCard
                questions={questions}
                compact
                onNavigateToQuestions={() => { /* handled by parent */ }}
              />
            )}

            {/* Agent list */}
            <div className="space-y-1">
              {filteredAgents.map((agent) => (
                <AgentCard
                  key={agent.name}
                  agent={agent}
                  selected={selected === agent.name}
                  onClick={() => {
                    setSelected(agent.name)
                    setGridView(false)
                  }}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Right panel */}
        <div className="flex-1 overflow-hidden" style={{ background: 'var(--bg)' }}>
          {gridView ? (
            <div
              className="h-full overflow-auto p-4"
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: 8,
                alignContent: 'start',
              }}
            >
              {filteredAgents.map((agent) => (
                <GridCard
                  key={agent.name}
                  agent={agent}
                  onClick={() => {
                    setSelected(agent.name)
                    setGridView(false)
                  }}
                />
              ))}
            </div>
          ) : selectedAgent ? (
            <AgentDetailPanel agent={selectedAgent} />
          ) : (
            <div className="flex h-full items-center justify-center" style={{ color: 'var(--text-3)' }}>
              Select an agent to view details.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
