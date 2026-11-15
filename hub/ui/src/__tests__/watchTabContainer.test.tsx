import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { WatchTabContainer } from '@/components/panel/WatchTabContainer'
import { NO_WATCH_CHOICE, useWatchChoiceStore, WATCH_CHOICE_STORAGE_KEY } from '@/store/watchChoiceStore'

/* The Watch tab over the app's own data (`the-side-panel-s-watch-tab-...`, FR-2..FR-9). The data
 * hooks are replaced by fixtures in the order the routes return them: the conversations route lists
 * them in no useful order, so the test hands them over oldest first and expects newest first. */

type Agent = { name: string; status: string; color_index: number; running_conversation_id: string | null }
type Conv = { id: string; agent: string; title: string; updated_at: string; lifecycle: 'open' | 'archived' }
type Q = { id: string; from_agent: string; answered: boolean; declined?: boolean; asker_waiting?: boolean }

const data = {
  agents: [] as Agent[],
  conversations: [] as Conv[],
  questions: [] as Q[],
}

vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: data.agents, isLoading: false }) }))
vi.mock('@/api/questions', () => ({ useQuestions: () => ({ data: data.questions }) }))
vi.mock('@/api/agentChat', () => ({
  conversationLabel: (c: { title: string | null }) => c.title ?? 'New conversation',
  useProjectConversations: () => ({ data: { conversations: data.conversations } }),
  useAgentChatHistory: (_agent: string, id: string) => ({
    data: { entries: [{ id }], runs: {} },
  }),
}))
vi.mock('@/components/agents/AgentTimeline', () => ({
  AgentTimeline: ({ agent, entries }: { agent: { name: string }; entries: { id: string }[] }) => (
    <div data-testid="timeline">{`${agent.name}:${entries[0].id}`}</div>
  ),
}))

const P = 'proj-1'
const at = (minute: number) => `2026-11-15T10:${String(minute).padStart(2, '0')}:00Z`
const agent = (name: string, over: Partial<Agent> = {}): Agent => ({ name, status: 'idle', color_index: 1, running_conversation_id: null, ...over })
const conv = (id: string, owner: string, minute: number, over: Partial<Conv> = {}): Conv => ({ id, agent: owner, title: `Title ${id}`, updated_at: at(minute), lifecycle: 'open', ...over })

function mount(main: string | null = 'c1', onOpen = vi.fn()) {
  const view = render(<WatchTabContainer projectId={P} mainConversationId={main} onOpenConversation={onOpen} />)
  const again = (next: string | null = main) =>
    view.rerender(<WatchTabContainer projectId={P} mainConversationId={next} onOpenConversation={onOpen} />)
  return { again, onOpen }
}

async function pickAgent(name: string) {
  await userEvent.click(screen.getByRole('button', { name: /Agent to watch/ }))
  await userEvent.click(screen.getByRole('menuitemradio', { name: new RegExp(`^${name}`) }))
}

beforeEach(() => {
  localStorage.clear()
  useWatchChoiceStore.setState({ choices: {} })
  data.agents = [agent('A'), agent('B')]
  data.conversations = [conv('c2', 'A', 5), conv('c1', 'A', 1), conv('c4', 'B', 3), conv('c3', 'B', 2)]
  data.questions = []
})
afterEach(cleanup)

describe('Watch tab container', () => {
  it('opens on an agent menu with nothing watched (watch-tab-opens)', () => {
    mount()
    expect(screen.getByTestId('watch-tab')).toBeTruthy()
    expect(screen.getByTestId('watch-choose-agent').textContent).toMatch(/Choose an agent/)
    expect(screen.queryByTestId('timeline')).toBeNull()
  })

  it('lists every agent with its state, and the picked agent’s conversations newest first (menus-list-right-things)', async () => {
    data.agents = [agent('A'), agent('B', { running_conversation_id: 'c3' })]
    mount('other')
    await userEvent.click(screen.getByRole('button', { name: /Agent to watch/ }))
    const agentRows = screen.getAllByRole('menuitemradio').map((r) => r.textContent ?? '')
    expect(agentRows).toHaveLength(2)
    expect(agentRows[0]).toMatch(/A.*idle/)
    expect(agentRows[1]).toMatch(/B.*working/)
    await userEvent.click(screen.getByRole('menuitemradio', { name: /^A/ }))
    await userEvent.click(screen.getByRole('button', { name: /^Conversation/ }))
    const rows = screen.getAllByRole('menuitemradio').map((r) => r.textContent ?? '')
    expect(rows.map((t) => /Title (c\d)/.exec(t)?.[1])).toEqual(['c2', 'c1'])
  })

  it('opens the running conversation, else the most recent, else says there is none (default-running)', async () => {
    data.agents = [agent('A'), agent('B', { running_conversation_id: 'c3' }), agent('E')]
    mount('other')
    await pickAgent('B')
    expect(screen.getByTestId('timeline').textContent).toBe('B:c3')
    data.agents = [agent('A'), agent('B'), agent('E')]
    cleanup()
    mount('other')
    expect(screen.getByTestId('timeline').textContent).toBe('B:c4')
    await pickAgent('E')
    expect(screen.getByTestId('watch-no-conversation').textContent).toMatch(/E has no conversation yet/)
    expect(screen.queryByTestId('timeline')).toBeNull()
  })

  it('follows the agent until a conversation is picked by hand (follows-until-hand-pick)', async () => {
    data.agents = [agent('A'), agent('B', { running_conversation_id: 'c3' })]
    const { again } = mount('other')
    await pickAgent('B')
    expect(screen.getByTestId('timeline').textContent).toBe('B:c3')
    data.agents = [agent('A'), agent('B', { running_conversation_id: 'c4' })]
    again()
    expect(screen.getByTestId('timeline').textContent).toBe('B:c4')
    await userEvent.click(screen.getByRole('button', { name: /^Conversation/ }))
    await userEvent.click(screen.getByRole('menuitemradio', { name: /Title c3/ }))
    expect(screen.getByTestId('timeline').textContent).toBe('B:c3')
    data.agents = [agent('A'), agent('B', { running_conversation_id: 'c4' }), ]
    data.conversations = [...data.conversations, conv('c5', 'B', 20)]
    data.agents[1].running_conversation_id = 'c5'
    again()
    expect(screen.getByTestId('timeline').textContent).toBe('B:c3')
    // Choosing an agent again gives the choice back to the agent.
    await pickAgent('B')
    expect(screen.getByTestId('timeline').textContent).toBe('B:c5')
  })

  it('has no way to send, answer, stop or queue (streams-live)', async () => {
    mount('other')
    await pickAgent('B')
    const tab = screen.getByTestId('watch-tab')
    expect(tab.querySelector('textarea, input, [contenteditable="true"]')).toBeNull()
    const buttons = within(tab).getAllByRole('button').map((b) => b.textContent ?? '')
    expect(buttons.filter((t) => /send|answer|stop|queue/i.test(t))).toEqual([])
  })

  it('reads working, then waiting for your answer, then idle (state-shown)', async () => {
    data.agents = [agent('A'), agent('B', { running_conversation_id: 'c3' })]
    const { again } = mount('other')
    await pickAgent('B')
    const status = () => document.querySelector('.aw-watch-status')?.textContent ?? ''
    expect(status()).toMatch(/B is working/)
    data.questions = [{ id: 'q1', from_agent: 'B', answered: false }]
    again()
    expect(status()).toMatch(/B is waiting for your answer/)
    data.questions = [{ id: 'q1', from_agent: 'B', answered: true }]
    data.agents = [agent('A'), agent('B')]
    again()
    expect(status()).toMatch(/B is idle/)
    // A question whose asking run has ended is not waited on.
    data.questions = [{ id: 'q2', from_agent: 'B', answered: false, asker_waiting: false }]
    again()
    expect(status()).toMatch(/B is idle/)
  })

  it('keeps B and C3 across the main view moving, and falls back when they go (survives-switch-and-reload)', async () => {
    const { again } = mount('c1')
    await pickAgent('B')
    await userEvent.click(screen.getByRole('button', { name: /^Conversation/ }))
    await userEvent.click(screen.getByRole('menuitemradio', { name: /Title c3/ }))
    again('d1')
    expect(screen.getByTestId('timeline').textContent).toBe('B:c3')
    // A reload: a fresh store reads what was written.
    expect(JSON.parse(localStorage.getItem(WATCH_CHOICE_STORAGE_KEY) ?? '{}')[P]).toEqual({ agent: 'B', conversationId: 'c3' })
    cleanup()
    useWatchChoiceStore.setState({ choices: JSON.parse(localStorage.getItem(WATCH_CHOICE_STORAGE_KEY) ?? '{}') })
    const second = mount('d1')
    expect(screen.getByTestId('timeline').textContent).toBe('B:c3')
    // C3 closed: B's default conversation.
    data.conversations = data.conversations.map((c) => (c.id === 'c3' ? { ...c, lifecycle: 'archived' as const } : c))
    second.again('d1')
    expect(screen.getByTestId('timeline').textContent).toBe('B:c4')
    // B deleted: the tab asks which agent to watch.
    data.agents = [agent('A')]
    second.again('d1')
    expect(screen.queryByTestId('timeline')).toBeNull()
    expect(screen.getByTestId('watch-choose-agent')).toBeTruthy()
  })

  it('draws no second copy of the main view’s conversation and offers the others (in-this-conversation)', async () => {
    const { again } = mount('c1')
    await pickAgent('A')
    expect(screen.getByTestId('timeline').textContent).toBe('A:c2')
    again('c2')
    expect(screen.queryByTestId('timeline')).toBeNull()
    const note = screen.getByTestId('watch-in-this-conversation')
    expect(note.textContent).toMatch(/You are in this conversation/)
    await userEvent.click(within(note).getByRole('button', { name: 'Title c1' }))
    expect(screen.getByTestId('timeline').textContent).toBe('A:c1')
    again('c1')
    expect(screen.queryByTestId('watch-in-this-conversation')).not.toBeNull()
    again('c2')
    expect(screen.getByTestId('timeline').textContent).toBe('A:c1')
  })

  it('Talk to hands the watched conversation to the main view (talk-to-switches)', async () => {
    data.agents = [agent('A'), agent('B', { running_conversation_id: 'c3' })]
    const { onOpen } = mount('c1')
    await pickAgent('B')
    await userEvent.click(screen.getByRole('button', { name: /Talk to B/ }))
    expect(onOpen).toHaveBeenCalledWith('B', 'c3')
  })

  it('starts empty for a project it has never seen', () => {
    expect(useWatchChoiceStore.getState().choices[P] ?? NO_WATCH_CHOICE).toEqual(NO_WATCH_CHOICE)
  })
})
