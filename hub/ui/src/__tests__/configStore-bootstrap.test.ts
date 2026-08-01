import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useConfigStore } from '@/store/configStore'

// Task 3.22: an unreachable Hub must not present the API-key prompt. bootstrap()
// discriminates a network failure (server not running) from a reachable Hub that
// declines to hand out a token (403/503), which is what api/setup.ts's
// SetupTokenResult exists to make possible.

const fetchMock = vi.fn()
;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = fetchMock

function resetStore() {
  useConfigStore.setState({
    apiKey: '',
    hubUrl: 'http://localhost:8000',
    projectId: 'proj-default',
    theme: 'cosmic',
    mode: 'light',
    isConfigured: false,
    bootstrapState: 'pending',
  })
}

describe('configStore.bootstrap — distinguishing unreachable from unconfigured', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    fetchMock.mockReset()
    resetStore()
  })

  it('sets bootstrapState to "unreachable" when fetch throws (Hub process not running)', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))

    await useConfigStore.getState().bootstrap()

    expect(useConfigStore.getState().bootstrapState).toBe('unreachable')
  })

  it('sets bootstrapState to "failed" when the Hub responds but declines (e.g. 403)', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 403, json: async () => ({}) })

    await useConfigStore.getState().bootstrap()

    expect(useConfigStore.getState().bootstrapState).toBe('failed')
  })

  it('sets bootstrapState to "ready" and stores the key when the Hub returns a token', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ api_key: 'aw_live_fresh', project_id: 'proj-x' }),
    })

    await useConfigStore.getState().bootstrap()

    const state = useConfigStore.getState()
    expect(state.bootstrapState).toBe('ready')
    expect(state.apiKey).toBe('aw_live_fresh')
  })
})
