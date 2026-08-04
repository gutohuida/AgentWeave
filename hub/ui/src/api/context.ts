import { postJson } from './client'

export async function requestCompact(projectId: string, agentName: string): Promise<void> {
  await postJson(`/api/v1/projects/${projectId}/agents/${agentName}/compact`)
}

export async function requestNewSession(projectId: string, agentName: string): Promise<void> {
  await postJson(`/api/v1/projects/${projectId}/agents/${agentName}/new-session`)
}
