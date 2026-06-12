export interface SetupConfig {
  apiKey: string
  projectId: string
}

export async function fetchSetupToken(): Promise<SetupConfig | null> {
  try {
    const resp = await fetch('/api/v1/setup/token', { credentials: 'same-origin' })
    if (!resp.ok) return null
    const data = await resp.json()
    return { apiKey: data.api_key, projectId: data.project_id ?? 'proj-default' }
  } catch {
    return null
  }
}
