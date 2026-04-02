import { useState } from 'react'
import { useAgents } from '@/api/agents'
import { AgentCard } from './AgentCard'
import { AgentPromptPanel } from './AgentPromptPanel'
import { AgentActivityTab } from './AgentActivityTab'
import { AgentInfoTab } from './AgentInfoTab'
import { EmptyState } from '@/components/common/EmptyState'

type ActiveTab = 'chat' | 'activity' | 'info'

export function AgentsPage() {
  const { data: agents = [], isLoading } = useAgents()
  const [selected, setSelected] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<ActiveTab>('chat')
  const selectedAgent = agents.find((a) => a.name === selected) ?? null

  if (isLoading) {
    return <div className="p-6 m3-body-medium" style={{ color: 'var(--on-sv)' }}>Loading agents…</div>
  }

  // No agents connected yet
  if (agents.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState
          icon="smart_toy"
          title="No agents connected"
          description="Run 'agentweave init' in your project, then 'agentweave start' to connect agents. They will appear here automatically."
        />
      </div>
    )
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left panel — agent list */}
      <div
        className="w-72 overflow-auto p-3 space-y-1.5 shrink-0 border-r"
        style={{ background: 'var(--surface-low)', borderColor: 'var(--outline-variant)' }}
      >
        {agents.map((agent) => (
          <AgentCard
            key={agent.name}
            agent={agent}
            selected={selected === agent.name}
            onClick={() => setSelected(agent.name)}
          />
        ))}
      </div>

      {/* Right panel */}
      <div className="flex-1 flex flex-col overflow-hidden" style={{ background: 'var(--background)' }}>
        {selectedAgent ? (
          <>
            {/* Tab bar */}
            <div
              className="flex shrink-0 border-b"
              style={{ background: 'var(--surface-high)', borderColor: 'var(--outline-variant)' }}
            >
              {(['chat', 'activity', 'info'] as ActiveTab[]).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className="px-5 py-3 m3-label-large capitalize transition-colors relative"
                  style={{
                    color: activeTab === tab ? 'var(--primary)' : 'var(--on-sv)',
                  }}
                >
                  {tab}
                  {activeTab === tab && (
                    <span
                      className="absolute bottom-0 left-0 right-0 h-0.5"
                      style={{ background: 'var(--primary)' }}
                    />
                  )}
                </button>
              ))}
            </div>
            <div className="flex-1 overflow-hidden">
              {activeTab === 'chat' ? (
                <AgentPromptPanel key={selectedAgent.name} agent={selectedAgent} />
              ) : activeTab === 'activity' ? (
                <AgentActivityTab key={selectedAgent.name} agent={selectedAgent} />
              ) : (
                <AgentInfoTab key={selectedAgent.name} agent={selectedAgent} />
              )}
            </div>
          </>
        ) : (
          <div className="flex h-full items-center justify-center m3-body-medium" style={{ color: 'var(--on-sv)' }}>
            Select an agent to view their output.
          </div>
        )}
      </div>
    </div>
  )
}
