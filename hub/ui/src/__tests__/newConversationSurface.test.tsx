import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NewConversationSurface } from '@/components/agents/NewConversationSurface'
import { useConfigStore } from '@/store/configStore'

vi.mock('@/api/agents', () => ({
  useAgents: () => ({
    data: [
      { name: 'claude', status: 'idle', message_count: 0, active_task_count: 0, color_index: 1, runner_id: 'runner-claude' },
      { name: 'codex', status: 'idle', message_count: 0, active_task_count: 0, color_index: 3, runner_id: 'runner-codex' },
    ],
  }),
}))
vi.mock('@/api/runners', () => ({
  useRunners: () => ({
    data: [
      { id: 'runner-claude', cli: 'claude', model: 'claude-opus-5' },
      { id: 'runner-codex', cli: 'codex', model: 'gpt-5' },
    ],
  }),
}))
vi.mock('@/api/workspace', () => ({ useWorkspacePaths: () => ({ data: [] }) }))
vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: undefined }) }
})

const fetchMock = vi.fn()
;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = fetchMock

/** The surface is controlled — the destination owns which agent the unsent message is for. This
 *  plays App's half of that, so a test can click a chip and see the surface follow. */
function Controlled({
  agent: initial,
  onStarted = vi.fn(),
  onChooseAgent,
}: {
  agent: string | null
  onStarted?: (agent: string, conversationId: string) => void
  onChooseAgent?: (agent: string) => void
}) {
  const [agent, setAgent] = useState<string | null>(initial)
  return (
    <NewConversationSurface
      projectId="proj-a"
      agent={agent}
      onChooseAgent={(next) => {
        setAgent(next)
        onChooseAgent?.(next)
      }}
      onStarted={onStarted}
    />
  )
}

function renderSurface(agent: string | null, onStarted = vi.fn()) {
  render(<Controlled agent={agent} onStarted={onStarted} />)
  return { onStarted }
}

describe('starting a conversation', () => {
  beforeEach(() => {
    cleanup()
    localStorage.clear()
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ status: 'started', conversation_id: 'conv-fresh' }), {
        status: 200,
      }),
    )
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-a',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('leads with the composer, not an empty transcript', () => {
    renderSurface('claude')
    expect(screen.getByTestId('new-conversation-surface')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    expect(screen.queryByTestId('conversation-output')).not.toBeInTheDocument()
  })

  it('asks what the bound agent should work on, by name', () => {
    renderSurface('claude')
    expect(screen.getByTestId('new-conversation-headline')).toHaveTextContent(
      'What should claude work on?',
    )
  })

  it('asks who should work on it when no agent is bound, and follows the choice', async () => {
    renderSurface(null)
    // The headline is the instruction here, not decoration above one.
    expect(screen.getByTestId('new-conversation-headline')).toHaveTextContent(
      'Who should work on this?',
    )

    fireEvent.click(screen.getByTestId('new-conversation-agent-codex'))
    await waitFor(() =>
      expect(screen.getByTestId('new-conversation-headline')).toHaveTextContent(
        'What should codex work on?',
      ),
    )
  })

  it('is already bound when started from an agent’s row, and needs no choice', async () => {
    const { onStarted } = renderSurface('claude')
    expect(screen.queryByTestId('composer-disabled-reason')).not.toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Look at the flaky test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({
      agent: 'claude',
      message: 'Look at the flaky test',
    })
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith('claude', 'conv-fresh'))
  })

  it('requires an agent when started from the recency view, and says so', async () => {
    renderSurface(null)
    expect(screen.getByTestId('composer-disabled-reason')).toHaveTextContent(
      'Choose an agent to start',
    )

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Who is listening?' } })
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    expect(fetchMock).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('new-conversation-agent-codex'))
    await waitFor(() =>
      expect(screen.queryByTestId('composer-disabled-reason')).not.toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string).agent).toBe('codex')
  })

  it('creates nothing when the operator leaves without sending', () => {
    const { unmount } = render(<Controlled agent="claude" />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'On second thoughts…' } })
    unmount()
    // A conversation is created by its first message; abandoning the surface leaves no row.
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('treats a pre-selected agent as a default, not a lock', async () => {
    // Operator, 2026-08-08: "I like the way that it pre select but it shouldn't lock. If I change
    // the conversation should be directed elsewhere." Arriving from codex's row menu and finding
    // claude's chip dead is worse than arriving with nothing selected at all.
    const onChooseAgent = vi.fn()
    const onStarted = vi.fn()
    render(<Controlled agent="codex" onStarted={onStarted} onChooseAgent={onChooseAgent} />)
    expect(screen.getByTestId('new-conversation-agent-codex')).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByTestId('new-conversation-agent-claude'))
    expect(onChooseAgent).toHaveBeenCalledWith('claude')
    await waitFor(() =>
      expect(screen.getByTestId('new-conversation-agent-claude')).toHaveAttribute('aria-pressed', 'true'),
    )
    expect(screen.getByTestId('new-conversation-agent-codex')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('new-conversation-headline')).toHaveTextContent(
      'What should claude work on?',
    )

    // And the message actually goes where the operator redirected it.
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Take this one instead' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string).agent).toBe('claude')
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith('claude', 'conv-fresh'))
  })

  it('keeps the typed message when the agent is changed', async () => {
    render(<Controlled agent="codex" />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Half-written thought' } })

    fireEvent.click(screen.getByTestId('new-conversation-agent-claude'))
    await waitFor(() =>
      expect(screen.getByTestId('new-conversation-headline')).toHaveTextContent('claude'),
    )
    // Retargeting is a change of recipient, not a fresh start.
    expect(screen.getByRole('textbox')).toHaveValue('Half-written thought')
  })
})

describe('declaring an exploration before the first message', () => {
  // Its own reset: this block sits outside the first describe, so that one's beforeEach does not
  // reach it and `fetchMock.mock.calls` would otherwise accumulate across these tests.
  beforeEach(() => {
    cleanup()
    fetchMock.mockReset()
    // A fresh Response per call, not one shared instance: a body can only be read once, and
    // these tests make two requests. `mockResolvedValue` hands the same Response to both, so the
    // second `.json()` throws on an already-consumed body.
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ status: 'started', conversation_id: 'conv-fresh' }), {
          status: 200,
        }),
      ),
    )
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-a',
      isConfigured: true,
      bootstrapState: 'ready',
      mode: 'light',
    })
  })

  it('offers the toggle, which the surface used to omit entirely', () => {
    // It was omitted deliberately when the control only *opened* an existing document: there is
    // no panel here to open one into. Under a toggle that is backwards — this is the surface
    // where an operator most needs to say "I want to explore an idea", before they have typed
    // anything. Omitting it meant the agent was never told the Hub has a specification flow,
    // and it reached for one of its own.
    renderSurface('claude')
    const toggle = screen.getByTestId('composer-start-exploration')
    expect(toggle).toHaveTextContent('Explore')
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
  })

  it('offers no reopen-existing control -- there is no picker here to open', () => {
    // ConversationView wires a real one because it owns a SpecDocumentPicker; this surface has
    // no conversation yet to attach an existing document to, so the control that reopens one
    // must not render here at all rather than render and lie about what it does.
    renderSurface('claude')
    expect(screen.queryByTestId('composer-open-existing-spec')).not.toBeInTheDocument()
  })

  it('shows the declaration as pressed, and lets it be taken back', () => {
    renderSurface('claude')
    const toggle = screen.getByTestId('composer-start-exploration')

    fireEvent.click(toggle)
    expect(screen.getByTestId('composer-start-exploration')).toHaveTextContent('Exploring')
    expect(screen.getByTestId('composer-start-exploration')).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByTestId('composer-start-exploration'))
    expect(screen.getByTestId('composer-start-exploration')).toHaveTextContent('Explore')
  })

  it('creates the document from the first message and opens the one the Hub minted', async () => {
    const minted = 'spec/changes/amber-griffin/spec.html'
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        String(url).includes('/project/documents')
          ? new Response(JSON.stringify({ id: 'spdoc-1', path: minted }), { status: 201 })
          : new Response(JSON.stringify({ status: 'started', conversation_id: 'conv-fresh' }), {
              status: 200,
            }),
      ),
    )
    const { onStarted } = renderSurface('claude')

    fireEvent.click(screen.getByTestId('composer-start-exploration'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'I want to build a budget app' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(onStarted).toHaveBeenCalled())

    const urls = fetchMock.mock.calls.map(([url]) => String(url))
    const documentIndex = urls.findIndex((url) => url.includes('/project/documents'))
    const triggerIndex = urls.findIndex((url) => url.includes('/agent/trigger'))

    expect(documentIndex, 'the document must be created').toBeGreaterThanOrEqual(0)
    // Order is the whole point. Creating it after the turn left the FIRST message — the one that
    // decides how the agent frames the exploration — with no document attached, so the context
    // carried no phase and no `submit_spec_document`, and the agent invented a workflow.
    expect(documentIndex, 'the document must exist before the turn').toBeLessThan(triggerIndex)

    // No path is sent. Deriving one here is what produced a permanent name from the operator's
    // opening guess, at the one moment nobody knows what the document is about.
    const created = JSON.parse(String((fetchMock.mock.calls[documentIndex][1] as RequestInit).body))
    expect(created.path).toBeUndefined()
    expect(created.title).toBe('I want to build a budget app')

    expect(
      JSON.parse(String((fetchMock.mock.calls[triggerIndex][1] as RequestInit).body)).spec_document,
      'the first turn must carry the document the Hub minted',
    ).toBe(minted)
    expect(onStarted).toHaveBeenCalledWith('claude', 'conv-fresh', minted)
  })

  it('still starts the conversation when the document cannot be created', async () => {
    // Losing the operator's first message to a document that could not be written would be a
    // worse failure than not having the document.
    const { onStarted } = renderSurface('claude')
    fetchMock.mockImplementation((url: string) =>
      String(url).includes('/project/documents')
        ? Promise.resolve(new Response('{"detail":"nope"}', { status: 409 }))
        : Promise.resolve(
            new Response(JSON.stringify({ status: 'started', conversation_id: 'conv-fresh' }), {
              status: 200,
            }),
          ),
    )

    fireEvent.click(screen.getByTestId('composer-start-exploration'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Budget app' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(onStarted).toHaveBeenCalled())
    // No document to attach: a minted name cannot collide, so a failure here is a real one and
    // there is no path to fall back to. The message still goes.
    expect(onStarted).toHaveBeenCalledWith('claude', 'conv-fresh')
  })

  it('creates no document when exploration was not declared', async () => {
    const { onStarted } = renderSurface('claude')
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Just a question' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(onStarted).toHaveBeenCalled())
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes('/project/documents')),
    ).toBe(false)
    expect(onStarted).toHaveBeenCalledWith('claude', 'conv-fresh')
  })
})
