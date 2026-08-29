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
  // A structured refusal — the gate's, and anything else that carries machine-readable fields
  // alongside the sentence a person should read. Without this the sentence is discarded and the
  // caller shows its fallback, which is how a gate that names exactly what to do about it ends up
  // reading as "the Hub refused this change".
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string' && message.trim()) return message
  }
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

/**
 * The refusal's own sentence, or *fallback* when the response carried no refusal to read.
 *
 * One difference from `readableApiError`, and it is the whole reason this exists: a body that is
 * not a structured refusal — an empty 502, a reverse proxy's HTML error page, the bare word
 * "failed" — yields the fallback rather than being rendered at the operator. `readableApiError`'s
 * callers put their result in a small inline message beside the control that failed, where a
 * stray token is survivable. This one's callers put it in a conversation banner and the composer's
 * own error line, which is where a person is told what to do next; a page of HTML there is worse
 * than the generic sentence it replaced.
 *
 * Added for F108, where the Hub began answering a request it will never honour with the refusal's
 * own words. Reading them is the point — but only when they are words.
 */
export function readableRefusal(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback
  try {
    JSON.parse(error.message)
  } catch {
    return fallback
  }
  return readableApiError(error, fallback)
}

/**
 * The machine-readable `code` from a structured refusal, or null.
 *
 * `readableApiError` deliberately returns only the sentence, which is all most callers need. A
 * caller that offers a *remedy* needs to know which refusal it is looking at — matching on the
 * sentence would tie the UI to prose that is free to be reworded.
 */
export function apiErrorCode(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(error.message)
  } catch {
    return null
  }
  const detail = (parsed as { detail?: unknown })?.detail
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return null
  const code = (detail as { code?: unknown }).code
  return typeof code === 'string' && code ? code : null
}
