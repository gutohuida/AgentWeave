/** Agent configuration API client */

import { useConfigStore } from '@/store/configStore'

export interface AgentConfig {
  agent: string
  role: 'principal' | 'delegate' | 'reviewer'
  yolo_enabled: boolean
  context_file: string
  settings?: Record<string, unknown>
  source: 'hub' | 'session.json' | 'manual' | 'default'
  updated_at?: string
}

export interface UpdateAgentConfigRequest {
  role?: 'principal' | 'delegate' | 'reviewer'
  yolo_enabled?: boolean
  settings?: Record<string, unknown>
}

const getApiKey = () => useConfigStore.getState().apiKey

export async function fetchAgentConfigs(): Promise<AgentConfig[]> {
  const apiKey = getApiKey()
  if (!apiKey) throw new Error('No API key')

  const response = await fetch('/api/v1/agents/configs', {
    headers: { Authorization: `Bearer ${apiKey}` },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch agent configs: ${response.statusText}`)
  }

  return response.json()
}

export async function fetchAgentConfig(agentName: string): Promise<AgentConfig> {
  const apiKey = getApiKey()
  if (!apiKey) throw new Error('No API key')

  const response = await fetch(`/api/v1/agents/${agentName}/config`, {
    headers: { Authorization: `Bearer ${apiKey}` },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch agent config: ${response.statusText}`)
  }

  return response.json()
}

export async function updateAgentConfig(
  agentName: string,
  config: UpdateAgentConfigRequest
): Promise<AgentConfig> {
  const apiKey = getApiKey()
  if (!apiKey) throw new Error('No API key')

  const response = await fetch(`/api/v1/agents/${agentName}/config`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(config),
  })

  if (!response.ok) {
    throw new Error(`Failed to update agent config: ${response.statusText}`)
  }

  return response.json()
}

export async function deleteAgent(agentName: string): Promise<void> {
  const apiKey = getApiKey()
  if (!apiKey) throw new Error('No API key')

  const response = await fetch(`/api/v1/agents/${agentName}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${apiKey}` },
  })

  if (!response.ok) {
    throw new Error(`Failed to delete agent: ${response.statusText}`)
  }
}

export async function addAgent(agentName: string): Promise<void> {
  const apiKey = getApiKey()
  if (!apiKey) throw new Error('No API key')

  const response = await fetch('/api/v1/agents/configure', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ agent_name: agentName }),
  })

  if (!response.ok) {
    throw new Error(`Failed to add agent: ${response.statusText}`)
  }
}
