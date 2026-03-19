import { useState } from 'react'
import { useAgents, useAgentOutput } from '@/api/agents'
import { AgentCard } from './AgentCard'
import { AgentTimeline } from './AgentTimeline'
import { AgentOutputPanel } from './AgentOutputPanel'
import { AgentMessageSender } from './AgentMessageSender'
import { AgentConfigurator } from './AgentConfigurator'
import { EmptyState } from '@/components/common/EmptyState'

type ActiveTab = 'output' | 'timeline' | 'send' | 'config'

export function AgentsPage() {
  const { data: agents = [], isLoading } = useAgents()
  const [selected, setSelected] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<ActiveTab>('output')
  const selectedAgent = agents.find((a) => a.name === selected) ?? null
  const { lines } = useAgentOutput(selected)

  if (isLoading) {
    return <div className="p-6 m3-body-medium" style={{ color: 'var(--on-sv)' }}>Loading agents…</div>
  }

  // No agents configured - show configurator
  if (agents.length === 0) {
    return (
      <div className="flex h-full overflow-hidden">
        <div className="w-80 border-r overflow-auto" style={{ background: 'var(--surface-low)', borderColor: 'var(--outline-variant)' }}>
          <div className="p-4 border-b" style={{ borderColor: 'var(--outline-variant)' }}>
            <h2 className="m3-title-large" style={{ color: 'var(--on-sv)' }}>Configure Agents</h2>
          </div>
          <AgentConfigurator />
        </div>
        <div className="flex-1 flex items-center justify-center">
          <EmptyState
            icon="smart_toy"
            title="No agents configured"
            description="Select agents on the left, then click 'Set Up Agents' to get started. Or run 'agentweave init' in your project."
          />
        </div>
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
        {/* Always-visible Add Agent button */}
        <button
          onClick={() => {
            setSelected(null)
            setActiveTab('config')
          }}
          className="w-full p-3 rounded-lg flex items-center justify-center gap-2 transition-colors m3-label-large"
          style={{ 
            background: 'var(--surface-high)',
            color: 'var(--on-sv)',
            border: '2px dashed var(--outline-variant)'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'var(--surface-highest)'
            e.currentTarget.style.borderColor = 'var(--primary)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'var(--surface-high)'
            e.currentTarget.style.borderColor = 'var(--outline-variant)'
          }}
        >
          <span className="material-symbols-rounded">add</span>
          Add Agent
        </button>
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
              {(['output', 'timeline', 'send', 'config'] as ActiveTab[]).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className="px-5 py-3 m3-label-large capitalize transition-colors relative"
                  style={{
                    color: activeTab === tab ? 'var(--primary)' : 'var(--on-sv)',
                  }}
                >
                  {tab === 'send' ? 'Send Message' : tab === 'config' ? 'Configure' : tab}
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
              {activeTab === 'output' ? (
                <AgentOutputPanel agent={selectedAgent} />
              ) : activeTab === 'timeline' ? (
                <AgentTimeline agent={selectedAgent} />
              ) : activeTab === 'send' ? (
                <AgentMessageSender 
                  agent={selectedAgent.name} 
                  existingSessionId={lines.find(l => l.session_id)?.session_id}
                />
              ) : (
                <AgentConfigurator />
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
