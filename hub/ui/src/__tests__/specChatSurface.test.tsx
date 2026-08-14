import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation, ChatHistoryResponse } from '@/api/agentChat'
import type { PermissionRequest } from '@/api/permissions'
import type { Question } from '@/api/questions'
import { useConfigStore } from '@/store/configStore'

/* Working on a specification uses the one conversation surface.
 *
 * The surface this replaced (`SpecChatPane`) could not render a permission card, a question card,
 * or a checkpoint banner — searching it for `permission|question|checkpoint|Banner` returned
 * nothing — so an agent that asked the operator anything from the Spec page blocked with nothing
 * shown. That is the defect this capability exists to fix, so it is demonstrated rather than
 * asserted: these tests render the real `ConversationView`, mounting the real `AgentOutputPanel`,
 * `Composer`, `PermissionRequestCard` and `AgentQuestionCard`, with a document open beside them.
 *
 * `SpecChat` — the intermediate wrapper, and its agent `<select>` — is gone. Which conversation is
 * on screen is the destination's answer (`conversationSelection.test.ts`), and which agent is the
 * rail's. The last describe here is the check that would have caught that `<select>`.
 */

let conversations: AgentConversation[] = []
let openQuestions: Question[] = []
let permissionRequests: PermissionRequest[] = []
const answerMutation = vi.fn().mockResolvedValue({})
const decide = vi.fn()

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  useSSEConnectionState: () => 'open',
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

// Partial mock: `importOriginal` keeps every export this file does not override real, so
// adding one to `@/api/spec` does not break a test that never used it. The whole-module form
// this replaced failed the moment the module grew `useSpecDocuments`.
vi.mock('@/api/spec', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/spec')>()),
  // Stubbed so the phase bar issues no request of its own: this file asserts on the *order*
  // of fetch calls, and a live document query would take index 0 from the trigger.
  useSpecDocuments: () => ({ data: { documents: [] } }),
  useSpecList: () => ({
    data: {
      specs: [{ path: 'spec/a1-probe.html', title: 'A1 probe', state: 'filed', parent: null, order: 0 }],
      home: 'spec/a1-probe.html',
      diagnostics: [],
      missing: [],
    },
    isLoading: false,
    refetch: () => {},
  }),
  useSpec: () => ({ data: { path: 'spec/a1-probe.html', content: '<html></html>' }, refetch: () => {} }),
  useSpecEvents: () => {},
}))

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentOutput: () => ({ lines: [], isLoading: false }),
    useAgents: () => ({ data: [] }),
    useAgentLaunchability: () => ({ data: { agents: {} } }),
    useAgentTimeline: () => ({ data: [] }),
  }
})

vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  const history = (): ChatHistoryResponse => ({
    conversation_id: conversations[0]?.id ?? null,
    session_id: null,
    agent: 'speccer',
    entries: [],
  })
  return {
    ...actual,
    useAgentConversations: () => ({ data: conversations }),
    useAgentChatHistory: () => ({ data: history(), isLoading: false }),
    useAgentRecentChat: () => ({ data: history(), isLoading: false }),
  }
})

vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: openQuestions }),
  useAnswerQuestion: () => ({ mutateAsync: answerMutation, isPending: false }),
  useDeclineQuestion: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/api/permissions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/permissions')>()),
  usePendingPermissionRequests: () => ({ data: permissionRequests }),
  useDecidePermissionRequest: () => ({ mutate: decide, isPending: false }),
}))

vi.mock('@/api/unaskedQuestions', () => ({
  usePendingUnaskedQuestions: () => ({ data: [] }),
  useResolveUnaskedQuestion: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/api/checkpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/checkpoints')>()
  return { ...actual, useCheckpoints: () => ({ data: [] }) }
})

vi.mock('@/api/queue', () => ({
  useQueuedEntries: () => ({ data: [] }),
  useQueueStatus: () => ({ data: { waiting_count: 0 } }),
  withdrawQueueEntry: vi.fn(),
}))

vi.mock('@/api/workspace', () => ({ useWorkspacePaths: () => ({ data: [] }) }))
vi.mock('@/api/runners', () => ({ useRunners: () => ({ data: [] }) }))
vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: undefined }) }
})

import { ConversationView } from '@/components/agents/ConversationView'

const fetchMock = vi.fn()
;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = fetchMock

const SPECCER: AgentSummary = {
  name: 'speccer',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
}

let queryClient: QueryClient

function conversation(overrides: Partial<AgentConversation> = {}): AgentConversation {
  return {
    id: 'conv-1',
    agent: 'speccer',
    provider_session_id: null,
    lifecycle: 'open',
    title: 'Reviewing the baseline',
    title_set_by_operator: false,
    origin: 'operator',
    attention: 'idle',
    created_at: '2026-08-10T10:00:00Z',
    updated_at: '2026-08-10T10:00:00Z',
    ...overrides,
  }
}

function renderChat(
  documentPath: string | null = 'spec/a1-probe.html',
  conversationId: string | null = null,
) {
  const onOpenDocument = vi.fn()
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <ConversationView
        agent={SPECCER}
        conversationId={conversationId}
        document={documentPath}
        onSelectConversation={() => {}}
        onOpenDocument={onOpenDocument}
        onBackToProject={() => {}}
        onOpenAgentSettings={() => {}}
      />
    </QueryClientProvider> as ReactNode,
  )
  return { ...utils, onOpenDocument }
}

/**
 * The JSON body of the Nth /agent/trigger call.
 *
 * Selected by path rather than by position in the mock's call list. Indexing assumed the trigger
 * was the only thing this surface fetched, so the coverage query added alongside the coverage bar
 * silently took slot zero and these assertions started reading the wrong request. Any future query
 * on this view would have done the same.
 */
function triggerBody(call = 0): Record<string, unknown> {
  const triggers = fetchMock.mock.calls.filter(([path]) =>
    String(path).includes('/agent/trigger'),
  ) as [string, RequestInit][]
  expect(triggers.length).toBeGreaterThan(call)
  return JSON.parse(triggers[call][1].body as string)
}

async function send(text: string) {
  const textarea = screen.getByRole('textbox')
  fireEvent.change(textarea, { target: { value: text } })
  fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
  await waitFor(() => expect(fetchMock).toHaveBeenCalled())
}

beforeEach(() => {
  cleanup()
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  conversations = []
  openQuestions = []
  permissionRequests = []
  answerMutation.mockClear()
  decide.mockClear()
  fetchMock.mockReset()
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ status: 'running', conversation_id: 'conv-new' }),
  })
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-test',
    isConfigured: true,
    bootstrapState: 'ready',
    mode: 'light',
  })
})

describe('a conversation with a document open mounts the one composer', () => {
  it('renders the shared composer rather than a second message input', () => {
    renderChat()
    expect(screen.getByTestId('conversation-output')).toBeInTheDocument()
    expect(screen.getByTestId('conversation-header')).toBeInTheDocument()
    expect(screen.getByTestId('spec-document-panel')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('creates a conversation with the first message when the agent has none', async () => {
    renderChat()
    expect(screen.getByTestId('session-continuity')).toHaveTextContent(
      'Next message starts a fresh conversation',
    )

    await send('what does this document say?')

    const body = triggerBody()
    expect(body.agent).toBe('speccer')
    expect(body.message).toBe('what does this document say?')
    // `conversationId: null` — the Hub creates one from the message (design.md Decision 1).
    expect(body.conversation_id).toBeUndefined()
    // No specification-scoped origin is produced. Nothing in the request names one.
    expect(JSON.stringify(body)).not.toContain('origin')
  })

  it('continues the conversation the destination names', () => {
    conversations = [conversation({ id: 'conv-old', title: 'Older' })]
    renderChat('spec/a1-probe.html', 'conv-old')
    expect(screen.getByTestId('session-continuity')).toHaveTextContent('Continuing Older')
  })
})

describe('the open document travels as context, not as the message', () => {
  it('sends the document the operator is viewing alongside their message', async () => {
    renderChat('spec/a1-probe.html')
    await send('why does this say that?')

    const body = triggerBody()
    expect(body.spec_document).toBe('spec/a1-probe.html')
    // The message is the durable record of what the operator said.
    expect(body.message).toBe('why does this say that?')
  })

  it('sends no document when none is open, rather than an empty one', async () => {
    renderChat(null)
    await send('hello')
    expect(triggerBody().spec_document).toBeUndefined()
  })
})

describe('the operator can be involved while a document is open', () => {
  it('renders a question the agent asked, and answers it', async () => {
    openQuestions = [
      {
        id: 'q-1',
        project_id: 'proj-test',
        from_agent: 'speccer',
        question: 'Should the baseline keep the old glossary?',
        blocking: true,
        options: [
          { label: 'Keep it', description: 'Nothing else references it yet' },
          { label: 'Drop it', description: 'It has been wrong since July' },
        ],
        header: 'Glossary',
        multi_select: false,
        answered: false,
        created_at: '2026-08-10T10:00:00Z',
      } as Question,
    ]
    renderChat()

    expect(screen.getByText('Should the baseline keep the old glossary?')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Drop it'))
    await waitFor(() => expect(answerMutation).toHaveBeenCalled())
    expect(answerMutation.mock.calls[0][0]).toMatchObject({ id: 'q-1', labels: ['Drop it'] })
    // The answer went to the question, not out as a new message. Asserted against the trigger
    // specifically: "fetch was never called" also forbade every unrelated query this view makes,
    // so the coverage bar's read broke a test about answering a question.
    const triggers = fetchMock.mock.calls.filter(([path]) =>
      String(path).includes('/agent/trigger'),
    )
    expect(triggers).toHaveLength(0)
  })

  it('renders a permission request and resolves it both ways', () => {
    permissionRequests = [
      {
        id: 'perm-1',
        agent: 'speccer',
        run_id: 'run-1',
        tool_name: 'Write',
        tool_use_id: 'toolu_1',
        tool_input: { file_path: 'spec/a1-probe.html', content: 'x' },
        status: 'pending',
        dismissed: false,
        created_at: '2026-08-10T10:00:00Z',
        decided_at: null,
        decided_by: null,
      },
    ]
    renderChat()

    expect(screen.getByText(/speccer wants to use Write/)).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('permission-allow-perm-1'))
    expect(decide).toHaveBeenCalledWith({ id: 'perm-1', allow: true })
    fireEvent.click(screen.getByTestId('permission-deny-perm-1'))
    expect(decide).toHaveBeenCalledWith({ id: 'perm-1', allow: false })
  })

  it('does not show another agent’s permission request', () => {
    permissionRequests = [
      {
        id: 'perm-2',
        agent: 'other',
        run_id: 'run-2',
        tool_name: 'Bash',
        tool_use_id: 'toolu_2',
        tool_input: { command: 'rm -rf /' },
        status: 'pending',
        dismissed: false,
        created_at: '2026-08-10T10:00:00Z',
        decided_at: null,
        decided_by: null,
      },
    ]
    renderChat()
    expect(screen.queryByTestId('permission-request-perm-2')).not.toBeInTheDocument()
  })
})

describe('one way to choose an agent', () => {
  /* Task 5.5, and the lesson rather than the line.
   *
   * A1 removed a second implementation of a chat surface and, in the same change, introduced a
   * second implementation of *agent selection* — a raw `<select>` beside the rail that already
   * did the job, which is why the agent's name appeared three times in one header. The standing
   * check is "how many ways does the application offer to do this?"
   */
  it('offers no agent selector on the conversation surface', () => {
    renderChat()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Agent')).not.toBeInTheDocument()
    expect(document.querySelectorAll('select')).toHaveLength(0)
  })

  it('names the agent exactly once in the conversation header', () => {
    renderChat()
    const header = screen.getByTestId('conversation-header')
    const occurrences = (header.textContent ?? '').split('speccer').length - 1
    expect(occurrences).toBe(1)
  })
})

describe('the specification is reached from the composer', () => {
  /* The `spec` project tab is gone. Reaching a specification used to mean leaving the
   * conversation, going to the project, and choosing a tab — for the surface the product is most
   * about (operator, 2026-08-10). The pill sits with Model / Effort / Permissions because that is
   * what it is: it states which document this turn is written against. */
  it('states which document is open, and opens the picker', async () => {
    renderChat('spec/a1-probe.html')

    const pill = screen.getByTestId('composer-spec-control')
    expect(pill).toHaveTextContent('A1 probe')
    expect(pill).toHaveAttribute('title', 'Spec: A1 probe')

    fireEvent.click(pill)
    expect(await screen.findByRole('dialog')).toHaveAccessibleName('Search documents')
  })

  it('offers to start an exploration when no document is open', () => {
    // Previously this showed "Spec: None" and opened the picker, which asked the operator to
    // name a document before they had one — and an agent with no document open was never told
    // the Hub has a specification flow at all, so it reached for a workflow of its own. One
    // press now creates the document this conversation needs.
    renderChat(null)
    const toggle = screen.getByTestId('composer-start-exploration')
    expect(toggle).toHaveTextContent('Explore')
    expect(toggle).toHaveAccessibleName('Start an exploration')
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByTestId('composer-spec-control')).not.toBeInTheDocument()
  })

  it('separates changing the document from closing it', () => {
    // The original concern still holds: a pill whose press means "open" sometimes and "close"
    // other times is two controls wearing one hat. The toggle keeps them as distinct targets
    // with distinct labels rather than overloading one press.
    renderChat('spec/a1-probe.html')
    expect(screen.getByTestId('composer-spec-control')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('composer-stop-exploring')).toHaveAccessibleName(
      'Close the document',
    )
    expect(screen.getByTestId('spec-document-close')).toBeInTheDocument()
  })
})
