import { useCallback, useEffect, useState } from 'react'
import {
  fetchAgentConfigs,
  updateAgentConfig,
  deleteAgent,
  addAgent,
  type AgentConfig,
  type UpdateAgentConfigRequest,
} from '@/api/agentConfig'

interface UseAgentConfigReturn {
  agents: AgentConfig[]
  isLoading: boolean
  error: string | null
  refresh: () => Promise<void>
  updateAgent: (agentName: string, config: UpdateAgentConfigRequest) => Promise<void>
  removeAgent: (agentName: string) => Promise<void>
  addNewAgent: (agentName: string, role: string, yoloEnabled: boolean) => Promise<void>
}

export function useAgentConfig(): UseAgentConfigReturn {
  const [agents, setAgents] = useState<AgentConfig[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const configs = await fetchAgentConfigs()
      setAgents(configs)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch agent configs')
    } finally {
      setIsLoading(false)
    }
  }, [])

  const updateAgent = useCallback(
    async (agentName: string, config: UpdateAgentConfigRequest) => {
      await updateAgentConfig(agentName, config)
      // Optimistically update local state
      setAgents((prev) =>
        prev.map((agent) =>
          agent.agent === agentName
            ? {
                ...agent,
                role: config.role || agent.role,
                yolo_enabled: config.yolo_enabled !== undefined ? config.yolo_enabled : agent.yolo_enabled,
                settings: config.settings || agent.settings,
                source: 'hub',
              }
            : agent
        )
      )
    },
    []
  )

  const removeAgent = useCallback(async (agentName: string) => {
    await deleteAgent(agentName)
    // Optimistically remove from local state
    setAgents((prev) => prev.filter((agent) => agent.agent !== agentName))
  }, [])

  const addNewAgent = useCallback(
    async (agentName: string, role: string, yoloEnabled: boolean) => {
      // First add the agent to the configured list
      await addAgent(agentName)
      // Then update its config
      await updateAgentConfig(agentName, { role: role as 'principal' | 'delegate' | 'reviewer', yolo_enabled: yoloEnabled })
      // Refresh to get the full config
      await refresh()
    },
    [refresh]
  )

  useEffect(() => {
    refresh()
  }, [refresh])

  return {
    agents,
    isLoading,
    error,
    refresh,
    updateAgent,
    removeAgent,
    addNewAgent,
  }
}
