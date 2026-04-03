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

  return (
    <div className="m3-top-bar flex items-center gap-3 px-4 shrink-0">
      {/* Logo / title */}
      <button
        onClick={onOpenSetup}
        className="m3-title-large shrink-0 transition-opacity hover:opacity-80"
        style={{ color: 'var(--primary)' }}
      >
        AgentWeave
      </button>

      <div className="h-5 w-px shrink-0" style={{ background: 'var(--outline-variant)' }} />

      {/* Status chips */}
      <div className="flex items-center gap-2 flex-1 flex-wrap">
        {/* Messages */}
        <div
          className="m3-chip m3-label-medium flex items-center gap-1.5"
          style={{ background: 'var(--surface-highest)', color: 'var(--on-sv)' }}
        >
          <Icon name="chat" size={14} />
          <span style={{ color: 'var(--foreground)', fontWeight: 500 }}>{pendingMsgs}</span>
          <span>msgs</span>
        </div>

        {/* Tasks */}
        <div
          className="m3-chip m3-label-medium flex items-center gap-1.5"
          style={{ background: 'var(--surface-highest)', color: 'var(--on-sv)' }}
        >
          <Icon name="task_alt" size={14} />
          <span style={{ color: 'var(--foreground)', fontWeight: 500 }}>{activeTasks}</span>
          <span>tasks</span>
        </div>

        {/* Questions */}
        <div
          className="m3-chip m3-label-medium flex items-center gap-1.5"
          style={{
            background: unanswered > 0 ? 'var(--error-cont)' : 'var(--surface-highest)',
            color:      unanswered > 0 ? 'var(--on-error-cont)' : 'var(--on-sv)',
          }}
        >
          <Icon name="help" size={14} />
          <span style={{ fontWeight: 500 }}>{unanswered}</span>
          <span>question{unanswered !== 1 ? 's' : ''}{unanswered > 0 ? '!' : ''}</span>
        </div>

        {/* Agents */}
        <div
          className="m3-chip m3-label-medium flex items-center gap-1.5"
          style={{ background: 'var(--surface-highest)', color: 'var(--on-sv)' }}
        >
          <Icon name="smart_toy" size={14} />
          <span style={{ color: 'var(--foreground)', fontWeight: 500 }}>{agentCount}</span>
          <span>agent{agentCount !== 1 ? 's' : ''}</span>
        </div>

        {/* Context warning chip */}
        {contextWarningCount > 0 && (
          <div
            className="m3-chip m3-label-medium flex items-center gap-1.5"
            style={{ background: 'var(--error-cont)', color: 'var(--on-error-cont)' }}
            title="One or more agents need context management"
          >
            <Icon name="memory" size={14} />
            <span style={{ fontWeight: 500 }}>{contextWarningCount}</span>
            <span>ctx{contextWarningCount !== 1 ? '!' : '!'}</span>
          </div>
        )}

        {data?.project_name && (
          <span className="m3-label-medium" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
            {data.project_name}
          </span>
        )}
      </div>

      {/* Mode toggle icon button */}
      <button
        onClick={toggleMode}
        className="m3-icon-btn"
        title={mode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
      >
        <Icon name={mode === 'light' ? 'dark_mode' : 'light_mode'} size={20} />
      </button>
    </div>
  )
}
