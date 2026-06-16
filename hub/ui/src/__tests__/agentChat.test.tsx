import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'
import { useAgentChatHistory } from '@/api/agentChat'
import { NEW_SESSION_ID } from '@/lib/constants'

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

describe('M20 — useAgentChatHistory gates on NEW_SESSION_ID, not the literal "new"', () => {
  beforeEach(() => {
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      projectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('the shared constant matches the sentinel the dashboard uses', () => {
    expect(NEW_SESSION_ID).toBe('__new__')
  })

  it('disables the query when sessionId === NEW_SESSION_ID (not just any non-empty value)', async () => {
    // First, with sessionId = a real-looking id, the query is enabled.
    const enabled = renderHook(
      () => useAgentChatHistory('claude', 'ses_real_123'),
      { wrapper: makeWrapper() }
    )
    await new Promise((r) => setTimeout(r, 10))
    expect(enabled.result.current.fetchStatus).toBe('fetching')
    enabled.unmount()

    // Then with sessionId = NEW_SESSION_ID, the query is disabled.
    const disabled = renderHook(
      () => useAgentChatHistory('claude', NEW_SESSION_ID),
      { wrapper: makeWrapper() }
    )
    await new Promise((r) => setTimeout(r, 10))
    expect(disabled.result.current.fetchStatus).toBe('idle')
    expect(disabled.result.current.isLoading).toBe(false)
    expect(disabled.result.current.data).toBeUndefined()
  })
})
