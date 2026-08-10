import { useConfigStore } from '@/store/configStore'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function fetchWithAuth(path: string, options: RequestInit = {}): Promise<Response> {
  const { apiKey, hubUrl } = useConfigStore.getState()
  const url = `${hubUrl}${path}`
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
      ...options.headers,
    },
  })
  if (res.status === 401) {
    console.warn('[AgentWeave] 401 Unauthorized — check API key in .env or Settings')
  }
  if (!res.ok) {
    const text = await res.text()
    throw new ApiError(res.status, text)
  }
  return res
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetchWithAuth(path)
  return res.json() as Promise<T>
}

export async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetchWithAuth(path, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
  return res.json() as Promise<T>
}

export async function postJson<T>(path: string, body: unknown = {}): Promise<T> {
  const res = await fetchWithAuth(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return res.json() as Promise<T>
}

/** DELETE with no body. Used where the thing being removed is a relationship, not a row. */
export async function deleteJson<T>(path: string): Promise<T> {
  const res = await fetchWithAuth(path, { method: 'DELETE' })
  return res.json() as Promise<T>
}

export async function putJson<T>(path: string, body: unknown = {}): Promise<T> {
  const res = await fetchWithAuth(path, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return res.json() as Promise<T>
}

/**
 * Reduce a FastAPI error body to a sentence a person can act on.
 *
 * A Pydantic failure arrives as a list of error objects, and `ApiError.message` is the raw
 * response text — so a refused setting rendered in the UI as
 * `[{"type":"value_error","loc":["body"],"msg":"Value error, A threshold of 200,000 tokens ..."}]`.
 * The useful sentence was in there; everything around it was noise.
 */
export function readableApiError(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback
  let parsed: unknown
  try {
    parsed = JSON.parse(error.message)
  } catch {
    return error.message || fallback
  }
  const detail = (parsed as { detail?: unknown })?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        const entry = item as { msg?: string; loc?: unknown[] }
        // Pydantic prefixes every custom validator message with "Value error, ".
        const message = String(entry?.msg ?? '').replace(/^Value error,\s*/, '').trim()
        if (!message) return ''
        const field = Array.isArray(entry?.loc)
          ? entry.loc.filter((part) => part !== 'body').join('.')
          : ''
        // A message that already reads as a sentence does not need its field name bolted on.
        return field && !/[A-Z]/.test(message.charAt(0)) ? `${field}: ${message}` : message
      })
      .filter(Boolean)
    if (messages.length) return messages.join('; ')
  }
  return fallback
}
