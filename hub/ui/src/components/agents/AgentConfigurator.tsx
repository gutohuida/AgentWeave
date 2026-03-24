import { useState, useEffect } from 'react'
import { useConfigStore } from '@/store/configStore'
import { Icon } from '@/components/common/Icon'

const COMMON_AGENTS = [
  { name: 'claude', label: 'Claude', description: 'Anthropic Claude Code' },
  { name: 'kimi', label: 'Kimi', description: 'Moonshot AI Kimi Code' },
  { name: 'gemini', label: 'Gemini', description: 'Google Gemini CLI' },
  { name: 'codex', label: 'Codex', description: 'OpenAI Codex CLI' },
  { name: 'gpt', label: 'GPT', description: 'Generic GPT agent' },
]

interface ConfiguredAgents {
  source: 'session.json' | 'manual'
  agents: string[]
  can_modify: boolean
}

export function AgentConfigurator() {
  const { apiKey } = useConfigStore()
  const [configured, setConfigured] = useState<ConfiguredAgents | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [selectedAgents, setSelectedAgents] = useState<Set<string>>(new Set())
  const [customAgentName, setCustomAgentName] = useState('')
  const [isApplying, setIsApplying] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)

  useEffect(() => {
    fetchConfiguredAgents()
  }, [apiKey])

  const fetchConfiguredAgents = async () => {
    if (!apiKey) return

    setIsLoading(true)
    try {
      const response = await fetch('/api/v1/agents/configured', {
        headers: { 'Authorization': `Bearer ${apiKey}` }
      })

      if (response.ok) {
        const data = await response.json()
        setConfigured(data)
        // Initialize selected agents from server state
        setSelectedAgents(new Set(data.agents))
        setHasChanges(false)
      }
    } catch (err) {
      console.error('Failed to fetch configured agents:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const toggleAgent = (agentName: string) => {
    setSelectedAgents(prev => {
      const next = new Set(prev)
      if (next.has(agentName)) {
        next.delete(agentName)
      } else {
        next.add(agentName)
      }
      return next
    })
    setHasChanges(true)
  }

  const addCustomAgent = () => {
    const name = customAgentName.trim().toLowerCase()
    if (!name) return

    setSelectedAgents(prev => new Set([...prev, name]))
    setCustomAgentName('')
    setHasChanges(true)
  }

  const removeSelectedAgent = (agentName: string) => {
    setSelectedAgents(prev => {
      const next = new Set(prev)
      next.delete(agentName)
      return next
    })
    setHasChanges(true)
  }

  const applyChanges = async () => {
    if (!apiKey || !configured) return

    setIsApplying(true)
    try {
      const currentAgents = new Set(configured.agents)
      const newAgents = selectedAgents

      // Calculate differences
      const toAdd = [...newAgents].filter(a => !currentAgents.has(a))
      const toRemove = [...currentAgents].filter(a => !newAgents.has(a))

      // Add new agents
      const addPromises = toAdd.map(agentName =>
        fetch('/api/v1/agents/configure', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${apiKey}`
          },
          body: JSON.stringify({ agent_name: agentName })
        })
      )

      // Remove agents no longer selected
      const removePromises = toRemove.map(agentName =>
        fetch(`/api/v1/agents/configure/${agentName}`, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${apiKey}` }
        })
      )

      await Promise.all([...addPromises, ...removePromises])

      // Refresh the configured agents list
      await fetchConfiguredAgents()
    } catch (err) {
      console.error('Failed to apply agent configuration:', err)
    } finally {
      setIsApplying(false)
    }
  }

  const discardChanges = () => {
    if (configured) {
      setSelectedAgents(new Set(configured.agents))
    }
    setCustomAgentName('')
    setHasChanges(false)
  }

  if (isLoading) {
    return (
      <div className="p-6 text-center" style={{ color: 'var(--on-sv)' }}>
        Loading agents...
      </div>
    )
  }

  // If using session.json, just show info
  if (configured?.source === 'session.json') {
    return (
      <div className="p-4 m3-body-medium" style={{ color: 'var(--on-sv)' }}>
        <p className="mb-2">
          <span className="m3-label-medium">Configured from:</span> session.json
        </p>
        <p className="opacity-70">
          Agents are loaded from your .agentweave/session.json file.
          Run <code>agentweave init</code> to change the configured agents.
        </p>
      </div>
    )
  }

  // Manual configuration mode
  const selectedCount = selectedAgents.size

  return (
    <div className="p-4 space-y-4">
      {/* Header with selection count */}
      <div className="flex items-center justify-between">
        <h3 className="m3-label-large" style={{ color: 'var(--on-sv)' }}>
          Select Agents
        </h3>
        <span
          className="px-2 py-1 rounded-full m3-label-small"
          style={{
            background: selectedCount > 0 ? 'var(--p-cont)' : 'var(--surface-high)',
            color: selectedCount > 0 ? 'var(--on-p-cont)' : 'var(--on-sv)'
          }}
        >
          {selectedCount} selected
        </span>
      </div>

      {/* Quick Select Common Agents */}
      <div className="grid grid-cols-1 gap-2">
        {COMMON_AGENTS.map((agent) => {
          const isSelected = selectedAgents.has(agent.name)
          return (
            <button
              key={agent.name}
              onClick={() => toggleAgent(agent.name)}
              className="p-3 rounded-lg text-left transition-all border-2"
              style={{
                background: isSelected ? 'var(--p-cont)' : 'var(--surface-high)',
                borderColor: isSelected ? 'var(--primary)' : 'transparent',
              }}
            >
              <div className="flex items-center justify-between">
                <div>
                  <span className="m3-label-large" style={{ color: 'var(--on-sv)' }}>
                    {agent.label}
                  </span>
                  <p className="m3-body-small opacity-70" style={{ color: 'var(--on-sv)' }}>
                    {agent.description}
                  </p>
                </div>
                <span
                  className="material-symbols-rounded"
                  style={{ color: isSelected ? 'var(--primary)' : 'var(--on-sv)' }}
                >
                  {isSelected ? 'check_circle' : 'radio_button_unchecked'}
                </span>
              </div>
            </button>
          )
        })}
      </div>

      {/* Custom Agent Input */}
      <div>
        <h3 className="m3-label-large mb-3" style={{ color: 'var(--on-sv)' }}>
          Add Custom Agent
        </h3>
        <div className="flex gap-2">
          <input
            type="text"
            value={customAgentName}
            onChange={(e) => setCustomAgentName(e.target.value)}
            placeholder="Agent name (e.g., 'my-agent')"
            className="flex-1 px-3 py-2 rounded-lg bg-surface-high border m3-body-medium"
            style={{
              background: 'var(--surface-high)',
              borderColor: 'var(--outline-variant)',
              color: 'var(--on-sv)'
            }}
            onKeyDown={(e) => e.key === 'Enter' && addCustomAgent()}
          />
          <button
            onClick={addCustomAgent}
            disabled={!customAgentName.trim()}
            className="m3-icon-btn"
            title="Add agent"
          >
            <Icon name="add" size={20} />
          </button>
        </div>
      </div>

      {/* Selected Agents Preview */}
      {selectedCount > 0 && (
        <div>
          <h3 className="m3-label-large mb-3" style={{ color: 'var(--on-sv)' }}>
            Selected Agents ({selectedCount})
          </h3>
          <div className="flex flex-wrap gap-2">
            {[...selectedAgents].map((agent) => (
              <span
                key={agent}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full m3-label-medium"
                style={{ background: 'var(--p-cont)', color: 'var(--on-p-cont)' }}
              >
                {agent}
                <button
                  onClick={() => removeSelectedAgent(agent)}
                  className="material-symbols-rounded text-sm hover:text-error transition-colors"
                  title="Remove agent"
                >
                  close
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Action Buttons */}
      {hasChanges && (
        <div
          className="sticky bottom-0 p-4 -mx-4 -mb-4 space-y-2"
          style={{
            background: 'var(--surface)',
            borderTop: '1px solid var(--outline-variant)'
          }}
        >
          <button
            onClick={applyChanges}
            disabled={isApplying || selectedCount === 0}
            className="m3-btn-filled w-full"
          >
            {isApplying ? (
              <>
                <Icon name="progress_activity" size={20} className="animate-spin" />
                Setting up agents...
              </>
            ) : (
              <>
                <Icon name="check" size={20} />
                Set Up {selectedCount} Agent{selectedCount !== 1 ? 's' : ''}
              </>
            )}
          </button>

          <button
            onClick={discardChanges}
            disabled={isApplying}
            className="m3-btn-text w-full"
          >
            Discard Changes
          </button>
        </div>
      )}

      {/* Tip */}
      <div
        className="p-3 rounded-lg text-xs"
        style={{ background: 'var(--surface-high)', color: 'var(--on-sv)' }}
      >
        <p className="opacity-80">
          <strong>Tip:</strong> To persist these agents across Hub restarts,
          create a session file with <code>agentweave init --agents agent1,agent2</code> in your project.
        </p>
      </div>
    </div>
  )
}
