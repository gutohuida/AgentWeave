import { useState } from 'react'
import { useAgents, useAgentOutput } from '@/api/agents'
import { useAgentConfig } from '@/hooks/useAgentConfig'

import { AgentTimeline } from './AgentTimeline'
import { AgentOutputPanel } from './AgentOutputPanel'
import { AgentMessageSender } from './AgentMessageSender'
import { AgentSidebar } from './AgentSidebar'

import { EmptyState } from '@/components/common/EmptyState'

type ActiveTab = 'output' | 'timeline' | 'send'

export function AgentsPage() {
  const { data: hubAgents = [], isLoading: isLoadingHubAgents } = useAgents()
  const {
    agents: configAgents,
    isLoading: isLoadingConfigs,
  } = useAgentConfig()
  const [selected, setSelected] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<ActiveTab>('output')

  // Merge Hub agents with config agents
  const mergedAgents = hubAgents.map((hubAgent) => {
    const config = configAgents.find((c) => c.agent === hubAgent.name)
    return {
      ...hubAgent,
      role: config?.role || 'delegate',
      yolo_enabled: config?.yolo_enabled || false,
      context_file: config?.context_file || 'AGENTS.md',
      source: config?.source || 'default',
      updated_at: config?.updated_at,
    }
  })

  // Also add config agents that don't have Hub activity yet
  const hubAgentNames = new Set(hubAgents.map((a) => a.name))
  configAgents.forEach((config) => {
    if (!hubAgentNames.has(config.agent)) {
      mergedAgents.push({
        name: config.agent,
        status: 'idle',
        latest_status_msg: undefined,
        last_seen: undefined,
        message_count: 0,
        active_task_count: 0,
        role: config.role,
        yolo_enabled: config.yolo_enabled,
        context_file: config.context_file,
        source: config.source,
        updated_at: config.updated_at,
      })
    }
  })

  const { lines } = useAgentOutput(selected)

  if (isLoadingHubAgents || isLoadingConfigs) {
    return (
      <div className="p-6 m3-body-medium" style={{ color: 'var(--on-sv)' }}>
        Loading agents…
      </div>
    )
  }

  return (
    <>
      <div className="flex h-full overflow-hidden">
        {/* Left sidebar — agent list */}
        <div
          className="w-72 shrink-0 border-r"
          style={{
            background: 'var(--surface-low)',
            borderColor: 'var(--outline-variant)',
          }}
        >
          <AgentSidebar
            agents={configAgents}
            selectedAgent={selected}
            onSelectAgent={(agent) => {
              setSelected(agent)
              setActiveTab('output')
            }}
            isLoading={isLoadingConfigs}
          />
        </div>

        {/* Right panel */}
        <div
          className="flex-1 flex flex-col overflow-hidden"
          style={{ background: 'var(--background)' }}
        >
          {selected ? (
            <>
              {/* Tab bar */}
              <div
                className="flex shrink-0 border-b"
                style={{
                  background: 'var(--surface-high)',
                  borderColor: 'var(--outline-variant)',
                }}
              >
                {(['output', 'timeline', 'send'] as ActiveTab[]).map(
                  (tab) => (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className="px-5 py-3 m3-label-large capitalize transition-colors relative"
                      style={{
                        color:
                          activeTab === tab ? 'var(--primary)' : 'var(--on-sv)',
                      }}
                    >
                      {tab === 'send' ? 'Send Message' : tab}
                      {activeTab === tab && (
                        <span
                          className="absolute bottom-0 left-0 right-0 h-0.5"
                          style={{ background: 'var(--primary)' }}
                        />
                      )}
                    </button>
                  )
                )}
              </div>
              <div className="flex-1 overflow-hidden">
                {activeTab === 'output' ? (
                  <AgentOutputPanel
                    agent={
                      mergedAgents.find((a) => a.name === selected)!
                    }
                  />
                ) : activeTab === 'timeline' ? (
                  <AgentTimeline
                    agent={
                      mergedAgents.find((a) => a.name === selected)!
                    }
                  />
                ) : (
                  <AgentMessageSender
                    agent={selected}
                    existingSessionId={
                      lines.find((l) => l.session_id)?.session_id
                    }
                  />
                )}
              </div>
            </>
          ) : (
            <div
              className="flex h-full items-center justify-center m3-body-medium"
              style={{ color: 'var(--on-sv)' }}
            >
              <EmptyState
                icon="smart_toy"
                title="Select an agent"
                description="Choose an agent from the sidebar to view their output, timeline, or configuration."
              />
            </div>
          )}
        </div>
      </div>

    </>
  )
}
