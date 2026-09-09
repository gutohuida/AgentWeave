import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentRunFacts, AgentSummary, AgentTimelineEvent } from '@/api/agents'
import type { AgentConversation, ChatHistoryResponse } from '@/api/agentChat'
import { AgentActivityTab } from '@/components/agents/AgentActivityTab'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'
import { useConfigStore } from '@/store/configStore'

/**
 * The guard the nine hook fixtures cannot be.
 *
 * `GET /agents/{name}/timeline` returns `{events, runs}` where it used to return a bare array.
 * Every existing fixture mocks `useAgentTimeline` with an EMPTY envelope, and an empty envelope
 * is indistinguishable from an empty array once `?? []` has run — task 3.1 says so in terms:
 * those nine "will keep passing if you forget them". So nothing in the suite would fail if a
 * consumer were left reading `data` as the event list, or if `runs` were dropped on the floor
 * between the hook and the only component that consumes it.
 *
 * These two tests are the only ones that put a NON-empty envelope through the hook.
 *
 * **The second test changed direction with F274 (task 4.7).** The panel used to take `runs` off
 * the timeline envelope; it takes it off the chat response now, because the map has to be keyed to
 * the same query as the turns it labels. So the two fixtures below hold DIFFERENT maps on purpose:
 * the timeline's is a decoy, and wiring the panel back to it is what the assertion catches.
 */

let timeline: { events: AgentTimelineEvent[]; runs: Record<string, AgentRunFacts> } = {
  events: [],
  runs: {},
}
let conversations: AgentConversation[] = []
/** Props `AgentOutputPanel` actually handed `AgentTimeline`, captured by the mock below. */
let handedToTimeline: Record<string, unknown> = {}

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentOutput: () => ({ lines: [], isLoading: false }),
    useAgents: () => ({ data: [] }),
    useAgentLaunchability: () => ({ data: { agents: {} } }),
    useAgentTimeline: () => ({ data: timeline }),
  }
})
// `AgentOutputPanel` never reads the run facts — it is the only thing that can carry them
// (task 3.3a). Asserting the carry means watching what it passes, so the recipient is stubbed.
vi.mock('@/components/agents/AgentTimeline', () => ({
  AgentTimeline: (props: Record<string, unknown>) => {
    handedToTimeline = props
    return <div data-testid="timeline-stub" />
  },
}))
vi.mock('@/components/common/Icon', () => ({
  Icon: ({ name }: { name: string }) => <span data-testid="icon" data-name={name} />,
}))
let chatRuns: Record<string, AgentRunFacts> = {}

vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  const history = (): ChatHistoryResponse => ({
    conversation_id: conversations[0]?.id ?? null,
    session_id: null,
    agent: 'claude',
    entries: [],
    runs: chatRuns,
  })
  return {
    ...actual,
    useAgentConversations: () => ({ data: conversations }),
    useAgentChatHistory: () => ({ data: history(), isLoading: false }),
    useAgentRecentChat: () => ({ data: history(), isLoading: false }),
  }
})
vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: [] }),
  useAnswerQuestion: () => ({ mutate: vi.fn(), isPending: false }),
  useDeclineQuestion: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('@/api/permissions', () => ({
  usePendingPermissionRequests: () => ({ data: [] }),
  useDecidePermissionRequest: () => ({ mutate: vi.fn(), isPending: false }),
  useDismissPermissionRequest: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('@/api/checkpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/checkpoints')>()
  return { ...actual, useCheckpoints: () => ({ data: [] }) }
})
vi.mock('@/api/queue', () => ({
  useQueuedEntries: () => ({ data: [] }),
  useQueueStatus: () => ({ data: undefined }),
  withdrawQueueEntry: vi.fn(),
}))
vi.mock('@/api/workspace', () => ({ useWorkspacePaths: () => ({ data: [] }) }))
vi.mock('@/api/runners', () => ({ useRunners: () => ({ data: [] }) }))
vi.mock('@/api/accounting', () => ({
  useAccounting: () => ({ data: undefined }),
  useConversationAccounting: () => ({ data: undefined }),
}))
vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: undefined }) }
})

const agent: AgentSummary = {
  name: 'claude',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
}

const stopEvent: AgentTimelineEvent = {
  id: 'ev-stop',
  event_type: 'run_stopped',
  timestamp: '2026-09-02T00:00:09Z',
  summary: 'Run stopped by the operator',
  data: { run_id: 'run-1' },
}

const stoppedRun: AgentRunFacts = {
  status: 'stopped',
  exit_code: 15,
  started_at: '2026-09-02T00:00:00Z',
  ended_at: '2026-09-02T00:00:09Z',
}

/** The decoy. Only the timeline route serves this one, and nothing on screen may be labelled
 *  from it — it stands for the run whose events are still inside that route's fifty-event
 *  window while the turn on screen names a run that has aged out of it (F274). */
const timelineOnlyRun: AgentRunFacts = {
  status: 'completed',
  exit_code: 0,
  started_at: '2026-09-02T00:00:20Z',
  ended_at: '2026-09-02T00:00:22Z',
}

describe('the timeline envelope is unwrapped by the two consumers that hold the hook', () => {
  beforeEach(() => {
    cleanup()
    handedToTimeline = {}
    timeline = { events: [stopEvent], runs: { 'run-timeline-only': timelineOnlyRun } }
    chatRuns = { 'run-1': stoppedRun }
    conversations = [
      {
        id: 'conv-1',
        agent: 'claude',
        provider_session_id: null,
        lifecycle: 'open',
        title: 'A conversation',
        title_set_by_operator: false,
        origin: 'operator',
        attention: 'idle',
        created_at: '2026-09-02T00:00:00Z',
        updated_at: '2026-09-02T00:00:00Z',
      },
    ]
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('AgentActivityTab lists an event out of the envelope, not out of the envelope object', () => {
    // Reading `data` as the array — the shape this route returned until this change — would put
    // the envelope object itself through `.map` and throw, or list nothing.
    render(<AgentActivityTab agent={agent} />)
    expect(screen.getByText('Run stopped by the operator')).toBeInTheDocument()
    expect(screen.queryByText('No activity yet')).not.toBeInTheDocument()
  })

  it("AgentOutputPanel hands the timeline the CHAT response's run facts, not the timeline route's", async () => {
    render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)
    await waitFor(() => expect(screen.getByTestId('timeline-stub')).toBeInTheDocument())

    // The point of task 3.3a: this panel is the only thing between the hook and the three
    // consumers, and it must carry a value it has no use for. F274 changed WHICH hook: the map
    // now rides on the response that carries the entries, so a turn's run row cannot be scoped
    // away by a window the turn was never in. Wiring `runFacts` back to `useAgentTimeline` fails
    // both halves of this assertion.
    expect(handedToTimeline.runs).toEqual({ 'run-1': stoppedRun })
    expect(handedToTimeline.runs).not.toHaveProperty('run-timeline-only')
    // And the other half of the envelope stops here (task 4.6a). `AgentTimeline` had no reader
    // left for the events, and the reader anyone would add back is the one F190 was: run state
    // reduced out of a list the route truncates. Asserted rather than merely deleted, so
    // re-threading it is a failing test rather than a silent regression.
    expect(handedToTimeline).not.toHaveProperty('timelineEvents')
  })
})
