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
    // signal to the app to show setup modal
    window.dispatchEvent(new CustomEvent('auth-error'))
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
