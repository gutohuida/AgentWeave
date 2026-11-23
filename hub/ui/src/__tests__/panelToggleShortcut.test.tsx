import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation } from '@/api/agentChat'
import { ConversationBar } from '@/components/conversation/ConversationBar'
import { isApplePlatform, isTogglePanelShortcut, togglePanelShortcutLabel } from '@/lib/shortcuts'
import { useConfigStore } from '@/store/configStore'

/* leaner-navigation FR-11, FR-12, FR-13: the thread bar's own side-panel toggle, the Ctrl+Alt+B
 * (Cmd+Option+B) shortcut that works with focus in the composer, and no toggle left in ⋯. */

const AGENT: AgentSummary = { name: 'dev', status: 'idle', message_count: 0, active_task_count: 0, runner: 'claude' }
const PROJECT_ID = 'proj-panel-toggle'

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  useSSEConnectionState: () => 'open',
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))
vi.mock('@/api/checkpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/checkpoints')>()),
  useCheckpoints: () => ({ data: [] }),
  useProjectCheckpoints: () => ({ data: { checkpoints: [], lineage: null }, isLoading: false, error: null, refetch: () => {} }),
  useCheckpointNotes: () => ({ data: { notes: [] }, error: null, refetch: () => {} }),
}))
vi.mock('@/api/agentChat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agentChat')>()),
  useAgentConversations: () => ({ data: [{ id: 'conv-1', agent: 'dev', title: 'Wire the toggle' }] }),
  useProjectConversations: () => ({ data: { conversations: [] }, error: null, refetch: () => {} }),
}))
vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useAgents: () => ({ data: [AGENT], error: null, refetch: () => {} }),
}))
vi.mock('@/api/spec', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/spec')>()),
  useSpecDocuments: () => ({ data: { documents: [] } }),
  useSpecList: () => ({ data: { specs: [], home: null, diagnostics: [], missing: [] }, isLoading: false, refetch: () => {} }),
  useSpecEvents: () => {},
}))
vi.mock('@/api/projectBuilds', () => ({ useProjectBuilds: () => ({ data: [], isLoading: false }) }))
vi.mock('@/api/loops', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/loops')>()),
  useLoops: () => ({ data: [], isLoading: false }),
}))
vi.mock('@/api/jobs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/jobs')>()),
  useJobs: () => ({ data: [], isLoading: false }),
  useArchivedJobs: () => ({ data: [] }),
}))
// The thread is AgentOutputPanel's; here it is a composer textarea and the toggle wiring the bar
// receives, so the test reads what ConversationView hands down.
vi.mock('@/components/agents/AgentOutputPanel', () => ({
  AgentOutputPanel: (props: { onTogglePanel?: () => void; panelOpen?: boolean }) => (
    <div data-testid="thread">
      <textarea data-testid="composer-input" aria-label="Message" />
      <button type="button" data-testid="conversation-toggle-panel" onClick={props.onTogglePanel}>
        {props.panelOpen ? 'Hide side panel' : 'Show side panel'}
      </button>
    </div>
  ),
}))

import { ConversationView } from '@/components/agents/ConversationView'
import { usePanelTabsStore } from '@/store/panelTabsStore'

function renderThread() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ConversationView
        agent={AGENT}
        conversationId="conv-1"
        projectId={PROJECT_ID}
        document={null}
        onSelectConversation={() => {}}
        onOpenDocument={() => {}}
        onBackToProject={() => {}}
        onOpenAgentSettings={() => {}}
      />
    </QueryClientProvider>,
  )
}

const shellOpen = () => usePanelTabsStore.getState().projects[PROJECT_ID]?.isOpen ?? false

beforeEach(() => {
  usePanelTabsStore.setState({ projects: {}, targets: {} })
  useConfigStore.setState({ selectedProjectId: PROJECT_ID })
  window.history.replaceState(null, '', `/?project=${PROJECT_ID}&agent=dev&conversation=conv-1`)
})

describe('toggle-shortcut (FR-12)', () => {
  it('Ctrl+Alt+B with focus in the composer toggles the panel and types nothing', async () => {
    const user = userEvent.setup()
    renderThread()
    const composer = screen.getByTestId('composer-input') as HTMLTextAreaElement
    await user.click(composer)
    await user.keyboard('hi')
    expect(shellOpen()).toBe(false)

    await user.keyboard('{Control>}{Alt>}b{/Alt}{/Control}')
    expect(shellOpen()).toBe(true)
    expect(screen.getByTestId('conversation-toggle-panel')).toHaveTextContent('Hide side panel')
    expect(composer).toHaveFocus()
    expect(composer.value).toBe('hi')

    await user.keyboard('{Control>}{Alt>}b{/Alt}{/Control}')
    expect(shellOpen()).toBe(false)
    expect(composer.value).toBe('hi')
  })

  it('Cmd+Option+B toggles it too, matched on the key code since Option+B types ∫', () => {
    renderThread()
    const composer = screen.getByTestId('composer-input')
    composer.focus()
    const event = new KeyboardEvent('keydown', { key: '∫', code: 'KeyB', metaKey: true, altKey: true, bubbles: true, cancelable: true })
    composer.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(shellOpen()).toBe(true)
  })

  it('leaves Ctrl+B, Ctrl+Alt+Shift+B and other Ctrl+Alt chords alone', () => {
    renderThread()
    const composer = screen.getByTestId('composer-input')
    for (const init of [
      { key: 'b', code: 'KeyB', ctrlKey: true },
      { key: 'B', code: 'KeyB', ctrlKey: true, altKey: true, shiftKey: true },
      { key: 'n', code: 'KeyN', ctrlKey: true, altKey: true },
    ]) {
      const event = new KeyboardEvent('keydown', { ...init, bubbles: true, cancelable: true })
      composer.dispatchEvent(event)
      expect(event.defaultPrevented).toBe(false)
    }
    expect(shellOpen()).toBe(false)
  })

  it('the shortcut and its label come from one helper, per platform', () => {
    expect(isTogglePanelShortcut({ ctrlKey: true, metaKey: false, altKey: true, shiftKey: false, code: 'KeyB' })).toBe(true)
    expect(isTogglePanelShortcut({ ctrlKey: false, metaKey: true, altKey: true, shiftKey: false, code: 'KeyB' })).toBe(true)
    expect(togglePanelShortcutLabel(false)).toBe('Ctrl+Alt+B')
    expect(togglePanelShortcutLabel(true)).toBe('⌘⌥B')
    expect(isApplePlatform({ platform: 'MacIntel', userAgent: '' })).toBe(true)
    expect(isApplePlatform({ platform: 'Win32', userAgent: '' })).toBe(false)
  })
})

describe('the bar’s toggle (FR-11, FR-12 tooltip, FR-13)', () => {
  const conversation = { id: 'conv-1', title: 'Wire the toggle' } as unknown as AgentConversation

  function renderBar(panelOpen: boolean, onTogglePanel = vi.fn()) {
    return render(
      <ConversationBar
        agent={AGENT}
        conversation={conversation}
        title="Wire the toggle"
        isRunning={false}
        elapsedSeconds={null}
        diagnosticsHidden={false}
        onToggleDiagnostics={() => undefined}
        onFoldAll={() => undefined}
        onTogglePanel={onTogglePanel}
        panelOpen={panelOpen}
      />,
    )
  }

  it('names what it will do, follows panelOpen, and its tooltip names the shortcut', () => {
    const onTogglePanel = vi.fn()
    const { rerender } = renderBar(true, onTogglePanel)
    const toggle = screen.getByTestId('conversation-toggle-panel')
    expect(toggle).toHaveAccessibleName('Hide side panel')
    expect(toggle).toHaveAttribute('title', `Hide side panel (${togglePanelShortcutLabel()})`)
    fireEvent.click(toggle)
    expect(onTogglePanel).toHaveBeenCalledTimes(1)
    rerender(
      <ConversationBar
        agent={AGENT}
        conversation={conversation}
        title="Wire the toggle"
        isRunning={false}
        elapsedSeconds={null}
        diagnosticsHidden={false}
        onToggleDiagnostics={() => undefined}
        onFoldAll={() => undefined}
        onTogglePanel={onTogglePanel}
        panelOpen={false}
      />,
    )
    expect(screen.getByTestId('conversation-toggle-panel')).toHaveAccessibleName('Show side panel')
    expect(screen.getByTestId('conversation-toggle-panel')).toHaveAttribute('title', `Show side panel (${togglePanelShortcutLabel()})`)
  })

  it('the ⋯ menu holds no Show or Hide side panel item', async () => {
    const user = userEvent.setup()
    renderBar(true)
    await user.click(screen.getByTestId('conversation-more'))
    const menu = await screen.findByRole('menu')
    expect(within(menu).queryByTestId('conversation-toggle-panel')).toBeNull()
    expect(within(menu).queryByText(/side panel/i)).toBeNull()
  })
})
