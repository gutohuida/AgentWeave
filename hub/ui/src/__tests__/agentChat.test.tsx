import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'
import { useAgentChatHistory, eventTargetsAgent } from '@/api/agentChat'
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
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
      () => new Promise<Response>(() => undefined),
    )
    // First, with sessionId = a real-looking id, the query is enabled.
    const enabled = renderHook(
      () => useAgentChatHistory('claude', 'ses_real_123'),
      { wrapper: makeWrapper() }
    )
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    expect(fetchSpy.mock.calls.some(
      ([url]) => url === 'http://hub.test/api/v1/agent/claude/chat/ses_real_123',
    )).toBe(true)
    enabled.unmount()

    // Then with sessionId = NEW_SESSION_ID, the query is disabled.
    fetchSpy.mockClear()
    const disabled = renderHook(
      () => useAgentChatHistory('claude', NEW_SESSION_ID),
      { wrapper: makeWrapper() }
    )
    await new Promise((r) => setTimeout(r, 10))
    expect(fetchSpy.mock.calls.some(
      ([url]) => String(url).includes(`/api/v1/agent/claude/chat/${NEW_SESSION_ID}`),
    )).toBe(false)
    expect(disabled.result.current.fetchStatus).toBe('idle')
    expect(disabled.result.current.isLoading).toBe(false)
    expect(disabled.result.current.data).toBeUndefined()
  })
})

describe('eventTargetsAgent — chat live-update matching (previously: no SSE coverage at all, pure 3s poll)', () => {
  it('matches message_created via the "to" key (messages.py, agent_trigger.py)', () => {
    expect(eventTargetsAgent('message_created', { to: 'claude' }, 'claude')).toBe(true)
  })

  it('matches message_created via the "recipient" key (agents.py system messages)', () => {
    expect(eventTargetsAgent('message_created', { recipient: 'claude' }, 'claude')).toBe(true)
  })

  it('matches agent_output via the "agent" key', () => {
    expect(eventTargetsAgent('agent_output', { agent: 'claude' }, 'claude')).toBe(true)
  })

  it('does not match a different agent', () => {
    expect(eventTargetsAgent('agent_output', { agent: 'codex' }, 'claude')).toBe(false)
  })

  it('does not match an unrelated event type even with a matching agent field', () => {
    expect(eventTargetsAgent('task_updated', { agent: 'claude' }, 'claude')).toBe(false)
  })

  it('matches queue lifecycle events so undelivered entries update live', () => {
    expect(eventTargetsAgent('queue_entry_queued', { agent: 'claude' }, 'claude')).toBe(true)
    expect(eventTargetsAgent('queue_entry_delivered', { agent: 'claude' }, 'claude')).toBe(true)
    expect(eventTargetsAgent('queue_entry_withdrawn', { agent: 'claude' }, 'claude')).toBe(true)
    expect(eventTargetsAgent('queue_chain_suspended', { agent: 'claude' }, 'claude')).toBe(true)
    expect(eventTargetsAgent('queue_entry_queued', { agent: 'codex' }, 'claude')).toBe(false)
  })
})
