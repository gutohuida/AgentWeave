import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import {
  useAgentChatHistory,
  useAgentConversations,
  useProjectConversations,
  insertStreamedOutput,
  type ChatHistoryResponse,
  type TimelineEntry,
} from '@/api/agentChat'
import { useAgents } from '@/api/agents'
import { useQuestions } from '@/api/questions'
import { usePendingPermissionRequests } from '@/api/permissions'
import { backstopAfterFailure, BACKSTOP_MS } from '@/lib/backstopPoll'
import { cancelReconnect, __resetSSEStateForTest } from '@/hooks/useSSE'

// A streamed agent output line or context reading is applied from its payload: the tab does not
// re-request the conversation's history, an agent's output or the agent list for it.
const enc = new TextEncoder()
let push: (text: string) => void = () => {}
let gets: string[] = []

const frame = (type: string, data: object) =>
  `event: ${type}\ndata: ${JSON.stringify({ project_id: 'p', ...data })}\n\n`

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })

const entry = (id: string, timestamp: string, extra: Partial<TimelineEntry> = {}): TimelineEntry => ({
  id,
  kind: 'agent_output',
  content: id,
  timestamp,
  delivery_state: 'delivered',
  ...extra,
})

const history: ChatHistoryResponse = {
  conversation_id: 'conv-1',
  session_id: null,
  agent: 'a',
  entries: [entry('o1', '2026-10-25T10:00:00Z')],
  runs: {},
}

function installHub() {
  gets = []
  ;(globalThis as unknown as { fetch: unknown }).fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/events')) {
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          push = (text) => controller.enqueue(enc.encode(text))
        },
      })
      return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    }
    gets.push(url.replace('http://hub.test', ''))
    if (url.endsWith('/chat/conv-1')) return json(history)
    if (url.endsWith('/agents')) return json([{ name: 'a', status: 'idle', message_count: 0, active_task_count: 0 }])
    if (url.includes('/conversations?')) {
      return json({ conversations: [{ id: 'conv-1', agent: 'a' }], archived_count: 0 })
    }
    if (url.endsWith('/agent/a/conversations')) return json([{ id: 'conv-1', agent: 'a' }])
    return json([])
  })
}

function Screen() {
  useAgentChatHistory('a', 'conv-1')
  useAgents()
  useAgentConversations('a')
  useProjectConversations('p')
  return null
}

function configure() {
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'p',
    isConfigured: true,
    bootstrapState: 'ready',
  })
}

describe('a streamed line or reading is applied without refetching', () => {
  beforeEach(() => {
    __resetSSEStateForTest()
    configure()
    installHub()
  })

  afterEach(() => {
    cancelReconnect()
    __resetSSEStateForTest()
  })

  async function mountScreen() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Screen />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(client.getQueryData(['project', 'p', 'agent', 'a', 'chat', 'conv-1'])).toBeTruthy())
    await waitFor(() => expect(client.getQueryData(['project', 'p', 'agents'])).toBeTruthy())
    await waitFor(() => expect(client.getQueryData(['project', 'p', 'agent', 'a', 'conversations'])).toBeTruthy())
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    return client
  }

  it('shows an output line in the history with no GET at all', async () => {
    const client = await mountScreen()
    gets = []
    await act(async () => {
      push(
        frame('agent_output', {
          id: 'o2',
          agent: 'a',
          conversation_id: 'conv-1',
          content: 'hello there',
          kind: 'text',
          payload: null,
          run_id: 'run-1',
          sequence: 1,
          timestamp: '2026-10-25T10:00:05Z',
        }),
      )
      await new Promise((r) => setTimeout(r, 150))
    })
    const cached = client.getQueryData<ChatHistoryResponse>(['project', 'p', 'agent', 'a', 'chat', 'conv-1'])
    expect(cached?.entries.map((e) => e.id)).toEqual(['o1', 'o2'])
    expect(cached?.entries[1].content).toBe('hello there')
    expect(gets).toEqual([])
  })

  it('puts a context reading on the roster and the conversation lists with no GET', async () => {
    const client = await mountScreen()
    gets = []
    await act(async () => {
      push(
        frame('context_warning', {
          agent: 'a',
          conversation_id: 'conv-1',
          status: 'measured',
          source: 'claude',
          percent: 41.5,
          observed_at: 1000,
        }),
      )
      await new Promise((r) => setTimeout(r, 150))
    })
    const roster = client.getQueryData<Array<{ context_usage?: { percent?: number } }>>(['project', 'p', 'agents'])
    expect(roster?.[0].context_usage?.percent).toBe(41.5)
    const rail = client.getQueryData<{ conversations: Array<{ context_usage?: { percent?: number } }> }>([
      'project',
      'p',
      'conversations',
      'open',
    ])
    expect(rail?.conversations[0].context_usage?.percent).toBe(41.5)
    expect(gets).toEqual([])
  })
})

describe('a run ending refreshes what only the run end changes', () => {
  beforeEach(() => {
    __resetSSEStateForTest()
    configure()
    installHub()
  })
  afterEach(() => {
    cancelReconnect()
    __resetSSEStateForTest()
  })

  it('refetches permission requests and questions on a terminal run event', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    function Probe() {
      useQuestions()
      usePendingPermissionRequests()
      useAgents()
      return null
    }
    render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(client.getQueryData(['project', 'p', 'agents'])).toBeTruthy())
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    for (const type of ['run_completed', 'run_failed', 'run_stopped', 'run_interrupted']) {
      gets = []
      await act(async () => {
        push(frame(type, { agent: 'a', run_id: 'run-1' }))
        await new Promise((r) => setTimeout(r, 150))
      })
      expect(gets.filter((g) => g.includes('/permission-requests')).length).toBe(1)
      expect(gets.filter((g) => g.includes('/questions')).length).toBe(1)
    }
  })

  it('does not apply a line with no conversation to the open one', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    function Probe() {
      useAgentChatHistory('a', 'conv-1')
      return null
    }
    render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(client.getQueryData(['project', 'p', 'agent', 'a', 'chat', 'conv-1'])).toBeTruthy())
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    await act(async () => {
      push(
        frame('agent_output', {
          id: 'o9',
          agent: 'a',
          conversation_id: null,
          content: 'stray',
          kind: 'text',
          payload: null,
          run_id: 'run-1',
          sequence: 1,
          timestamp: '2026-10-25T10:00:07Z',
        }),
      )
      await new Promise((r) => setTimeout(r, 150))
    })
    const cached = client.getQueryData<ChatHistoryResponse>(['project', 'p', 'agent', 'a', 'chat', 'conv-1'])
    expect(cached?.entries.map((e) => e.id)).toEqual(['o1'])
  })
})

describe('insertStreamedOutput', () => {
  it('keeps still-queued entries last and orders by time', () => {
    const base: ChatHistoryResponse = {
      ...history,
      entries: [
        entry('o1', '2026-10-25T10:00:00Z'),
        entry('o3', '2026-10-25T10:00:09Z'),
        entry('q1', '2026-10-25T10:00:01Z', { kind: 'operator_input', delivery_state: 'queued' }),
      ],
    }
    const next = insertStreamedOutput(base, entry('o2', '2026-10-25T10:00:05Z'))
    expect(next.entries.map((e) => e.id)).toEqual(['o1', 'o2', 'o3', 'q1'])
    expect(insertStreamedOutput(next, entry('o2', '2026-10-25T10:00:05Z'))).toBe(next)
  })
})

describe('the polls the stream already covers are backstops', () => {
  afterEach(() => {
    cancelReconnect()
    __resetSSEStateForTest()
  })

  it('poll only after a failure, at most every 30s', () => {
    expect(BACKSTOP_MS).toBeGreaterThanOrEqual(30_000)
    const q = (status: string) => ({ state: { status } }) as never
    expect(backstopAfterFailure(q('success'))).toBe(false)
    expect(backstopAfterFailure(q('error'))).toBe(BACKSTOP_MS)
  })

  it('questions and permission requests use that backstop', async () => {
    __resetSSEStateForTest()
    configure()
    installHub()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    function Probe() {
      useQuestions()
      usePendingPermissionRequests()
      return null
    }
    render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(client.getQueryCache().findAll().length).toBeGreaterThanOrEqual(2))
    for (const q of client.getQueryCache().findAll()) {
      expect((q.options as { refetchInterval?: unknown }).refetchInterval).toBe(backstopAfterFailure)
    }
  })
})
