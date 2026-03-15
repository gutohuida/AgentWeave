import { useState } from 'react'
import { Bot } from 'lucide-react'
import { useAgents } from '@/api/agents'
import { AgentCard } from './AgentCard'
import { AgentTimeline } from './AgentTimeline'
import { AgentOutputPanel } from './AgentOutputPanel'
import { EmptyState } from '@/components/common/EmptyState'
import { cn } from '@/lib/utils'

type ActiveTab = 'output' | 'timeline'

export function AgentsPage() {
  const { data: agents = [], isLoading } = useAgents()
  const [selected, setSelected] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<ActiveTab>('output')
  const selectedAgent = agents.find((a) => a.name === selected) ?? null

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading agents…</div>
  }

  if (agents.length === 0) {
    return (
      <EmptyState
        icon={Bot}
        title="No agents detected"
        description="Agents appear here once they send messages or are assigned tasks in the last 24 hours."
      />
    )
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left panel — agent list */}
      <div className="w-1/3 border-r overflow-auto p-3 space-y-1">
        {agents.map((agent) => (
          <AgentCard
            key={agent.name}
            agent={agent}
            selected={selected === agent.name}
            onClick={() => setSelected(agent.name)}
          />
        ))}
      </div>

      {/* Right panel — tabbed view */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {selectedAgent ? (
          <>
            {/* Tab bar */}
            <div className="flex border-b shrink-0">
              {(['output', 'timeline'] as ActiveTab[]).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={cn(
                    'px-4 py-2 text-sm font-medium capitalize transition-colors',
                    activeTab === tab
                      ? 'border-b-2 border-primary text-primary'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-hidden">
              {activeTab === 'output' ? (
                <AgentOutputPanel agent={selectedAgent} />
              ) : (
                <AgentTimeline agent={selectedAgent} />
              )}
            </div>
          </>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Select an agent to view their output.
          </div>
        )}
      </div>
    </div>
  )
}
