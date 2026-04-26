import { Icon } from '@/components/common/Icon'
import { useStatus } from '@/api/status'
import { useAgents } from '@/api/agents'
import { useConfigStore } from '@/store/configStore'

interface StatusBarProps {
  onOpenSetup: () => void
}

export function StatusBar({ onOpenSetup }: StatusBarProps) {
  const { data } = useStatus()
  const { data: agents = [] } = useAgents()
  const { mode, setMode } = useConfigStore()

  const contextWarningCount = agents.filter(
    (a) => a.context_usage?.warning || a.context_usage?.critical
  ).length

  const pendingMsgs = data?.message_counts?.pending ?? 0
  const activeTasks = data ? Object.values(data.task_counts).reduce((a, b) => a + b, 0) : 0
  const unanswered  = data?.question_counts?.unanswered ?? 0
  const agentCount  = data?.agents_active?.length ?? 0

  function toggleMode() {
    const next = mode === 'light' ? 'dark' : 'light'
    setMode(next)
    document.documentElement.dataset.mode = next
  }

  const chipBase = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    background: 'var(--surface-2)',
    border: '1px solid var(--border)',
    borderRadius: '4px',
    fontSize: '12px',
    padding: '3px 10px',
    color: 'var(--text-2)',
  } as React.CSSProperties

  return (
    <div
      className="flex items-center gap-3 px-4 shrink-0"
      style={{ height: 44, background: 'var(--bg)', borderBottom: '1px solid var(--border)' }}
    >
      {/* Logo / title */}
      <button
        onClick={onOpenSetup}
        className="shrink-0 transition-opacity hover:opacity-80"
        style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}
      >
        AgentWeave
      </button>

      <div className="h-5 w-px shrink-0" style={{ background: 'var(--border)' }} />

      {/* Status chips */}
      <div className="flex items-center gap-2 flex-1 flex-wrap">
        {/* Messages */}
        <div style={chipBase}>
          <Icon name="chat" size={14} />
          <span style={{ color: 'var(--text)', fontWeight: 500 }}>{pendingMsgs}</span>
          <span>msgs</span>
        </div>

        {/* Tasks */}
        <div style={chipBase}>
          <Icon name="task_alt" size={14} />
          <span style={{ color: 'var(--text)', fontWeight: 500 }}>{activeTasks}</span>
          <span>tasks</span>
        </div>

        {/* Questions */}
        <div
          style={{
            ...chipBase,
            background: unanswered > 0 ? 'rgba(245,158,11,0.06)' : 'var(--surface-2)',
            borderColor: unanswered > 0 ? 'rgba(245,158,11,0.3)' : 'var(--border)',
            color: unanswered > 0 ? 'var(--amber)' : 'var(--text-2)',
          }}
        >
          <Icon name="help" size={14} />
          <span style={{ fontWeight: 500 }}>{unanswered}</span>
          <span>question{unanswered !== 1 ? 's' : ''}{unanswered > 0 ? '!' : ''}</span>
        </div>

        {/* Agents */}
        <div style={chipBase}>
          <Icon name="smart_toy" size={14} />
          <span style={{ color: 'var(--text)', fontWeight: 500 }}>{agentCount}</span>
          <span>agent{agentCount !== 1 ? 's' : ''}</span>
        </div>

        {/* Context warning chip */}
        {contextWarningCount > 0 && (
          <div
            style={{
              ...chipBase,
              background: 'rgba(239,68,68,0.08)',
              borderColor: 'rgba(239,68,68,0.25)',
              color: 'var(--red)',
            }}
            title="One or more agents need context management"
          >
            <Icon name="memory" size={14} />
            <span style={{ fontWeight: 500 }}>{contextWarningCount}</span>
            <span>ctx!</span>
          </div>
        )}

        {data?.project_name && (
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
            {data.project_name}
          </span>
        )}
      </div>

      {/* Mode toggle icon button */}
      <button
        onClick={toggleMode}
        className="shrink-0 flex items-center justify-center rounded transition-colors hover:bg-white/5"
        style={{ width: 32, height: 32, color: 'var(--text-2)' }}
        title={mode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
      >
        <Icon name={mode === 'light' ? 'dark_mode' : 'light_mode'} size={18} />
      </button>
    </div>
  )
}
