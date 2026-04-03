import { postJson } from './client'

export async function requestCompact(agentName: string): Promise<void> {
  await postJson(`/api/v1/agents/${agentName}/compact`)
}

export async function requestNewSession(agentName: string): Promise<void> {
  await postJson(`/api/v1/agents/${agentName}/new-session`)
}
