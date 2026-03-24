import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import type { AgentConfig } from '@/api/agentConfig'

interface AgentSidebarProps {
  agents: AgentConfig[]
  selectedAgent: string | null
  onSelectAgent: (agent: string) => void
  isLoading?: boolean
}

export function AgentSidebar({
  agents,
  selectedAgent,
  onSelectAgent,
  isLoading,
}: AgentSidebarProps) {
  const [searchQuery, setSearchQuery] = useState('')

  const filteredAgents = agents.filter((agent) =>
    agent.agent.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // Sort: principals first, then by name
  const sortedAgents = [...filteredAgents].sort((a, b) => {
    if (a.role === 'principal' && b.role !== 'principal') return -1
    if (a.role !== 'principal' && b.role === 'principal') return 1
    return a.agent.localeCompare(b.agent)
  })

  return (
    <div className="h-full flex flex-col" style={{ background: 'var(--surface-low)' }}>
      {/* Header */}
      <div className="p-4 border-b" style={{ borderColor: 'var(--outline-variant)' }}>
        <div className="flex items-center mb-3">
          <h2 className="m3-title-medium" style={{ color: 'var(--on-sv)' }}>
            Agents
          </h2>
        </div>

        {/* Search */}
        <div className="relative">
          <Icon
            name="search"
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 opacity-50"
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search agents..."
            className="w-full pl-10 pr-3 py-2 rounded-lg m3-body-medium"
            style={{
              background: 'var(--surface-high)',
              color: 'var(--on-sv)',
              border: '1px solid var(--outline-variant)',
            }}
          />
        </div>
      </div>

      {/* Agent List */}
      <div className="flex-1 overflow-y-auto p-2">
        {isLoading ? (
          <div className="p-4 text-center" style={{ color: 'var(--on-sv)' }}>
            <Icon name="progress_activity" size={24} className="animate-spin mb-2" />
            <p className="m3-body-small opacity-70">Loading agents...</p>
          </div>
        ) : sortedAgents.length === 0 ? (
          <div className="p-4 text-center" style={{ color: 'var(--on-sv)' }}>
            <Icon name="smart_toy" size={32} className="opacity-30 mb-2" />
            <p className="m3-body-small opacity-70">No agents configured</p>
            <p className="m3-body-small opacity-50 mt-1">Use CLI to add agents</p>
          </div>
        ) : (
          <div className="space-y-1">
            {sortedAgents.map((agent) => (
              <AgentListItem
                key={agent.agent}
                agent={agent}
                isSelected={selectedAgent === agent.agent}
                onClick={() => onSelectAgent(agent.agent)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer with count */}
      <div
        className="p-3 border-t text-center"
        style={{ borderColor: 'var(--outline-variant)' }}
      >
        <span className="m3-label-small opacity-70" style={{ color: 'var(--on-sv)' }}>
          {agents.length} agent{agents.length !== 1 ? 's' : ''}
          {agents.filter((a) => a.role === 'principal').length > 0 &&
            ` · ${agents.filter((a) => a.role === 'principal').length} principal`}
        </span>
      </div>
    </div>
  )
}

interface AgentListItemProps {
  agent: AgentConfig
  isSelected: boolean
  onClick: () => void
}

function AgentListItem({ agent, isSelected, onClick }: AgentListItemProps) {
  const roleIcons: Record<string, string> = {
    principal: 'star',
    delegate: 'person',
    reviewer: 'rate_review',
  }

  const roleColors: Record<string, string> = {
    principal: 'var(--primary)',
    delegate: 'var(--on-sv)',
    reviewer: 'var(--tertiary)',
  }

  return (
    <button
      onClick={onClick}
      className="w-full p-3 rounded-lg text-left transition-all"
      style={{
        background: isSelected ? 'var(--p-cont)' : 'transparent',
        borderLeft: isSelected ? '3px solid var(--primary)' : '3px solid transparent',
      }}
      onMouseEnter={(e) => {
        if (!isSelected)
          (e.currentTarget as HTMLElement).style.background = 'var(--surface-high)'
      }}
      onMouseLeave={(e) => {
        if (!isSelected) (e.currentTarget as HTMLElement).style.background = 'transparent'
      }}
    >
      <div className="flex items-center gap-3">
        {/* Agent Icon */}
        <div
          className="w-10 h-10 rounded-full flex items-center justify-center"
          style={{
            background: isSelected ? 'var(--p-cont)' : 'var(--surface-high)',
          }}
        >
          <Icon
            name="smart_toy"
            size={20}
            style={{ color: isSelected ? 'var(--primary)' : 'var(--on-sv)' }}
          />
        </div>

        {/* Agent Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span
              className="m3-body-large font-medium truncate capitalize"
              style={{ color: 'var(--on-sv)' }}
            >
              {agent.agent}
            </span>
            {agent.yolo_enabled && (
              <span title="YOLO mode enabled" className="text-sm">
                🚀
              </span>
            )}
          </div>
          <div className="flex items-center gap-1 mt-0.5">
            <Icon
              name={roleIcons[agent.role] || 'person'}
              size={14}
              style={{ color: roleColors[agent.role] || 'var(--on-sv)' }}
            />
            <span
              className="m3-label-small capitalize"
              style={{ color: roleColors[agent.role] || 'var(--on-sv)', opacity: 0.8 }}
            >
              {agent.role}
            </span>
          </div>
        </div>

        {/* Selected indicator */}
        {isSelected && (
          <Icon name="chevron_right" size={20} style={{ color: 'var(--primary)' }} />
        )}
      </div>
    </button>
  )
}
