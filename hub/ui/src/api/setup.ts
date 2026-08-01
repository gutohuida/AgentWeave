export interface SetupConfig {
  apiKey: string
  projectId: string
}

export type SetupTokenResult =
  | { status: 'ok'; apiKey: string; projectId: string }
  // The Hub process could not be reached at all (connection refused, DNS
  // failure, etc.) — distinct from a reachable Hub that declines to hand
  // out a token, since the operator can't fix "server is not running" by
  // pasting an API key.
  | { status: 'unreachable' }
  // The Hub answered but declined (e.g. 403 from a non-local caller, or 503
  // with no key configured yet) — a genuinely unconfigured/remote Hub.
  | { status: 'unavailable' }

export async function fetchSetupToken(): Promise<SetupTokenResult> {
  let resp: Response
  try {
    resp = await fetch('/api/v1/setup/token', { credentials: 'same-origin' })
  } catch {
    return { status: 'unreachable' }
  }
  if (!resp.ok) return { status: 'unavailable' }
  const data = await resp.json()
  return { status: 'ok', apiKey: data.api_key, projectId: data.project_id ?? 'proj-default' }
}
